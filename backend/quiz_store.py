import json
import os
import sqlite3
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
PAUSED = {"pending", "replacement_failed"}
def database_path() -> Path:
    override = os.getenv("QUIZ_DB_PATH", "").strip()
    return ROOT / (override or ".local/quiz.sqlite3")


@contextmanager
def database():
    connection = sqlite3.connect(database_path(), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize():
    path = database_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with database() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("""CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY, username TEXT NOT NULL,
                username_key TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
                education_stage TEXT, goal TEXT
            )""")
            user_columns = {row["name"] for row in connection.execute("PRAGMA table_info(users)")}
            if "education_stage" not in user_columns:
                connection.execute("ALTER TABLE users ADD COLUMN education_stage TEXT")
            if "goal" not in user_columns:
                connection.execute("ALTER TABLE users ADD COLUMN goal TEXT")
            if "goal_approved" not in user_columns:
                connection.execute("ALTER TABLE users ADD COLUMN goal_approved INTEGER NOT NULL DEFAULT 0")
            if "exam_target" not in user_columns:
                connection.execute("ALTER TABLE users ADD COLUMN exam_target TEXT")
            connection.execute("""CREATE TABLE IF NOT EXISTS login_sessions (
                token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
                expires_at INTEGER NOT NULL
            )""")
            connection.execute("""CREATE TABLE IF NOT EXISTS quizzes (
                id TEXT PRIMARY KEY, owner TEXT NOT NULL, version TEXT NOT NULL, data TEXT NOT NULL
            )""")
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(quizzes)")}
            if "account_id" not in columns:
                connection.execute("ALTER TABLE quizzes ADD COLUMN account_id TEXT REFERENCES users(id)")
            if "learning_session" not in columns:
                connection.execute("ALTER TABLE quizzes ADD COLUMN learning_session TEXT")
            if "qualifies" not in columns:
                connection.execute("ALTER TABLE quizzes ADD COLUMN qualifies INTEGER NOT NULL DEFAULT 0")
            connection.execute("CREATE INDEX IF NOT EXISTS quiz_by_owner_version ON quizzes(owner, version)")
            connection.execute("""CREATE INDEX IF NOT EXISTS qualifying_quizzes
                ON quizzes(account_id, learning_session) WHERE qualifies = 1""")
            for row in connection.execute("SELECT * FROM quizzes"):
                quiz = unpack(row)
                changed = False
                if quiz["status"] == "generating":
                    quiz.update(status="failed", message="服务重启中断了出题，请重试。")
                    changed = True
                reviews = list(quiz["reviews"].values())
                for review in reviews:
                    if review["status"] == "pending":
                        status = "replacement_failed" if review.get("confirmed_invalid") else "failed"
                        review.update(status=status, message="服务重启中断了审核，请重试。")
                        changed = True
                if changed or quiz["report"] != calculate_report(quiz):
                    save(connection, quiz)
    except (OSError, sqlite3.Error) as error:
        raise RuntimeError(f"无法写入练习数据库 {path}，请检查 QUIZ_DB_PATH。") from error


def owner_key(owner: str) -> str:
    return sha256(owner.encode()).hexdigest()


def unpack(row):
    quiz = json.loads(row["data"])
    quiz["account_id"] = row["account_id"]
    quiz["learning_session"] = row["learning_session"]
    return quiz


def latest(connection, owner: str, version: str):
    row = connection.execute(
        "SELECT * FROM quizzes WHERE owner = ? AND version = ? ORDER BY rowid DESC LIMIT 1",
        (owner_key(owner), version),
    ).fetchone()
    return unpack(row) if row else None


def owned(connection, owner: str, quiz_id: str):
    row = connection.execute("SELECT * FROM quizzes WHERE id = ? AND owner = ?", (quiz_id, owner_key(owner))).fetchone()
    if not row:
        raise HTTPException(404, "找不到此练习。")
    return unpack(row)


def insert(connection, owner: str, version: str, context, *, account_id=None, learning_session=None):
    quiz = {
        "id": str(uuid4()), "version_id": version, "status": "generating",
        "message": "", "questions": [], "topics": [], "answers": {}, "reviews": {},
        "report": None, "context": context, "retired": [],
        "account_id": account_id, "learning_session": learning_session,
    }
    connection.execute(
        "INSERT INTO quizzes(id, owner, version, data, account_id, learning_session) VALUES (?, ?, ?, ?, ?, ?)",
        (quiz["id"], owner_key(owner), version, json.dumps(quiz, ensure_ascii=False), account_id, learning_session),
    )
    return quiz


def find_question(quiz, question_id: str):
    for question in quiz["questions"]:
        if question["id"] == question_id:
            return question
    raise HTTPException(409, "这道题已更新，请刷新题目后继续。")


def calculate_report(quiz):
    questions = quiz["questions"]
    answers = quiz["answers"]
    if not questions or len(answers) != len(questions):
        return None
    if any(quiz["reviews"].get(q["id"], {}).get("status") in PAUSED for q in questions):
        return None
    topics = {topic: {"topic": topic, "correct": 0, "total": 0} for topic in quiz["topics"]}
    wrong = []
    correct = 0
    for question in questions:
        item = topics[question["topic"]]
        item["total"] += 1
        if answers[question["id"]]["is_correct"]:
            item["correct"] += 1
            correct += 1
        else:
            wrong.append(question["id"])
    return {
        "total": len(questions), "correct": correct, "percent": round(100 * correct / len(questions), 2),
        "passed": correct * 10 >= 9 * len(questions), "topics": list(topics.values()), "wrong_ids": wrong,
    }


def save(connection, quiz):
    quiz["report"] = calculate_report(quiz)
    report = quiz["report"]
    # A pending review without a confirmed flaw temporarily hides the report, but keeps an earned point.
    preserve = len(quiz["questions"]) == len(quiz["answers"]) and any(
        review["status"] == "pending" for review in quiz["reviews"].values()
    ) and not any(review.get("confirmed_invalid") for review in quiz["reviews"].values())
    qualifies = None if report is None and preserve else int(bool(quiz["account_id"] and report and report["passed"]))
    connection.execute(
        "UPDATE quizzes SET data = ?, qualifies = COALESCE(?, qualifies) WHERE id = ?",
        (json.dumps(quiz, ensure_ascii=False), qualifies, quiz["id"]),
    )


def public(quiz, connection):
    questions = []
    for question in quiz["questions"]:
        item = {key: question[key] for key in ("id", "kind", "topic", "stem", "options")}
        question_id = question["id"]
        answer = quiz["answers"].get(question_id)
        if answer:
            item["answer"] = {**answer, "correct": question["correct"], "explanation": question["explanation"]}
        review = quiz["reviews"].get(question_id)
        if review:
            item["review"] = {key: review[key] for key in ("status", "message", "objection") if key in review}
        questions.append(item)
    account_id = quiz["account_id"]
    earned = account_id is not None and connection.execute(
        "SELECT 1 FROM quizzes WHERE account_id = ? AND learning_session = ? AND qualifies = 1 LIMIT 1",
        (account_id, quiz["learning_session"]),
    ).fetchone() is not None
    result = {key: quiz[key] for key in ("id", "version_id", "status", "message", "report")} | {
        "questions": questions,
        "ranking": {"enabled": account_id is not None, "session_point": int(earned)},
    }
    return result
