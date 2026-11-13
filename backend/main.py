import json
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from . import quiz_store
from .accounts import Profile
from .accounts import router as accounts_router
from .learning import AskRequest, Explanation, ask_lesson
from .model import REVISION_PROMPT, SYSTEM_PROMPT, GenerationError, ModelSettings, generate_lesson, model_client, teaching_material
from .papers import router as papers_router
from .quizzes import router as quiz_router
from .schemas import GenerateRequest, Lesson, LessonResponse, ReviseRequest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_IDS = {"quadratic", "recursion"}
load_dotenv(PROJECT_ROOT / ".env")


@asynccontextmanager
async def lifespan(_app):
    quiz_store.initialize()
    yield


app = FastAPI(title="可视化理论中心", lifespan=lifespan)
app.include_router(accounts_router)
app.include_router(quiz_router)
app.include_router(papers_router)


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, error: RequestValidationError):
    return JSONResponse(status_code=422, content={"detail": [
        {key: item[key] for key in ("loc", "msg", "type")} for item in error.errors()
    ]})


@app.post("/api/lessons/ask", response_model=Explanation)
async def explain(request: AskRequest, profile: Profile, client: httpx.AsyncClient = Depends(model_client)):
    try:
        return await ask_lesson(request, client, profile=profile)
    except GenerationError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"code": error.code, "message": str(error)},
        ) from error


async def request_lesson(content: str, client: httpx.AsyncClient, prompt: str):
    try:
        result = await generate_lesson(content, ModelSettings.from_environment(), client, system_prompt=prompt)
    except GenerationError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"code": error.code, "message": str(error)},
        ) from error
    return LessonResponse(source="live", result=result)


@app.post("/api/lessons/generate", response_model=LessonResponse)
async def create_lesson(request: GenerateRequest, profile: Profile, client: httpx.AsyncClient = Depends(model_client)):
    content = request.question
    if profile is not None:
        content = json.dumps(teaching_material(request.model_dump(), profile), ensure_ascii=False)
    return await request_lesson(content, client, SYSTEM_PROMPT)


@app.post("/api/lessons/revise", response_model=LessonResponse)
async def revise_lesson(request: ReviseRequest, profile: Profile, client: httpx.AsyncClient = Depends(model_client)):
    content = teaching_material(request.model_dump(mode="json"), profile)
    return await request_lesson(json.dumps(content, ensure_ascii=False), client, REVISION_PROMPT)


@app.get("/api/examples/{example_id}", response_model=LessonResponse)
async def get_example(example_id: str):
    if example_id not in EXAMPLE_IDS:
        raise HTTPException(status_code=404, detail={"code": "example_not_found", "message": "找不到该预置案例。"})
    lesson = Lesson.model_validate_json(
        (PROJECT_ROOT / "backend" / "examples" / f"{example_id}.json").read_text(encoding="utf-8")
    )
    return LessonResponse(source="example", result=lesson)
