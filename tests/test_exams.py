import json
from uuid import uuid4

import httpx
import pytest

from backend.exam_discovery import SOURCE_AUDIT_PROMPT
from backend.exams import EXAM_SELECT_PROMPT, IMAGE_READ_PROMPT, IMAGE_VERIFY_PROMPT, aligned_section, extract_original
from backend.goals import GOAL_PROMPT
from backend.main import app, model_client
from backend.quiz_models import CHALLENGE_PROMPT, DRAFT_PROMPT, FIRST_REVIEW_PROMPT
from test_learning_quiz import client, context, question

PAPER = "https://publisher.example/archive/paper"
UNKNOWN = "https://unapproved.example/archive/paper"
PUBLISHER = "成都市教育考试院"
TITLE = "2024年成都中考数学原卷"
PERMISSION = "本试卷允许在第三方教育网站转载。"
TARGET = {"exam": "成都市数学中考", "subject": "数学"}
ORIGINAL = f"""{TITLE}
来源：{PUBLISHER}
{PERMISSION}
## A卷
1. 计算 2**2。
A. 4
B. 3
C. 2
答案：A
2. 计算 3+3。
A. 4
B. 6
C. 5
答案：B
3. 计算 8-1。
A. 6
B. 8
C. 7
答案：C
"""


def test_extract_requires_complete_ordered_original_and_consistent_number():
    assert extract_original(ORIGINAL)[0] == {
        "number": "1", "stem": "计算 2**2。", "options": ["4", "3", "2"], "correct": [0],
    }
    assert len(extract_original(ORIGINAL.replace("A. 4\nB. 3", "B. 3\nA. 4"))) == 2
    assert len(extract_original(ORIGINAL.replace("计算 2**2。", "如图，计算 2**2。"))) == 2
    assert len(extract_original(ORIGINAL.replace("答案：A", "答案：A\n1. 计算 1+1。\nA. 2\nB. 3\nC. 4\n答案：A"))) == 2
    assert len(extract_original(ORIGINAL, {"1": [1]})) == 2
    mixed = "# 语文\n## A卷\n语文试卷\n# 数学\n## A卷\n数学试卷"
    assert aligned_section(mixed, "## A卷", "数学", "A卷") == "数学试卷"


@pytest.fixture
def exam_upstream(client, monkeypatch):
    monkeypatch.setenv("EXAM_DEEPSEEK_API_KEY", "exam-test")
    monkeypatch.setenv("EXAM_QUIZ_MODE", "debug")
    state = {"paper": ORIGINAL, "incorrect": False, "rewrite": False, "timeout": False, "ocr_change": None, "calls": [],
             "knowledge": False}

    def respond(request):
        data = json.loads(request.content)
        state["calls"].append((request.url.path, data))
        if request.url.path.endswith("/search"):
            assert set(data) == {"query", "count"}
            assert "private goal notes" not in data["query"]
            if state["timeout"]:
                raise httpx.ReadTimeout("search timed out", request=request)
            return httpx.Response(200, json={"results": [{"url": UNKNOWN, "authority": 2},
                                                       {"url": PAPER, "authority": 3, "site_name": PUBLISHER}]})
        if request.url.path.endswith("/fetch"):
            if data["url"] == UNKNOWN:
                return httpx.Response(200, json={"title": "无来源", "content": "广告"})
            assert data["url"] == PAPER
            title = state["paper"].splitlines()[0]
            return httpx.Response(200, json={"title": title, "content": state["paper"]})
        prompt = data["messages"][0]["content"]
        content = data["messages"][1]["content"]
        material = json.loads(content) if isinstance(content, str) else content
        if prompt == GOAL_PROMPT:
            result = {"verdict": "approved", "message": "通过", "exam": None if state["knowledge"] else TARGET}
        elif prompt == SOURCE_AUDIT_PROMPT:
            if state["knowledge"]:
                assert material["exam"] is None and material["knowledge_topic"]
            records = [{"page": page["page"], "exam": "北京中考数学" if state["knowledge"] else TARGET["exam"], "year": 2024,
                        "edition_quote": page["title"], "publisher": PUBLISHER, "publisher_quote": f"来源：{PUBLISHER}",
                        "role": "issuer", "subject_quote": "数学", "paper": "A卷", "question_heading": "## A卷",
                        "layout": "images" if "![" in state["paper"] else "text", "permission_quote": PERMISSION}
                       for page in material["pages"]]
            result = {"sources": records}
        elif prompt in (IMAGE_READ_PROMPT, IMAGE_VERIFY_PROMPT):
            assert [item["image_url"]["url"] for item in material[1:]] == ["https://publisher.example/original.png"]
            options = [{"label": "A", "text": "4"}, {"label": "B", "text": "3"}, {"label": "C", "text": "2"}]
            stem, answer = "计算 2**2。", ["A"]
            if prompt == IMAGE_VERIFY_PROMPT:
                if state["ocr_change"] == "order":
                    options[0], options[1] = options[1], options[0]
                elif state["ocr_change"] == "formula":
                    stem = "计算 2**3。"
                elif state["ocr_change"] == "answer":
                    answer = ["B"]
            result = {"questions": [{"number": "1", "stem": stem, "options": options, "needs_figure": False}],
                      "answers": [{"number": "1", "choices": answer}]}
        elif prompt == EXAM_SELECT_PROMPT:
            choices = []
            for candidate in material["candidates"]:
                index = candidate["candidate"]
                correct = {"计算 2**2。": 0, "计算 3+3。": 1, "计算 8-1。": 2}[candidate["stem"]]
                item = {"candidate": index, "topic": "算术", "correct": [(correct + 1) % 3 if state["incorrect"] else correct],
                        "explanation": "依次计算。"}
                if state["rewrite"]:
                    item["stem"] = "改写内容"
                choices.append(item)
            result = {"questions": choices}
        elif prompt == FIRST_REVIEW_PROMPT:
            result = {"answers": [item["correct"] for item in material["draft"]["questions"]], "issues": []}
        elif prompt == DRAFT_PROMPT:
            scope = material["scope"]
            offset = 200 if "replace" in scope else 100
            kind = scope.get("kind")
            questions = [question(offset + i, scope.get("required_topics", ["算术"])[0],
                                  kind if kind in {"single", "multiple"} else "multiple" if i == 0 else "single")
                         for i in range(scope["count"])]
            result = {"topics": [questions[0]["topic"]], "questions": questions}
        else:
            assert prompt == CHALLENGE_PROMPT
            result = {"verdict": "invalid", "user_perspective": "题意不清楚", "objective": "需要更换"}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(result)}}]})

    async def dependency():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as upstream:
            yield upstream

    app.dependency_overrides[model_client] = dependency
    response = client.post("/api/auth/register", json={
        "username": "ExamUser", "password": "Browser-test-42",
        "profile": {"education_stage": "高中", "goal": "备考成都中考数学，private goal notes"},
    })
    assert response.status_code == 201
    return state


def exam_start(client):
    owner = {"X-Study-Session": str(uuid4())}
    result = client.post("/api/quizzes", headers=owner, json=context(client) | {"version_id": str(uuid4())})
    assert result.status_code == 202
    path = "/api/quizzes/" + result.json()["id"]
    return owner, path, client.get(path, headers=owner).json()


@pytest.mark.parametrize(("mode", "past_count", "simulated_count"), [("debug", 1, 1), ("standard", 3, 7)])
def test_exam_counts_and_source_after_answer(client, exam_upstream, monkeypatch, mode, past_count, simulated_count):
    monkeypatch.setenv("EXAM_QUIZ_MODE", mode)
    owner, path, quiz = exam_start(client)
    assert quiz["status"] == "ready", quiz["message"]
    assert [item["origin"] for item in quiz["questions"]] == ["past"] * past_count + ["simulated"] * simulated_count
    first = quiz["questions"][0]
    assert first["stem"] == "计算 2**2。" and first["options"] == ["4", "3", "2"]
    assert first["source"]["number"] == "1" and "url" not in first["source"]
    updated = client.post(f"{path}/questions/{first['id']}/answer", headers=owner, json={"selected": [0]}).json()
    first = updated["questions"][0]
    assert first["source"]["url"] == PAPER and first["source"]["publisher"] == PUBLISHER
    assert first["source"]["paper"] == "A卷"
    assert "correct" not in first["answer"]
    searches = sum(path.endswith("/search") for path, _ in exam_upstream["calls"])
    assert client.get(path, headers=owner).json()["questions"][0]["source"] == first["source"]
    assert sum(path.endswith("/search") for path, _ in exam_upstream["calls"]) == searches
    _, new_path, fresh = exam_start(client)
    assert new_path != path and fresh["status"] == "ready"
    assert sum(path.endswith("/search") for path, _ in exam_upstream["calls"]) > searches


@pytest.mark.parametrize("failure", [None, "permission", "timeout"])
def test_knowledge_goal_searches_then_automatically_falls_back(client, exam_upstream, monkeypatch, failure):
    monkeypatch.setenv("EXAM_QUIZ_MODE", "standard")
    exam_upstream.update(knowledge=True, paper=ORIGINAL.replace(TITLE, TITLE.replace("成都", "北京")))
    if failure == "permission":
        exam_upstream["paper"] = exam_upstream["paper"].replace(PERMISSION, "欢迎转发链接。")
    if failure == "timeout":
        exam_upstream["timeout"] = True
    update = client.post("/api/auth/profile", json={"education_stage": "初中", "goal": "学懂二次函数"})
    assert update.status_code == 200
    _, _, quiz = exam_start(client)
    assert quiz["status"] == "ready" and "exam" not in quiz
    assert [item["origin"] for item in quiz["questions"]] == (["simulated", "simulated"] if failure else ["past", "simulated"])
    searches = [data["query"] for path, data in exam_upstream["calls"] if path.endswith("/search")]
    assert searches and all("成都" not in query and "private goal" not in query for query in searches)
    if not failure:
        assert quiz["questions"][0]["source"]["exam"] == "北京中考数学"


@pytest.mark.parametrize("reason", ["missing", "incorrect", "rewrite", "permission", "restricted", "wrong_region", "timeout"])
def test_exam_fallback_requires_choice(client, exam_upstream, reason):
    if reason == "missing":
        exam_upstream["paper"] = "搜索摘要不含核准试卷原文"
    elif reason == "permission":
        exam_upstream["paper"] = ORIGINAL.replace(PERMISSION, "欢迎转发链接。")
    elif reason == "restricted":
        exam_upstream["paper"] = ORIGINAL + "\n不允许在第三方教育网站转载。\n"
    elif reason == "wrong_region":
        exam_upstream["paper"] = ORIGINAL.replace(TITLE, TITLE.replace("成都", "北京"))
    else:
        exam_upstream[reason] = True
    owner, path, quiz = exam_start(client)
    assert quiz["status"] == "exam_choice" and quiz["questions"] == []
    assert [item["url"] for item in quiz.get("public_papers", [])] == (
        [PAPER] if reason in {"incorrect", "rewrite", "permission", "restricted"} else [])
    assert client.post(path + "/exam-choice", headers=owner, json={"action": "retry"}).status_code == 202
    assert client.get(path, headers=owner).json()["status"] == "exam_choice"
    assert client.post(path + "/exam-choice", headers=owner, json={"action": "simulated"}).status_code == 202
    updated = client.get(path, headers=owner).json()
    assert updated["status"] == "ready"
    assert [item["origin"] for item in updated["questions"]] == ["simulated", "simulated"]


@pytest.mark.parametrize("change", [None, "order", "formula", "answer"])
def test_image_exam_needs_two_agreeing_reads(client, exam_upstream, change):
    exam_upstream["paper"] = ORIGINAL.split("1. 计算")[0] + "![原卷和参考答案](/original.png)"
    exam_upstream["ocr_change"] = change
    _, _, quiz = exam_start(client)
    reads = [payload["messages"][0]["content"] for path, payload in exam_upstream["calls"]
             if path.endswith("/chat/completions") and payload["messages"][0]["content"] in {
                 IMAGE_READ_PROMPT, IMAGE_VERIFY_PROMPT,
             }]
    assert set(reads) == {IMAGE_READ_PROMPT, IMAGE_VERIFY_PROMPT}
    if change is None:
        assert quiz["status"] == "ready" and quiz["questions"][0]["origin"] == "past"
    else:
        assert quiz["status"] == "exam_choice" and quiz["public_papers"][0]["url"] == PAPER


def test_disputed_past_question_requires_confirmation_for_simulated_replacement(client, exam_upstream):
    exam_upstream["paper"] = ORIGINAL.split("2. 计算")[0]
    owner, path, quiz = exam_start(client)
    first, second = quiz["questions"]
    client.post(f"{path}/questions/{second['id']}/answer", headers=owner, json={"selected": [0, 1]})
    challenge = f"{path}/questions/{first['id']}/challenge"
    objection = {"objection": "题意不够清楚"}
    assert client.post(challenge, headers=owner, json=objection | {"allow_simulated": True}).status_code == 409
    assert client.post(challenge, headers=owner, json=objection).status_code == 202
    paused = client.get(path, headers=owner).json()
    assert paused["questions"][0]["review"]["can_replace_simulated"]
    assert client.post(challenge, headers=owner, json=objection | {"allow_simulated": True}).status_code == 202
    updated = client.get(path, headers=owner).json()
    assert updated["questions"][0]["origin"] == "simulated" and updated["questions"][0]["id"] != first["id"]
    assert updated["questions"][1]["answer"]["is_correct"]
