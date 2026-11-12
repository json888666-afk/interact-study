import json
import sqlite3
from uuid import uuid4

from fastapi.testclient import TestClient

from backend import quiz_store as store
from backend.accounts import passwords
from backend.main import app
from test_learning_quiz import client, legacy_draft, mock_upstream

PASSWORD = "Example-password-42"
PROFILE = {"education_stage": "高中", "goal": "用图像理解二次函数"}
DEMO_RANKS = [{"username": "小王", "points": 5, "rank": 1}, {"username": "小明", "points": 3, "rank": 2}]


def register(client, username):
    return client.post("/api/auth/register", json={"username": username, "password": PASSWORD, "profile": PROFILE})


def test_register_login_logout_and_cross_origin(client):
    assert client.get("/api/auth/me").json() == {"user": None}
    assert client.post("/api/auth/profile", json=PROFILE).status_code == 401
    assert client.post("/api/auth/register", json={"username": "Alice", "password": PASSWORD}).status_code == 422
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
