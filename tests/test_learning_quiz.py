import json
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from backend import quiz_store
from backend.main import app, model_client
from backend.quiz_models import CHALLENGE_PROMPT, DRAFT_PROMPT, FIRST_REVIEW_PROMPT


def question(index=0, topic="开口", kind="single"):
    return {
        "kind": kind, "topic": topic, "stem": f"测试题 {index} 有哪些正确选项？",
        "options": ["甲", "乙", "丙", "丁"],
        "correct": [0] if kind == "single" else [0, 1], "explanation": "解析",
    }


def draft():
    return {"topics": ["开口", "宽窄"], "questions": [
        question(index, "开口" if index < 5 else "宽窄", "multiple" if index == 1 else "single")
        for index in range(10)
    ]}


@pytest.fixture
def client(monkeypatch):
    for prefix, name in (("MODEL", "flash"), ("REVIEW_MODEL", "independent")):
        monkeypatch.setenv(prefix + "_BASE_URL", f"https://{name}.example/v1")
        monkeypatch.setenv(prefix + "_API_KEY", "test-key")
        monkeypatch.setenv(prefix + "_NAME", name)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def mock_upstream(handler, inspect_request=None):
    def respond(request):
        if inspect_request is not None:
            inspect_request(request)
        payload = json.loads(request.content)
        result = handler(payload["messages"][0]["content"], payload["messages"][1]["content"], payload["model"])
        if isinstance(result, httpx.Response):
            return result
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(result)}}]})

    async def dependency():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            yield client

    app.dependency_overrides[model_client] = dependency


def context(client):
    return {"question": "如何理解二次函数？", "lesson": client.get("/api/examples/quadratic").json()["result"],
            "history": [{"question": "如何判断开口？", "answer": "检查 a 的符号。"}]}


def start(client):
    version = str(uuid4())
    owner = {"X-Study-Session": str(uuid4())}
    response = client.post("/api/quizzes", headers=owner, json={**context(client), "version_id": version})
    assert response.status_code == 202
    assert response.json()["status"] == "generating"
    path = "/api/quizzes/" + response.json()["id"]
    result = client.get(path, headers=owner).json()
    assert client.get("/api/quizzes", headers=owner, params={"version_id": version}).json() == result
    return owner, path, result


def test_text_and_screenshot_question(client):
    data_url = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aIRkAAAAASUVORK5CYII="
    expected = {**context(client), "message": "截图里为什么向下？"}
    seen = []

    def handler(_prompt, content, model):
        assert model == "flash"
        if isinstance(content, str):
            assert json.loads(content) == expected
        else:
            assert json.loads(content[0]["text"]) == expected
            assert content[1] == {"type": "image_url", "image_url": {"url": data_url}}
        seen.append(content)
        return {"answer": "因为 a 小于零。"}

    mock_upstream(handler)
    for image in (None, data_url):
        assert client.post("/api/lessons/ask", json={**expected, "image": image}).json() == {"answer": "因为 a 小于零。"}
    bad = client.post("/api/lessons/ask", json={**expected, "image": "data:image/png;base64,abcd"})
    assert bad.status_code == 422 and "base64,abcd" not in bad.text
    assert len(seen) == 2


def test_initial_review_retry_then_grade_and_replace_single_question(client, quiz_database):
    seen = []
    reviews = 0

    def handler(prompt, content, model):
        nonlocal reviews
        data = json.loads(content)
        seen.append((prompt, model))
        if prompt == DRAFT_PROMPT:
            if data["scope"]["count"] == 1:
                assert data["scope"]["required_topics"] == ["开口"]
                return {"topics": ["开口"], "questions": [question(100, kind="multiple")]}
            if reviews:
                assert data["feedback"] == ["核对题干"]
            return draft()
        if prompt == FIRST_REVIEW_PROMPT:
            reviews += 1
            return {"answers": [item["correct"] for item in data["draft"]["questions"]],
                    "issues": ["核对题干"] if reviews == 1 else []}
        assert prompt == CHALLENGE_PROMPT and data["objection"] == "这个多选题不该如此判分"
        assert data["question"]["correct"] == [0, 1]
        return {"verdict": "invalid", "user_perspective": "条件容易误解", "objective": "缺少限定条件"}

    mock_upstream(handler)
    owner, path, quiz = start(client)
    assert quiz["status"] == "ready"
    assert [model for _, model in seen] == ["flash"] * 4
    assert quiz_database.is_file() and quiz_database.drive == quiz_store.ROOT.drive
    ids = [item["id"] for item in quiz["questions"]]
    assert all("correct" not in item and "answer" not in item for item in quiz["questions"])
    assert client.get(path, headers={"X-Study-Session": str(uuid4())}).status_code == 404
    for question_id in ids:
        response = client.post(f"{path}/questions/{question_id}/answer", headers=owner, json={"selected": [0]})
        assert response.status_code == 200
    report = response.json()["report"]
    assert report["percent"] == 90 and not report["passed"]
    multi = f"{path}/questions/{ids[1]}"
    duplicate = client.post(multi + "/answer", headers=owner, json={"selected": [0, 1]})
    assert duplicate.json()["questions"][1]["answer"]["selected"] == [0]
    assert len(seen) == 4
    review = client.post(multi + "/challenge", headers=owner, json={"objection": "这个多选题不该如此判分"})
    assert review.status_code == 202
    assert review.json()["report"] is None
    assert review.json()["questions"][1]["review"]["status"] == "pending"
    updated = client.get(path, headers=owner).json()
    replacement_id = updated["questions"][1]["id"]
    assert replacement_id != ids[1]
    assert "answer" not in updated["questions"][1] and updated["report"] is None
    assert all("answer" in item for i, item in enumerate(updated["questions"]) if i != 1)
    assert [model for _, model in seen] == ["flash"] * 4 + ["independent", "flash", "flash"]
    assert client.post(multi + "/answer", headers=owner, json={"selected": [0]}).status_code == 409
    completed = client.post(f"{path}/questions/{replacement_id}/answer", headers=owner, json={"selected": [0, 1]})
    assert completed.json()["report"]["passed"]
    quiz_store.initialize()
    assert client.get(path, headers=owner).json() == completed.json()


@pytest.mark.parametrize("verdict", ["valid", "uncertain", "failed"])
def test_challenge_leaves_original_and_answer_on_other_outcomes(client, verdict):
    def handler(prompt, content, model):
        if prompt == DRAFT_PROMPT:
            assert model == "flash"
            return draft()
        if prompt == FIRST_REVIEW_PROMPT:
            return {"answers": [item["correct"] for item in draft()["questions"]], "issues": []}
        assert model == "independent"
        if verdict == "failed":
            return httpx.Response(503)
        return {"verdict": verdict, "user_perspective": "疑问源于题干范围", "objective": "检查题干条件"}

    mock_upstream(handler)
    owner, path, quiz = start(client)
    question_id = quiz["questions"][0]["id"]
    action = f"{path}/questions/{question_id}"
    client.post(action + "/answer", headers=owner, json={"selected": [0]})
    assert client.post(action + "/challenge", headers=owner, json={"objection": "条件够吗？"}).status_code == 202
    original = client.get(path, headers=owner).json()["questions"][0]
    assert original["id"] == question_id and original["answer"]["is_correct"]
    assert original["review"]["status"] == verdict
    if verdict == "valid":
        assert "可以继续作答" in original["review"]["message"]


def test_failed_initial_review_keeps_quiz_closed(client, monkeypatch):
    monkeypatch.delenv("REVIEW_MODEL_API_KEY")

    def handler(prompt, content, model):
        assert model == "flash"
        return draft() if prompt == DRAFT_PROMPT else {"answers": [[3]] * 10, "issues": []}

    mock_upstream(handler)
    _, _, quiz = start(client)
    assert quiz["status"] == "failed"
    assert quiz["questions"] == [] and "未通过初审" in quiz["message"]


def test_failed_replacement_stays_paused_until_retry_succeeds(client):
    replacements = 0
    challenges = 0

    def handler(prompt, content, _model):
        nonlocal replacements, challenges
        data = json.loads(content)
        if prompt == DRAFT_PROMPT:
            if data["scope"]["count"] != 1:
                return draft()
            replacements += 1
            if replacements == 1:
                return httpx.Response(503)
            return {"topics": ["开口"], "questions": [question(100)]}
        if prompt == FIRST_REVIEW_PROMPT:
            return {"answers": [item["correct"] for item in data["draft"]["questions"]], "issues": []}
        challenges += 1
        return {"verdict": "invalid", "user_perspective": "疑问来自表述", "objective": "题干漏写条件"}

    mock_upstream(handler)
    owner, path, quiz = start(client)
    question_id = quiz["questions"][0]["id"]
    action = f"{path}/questions/{question_id}"
    objection = {"objection": "这个条件是否遗漏？"}
    assert client.post(action + "/challenge", headers=owner, json=objection).status_code == 202
    paused = client.get(path, headers=owner).json()["questions"][0]
    assert paused["review"]["status"] == "replacement_failed"
    assert client.post(action + "/answer", headers=owner, json={"selected": [0]}).status_code == 409
    assert client.post(action + "/challenge", headers=owner, json=objection).status_code == 202
    replaced = client.get(path, headers=owner).json()["questions"][0]
    assert replaced["id"] != question_id and "题干漏写条件" in replaced["review"]["message"]
    assert "新题未能生成" not in replaced["review"]["message"]
    assert replacements == 2 and challenges == 1


def test_same_model_challenge_uses_separate_key(client, monkeypatch):
    for prefix, key in (("MODEL", "generator-key"), ("REVIEW_MODEL", "reviewer-key")):
        monkeypatch.setenv(prefix + "_BASE_URL", "https://api.deepseek.com")
        monkeypatch.setenv(prefix + "_NAME", "deepseek-flash")
        monkeypatch.setenv(prefix + "_API_KEY", key)
    keys = []

    def handler(prompt, _content, model):
        assert model == "deepseek-flash"
        if prompt == DRAFT_PROMPT:
            return draft()
        if prompt == FIRST_REVIEW_PROMPT:
            return {"answers": [item["correct"] for item in draft()["questions"]], "issues": []}
        assert prompt == CHALLENGE_PROMPT
        return {"verdict": "valid", "user_perspective": "条件可能被误读", "objective": "题目条件充分"}

    mock_upstream(handler, lambda request: keys.append(request.headers["authorization"]))
    owner, path, quiz = start(client)
    question_id = quiz["questions"][0]["id"]
    endpoint = f"{path}/questions/{question_id}/challenge"
    assert client.post(endpoint, headers=owner, json={"objection": "需要补充条件吗？"}).status_code == 202
    assert client.get(path, headers=owner).json()["questions"][0]["review"]["status"] == "valid"
    assert keys == ["Bearer generator-key", "Bearer generator-key", "Bearer reviewer-key"]

    monkeypatch.setenv("REVIEW_MODEL_API_KEY", "generator-key")
    assert client.post(endpoint, headers=owner, json={"objection": "选项是否互斥？"}).status_code == 202
    assert client.get(path, headers=owner).json()["questions"][0]["review"]["status"] == "failed"
    assert len(keys) == 3
