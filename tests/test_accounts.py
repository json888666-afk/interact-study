import json
import sqlite3
from uuid import uuid4

from fastapi.testclient import TestClient

from backend import quiz_store as store
from backend.accounts import passwords
from backend.learning import ASK_PROMPT
from backend.main import app
from backend.model import REVISION_PROMPT, SYSTEM_PROMPT
from backend.quiz_models import CHALLENGE_PROMPT, DRAFT_PROMPT, DRILL_ANALYSIS_PROMPT, DRILL_DRAFT_PROMPT, FIRST_REVIEW_PROMPT
from test_learning_quiz import client, context, draft, legacy_draft, mock_drill_response, mock_upstream, pass_drill, question, start

PASSWORD = "Example-password-42"
PROFILE = {"education_stage": "高中", "goal": "用图像理解二次函数"}
DEMO_RANKS = [{"username": "小王", "points": 5, "rank": 1}, {"username": "小明", "points": 3, "rank": 2}]


def register(client, username):
    return client.post("/api/auth/register", json={"username": username, "password": PASSWORD, "profile": PROFILE})


def test_register_login_logout_and_cross_origin(client):
    assert client.get("/api/auth/me").json() == {"user": None}
    assert client.post("/api/auth/profile", json=PROFILE).status_code == 401
    created_without_profile = client.post("/api/auth/register", json={"username": "NoProfile", "password": PASSWORD})
    assert created_without_profile.status_code == 201
    assert created_without_profile.json()["user"]["profile"] is None
    for password in ("onlyletters", "12345678"):
        rejected = client.post("/api/auth/register", json={"username": "Alice", "password": password, "profile": PROFILE})
        assert rejected.status_code == 422
        assert "英文字母和一个数字" in rejected.json()["detail"]
    response = register(client, "Alice")
    assert response.status_code == 201
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "max-age=604800" in response.headers["set-cookie"].lower()
    user = response.json()["user"]
    token = client.cookies.get("interact_study_login")
    assert client.get("/api/auth/me").json()["user"] == user
    with store.database() as db:
        assert db.execute("SELECT password_hash FROM users").fetchone()[0].startswith("$argon2id$")
        assert db.execute("SELECT token_hash FROM login_sessions").fetchone()[0] != token
    assert register(client, "alice").status_code == 409
    assert client.post("/api/auth/logout", headers={"Origin": "https://other.example"}).status_code == 403
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me", headers={"Cookie": "interact_study_login=" + token}).json()["user"] is None
    assert client.post("/api/auth/login", json={"username": "Alice", "password": "invalid-password"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "alice", "password": PASSWORD}).json()["user"] == user


def test_model_uses_current_profile_without_sending_account_identity(client):
    material = context(client)
    lesson = material["lesson"]
    updated = {"education_stage": "本科", "goal": "学习二次函数与导数的联系"}
    seen = []

    def handler(prompt, content, _model):
        if prompt == SYSTEM_PROMPT and not content.startswith("{"):
            seen.append((prompt, {}))
            return lesson
        data = json.loads(content)
        assert {"username", "id", "account_id", "password"}.isdisjoint(data)
        seen.append((prompt, data))
        if prompt in (SYSTEM_PROMPT, REVISION_PROMPT):
            return lesson
        if prompt == ASK_PROMPT:
            return {"answer": "看图中的开口和顶点。"}
        if prompt == DRAFT_PROMPT:
            return draft()
        if prompt == FIRST_REVIEW_PROMPT:
            assert "learner_profile" not in data and "learner_profile" not in data["context"]
            return {"answers": [item["correct"] for item in data["draft"]["questions"]], "issues": []}
        return mock_drill_response(prompt, data)

    mock_upstream(handler)
    generate = "/api/lessons/generate"
    question_body = {"question": material["question"]}
    assert client.post(generate, json=question_body).status_code == 200
    assert seen[-1][1] == {}
    alice = register(client, "Alice").json()["user"]
    assert client.post(generate, json=question_body | {"learner_profile": updated}).status_code == 422
    assert client.post(generate, json=question_body).status_code == 200
    assert seen[-1][1]["learner_profile"] == PROFILE
    for invalid in ({"goal": " "}, {"goal": "字" * 301}, {"education_stage": "其他"}):
        assert client.post("/api/auth/profile", json=PROFILE | invalid).status_code == 422
    assert client.post("/api/auth/profile", headers={"Origin": "https://other.example"}, json=updated).status_code == 403
    assert client.post("/api/auth/profile", json=updated | {"id": alice["id"]}).status_code == 422
    assert client.post("/api/auth/profile", json=updated | {"goal": "  " + updated["goal"] + "  "}).json()["user"]["profile"] == updated
    assert client.get("/api/auth/me").json()["user"]["profile"] == updated
    assert client.post("/api/lessons/ask", json=material | {"message": "怎么理解开口？"}).status_code == 200
    assert client.post("/api/lessons/revise", json=question_body | {"lesson": lesson, "instruction": "增加坐标轴"}).status_code == 200
    owner, path, quiz = start(client)
    first = quiz["questions"][0]["id"]
    assert client.post(f"{path}/questions/{first}/answer", headers=owner, json={"unsure": True}).status_code == 200
    latest = updated | {"goal": "本周重点理解二次函数的顶点"}
    assert client.post("/api/auth/profile", json=latest).status_code == 200
    pass_drill(client, path, owner, first)
    for prompt, expected in ((ASK_PROMPT, updated), (REVISION_PROMPT, updated), (DRAFT_PROMPT, updated),
                             (DRILL_ANALYSIS_PROMPT, latest), (DRILL_DRAFT_PROMPT, latest)):
        assert [data["learner_profile"] for call, data in seen if call == prompt] == [expected]

    assert register(client, "Bob").json()["user"]["profile"] == PROFILE
    assert client.post("/api/auth/profile", json=PROFILE | {"goal": "另一个账户的目标"}).status_code == 200
    assert client.post("/api/auth/login", json={"username": "Alice", "password": PASSWORD}).json()["user"]["profile"] == latest
    assert all(set(entry) == {"username", "rank", "points"} for entry in client.get("/api/leaderboard").json()["entries"])


def test_ranked_quizzes_are_scoped_and_only_score_once_per_lesson(client):
    def handler(prompt, content, _model):
        data = json.loads(content)
        if prompt == DRAFT_PROMPT:
            if data["scope"]["count"] == 1:
                assert "learner_profile" not in data
                with store.database() as db:
                    assert db.execute("SELECT SUM(qualifies) FROM quizzes").fetchone()[0] == 0
                return {"topics": ["开口"], "questions": [question(300, kind="multiple")]}
            quiz = draft()
            assert data["scope"]["count"] == 2
            if data.get("excluded_stems"):
                assert data["scope"]["required_topics"] == ["开口"]
                for index, item in enumerate(quiz["questions"]):
                    item["stem"] = "新题 " + item["stem"]
            return quiz
        if prompt == FIRST_REVIEW_PROMPT:
            return {"answers": [item["correct"] for item in data["draft"]["questions"]], "issues": []}
        if prompt in (DRILL_ANALYSIS_PROMPT, DRILL_DRAFT_PROMPT):
            return mock_drill_response(prompt, data)
        assert prompt == CHALLENGE_PROMPT
        assert set(data) == {"question", "objection"}
        with store.database() as db:
            assert db.execute("SELECT SUM(qualifies) FROM quizzes").fetchone()[0] == 1
        return {"verdict": "invalid", "user_perspective": "理解范围有歧义", "objective": "需要补齐条件"}

    mock_upstream(handler)
    version = str(uuid4())
    headers = {"X-Study-Session": str(uuid4())}

    def new_quiz(version, previous=None):
        request = context(client) | {"version_id": version, "previous_id": previous}
        result = client.post("/api/quizzes", headers=headers, json=request)
        assert result.status_code == 202
        url = "/api/quizzes/" + result.json()["id"]
        quiz = client.get(url, headers=headers).json()
        assert quiz["status"] == "ready", quiz["message"]
        return url, quiz

    def answer(path, question_id, selected):
        response = client.post(f"{path}/questions/{question_id}/answer", headers=headers, json={"selected": selected})
        assert response.status_code == 200
        result = response.json()
        if result["blocked_question_id"] == question_id:
            assert result["report"] is None and result["ranking"]["session_point"] == 0
            return pass_drill(client, path, headers, question_id)
        return result

    guest_path, guest_quiz = new_quiz(version)
    for item in guest_quiz["questions"]:
        guest = answer(guest_path, item["id"], [0, 1] if item["kind"] == "multiple" else [0])
    assert guest["report"]["passed"] and guest["ranking"] == {"enabled": False, "session_point": 0}
    assert client.get("/api/leaderboard").json()["entries"] == DEMO_RANKS

    alice = register(client, "Alice").json()["user"]
    assert client.get(guest_path, headers=headers).status_code == 404
    path, quiz = new_quiz(version)
    assert quiz["id"] != guest_quiz["id"]
    for item in quiz["questions"]:
        result = answer(path, item["id"], [0, 1] if item["kind"] == "multiple" else [0])
    assert result["report"]["percent"] == 100 and result["report"]["passed"]
    assert result["ranking"] == {"enabled": True, "session_point": 1}
    board = client.get("/api/leaderboard").json()
    assert board["me"] == {"username": "Alice", "points": 1, "rank": 3, "listed_page": 1}
    item = quiz["questions"][1]
    assert answer(path, item["id"], [0]) == result
    response = client.post(f"{path}/questions/{item['id']}/challenge", headers=headers,
                           json={"objection": "多选题缺少条件吗？"})
    assert response.status_code == 202
    assert response.json()["ranking"]["session_point"] == 1
    updated = client.get(path, headers=headers).json()
    assert updated["ranking"]["session_point"] == 0
    assert client.get("/api/leaderboard").json()["me"]["points"] == 0
    assert answer(path, updated["questions"][1]["id"], [0, 1])["ranking"]["session_point"] == 1

    for variant, previous in ((version, quiz["id"]), (str(uuid4()), None)):
        other, new = new_quiz(variant, previous)
        for item in new["questions"]:
            answer(other, item["id"], [0, 1] if item["kind"] == "multiple" else [0])
    assert client.get("/api/leaderboard").json()["me"]["points"] == 1

    bob = register(client, "Bob").json()["user"]
    assert client.get(path, headers=headers).status_code == 404
    assert client.get(path, headers=headers | {"X-Study-Account": alice["id"]}).status_code == 409
    assert client.get("/api/leaderboard").json()["me"] == {
        "username": bob["username"], "points": 0, "rank": 4, "listed_page": 1,
    }
    bob_path, bob_quiz = new_quiz(version)
    for item in bob_quiz["questions"]:
        bob_result = answer(bob_path, item["id"], [0])
    assert bob_result["report"]["percent"] == 50 and not bob_result["report"]["passed"]
    assert bob_result["ranking"]["session_point"] == 0
    client.post("/api/auth/logout")
    assert client.get(guest_path, headers=headers).json() == guest


def test_leaderboard_paginates_and_ranks_ties(client):
    with store.database() as db:
        for index in range(101):
            account = str(uuid4())
            name = f"learner{index:03}"
            db.execute("INSERT INTO users (id, username, username_key, password_hash) VALUES (?, ?, ?, ?)",
                       (account, name, name, "unused"))
            for learning_session in range(2 if index < 2 else 1):
                session = str(uuid4())
                quiz = store.insert(db, account, str(uuid4()), {}, account_id=account, learning_session=session)
                db.execute("UPDATE quizzes SET qualifies=1 WHERE id=?", (quiz["id"],))
    first = client.get("/api/leaderboard").json()
    last = client.get("/api/leaderboard?page=10").json()
    assert len(first["entries"]) == 10 and first["has_more"]
    assert first["entries"][:2] == DEMO_RANKS
    assert [entry["rank"] for entry in first["entries"][2:5]] == [3, 3, 5]
    assert len(last["entries"]) == 10 and not last["has_more"]
    assert last["entries"][-1] == {"username": "learner097", "rank": 5, "points": 1}
    assert client.get("/api/leaderboard?page=11").status_code == 422
    assert register(client, "Outside").status_code == 201
    assert client.get("/api/leaderboard").json()["me"] == {
        "username": "Outside", "points": 0, "rank": 104, "listed_page": None,
    }


def test_legacy_database_migrates_report_and_preserves_guest_access(quiz_database, monkeypatch):
    async def approve(_goal, _client):
        return None

    monkeypatch.setattr("backend.accounts.review_goal", approve)
    owner, version, quiz_id = (str(uuid4()) for _ in range(3))
    source = legacy_draft()
    questions = [{"id": str(uuid4()), **item} for item in source["questions"]]
    quiz = {"id": quiz_id, "version_id": version, "status": "ready", "message": "", "questions": questions,
            "topics": source["topics"], "answers": {item["id"]: {"selected": [0], "is_correct": index != 1}
                                                   for index, item in enumerate(questions)},
            "report": {"passed": False, "percent": 90}, "reviews": {}, "context": {}, "retired": []}
    db = sqlite3.connect(quiz_database)
    try:
        with db:
            db.execute("CREATE TABLE users (id TEXT PRIMARY KEY, username TEXT NOT NULL, username_key TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL)")
            db.execute("INSERT INTO users VALUES (?, ?, ?, ?)", (str(uuid4()), "Legacy", "legacy", passwords.hash(PASSWORD)))
            db.execute("CREATE TABLE quizzes (id TEXT PRIMARY KEY, owner TEXT NOT NULL, version TEXT NOT NULL, data TEXT NOT NULL)")
            db.execute("INSERT INTO quizzes VALUES (?, ?, ?, ?)", (quiz_id, store.owner_key(owner), version, json.dumps(quiz)))
    finally:
        db.close()
    with TestClient(app) as client:
        old = client.get("/api/quizzes/" + quiz_id, headers={"X-Study-Session": owner}).json()
        assert len(old["questions"]) == 10
        assert old["report"]["passed"] and old["report"]["percent"] == 90
        assert old["ranking"] == {"enabled": False, "session_point": 0}
        assert client.get("/api/leaderboard").json()["entries"][:2] == DEMO_RANKS
        credentials = {"username": "Legacy", "password": PASSWORD}
        assert client.post("/api/auth/login", json=credentials).json()["user"]["profile"] is None
        assert client.post("/api/lessons/generate", json={"question": "怎么理解函数？"}).status_code == 409
        assert client.post("/api/auth/profile", json=PROFILE).status_code == 200
        assert client.post("/api/auth/login", json=credentials).json()["user"]["profile"] == PROFILE


def test_goal_review_preserves_existing_profile_on_failure_and_extracts_exam(client):
    import httpx

    def moderate(data):
        assert set(data) == {"goal"}
        goal = data["goal"]
        if goal == "不明确":
            return {"verdict": "clarify", "message": "请说明希望学习的知识点。"}
        if goal == "找泄漏答案":
            return {"verdict": "rejected", "message": "目标需要调整。"}
        if goal == "正常学习但服务暂不可用":
            return httpx.Response(503)
        if goal == "备考成都中考数学":
            return {"verdict": "approved", "message": "通过", "exam": {"exam": "成都中考", "subject": "数学"}}
        exam = {"exam": "MIT 6.005", "subject": "软件构造"} if goal == "备考 MIT 6.005 软件构造" else None
        return {"verdict": "approved", "message": "通过", "exam": exam}

    mock_upstream(lambda *_args: {}, goal_handler=moderate)
    rejected = client.post("/api/auth/register", json={
        "username": "Alice", "password": PASSWORD, "profile": PROFILE | {"goal": "找泄漏答案"},
    })
    assert rejected.status_code == 422 and client.get("/api/auth/me").json()["user"] is None
    user = register(client, "Alice").json()["user"]
    for goal, expected in (("不明确", 422), ("找泄漏答案", 422), ("正常学习但服务暂不可用", 503)):
        assert client.post("/api/auth/profile", json=PROFILE | {"goal": goal}).status_code == expected
        assert client.get("/api/auth/me").json()["user"]["profile"] == PROFILE
    valid = PROFILE | {"goal": "备考 MIT 6.005 软件构造"}
    assert client.post("/api/auth/profile", json=valid).json()["user"]["profile"] == valid
    with store.database() as db:
        from backend.accounts import account_exam
        assert account_exam(db, user["id"]).exam == "MIT 6.005"
    generic = PROFILE | {"goal": "准备期末数学考试"}
    assert client.post("/api/auth/profile", json=generic).json()["user"]["profile"] == generic
    with store.database() as db:
        assert account_exam(db, user["id"]) is None
    specific = PROFILE | {"goal": "备考成都中考数学"}
    assert client.post("/api/auth/profile", json=specific).json()["user"]["profile"] == specific
    with store.database() as db:
        assert account_exam(db, user["id"]).exam == "成都中考"


def test_repractice_from_old_quiz_keeps_two_weakest_topics(client):
    def handler(prompt, content, _model):
        data = json.loads(content)
        if prompt == DRAFT_PROMPT:
            assert data["scope"]["count"] == 2
            assert data["scope"]["required_topics"] == ["开口", "宽窄"]
            assert data["scope"]["weak_topics"] == ["开口"]
            return {"topics": ["开口", "宽窄"], "questions": [question(100), question(101, "宽窄", "multiple")]}
        assert prompt == FIRST_REVIEW_PROMPT
        return {"answers": [[0], [0, 1]], "issues": []}

    mock_upstream(handler)
    version, owner = (str(uuid4()) for _ in range(2))
    material = context(client) | {"version_id": version}
    legacy = legacy_draft()
    legacy["topics"].append("顶点")
    legacy["questions"][-1]["topic"] = "顶点"
    questions = [{"id": str(uuid4()), **item} for item in legacy["questions"]]
    with store.database() as db:
        old = store.insert(db, owner, version, material)
        old.update(status="ready", questions=questions, topics=legacy["topics"],
                   answers={item["id"]: {"selected": [0], "is_correct": index != 1}
                            for index, item in enumerate(questions)})
        store.save(db, old)
    headers = {"X-Study-Session": owner}
    resume = client.post("/api/quizzes", headers=headers, json=material).json()
    assert resume["id"] == old["id"] and len(resume["questions"]) == 10
    restart = client.post("/api/quizzes", headers=headers, json=material | {"previous_id": old["id"]}).json()
    result = client.get("/api/quizzes/" + restart["id"], headers=headers).json()
    assert result["status"] == "ready" and len(result["questions"]) == 2


def test_register_without_profile_then_onboard(client):
    response = client.post("/api/auth/register", json={"username": "NewUser", "password": PASSWORD})
    assert response.status_code == 201
    assert response.json()["user"]["profile"] is None
    assert client.get("/api/auth/me").json()["user"]["profile"] is None
    assert client.post("/api/auth/profile", json=PROFILE).status_code == 200
    assert client.get("/api/auth/me").json()["user"]["profile"] == PROFILE


def test_profile_guidance_covers_stages_and_goals():
    from backend.model import PROFILE_GUIDANCE, STAGE_GUIDANCE, SYSTEM_PROMPT

    for stage in ("幼儿园", "小学", "初中", "高中", "本科", "硕士", "博士"):
        assert stage in STAGE_GUIDANCE
    assert "goal" in PROFILE_GUIDANCE
    assert "备考" in PROFILE_GUIDANCE and "项目" in PROFILE_GUIDANCE
    assert "以用户当前问题为主" in PROFILE_GUIDANCE
    assert STAGE_GUIDANCE in SYSTEM_PROMPT


def test_goal_prompt_allows_generic_learning_goals():
    from backend.goals import GOAL_PROMPT

    assert "不要求写清具体考试" in GOAL_PROMPT
    assert "准备期末数学考试" in GOAL_PROMPT
    assert "exam 为 null" in GOAL_PROMPT
    assert "不要因此要求补充" in GOAL_PROMPT


def test_generic_goal_does_not_search_exam_questions(client, monkeypatch):
    called = {"search": False}

    def unavailable(*_args, **_kwargs):
        called["search"] = True
        raise RuntimeError("generic goal must not search")

    monkeypatch.setattr("backend.quizzes.find_exam_questions", unavailable)

    def handler(prompt, content, _model):
        data = json.loads(content) if isinstance(content, str) and content.startswith("{") else content
        if prompt == DRAFT_PROMPT:
            return draft()
        assert prompt == FIRST_REVIEW_PROMPT
        return {"answers": [item["correct"] for item in data["draft"]["questions"]], "issues": []}

    mock_upstream(handler, goal_handler=lambda _data: {"verdict": "approved", "message": "通过"})
    register(client, "GenericGoalUser")
    owner, path, _ = start(client)
    quiz = client.get(path, headers=owner).json()
    assert quiz["status"] == "ready", quiz
    assert called["search"] is False
    assert len(quiz["questions"]) == 2
