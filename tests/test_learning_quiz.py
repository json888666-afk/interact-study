import json
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from backend import quiz_store
from backend.goals import GOAL_PROMPT
from backend.main import app, model_client
from backend.quiz_models import CHALLENGE_PROMPT, DRAFT_PROMPT, DRILL_ANALYSIS_PROMPT, DRILL_DRAFT_PROMPT, FIRST_REVIEW_PROMPT


def question(index=0, topic="开口", kind="single"):
    return {
        "kind": kind, "topic": topic, "stem": f"测试题 {index} 有哪些正确选项？",
        "options": ["甲", "乙", "丙", "丁"],
        "correct": [0] if kind == "single" else [0, 1], "explanation": "解析",
    }


def draft():
    return {"topics": ["开口"], "questions": [
        question(index, "开口", "multiple" if index == 1 else "single") for index in range(10)
    ]}


def legacy_draft():
    return {"topics": ["开口", "宽窄"], "questions": [
        question(index, "开口" if index < 5 else "宽窄", "multiple" if index == 1 else "single")
        for index in range(10)
    ]}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("EXAM_DEEPSEEK_API_KEY", raising=False)
    for prefix, name in (("MODEL", "flash"), ("REVIEW_MODEL", "independent")):
        monkeypatch.setenv(prefix + "_BASE_URL", f"https://{name}.example/v1")
        monkeypatch.setenv(prefix + "_API_KEY", "test-key")
        monkeypatch.setenv(prefix + "_NAME", name)
    mock_upstream(lambda *_args: {})
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def mock_upstream(handler, inspect_request=None, goal_handler=None):
    def respond(request):
        if inspect_request is not None:
            inspect_request(request)
        payload = json.loads(request.content)
        prompt = payload["messages"][0]["content"]
        content = payload["messages"][1]["content"]
        if prompt == GOAL_PROMPT:
            result = goal_handler(json.loads(content)) if goal_handler else {"verdict": "approved", "message": "通过"}
        else:
            result = handler(prompt, content, payload["model"])
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


def mock_drill_response(prompt, data, offset=1000):
    if prompt == DRILL_ANALYSIS_PROMPT:
        return {"points": ["符号判断", "开口方向"], "priority": ["符号判断"]}
    if prompt == DRILL_DRAFT_PROMPT:
        return {"questions": [
            question(offset + i, data["scope"]["topic"]) | {"points": ["符号判断", "开口方向"] if i == 0 else ["符号判断"]}
            for i in range(3)
        ]}
    raise AssertionError("unexpected drill prompt")


def pass_drill(client, path, owner, question_id):
    original = f"{path}/questions/{question_id}"
    response = client.post(original + "/explanation", headers=owner)
    assert response.status_code == 200
    current = next(item for item in client.get(path, headers=owner).json()["questions"] if item["id"] == question_id)
    assert current["drill"]["status"] == "ready", current["drill"]
    for item in current["drill"]["questions"]:
        response = client.post(f"{original}/drill/questions/{item['id']}/answer", headers=owner, json={"selected": [0]})
        assert response.status_code == 200
    return response.json()


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
                assert "核对题干" in data["feedback"]
                assert any("初审独立求解" in item for item in data["feedback"])
            return draft()
        if prompt == FIRST_REVIEW_PROMPT:
            reviews += 1
            return {"answers": [item["correct"] for item in data["draft"]["questions"]],
                    "issues": ["核对题干"] if reviews == 1 else []}
        if prompt in (DRILL_ANALYSIS_PROMPT, DRILL_DRAFT_PROMPT):
            return mock_drill_response(prompt, data)
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
    for question_id in ids[:-1]:
        response = client.post(f"{path}/questions/{question_id}/answer", headers=owner, json={"selected": [0]})
        assert response.status_code == 200
        if question_id == ids[1]:
            assert response.json()["report"] is None
            pass_drill(client, path, owner, question_id)
    assert client.get(path, headers=owner).json()["report"] is None
    multi = f"{path}/questions/{ids[1]}"
    duplicate = client.post(multi + "/answer", headers=owner, json={"selected": [0, 1]})
    assert duplicate.json()["questions"][1]["answer"]["selected"] == [0]
    assert len(seen) == 7
    review = client.post(multi + "/challenge", headers=owner, json={"objection": "这个多选题不该如此判分"})
    assert review.status_code == 202
    assert review.json()["report"] is None
    assert review.json()["questions"][1]["review"]["status"] == "pending"
    assert "answer" not in review.json()["questions"][1]
    updated = client.get(path, headers=owner).json()
    replacement_id = updated["questions"][1]["id"]
    assert replacement_id != ids[1]
    assert "answer" not in updated["questions"][1] and updated["report"] is None
    assert updated["questions"][1]["review"]["message"] == "感谢你的纠正！这道题已更换，请继续作答。"
    assert all("answer" in item for i, item in enumerate(updated["questions"])
               if i not in {1, len(updated["questions"]) - 1})
    assert [model for _, model in seen] == ["flash"] * 7 + ["independent", "flash", "flash"]
    assert client.post(multi + "/answer", headers=owner, json={"selected": [0]}).status_code == 409
    completed = client.post(f"{path}/questions/{replacement_id}/answer", headers=owner, json={"selected": [0, 1]})
    assert completed.json()["report"] is None
    final = client.post(f"{path}/questions/{ids[-1]}/answer", headers=owner, json={"selected": [0]})
    assert final.json()["report"]["passed"]
    quiz_store.initialize()
    assert client.get(path, headers=owner).json() == final.json()


def test_regenerate_uses_feedback_and_keeps_all_topics(client):
    feedback_seen = []
    round_number = 0

    def handler(prompt, content, _model):
        nonlocal round_number
        data = json.loads(content)
        if prompt == DRAFT_PROMPT:
            feedback_seen.append(data["scope"].get("learner_feedback"))
            if data["scope"].get("learner_feedback"):
                round_number += 1
                offset = 900 + round_number * 100
                return {"topics": ["开口"], "questions": [
                    question(offset + index, "开口", "multiple" if index == 0 else "single") for index in range(10)
                ]}
            return draft()
        assert prompt == FIRST_REVIEW_PROMPT
        return {"answers": [item["correct"] for item in data["draft"]["questions"]], "issues": []}

    mock_upstream(handler)
    owner, path, quiz = start(client)
    old_stems = {item["stem"] for item in quiz["questions"]}
    assert quiz["status"] == "ready" and len(quiz["questions"]) == 10
    assert client.post(path + "/regenerate", headers=owner, json={"feedback": "   "}).status_code == 422
    assert client.post(path + "/regenerate", headers=owner, json={"feedback": "x" * 501}).status_code == 422

    first = client.post(path + "/regenerate", headers=owner,
                        json={"feedback": "这批题太难了，题干也太长"})
    assert first.status_code == 202, first.text
    first_quiz = client.get("/api/quizzes/" + first.json()["id"], headers=owner).json()
    assert first_quiz["status"] == "ready" and len(first_quiz["questions"]) == 10
    assert {item["stem"] for item in first_quiz["questions"]}.isdisjoint(old_stems)
    assert feedback_seen == [None, "这批题太难了，题干也太长"]

    second = client.post(f"/api/quizzes/{first_quiz['id']}/regenerate", headers=owner,
                         json={"feedback": "再简单一点"})
    assert second.status_code == 202
    second_quiz = client.get("/api/quizzes/" + second.json()["id"], headers=owner).json()
    assert second_quiz["status"] == "ready" and len(second_quiz["questions"]) == 10
    assert {item["stem"] for item in second_quiz["questions"]}.isdisjoint(
        {item["stem"] for item in first_quiz["questions"]})
    assert feedback_seen[-1] == "再简单一点"
    assert client.get(path, headers=owner).status_code == 200

    for item in second_quiz["questions"]:
        selected = [0] if item["kind"] == "single" else [0, 1]
        assert client.post(f"/api/quizzes/{second_quiz['id']}/questions/{item['id']}/answer",
                           headers=owner, json={"selected": selected}).status_code == 200
    assert client.get("/api/quizzes/" + second_quiz["id"], headers=owner).json()["report"] is not None
    assert client.post(f"/api/quizzes/{second_quiz['id']}/regenerate", headers=owner,
                       json={"feedback": "再换一批"}).status_code == 409


@pytest.mark.parametrize(("verdict", "answered"), [("valid", False), ("valid", True), ("uncertain", True), ("failed", True)])
def test_challenge_leaves_original_and_answer_on_other_outcomes(client, verdict, answered):
    def handler(prompt, content, model):
        if prompt == DRAFT_PROMPT:
            assert model == "flash"
            return draft()
        if prompt == FIRST_REVIEW_PROMPT:
            return {"answers": [item["correct"] for item in draft()["questions"]], "issues": []}
        assert model == "independent"
        if verdict == "failed":
            return httpx.Response(503)
        return {"verdict": verdict, "user_perspective": "疑问源于题干条件", "objective": "正确答案是 A",
                "clarification_focus": "conditions"}

    mock_upstream(handler)
    owner, path, quiz = start(client)
    question_id = quiz["questions"][0]["id"]
    action = f"{path}/questions/{question_id}"
    if answered:
        client.post(action + "/answer", headers=owner, json={"selected": [0]})
    submitted = client.post(action + "/challenge", headers=owner, json={"objection": "条件够吗？"})
    assert submitted.status_code == 202 and "answer" not in submitted.json()["questions"][0]
    original = client.get(path, headers=owner).json()["questions"][0]
    assert original["id"] == question_id and ("answer" in original) == answered
    if answered:
        assert original["answer"]["is_correct"]
    assert original["review"]["status"] == verdict
    assert "正确答案是 A" not in original["review"]["message"]
    if verdict == "valid":
        assert "可以继续作答" in original["review"]["message"]
        assert "题目给出的条件需要一起使用" in original["review"]["message"]


def test_failed_initial_review_keeps_quiz_closed(client, monkeypatch):
    monkeypatch.delenv("REVIEW_MODEL_API_KEY")

    def handler(prompt, content, model):
        assert model == "flash"
        return draft() if prompt == DRAFT_PROMPT else {"answers": [[3], [3]], "issues": []}

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
    assert "题干漏写条件" not in paused["review"]["message"]
    assert client.post(action + "/answer", headers=owner, json={"selected": [0]}).status_code == 409
    assert client.post(action + "/challenge", headers=owner, json=objection).status_code == 202
    replaced = client.get(path, headers=owner).json()["questions"][0]
    assert replaced["id"] != question_id and "感谢你的纠正" in replaced["review"]["message"]
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


def test_required_drill_retries_and_uses_original_and_previous_round(client):
    analyses = []
    drafts = 0

    def handler(prompt, content, model):
        nonlocal drafts
        data = json.loads(content)
        assert model == "flash"
        if prompt == DRAFT_PROMPT:
            return draft()
        if prompt == FIRST_REVIEW_PROMPT:
            return {"answers": [item["correct"] for item in data["draft"]["questions"]], "issues": []}
        if prompt == DRILL_ANALYSIS_PROMPT:
            analyses.append(data)
            return mock_drill_response(prompt, data)
        assert prompt == DRILL_DRAFT_PROMPT
        drafts += 1
        if drafts == 1:
            return httpx.Response(503)
        return mock_drill_response(prompt, data, 1000 + 10 * drafts)

    mock_upstream(handler)
    owner, path, quiz = start(client)
    first, second = quiz["questions"][:2]
    original = f"{path}/questions/{first['id']}"
    next_question = f"{path}/questions/{second['id']}/answer"
    assert client.post(original + "/explanation", headers=owner).status_code == 409
    assert client.post(original + "/answer", headers=owner, json={"unsure": True, "selected": [0]}).status_code == 422
    answer = client.post(original + "/answer", headers=owner, json={"unsure": True}).json()
    assert answer["questions"][0]["answer"] == {"selected": [], "is_correct": False, "unsure": True}
    assert answer["blocked_question_id"] == first["id"] and answer["report"] is None
    assert client.post(next_question, headers=owner, json={"selected": [0, 1]}).status_code == 409
    assert client.post(original + "/answer", headers=owner, json={"selected": [0]}).json() == answer

    response = client.post(original + "/explanation", headers=owner).json()
    assert response["questions"][0]["answer"]["correct"] == [0]
    assert response["questions"][0]["drill"]["status"] == "generating"
    assert client.get(path, headers=owner).json()["questions"][0]["drill"]["status"] == "failed"
    assert len(analyses) == 1 and analyses[0]["original_answer"]["unsure"]
    assert client.post(original + "/drill/retry", headers=owner).status_code == 200
    assert len(analyses) == 1
    quiz_store.initialize()
    current = client.get(path, headers=owner).json()["questions"][0]["drill"]
    assert current["round"] == 1 and current["status"] == "ready"
    for i, item in enumerate(current["questions"]):
        endpoint = f"{original}/drill/questions/{item['id']}/answer"
        response = client.post(endpoint, headers=owner, json={"selected": [1 if i == 0 else 0]}).json()
        if i == 0:
            assert response["questions"][0]["drill"]["questions"][0]["answer"] == {"selected": [1]}
            assert client.post(endpoint, headers=owner, json={"selected": [0]}).json() == response
    drill = response["questions"][0]["drill"]
    assert drill["round"] == 2 and drill["status"] == "generating"
    assert drill["feedback"][0]["id"] == current["questions"][0]["id"]
    assert drill["feedback"][0]["correct"] == [0] and drill["feedback"][0]["explanation"] == "解析"
    assert len(analyses) == 2 and analyses[1]["original"]["id"] == first["id"]
    assert [item["answer"]["is_correct"] for item in analyses[1]["previous_round"]] == [False, True, True]
    assert set(analyses[1]["required_points"]) == {"符号判断", "开口方向"}
    assert client.post(endpoint, headers=owner, json={"selected": [0]}).status_code == 409

    current = client.get(path, headers=owner).json()["questions"][0]["drill"]
    for item in current["questions"]:
        response = client.post(f"{original}/drill/questions/{item['id']}/answer",
                               headers=owner, json={"selected": [0]}).json()
    assert response["blocked_question_id"] is None
    assert response["questions"][0]["drill"]["status"] == "passed"
    assert not response["questions"][0]["answer"]["is_correct"]
    assert client.post(next_question, headers=owner, json={"selected": [0, 1]}).status_code == 200
    for item in quiz["questions"][2:]:
        assert client.post(f"{path}/questions/{item['id']}/answer", headers=owner,
                           json={"selected": [0]}).status_code == 200
    report = client.get(path, headers=owner).json()["report"]
    assert report["correct"] == 9 and report["percent"] == 90


def test_optional_drill_does_not_lock_and_replacement_preserves_other_answers(client):
    challenges = 0

    def handler(prompt, content, model):
        nonlocal challenges
        data = json.loads(content)
        if prompt == DRAFT_PROMPT:
            if data["scope"]["count"] == 1:
                assert data["scope"]["required_points"] == ["符号判断"]
                return {"topics": ["开口"], "questions": [question(500)]}
            return draft()
        if prompt == FIRST_REVIEW_PROMPT:
            return {"answers": [item["correct"] for item in data["draft"]["questions"]], "issues": []}
        if prompt == CHALLENGE_PROMPT:
            challenges += 1
            assert model == "independent"
            return {"verdict": "invalid", "user_perspective": "题意可能误解", "objective": "正确答案是 A"}
        return mock_drill_response(prompt, data)

    mock_upstream(handler)
    owner, path, quiz = start(client)
    original = f"{path}/questions/{quiz['questions'][0]['id']}"
    answer = client.post(original + "/answer", headers=owner, json={"selected": [0]}).json()
    assert "explanation" not in answer["questions"][0]["answer"]
    explained = client.post(original + "/explanation", headers=owner).json()
    assert explained["blocked_question_id"] is None and "drill" not in explained["questions"][0]
    assert client.post(original + "/drill/start", headers=owner).status_code == 200
    for item in quiz["questions"][1:]:
        response = client.post(f"{path}/questions/{item['id']}/answer",
                               headers=owner, json={"selected": [0, 1] if item["kind"] == "multiple" else [0]})
        assert response.status_code == 200
    assert response.json()["report"]["percent"] == 100

    questions = response.json()["questions"][0]["drill"]["questions"]
    for item in questions[:2]:
        assert client.post(f"{original}/drill/questions/{item['id']}/answer",
                           headers=owner, json={"selected": [0]}).status_code == 200
    url = f"{original}/drill/questions/{questions[1]['id']}"
    submitted = client.post(url + "/challenge", headers=owner, json={"objection": "定义是否完整？"}).json()
    assert "answer" not in submitted["questions"][0]["drill"]["questions"][1]
    updated = client.get(path, headers=owner).json()
    first, replaced, third = updated["questions"][0]["drill"]["questions"]
    assert first["answer"] == {"selected": [0]}
    assert replaced["id"] != questions[1]["id"] and "answer" not in replaced and "answer" not in third
    assert "感谢" in replaced["review"]["message"] and "正确答案是 A" not in replaced["review"]["message"]
    assert client.post(url + "/answer", headers=owner, json={"selected": [0]}).status_code == 409
    assert updated["report"]["percent"] == 100 and challenges == 1
