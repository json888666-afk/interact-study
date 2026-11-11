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
            connection.execute("""CREATE TABLE IF NOT EXISTS quizzes (
                id TEXT PRIMARY KEY, owner TEXT NOT NULL, version TEXT NOT NULL, data TEXT NOT NULL
            )""")
            connection.execute("CREATE INDEX IF NOT EXISTS quiz_by_owner_version ON quizzes(owner, version)")
            connection.execute("BEGIN IMMEDIATE")
            for row in connection.execute("SELECT id, data FROM quizzes"):
                quiz = json.loads(row["data"])
                changed = False
                if quiz["status"] == "generating":
                    quiz.update(status="failed", message="服务重启中断了出题，请重试。")
                    changed = True
                for review in quiz["reviews"].values():
                    if review["status"] == "pending":
                        status = "replacement_failed" if review.get("confirmed_invalid") else "failed"
                        review.update(status=status, message="服务重启中断了审核，请重试。")
                        changed = True
                if changed:
                    save(connection, quiz)
    except (OSError, sqlite3.Error) as error:
        raise RuntimeError(f"无法写入练习数据库 {path}，请检查 QUIZ_DB_PATH。") from error


def owner_key(owner: str) -> str:
    return sha256(owner.encode()).hexdigest()


def latest(connection, owner: str, version: str):
    row = connection.execute(
        "SELECT data FROM quizzes WHERE owner = ? AND version = ? ORDER BY rowid DESC LIMIT 1",
        (owner_key(owner), version),
    ).fetchone()
    return json.loads(row["data"]) if row else None


def owned(connection, owner: str, quiz_id: str):
    row = connection.execute("SELECT data FROM quizzes WHERE id = ? AND owner = ?", (quiz_id, owner_key(owner))).fetchone()
    if not row:
        raise HTTPException(404, "找不到此练习。")
    return json.loads(row["data"])


def insert(connection, owner: str, version: str, context):
    quiz = {
        "id": str(uuid4()), "version_id": version, "status": "generating",
        "message": "", "questions": [], "topics": [], "answers": {}, "reviews": {},
        "report": None, "context": context, "retired": [],
    }
    connection.execute(
        "INSERT INTO quizzes(id, owner, version, data) VALUES (?, ?, ?, ?)",
        (quiz["id"], owner_key(owner), version, json.dumps(quiz, ensure_ascii=False)),
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
        "passed": correct * 10 > 9 * len(questions), "topics": list(topics.values()), "wrong_ids": wrong,
    }


def save(connection, quiz):
    quiz["report"] = calculate_report(quiz)
    connection.execute("UPDATE quizzes SET data = ? WHERE id = ?", (json.dumps(quiz, ensure_ascii=False), quiz["id"]))


def public(quiz):
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
    return {key: quiz[key] for key in ("id", "version_id", "status", "message", "report")} | {"questions": questions}
