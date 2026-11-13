import json
import re
import secrets
import sqlite3
import time
import unicodedata
from hashlib import sha256
from typing import Annotated
from uuid import uuid4

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import Field, field_validator
from starlette.concurrency import run_in_threadpool

from .goals import ExamTarget, review_goal
from .model import model_client
from .quiz_store import database
from .schemas import LearnerProfile, StrictModel

router = APIRouter()
COOKIE = "interact_study_login"
SESSION_SECONDS = 7 * 24 * 60 * 60
PAGE_SIZE = 10
LEADERBOARD_LIMIT = 100
passwords = PasswordHasher()
dummy_hash = passwords.hash(secrets.token_urlsafe(32))


class Credentials(StrictModel):
    username: Annotated[str, Field(max_length=64)]
    password: Annotated[str, Field(min_length=8, max_length=128)]

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        value = unicodedata.normalize("NFKC", value).strip()
        if not re.fullmatch(r"[\w-]{3,24}", value):
            raise ValueError("用户名须为 3–24 个字母、汉字、数字、下划线或连字符。")
        return value


class Registration(Credentials):
    profile: LearnerProfile | None = None


def stored_profile(row):
    if row and row["education_stage"] and row["goal"]:
        return {"education_stage": row["education_stage"], "goal": row["goal"]}
    return None


def account_profile(connection, account_id):
    if account_id is None:
        return None
    row = connection.execute("""SELECT education_stage, goal FROM users
                              WHERE id = ? AND goal_approved = 1""", (account_id,)).fetchone()
    return stored_profile(row)


def account_exam(connection, account_id):
    if account_id is None:
        return None
    row = connection.execute("SELECT exam_target FROM users WHERE id = ? AND goal_approved = 1", (account_id,)).fetchone()
    return ExamTarget.model_validate(json.loads(row["exam_target"])) if row and row["exam_target"] else None


def public_user(row):
    user = {"id": row["id"], "username": row["username"], "profile": stored_profile(row)}
    if user["profile"] and not row["goal_approved"]:
        user["needs_goal_review"] = True
    return user


def same_origin(request: Request):
    origin = request.headers.get("origin")
    if origin and origin != f"{request.url.scheme}://{request.url.netloc}":
        raise HTTPException(403, "请求来源无效。")


def token_hash(token: str) -> str:
    return sha256(token.encode()).hexdigest()


def current_user(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    if request.method == "POST":
        same_origin(request)
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    with database() as connection:
        row = connection.execute("""
            SELECT users.id, users.username, users.education_stage, users.goal, users.goal_approved
            FROM login_sessions JOIN users ON users.id = login_sessions.user_id
            WHERE token_hash = ? AND expires_at > ?
        """, (token_hash(token), int(time.time()))).fetchone()
    return public_user(row) if row else None


User = Annotated[dict | None, Depends(current_user)]


def learning_profile(user: User):
    if user is None:
        return None
    if user["profile"] is None or user.get("needs_goal_review"):
        raise HTTPException(409, "请先在学习设置提交学习目标审核。")
    return user["profile"]


Profile = Annotated[dict | None, Depends(learning_profile)]


def replace_session(connection, user_id: str, request: Request, response: Response):
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    connection.execute("DELETE FROM login_sessions WHERE expires_at <= ?", (now,))
    old = request.cookies.get(COOKIE)
    if old:
        connection.execute("DELETE FROM login_sessions WHERE token_hash = ?", (token_hash(old),))
    connection.execute("INSERT INTO login_sessions VALUES (?, ?, ?)", (token_hash(token), user_id, now + SESSION_SECONDS))
    response.set_cookie(COOKIE, token, max_age=SESSION_SECONDS, httponly=True, samesite="lax",
                        secure=request.url.scheme == "https")
    response.headers["Cache-Control"] = "no-store"


@router.post("/api/auth/register", status_code=201)
async def register(credentials: Registration, request: Request, response: Response, client=Depends(model_client)):
    same_origin(request)
    if not (re.search(r"[A-Za-z]", credentials.password) and re.search(r"[0-9]", credentials.password)):
        raise HTTPException(422, "密码须至少包含一个英文字母和一个数字。")
    with database() as connection:
        if connection.execute("SELECT 1 FROM users WHERE username_key = ?", (credentials.username.casefold(),)).fetchone():
            raise HTTPException(409, "该用户名已被注册。")
    exam = await review_goal(credentials.profile.goal, client) if credentials.profile else None
    user = {"id": str(uuid4()), "username": credentials.username,
            "profile": credentials.profile.model_dump() if credentials.profile else None}
    password_hash = await run_in_threadpool(passwords.hash, credentials.password)
    try:
        with database() as connection:
            connection.execute("""INSERT INTO users
                (id, username, username_key, password_hash, education_stage, goal, goal_approved, exam_target)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", (
                user["id"], user["username"], user["username"].casefold(), password_hash,
                credentials.profile.education_stage if credentials.profile else None,
                credentials.profile.goal if credentials.profile else None,
                1 if credentials.profile else 0,
                exam.model_dump_json() if exam else None,
            ))
            replace_session(connection, user["id"], request, response)
    except sqlite3.IntegrityError as error:
        raise HTTPException(409, "该用户名已被注册。") from error
    return {"user": user}


@router.post("/api/auth/login")
def login(credentials: Credentials, request: Request, response: Response):
    same_origin(request)
    with database() as connection:
        row = connection.execute(
            "SELECT id, username, password_hash, education_stage, goal, goal_approved FROM users WHERE username_key = ?",
            (credentials.username.casefold(),),
        ).fetchone()
    try:
        passwords.verify(row["password_hash"] if row else dummy_hash, credentials.password)
    except VerifyMismatchError:
        raise HTTPException(401, "用户名或密码有误。") from None
    if not row:
        raise HTTPException(401, "用户名或密码有误。")
    with database() as connection:
        replace_session(connection, row["id"], request, response)
    return {"user": public_user(row)}


@router.post("/api/auth/logout")
def logout(request: Request, response: Response):
    same_origin(request)
    token = request.cookies.get(COOKIE)
    if token:
        with database() as connection:
            connection.execute("DELETE FROM login_sessions WHERE token_hash = ?", (token_hash(token),))
    response.delete_cookie(COOKIE, httponly=True, samesite="lax", secure=request.url.scheme == "https")
    response.headers["Cache-Control"] = "no-store"
    return {"user": None}


@router.get("/api/auth/me")
def me(user: User):
    return {"user": user}


@router.post("/api/auth/profile")
async def update_profile(profile: LearnerProfile, user: User, client=Depends(model_client)):
    if user is None:
        raise HTTPException(401, "请先登录。")
    exam = await review_goal(profile.goal, client)
    with database() as connection:
        result = connection.execute("""UPDATE users SET education_stage = ?, goal = ?, goal_approved = 1, exam_target = ?
                                    WHERE id = ?""",
                                    (profile.education_stage, profile.goal, exam.model_dump_json() if exam else None,
                                     user["id"]))
        if result.rowcount != 1:
            raise HTTPException(401, "请重新登录。")
    return {"user": {"id": user["id"], "username": user["username"], "profile": profile.model_dump()}}


RANKINGS = """
WITH scores AS (
    SELECT account_id, COUNT(DISTINCT learning_session) AS points
    FROM quizzes
    WHERE qualifies = 1 AND account_id IS NOT NULL
    GROUP BY account_id
), participants AS (
    SELECT users.id, users.username, COALESCE(scores.points, 0) AS points
    FROM users LEFT JOIN scores ON users.id = scores.account_id
    UNION ALL SELECT 'demo-wang', '小王', 5
    UNION ALL SELECT 'demo-ming', '小明', 3
), rankings AS (
    SELECT id, username, points, RANK() OVER (ORDER BY points DESC) AS rank,
           ROW_NUMBER() OVER (ORDER BY points DESC, username COLLATE BINARY, id) AS position
    FROM participants
)
"""


@router.get("/api/leaderboard")
def leaderboard(user: User, page: Annotated[int, Query(ge=1, le=LEADERBOARD_LIMIT // PAGE_SIZE)] = 1):
    with database() as connection:
        connection.execute("BEGIN")
        rows = connection.execute(RANKINGS + """
            SELECT username, points, rank FROM rankings
            WHERE position <= ? ORDER BY position LIMIT ? OFFSET ?
        """, (LEADERBOARD_LIMIT, PAGE_SIZE + 1, (page - 1) * PAGE_SIZE)).fetchall()
        mine = connection.execute(
            RANKINGS + "SELECT username, points, rank, position FROM rankings WHERE id = ?", (user["id"],),
        ).fetchone() if user else None
    my_rank = None
    if mine:
        my_rank = {key: mine[key] for key in ("username", "points", "rank")}
        my_rank["listed_page"] = (
            (mine["position"] - 1) // PAGE_SIZE + 1 if mine["position"] <= LEADERBOARD_LIMIT else None
        )
    return {
        "page": page, "has_more": len(rows) > PAGE_SIZE, "entries": [dict(row) for row in rows[:PAGE_SIZE]],
        "me": my_rank,
    }
