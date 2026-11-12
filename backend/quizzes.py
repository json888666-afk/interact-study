import logging
from dataclasses import dataclass
from typing import Annotated
from uuid import uuid4

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from pydantic import UUID4

from . import quiz_store as store
from .accounts import Profile, User
from .model import GenerationError, model_client
from .quiz_models import AnswerRequest, ChallengeRequest, QuizRequest, build_quiz, review_challenge

router = APIRouter(prefix="/api/quizzes")
Client = Annotated[httpx.AsyncClient, Depends(model_client, scope="request")]
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class QuizOwner:
    learning_session: str
    account_id: str | None

    @property
    def key(self):
        return f"account:{self.account_id}:{self.learning_session}" if self.account_id else self.learning_session


def quiz_owner(study_session: Annotated[UUID4, Header(alias="X-Study-Session")], user: User,
               expected_account: Annotated[str | None, Header(alias="X-Study-Account")] = None):
    account_id = user["id"] if user else None
    if expected_account is not None and expected_account != (account_id or "guest"):
        raise HTTPException(409, "登录状态已变化，请刷新页面后继续。")
    return QuizOwner(str(study_session), account_id)


Owner = Annotated[QuizOwner, Depends(quiz_owner)]


def practice_scope(quiz):
    topics = quiz["topics"]
    if not topics:
        return None
    stats = (quiz["report"] or {}).get("topics", [])
    weak = [item for item in stats if item["correct"] < item["total"]]
    minimum = dict.fromkeys(topics, 1)
    remaining = 15 - len(topics)
    for item in sorted(weak, key=lambda entry: entry["correct"] / entry["total"]):
        additional = min(item["total"], remaining)
        minimum[item["topic"]] += additional
        remaining -= additional
    return {"required_topics": topics, "weak_topics": [item["topic"] for item in weak],
            "minimum_counts": minimum}


async def generate_job(owner, quiz_id, request, client, previous, excluded, profile):
    try:
        draft = await build_quiz(request, client, previous=previous, excluded=excluded, profile=profile)
        update = {"status": "ready", "topics": draft.topics, "questions": [
            {"id": str(uuid4()), **question.model_dump()} for question in draft.questions
        ]}
    except GenerationError as error:
        update = {"status": "failed", "message": str(error)}
    except Exception:
        logger.exception("Quiz generation failed")
        update = {"status": "failed", "message": "出题服务暂时无法完成请求，请重试。"}
    with store.database() as connection:
        connection.execute("BEGIN IMMEDIATE")
        quiz = store.owned(connection, owner, quiz_id)
        quiz.update(update)
        store.save(connection, quiz)


@router.post("", status_code=202)
def start_quiz(request: QuizRequest, owner: Owner, jobs: BackgroundTasks, client: Client, profile: Profile):
    with store.database() as connection:
        connection.execute("BEGIN IMMEDIATE")
        old = store.latest(connection, owner.key, str(request.version_id))
        if old and (old["id"] != str(request.previous_id)
                    or (old["status"] != "failed" and not old["report"])):
            return store.public(old, connection)
        if old and not request.history:
            request = QuizRequest.model_validate(request.model_dump(mode="json") | {"history": old["context"]["history"]})
        quiz = store.insert(connection, owner.key, str(request.version_id), request.model_dump(mode="json"),
                            account_id=owner.account_id, learning_session=owner.learning_session)
        response = store.public(quiz, connection)
    previous = practice_scope(old) if old else None
    excluded = [question["stem"] for question in old["questions"] + old["retired"]] if old else []
    jobs.add_task(generate_job, owner.key, quiz["id"], request, client, previous, excluded, profile)
    return response


@router.get("")
def find_quiz(version_id: UUID4, owner: Owner):
    with store.database() as connection:
        quiz = store.latest(connection, owner.key, str(version_id))
        return store.public(quiz, connection) if quiz else None


@router.get("/{quiz_id}")
def get_quiz(quiz_id: UUID4, owner: Owner):
    with store.database() as connection:
        return store.public(store.owned(connection, owner.key, str(quiz_id)), connection)


@router.post("/{quiz_id}/questions/{question_id}/answer")
def answer_question(quiz_id: UUID4, question_id: UUID4, request: AnswerRequest, owner: Owner):
    question_id = str(question_id)
    with store.database() as connection:
        connection.execute("BEGIN IMMEDIATE")
        quiz = store.owned(connection, owner.key, str(quiz_id))
        question = store.find_question(quiz, question_id)
        if quiz["reviews"].get(question_id, {}).get("status") in store.PAUSED:
            raise HTTPException(409, "此题正在核查或更换，可先作答其他题目。")
        if question_id not in quiz["answers"]:
            selected = set(request.selected)
            if (len(selected) != len(request.selected) or max(selected) >= len(question["options"])
                    or (question["kind"] == "single" and len(selected) != 1)):
                raise HTTPException(422, "请选择有效选项。")
            quiz["answers"][question_id] = {
                "selected": sorted(selected), "is_correct": selected == set(question["correct"]),
            }
            store.save(connection, quiz)
        return store.public(quiz, connection)


async def challenge_job(owner, quiz_id, question, quiz, objection, confirmed_invalid, client):
    question_id = question["id"]
    replacement = None
    if not confirmed_invalid:
        try:
            finding = await review_challenge(question, objection, client)
            confirmed_invalid = finding.verdict == "invalid"
            prefix = "题目可以继续作答。" if finding.verdict == "valid" else ""
            basis = prefix + finding.user_perspective + "\n" + finding.objective
            update = {"status": finding.verdict, "message": basis, "basis": basis, "confirmed_invalid": confirmed_invalid}
        except GenerationError as error:
            update = {"status": "failed", "message": str(error)}
        except Exception:
            logger.exception("Question review failed")
            update = {"status": "failed", "message": "审核服务暂时无法完成请求，请重试。"}
    else:
        update = {"status": "invalid", "message": quiz["reviews"][question_id]["basis"], "confirmed_invalid": True}
    if confirmed_invalid:
        # Persist the finding before requesting a replacement so a restart cannot re-enable this question.
        with store.database() as connection:
            connection.execute("BEGIN IMMEDIATE")
            fresh = store.owned(connection, owner, quiz_id)
            fresh["reviews"][question_id].update(update | {"status": "pending"})
            store.save(connection, fresh)
        try:
            context = QuizRequest.model_validate(quiz["context"])
            excluded = [item["stem"] for item in quiz["questions"] + quiz["retired"]]
            draft = await build_quiz(context, client, replacement=question, excluded=excluded)
            replacement = {"id": str(uuid4()), **draft.questions[0].model_dump()}
        except Exception:
            logger.exception("Replacement generation failed")
            update.update(status="replacement_failed", message=update["message"] + "\n新题未能生成，请重试。")
    with store.database() as connection:
        connection.execute("BEGIN IMMEDIATE")
        fresh = store.owned(connection, owner, quiz_id)
        if replacement:
            index = next(i for i, item in enumerate(fresh["questions"]) if item["id"] == question_id)
            if any(item["stem"].casefold() == replacement["stem"].casefold() for item in fresh["questions"] + fresh["retired"]):
                fresh["reviews"][question_id].update(update | {"status": "replacement_failed",
                    "message": update["message"] + "\n新题与另一题重复，请重试。"})
            else:
                fresh["questions"][index] = replacement
                fresh["answers"].pop(question_id, None)
                fresh["reviews"].pop(question_id)
                fresh["retired"].append(question | {"review": update, "objection": objection})
                fresh["reviews"][replacement["id"]] = {"status": "replaced", "message": "已更换此题。\n" + update["message"]}
        else:
            fresh["reviews"][question_id].update(update)
        store.save(connection, fresh)


@router.post("/{quiz_id}/questions/{question_id}/challenge", status_code=202)
def challenge(quiz_id: UUID4, question_id: UUID4, request: ChallengeRequest,
              owner: Owner, jobs: BackgroundTasks, client: Client):
    owner, quiz_id, question_id = owner.key, str(quiz_id), str(question_id)
    with store.database() as connection:
        connection.execute("BEGIN IMMEDIATE")
        quiz = store.owned(connection, owner, quiz_id)
        question = store.find_question(quiz, question_id)
        previous = quiz["reviews"].get(question_id, {})
        if previous.get("status") == "pending" or (
            previous.get("status") == "valid" and previous.get("objection") == request.objection
        ):
            return store.public(quiz, connection)
        confirmed_invalid = previous.get("confirmed_invalid", False)
        quiz["reviews"][question_id] = {
            "status": "pending", "objection": request.objection,
            "message": previous.get("message", "") if confirmed_invalid else "",
            "confirmed_invalid": confirmed_invalid,
            "basis": previous.get("basis", ""),
        }
        store.save(connection, quiz)
        response = store.public(quiz, connection)
    jobs.add_task(challenge_job, owner, quiz_id, question, quiz, request.objection, confirmed_invalid, client)
    return response
