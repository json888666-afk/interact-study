import logging
from dataclasses import dataclass
from hashlib import sha256
from typing import Annotated, Literal
from uuid import uuid4

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from pydantic import UUID4

from . import quiz_store as store
from .accounts import Profile, User, account_exam, account_profile, learning_profile
from .exams import ExamUnavailable, exam_counts, find_exam_questions
from .goals import ExamTarget
from .model import GenerationError, model_client
from .papers import local_questions
from .quiz_models import (
    MAIN_PAST_TARGET, MAIN_QUESTION_COUNT, AnswerRequest, ChallengeRequest, QuizRequest, analyze_drill, build_drill, build_quiz,
    review_challenge,
)
from .schemas import StrictModel, bounded_text

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
    accuracy = {item["topic"]: item["correct"] / item["total"] for item in stats if item["total"]}
    selected = sorted(topics, key=lambda topic: accuracy.get(topic, 1))[:2]
    return {"required_topics": selected, "weak_topics": [topic for topic in selected if accuracy.get(topic, 1) < 1]}


class ExamChoice(StrictModel):
    action: Literal["retry", "simulated"]


class FeedbackRequest(StrictModel):
    feedback: Annotated[str, bounded_text(500)]


def exam_context(connection, account_id):
    target = account_exam(connection, account_id)
    if not target:
        return None
    past_count, simulated_count = exam_counts()
    return {"target": target.model_dump(), "past_count": past_count, "simulated_count": simulated_count,
            "simulated_only": False}


def feedback_scope(quiz):
    topics = list(dict.fromkeys(question["topic"] for question in quiz["questions"])) or list(quiz["topics"])
    wrong = list(dict.fromkeys(
        question["topic"] for question in quiz["questions"]
        if quiz["answers"].get(question["id"], {}).get("is_correct") is False
    ))
    return {"required_topics": topics, "weak_topics": wrong or topics}


async def generate_job(owner, quiz_id, request, client, previous, excluded, profile, exam=None, account_id=None,
                       learner_feedback=None):
    try:
        past = []
        if exam:
            if not exam["simulated_only"]:
                target = ExamTarget.model_validate(exam["target"])
                past = await practice_questions(account_id, target, request, client, count=MAIN_PAST_TARGET,
                                                excluded=excluded, local_only=exam.get("local_only", False), fallback=True)
        elif account_id:
            past = await practice_questions(account_id, None, request, client, count=MAIN_PAST_TARGET, excluded=excluded)
        simulated_count = MAIN_QUESTION_COUNT - len(past)
        draft = await build_quiz(request, client, previous=previous, profile=profile, simulated_count=simulated_count,
                                 past_questions=past, excluded=[*excluded, *(question["stem"] for question in past)],
                                 learner_feedback=learner_feedback)
        questions = past + [question.model_dump() | {"origin": "simulated"} for question in draft.questions]
        update = {"status": "ready", "message": "", "public_papers": [],
                  "topics": list(dict.fromkeys(q["topic"] for q in questions)),
                  "questions": [{"id": str(uuid4()), **question} for question in questions]}
    except GenerationError as error:
        update = {"status": "failed", "message": str(error)}
    except Exception:
        logger.exception("Quiz generation failed")
        update = {"status": "failed", "message": "出题服务暂时无法完成请求，请重试。"}
    with store.database() as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            quiz = store.owned(connection, owner, quiz_id)
        except HTTPException as error:
            if error.status_code == 404:
                return
            raise
        quiz.update(update)
        store.save(connection, quiz)


async def practice_questions(account, target, context, client, *, count, excluded=(), local_only=False, replacement=None,
                             fallback=False):
    local = await local_questions(account, target, context, client, count=count, excluded=excluded,
                                 replacement=replacement) if account else []
    if len(local) == count or local_only:
        return local
    if target is None:
        return local
    try:
        online = await find_exam_questions(target, context, client, count=count - len(local),
                                           excluded=[*excluded, *(item["stem"] for item in local)], replacement=replacement)
    except ExamUnavailable:
        if fallback:
            return local
        raise
    return local + online


@router.post("", status_code=202)
def start_quiz(request: QuizRequest, owner: Owner, jobs: BackgroundTasks, client: Client, profile: Profile):
    with store.database() as connection:
        connection.execute("BEGIN IMMEDIATE")
        old = store.latest(connection, owner.key, str(request.version_id))
        if old and (old["id"] != str(request.previous_id)
                    or (old["status"] != "failed" and not old["report"])):
            return store.public(old, connection)
        if old and not request.history:
            request = QuizRequest.model_validate(request.model_dump(mode="json") | {"history": old["context"].get("history", [])})
        quiz = store.insert(connection, owner.key, str(request.version_id), request.model_dump(mode="json"),
                            account_id=owner.account_id, learning_session=owner.learning_session)
        previous = practice_scope(old) if old else None
        excluded = store.seen_stems(old) if old else []
        exam = exam_context(connection, owner.account_id)
        if exam:
            exam.update(previous=previous, excluded=excluded)
            quiz["exam"] = exam
            store.save(connection, quiz)
        response = store.public(quiz, connection)
    jobs.add_task(generate_job, owner.key, quiz["id"], request, client, previous, excluded, profile, exam, owner.account_id)
    return response


@router.post("/{quiz_id}/regenerate", status_code=202)
def regenerate(quiz_id: UUID4, request: FeedbackRequest, owner: Owner, jobs: BackgroundTasks, client: Client,
               profile: Profile):
    with store.database() as connection:
        connection.execute("BEGIN IMMEDIATE")
        quiz = store.owned(connection, owner.key, str(quiz_id))
        if quiz["status"] != "ready" or quiz["report"]:
            raise HTTPException(409, "本次练习已完成或正在生成，不能换一批题。")
        if store.blocked_question(quiz) or any(
            review["status"] == "pending" for review in quiz["reviews"].values()
        ):
            raise HTTPException(409, "请先完成当前核查或巩固，再换一批题。")
        context = QuizRequest.model_validate(quiz["context"])
        previous = feedback_scope(quiz)
        excluded = store.seen_stems(quiz)
        new = store.insert(connection, owner.key, str(quiz["version_id"]), context.model_dump(mode="json"),
                           account_id=owner.account_id, learning_session=owner.learning_session)
        new["learner_feedback"] = request.feedback
        exam = exam_context(connection, owner.account_id)
        if exam:
            exam.update(previous=previous, excluded=excluded)
            new["exam"] = exam
        store.save(connection, new)
        response = store.public(new, connection)
    jobs.add_task(generate_job, owner.key, new["id"], context, client, previous, excluded, profile, exam, owner.account_id,
                  request.feedback)
    return response


@router.post("/{quiz_id}/exam-choice", status_code=202)
def choose_exam(quiz_id: UUID4, choice: ExamChoice, owner: Owner, jobs: BackgroundTasks, client: Client, profile: Profile):
    with store.database() as connection:
        connection.execute("BEGIN IMMEDIATE")
        quiz = store.owned(connection, owner.key, str(quiz_id))
        exam = quiz.get("exam")
        if not exam or quiz["status"] not in {"generating", "exam_choice"}:
            raise HTTPException(409, "当前练习无需选择真题检索方式。")
        if quiz["status"] == "exam_choice":
            exam["simulated_only"] = choice.action == "simulated"
            quiz.update(status="generating", message="")
            store.save(connection, quiz)
            context = QuizRequest.model_validate(quiz["context"])
            jobs.add_task(generate_job, owner.key, quiz["id"], context, client, exam["previous"], exam["excluded"],
                          profile, exam, owner.account_id)
        return store.public(quiz, connection)


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
        question = accessible_question(quiz, question_id)
        require_review_finished(quiz, question_id)
        if question_id not in quiz["answers"]:
            answer = grade(question, request)
            quiz["answers"][question_id] = answer
            if not answer["is_correct"]:
                quiz["drills"][question_id] = new_drill(required=True)
            store.save(connection, quiz)
        return store.public(quiz, connection)


def accessible_question(quiz, question_id):
    question = store.find_question(quiz, question_id)
    blocked = store.blocked_question(quiz)
    order = [item["id"] for item in quiz["questions"]]
    if blocked and order.index(question_id) > order.index(blocked):
        raise HTTPException(409, "请先完成当前题的三题巩固。")
    return question


def require_review_finished(container, question_id):
    if container["reviews"].get(question_id, {}).get("status") in store.PAUSED:
        raise HTTPException(409, "此题正在核查或更换，可先作答其他可用题目。")


def grade(question, request):
    if request.unsure:
        return {"selected": [], "is_correct": False, "unsure": True}
    selected = set(request.selected)
    if (len(selected) != len(request.selected) or max(selected) >= len(question["options"])
            or (question["kind"] == "single" and len(selected) != 1)):
        raise HTTPException(422, "请选择有效选项。")
    return {"selected": sorted(selected), "is_correct": selected == set(question["correct"])}


def new_drill(*, required=False):
    return {"required": required, "status": "awaiting_explanation", "round": 1, "message": "",
            "questions": [], "answers": {}, "reviews": {}, "history": [], "retired": [], "analysis": None}


def settle_drill(drill):
    if len(drill["answers"]) != 3 or any(
        review["status"] in store.PAUSED for review in drill["reviews"].values()
    ):
        return False
    if all(answer["is_correct"] for answer in drill["answers"].values()):
        drill["status"] = "passed"
        return False
    drill["history"].append([{"question": question, "answer": drill["answers"][question["id"]]}
                             for question in drill["questions"]])
    drill.update(status="generating", round=drill["round"] + 1, questions=[], answers={}, reviews={}, analysis=None)
    return True


async def drill_job(owner, quiz_id, question_id, round_number, client):
    def current_drill(quiz):
        drill = quiz["drills"].get(question_id)
        if drill and drill["status"] == "generating" and drill["round"] == round_number:
            return drill
        return None

    with store.database() as connection:
        quiz = store.owned(connection, owner, quiz_id)
        drill = current_drill(quiz)
        if drill is None:
            return
        profile = account_profile(connection, quiz["account_id"])
    original = store.find_question(quiz, question_id)
    profile_key = None
    if profile is not None:
        profile_key = sha256((profile["education_stage"] + "\0" + profile["goal"]).encode()).hexdigest()
    try:
        analysis = drill["analysis"]
        if analysis is None or drill.get("analysis_profile_key") != profile_key:
            previous = drill["history"][-1] if drill["history"] else []
            result = await analyze_drill(original, quiz["answers"][question_id], previous, client, profile=profile)
            analysis = result.model_dump()
            with store.database() as connection:
                connection.execute("BEGIN IMMEDIATE")
                fresh = store.owned(connection, owner, quiz_id)
                active = current_drill(fresh)
                if active is None:
                    return
                active["analysis"] = analysis
                active["analysis_profile_key"] = profile_key
                store.save(connection, fresh)
        draft = await build_drill(original, analysis, client, excluded=store.seen_stems(quiz), profile=profile)
        questions = [{"id": str(uuid4()), **question.model_dump()} for question in draft.questions]
        update = {"status": "ready", "questions": questions}
    except GenerationError as error:
        update = {"status": "failed", "message": str(error)}
    except Exception:
        logger.exception("Drill generation failed")
        update = {"status": "failed", "message": "暂时无法生成巩固题，请重试。"}
    with store.database() as connection:
        connection.execute("BEGIN IMMEDIATE")
        fresh = store.owned(connection, owner, quiz_id)
        active = current_drill(fresh)
        if active is None:
            return
        seen = {stem.casefold() for stem in store.seen_stems(fresh)}
        if any(question["stem"].casefold() in seen for question in update.get("questions", [])):
            update = {"status": "failed", "message": "生成的巩固题与已有题目重复，请重试。"}
        active.update(update)
        store.save(connection, fresh)


@router.post("/{quiz_id}/questions/{question_id}/explanation", dependencies=[Depends(learning_profile)])
@router.post("/{quiz_id}/questions/{question_id}/drill/start", dependencies=[Depends(learning_profile)])
@router.post("/{quiz_id}/questions/{question_id}/drill/retry", dependencies=[Depends(learning_profile)])
def prepare_drill(quiz_id: UUID4, question_id: UUID4, request: Request,
                  owner: Owner, jobs: BackgroundTasks, client: Client):
    quiz_id, question_id = str(quiz_id), str(question_id)
    action = request.url.path.rsplit("/", 1)[-1]
    with store.database() as connection:
        connection.execute("BEGIN IMMEDIATE")
        quiz = store.owned(connection, owner.key, quiz_id)
        accessible_question(quiz, question_id)
        require_review_finished(quiz, question_id)
        answer = quiz["answers"].get(question_id)
        if answer is None:
            raise HTTPException(409, "请先提交答案，再查看解析。")
        drill = quiz["drills"].get(question_id)
        if action == "explanation":
            answer["explained"] = True
            generate = drill is not None and drill["status"] == "awaiting_explanation"
        else:
            if not answer.get("explained"):
                raise HTTPException(409, "请先查看解析。")
            if drill is None and action == "start":
                drill = quiz["drills"][question_id] = new_drill()
            generate = drill is not None and drill["status"] == (
                "failed" if action == "retry" else "awaiting_explanation"
            )
        if generate:
            drill.update(status="generating", message="")
            jobs.add_task(drill_job, owner.key, quiz_id, question_id, drill["round"], client)
        store.save(connection, quiz)
        return store.public(quiz, connection)


def drill_target(quiz, parent_id, question_id):
    drill = quiz["drills"].get(parent_id)
    if drill and drill["status"] == "ready":
        for question in drill["questions"]:
            if question["id"] == question_id:
                return drill, question
    raise HTTPException(409, "这道巩固题已结束或更新，请继续当前轮。")


@router.post("/{quiz_id}/questions/{parent_id}/drill/questions/{question_id}/answer",
             dependencies=[Depends(learning_profile)])
def answer_drill(quiz_id: UUID4, parent_id: UUID4, question_id: UUID4, request: AnswerRequest,
                 owner: Owner, jobs: BackgroundTasks, client: Client):
    quiz_id, parent_id, question_id = str(quiz_id), str(parent_id), str(question_id)
    with store.database() as connection:
        connection.execute("BEGIN IMMEDIATE")
        quiz = store.owned(connection, owner.key, quiz_id)
        accessible_question(quiz, parent_id)
        require_review_finished(quiz, parent_id)
        drill, question = drill_target(quiz, parent_id, question_id)
        require_review_finished(drill, question_id)
        if request.unsure:
            raise HTTPException(422, "巩固题需要选择题目给出的选项。")
        if question_id not in drill["answers"]:
            drill["answers"][question_id] = grade(question, request)
        if settle_drill(drill):
            jobs.add_task(drill_job, owner.key, quiz_id, parent_id, drill["round"], client)
        store.save(connection, quiz)
        return store.public(quiz, connection)


async def challenge_job(owner, quiz_id, question, quiz, objection, confirmed_invalid, client, parent_id=None,
                        allow_simulated=False):
    question_id = question["id"]
    replacement = None
    initial = quiz if parent_id is None else quiz["drills"][parent_id]
    if not confirmed_invalid:
        try:
            finding = await review_challenge(question, objection, client)
            confirmed_invalid = finding.verdict == "invalid"
            update = {
                "status": finding.verdict, "basis": finding.user_perspective + "\n" + finding.objective,
                "clarification_focus": finding.clarification_focus, "confirmed_invalid": confirmed_invalid,
            }
        except GenerationError as error:
            update = {"status": "failed", "message": str(error)}
        except Exception:
            logger.exception("Question review failed")
            update = {"status": "failed", "message": "审核服务暂时无法完成请求，请重试。"}
    else:
        update = {"status": "invalid", "basis": initial["reviews"][question_id]["basis"], "confirmed_invalid": True}
    if confirmed_invalid:
        # Persist the finding before requesting a replacement so a restart cannot re-enable this question.
        with store.database() as connection:
            connection.execute("BEGIN IMMEDIATE")
            fresh = store.owned(connection, owner, quiz_id)
            target = fresh if parent_id is None else fresh["drills"].get(parent_id)
            if target is None or question_id not in target["reviews"]:
                return
            target["reviews"][question_id].update(update | {"status": "pending"})
            store.save(connection, fresh)
        try:
            context = QuizRequest.model_validate(quiz["context"])
            excluded = store.seen_stems(fresh)
            if question.get("origin") == "past" and not allow_simulated:
                exam = fresh.get("exam")
                target_exam = ExamTarget.model_validate(exam["target"]) if exam else None
                past = await practice_questions(fresh["account_id"], target_exam, context, client, count=1,
                                                excluded=excluded, replacement=question,
                                                local_only=bool(exam and exam.get("local_only")))
                if not past:
                    raise ExamUnavailable("未找到可核验的替代真题。")
                replacement = {"id": str(uuid4()), **past[0]}
            else:
                draft = await build_quiz(context, client, replacement=question, excluded=excluded)
                replacement = {"id": str(uuid4()), **draft.questions[0].model_dump(), "origin": "simulated"}
            if parent_id is not None:
                replacement["points"] = question["points"]
        except ExamUnavailable:
            update.update(status="replacement_failed", can_replace_simulated=True)
        except Exception:
            logger.exception("Replacement generation failed")
            update["status"] = "replacement_failed"
    next_round = None
    with store.database() as connection:
        connection.execute("BEGIN IMMEDIATE")
        fresh = store.owned(connection, owner, quiz_id)
        target = fresh if parent_id is None else fresh["drills"].get(parent_id)
        if target is None or question_id not in target["reviews"]:
            return
        if replacement:
            index = next(i for i, item in enumerate(target["questions"]) if item["id"] == question_id)
            if replacement["stem"].casefold() in {stem.casefold() for stem in store.seen_stems(fresh)}:
                target["reviews"][question_id].update(update | {"status": "replacement_failed",
                                                      "can_replace_simulated": question.get("origin") == "past"})
            else:
                target["questions"][index] = replacement
                target["answers"].pop(question_id, None)
                target["reviews"].pop(question_id)
                target["retired"].append(question | {"review": update, "objection": objection})
                target["reviews"][replacement["id"]] = {"status": "replaced"}
                if parent_id is None:
                    retired_drill = fresh["drills"].pop(question_id, None)
                    if retired_drill:
                        fresh["retired"].extend({"stem": item["stem"]} for item in store.drill_questions(retired_drill))
        else:
            target["reviews"][question_id].update(update)
        if parent_id is not None and settle_drill(target):
            next_round = target["round"]
        store.save(connection, fresh)
    if next_round is not None:
        await drill_job(owner, quiz_id, parent_id, next_round, client)


@router.post("/{quiz_id}/questions/{question_id}/challenge", status_code=202)
def challenge(quiz_id: UUID4, question_id: UUID4, request: ChallengeRequest,
              owner: Owner, jobs: BackgroundTasks, client: Client):
    return queue_challenge(str(quiz_id), str(question_id), request, owner, jobs, client)


@router.post("/{quiz_id}/questions/{parent_id}/drill/questions/{question_id}/challenge", status_code=202,
             dependencies=[Depends(learning_profile)])
def challenge_drill(quiz_id: UUID4, parent_id: UUID4, question_id: UUID4, request: ChallengeRequest,
                    owner: Owner, jobs: BackgroundTasks, client: Client):
    return queue_challenge(str(quiz_id), str(question_id), request, owner, jobs, client, str(parent_id))


def queue_challenge(quiz_id, question_id, request, owner, jobs, client, parent_id=None):
    with store.database() as connection:
        connection.execute("BEGIN IMMEDIATE")
        quiz = store.owned(connection, owner.key, quiz_id)
        question = accessible_question(quiz, parent_id or question_id)
        target = quiz
        if parent_id is not None:
            require_review_finished(quiz, parent_id)
            target, question = drill_target(quiz, parent_id, question_id)
        previous = target["reviews"].get(question_id, {})
        if previous.get("status") == "pending" or (
            previous.get("status") == "valid" and previous.get("objection") == request.objection
        ):
            return store.public(quiz, connection)
        confirmed_invalid = previous.get("confirmed_invalid", False)
        if request.allow_simulated and not (confirmed_invalid and previous.get("status") == "replacement_failed"
                                            and previous.get("can_replace_simulated") and question.get("origin") == "past"):
            raise HTTPException(409, "此题还不能替换为模拟题。")
        target["reviews"][question_id] = {
            "status": "pending", "objection": request.objection,
            "confirmed_invalid": confirmed_invalid,
            "basis": previous.get("basis", ""),
            "can_replace_simulated": previous.get("can_replace_simulated", False),
        }
        store.save(connection, quiz)
        response = store.public(quiz, connection)
    jobs.add_task(challenge_job, owner.key, quiz_id, question, quiz, request.objection, confirmed_invalid, client, parent_id,
                  request.allow_simulated)
    return response
