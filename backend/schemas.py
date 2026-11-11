from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


def bounded_text(maximum: int):
    return StringConstraints(strip_whitespace=True, min_length=1, max_length=maximum)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GenerateRequest(StrictModel):
    question: Annotated[str, bounded_text(2000)]


class Lesson(StrictModel):
    kind: Literal["lesson"]
    title: Annotated[str, bounded_text(100)]
    summary: Annotated[str, bounded_text(500)]
    html: Annotated[str, bounded_text(24000)]
    css: str = Field(max_length=16000)
    javascript: Annotated[str, bounded_text(32000)]


class ReviseRequest(GenerateRequest):
    instruction: Annotated[str, bounded_text(2000)]
    lesson: Lesson


class Clarification(StrictModel):
    kind: Literal["clarification"]
    message: Annotated[str, bounded_text(500)]


class OutOfScope(StrictModel):
    kind: Literal["out_of_scope"]
    message: Annotated[str, bounded_text(500)]


ModelResult = Annotated[Lesson | Clarification | OutOfScope, Field(discriminator="kind")]


class LessonResponse(StrictModel):
    source: Literal["live", "example"]
    result: ModelResult
