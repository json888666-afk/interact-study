from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException

from .model import GenerationError, ModelSettings, generate_lesson
from .schemas import GenerateRequest, Lesson, LessonResponse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_IDS = {"quadratic", "recursion"}
load_dotenv(PROJECT_ROOT / ".env")
app = FastAPI(title="演算室")


async def model_client():
    async with httpx.AsyncClient(timeout=60) as client:
        yield client


@app.post("/api/lessons/generate", response_model=LessonResponse)
async def create_lesson(request: GenerateRequest, client: httpx.AsyncClient = Depends(model_client)):
    try:
        result = await generate_lesson(request.question, ModelSettings.from_environment(), client)
    except GenerationError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"code": error.code, "message": str(error)},
        ) from error
    return LessonResponse(source="live", result=result)


@app.get("/api/examples/{example_id}", response_model=LessonResponse)
async def get_example(example_id: str):
    if example_id not in EXAMPLE_IDS:
        raise HTTPException(status_code=404, detail={"code": "example_not_found", "message": "找不到该预置案例。"})
    lesson = Lesson.model_validate_json(
        (PROJECT_ROOT / "backend" / "examples" / f"{example_id}.json").read_text(encoding="utf-8")
    )
    return LessonResponse(source="example", result=lesson)
