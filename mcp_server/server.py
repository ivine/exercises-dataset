import json
import logging
import os
from pathlib import Path
from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse

Language = Literal["en", "es", "it", "tr", "ru", "zh", "hi", "pl", "ko", "fr"]
LANGUAGES = ("en", "es", "it", "tr", "ru", "zh", "hi", "pl", "ko", "fr")
DATA_PATH = Path(os.getenv("DATA_PATH", Path(__file__).resolve().parent.parent / "data/exercises.json"))
MEDIA_BASE_URL = os.getenv("MEDIA_BASE_URL", "http://localhost:8080").rstrip("/")
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)


def load_exercises() -> list[dict]:
    with DATA_PATH.open(encoding="utf-8") as data_file:
        exercises = json.load(data_file)
    if not isinstance(exercises, list):
        raise ValueError(f"{DATA_PATH} must contain a JSON array")

    required = {
        "id", "name", "body_part", "equipment", "target", "instructions",
        "instruction_steps", "image", "gif_url", "attribution",
    }
    by_id = {}
    for exercise in exercises:
        if not isinstance(exercise, dict) or not required.issubset(exercise):
            raise ValueError("An exercise record is missing required fields")
        exercise_id = exercise["id"]
        if exercise_id in by_id:
            raise ValueError(f"Duplicate exercise ID: {exercise_id}")
        by_id[exercise_id] = exercise
    return exercises


EXERCISES = load_exercises()
BY_ID = {exercise["id"]: exercise for exercise in EXERCISES}

mcp = MCPServer(
    "exercises-dataset",
    instructions=(
        "Read-only access to 1,324 fitness exercises. Use list_exercise_filters to discover "
        "valid filter values, search_exercises to find exercises, and get_exercise for full "
        "multilingual instructions. Media is copyright Gym visual; preserve attribution."
    ),
)


def media_url(path: str) -> str:
    return f"{MEDIA_BASE_URL}/{path}" if MEDIA_BASE_URL else path


def summary(exercise: dict) -> dict:
    return {
        "id": exercise["id"],
        "name": exercise["name"],
        "body_part": exercise["body_part"],
        "equipment": exercise["equipment"],
        "target": exercise["target"],
        "secondary_muscles": exercise["secondary_muscles"],
        "image": media_url(exercise["image"]),
        "gif_url": media_url(exercise["gif_url"]),
        "attribution": exercise["attribution"],
    }


@mcp.tool(annotations=READ_ONLY)
def search_exercises(
    query: Annotated[str, Field(description="Optional case-insensitive text search; empty matches all exercises")] = "",
    body_part: Annotated[str | None, Field(description="Exact body part, such as chest or upper legs")] = None,
    equipment: Annotated[str | None, Field(description="Exact equipment, such as dumbbell or body weight")] = None,
    target: Annotated[str | None, Field(description="Exact target muscle, such as abs or biceps")] = None,
    language: Language = "en",
    limit: Annotated[int, Field(ge=1, le=50)] = 10,
    offset: Annotated[int, Field(ge=0)] = 0,
) -> dict:
    """Search exercises with optional filters and compact, paginated results."""
    needle = query.strip().casefold()
    expected = {
        key: value.casefold().strip()
        for key, value in (("body_part", body_part), ("equipment", equipment), ("target", target))
        if value is not None
    }

    matches = []
    for exercise in EXERCISES:
        if any(exercise[key].casefold() != value for key, value in expected.items()):
            continue
        if needle:
            searchable = " ".join([
                exercise["id"], exercise["name"], exercise["body_part"], exercise["equipment"],
                exercise["target"], exercise["instructions"][language],
                *exercise["secondary_muscles"],
            ]).casefold()
            if needle not in searchable:
                continue
        matches.append(exercise)

    page = matches[offset:offset + limit]
    next_offset = offset + len(page)
    return {
        "total": len(matches),
        "offset": offset,
        "limit": limit,
        "next_offset": next_offset if next_offset < len(matches) else None,
        "exercises": [summary(exercise) for exercise in page],
    }


@mcp.tool(annotations=READ_ONLY)
def get_exercise(
    exercise_id: Annotated[str, Field(pattern=r"^[0-9]{4}$", description="Four-digit exercise ID")],
    language: Language = "en",
) -> dict:
    """Get one exercise's metadata, media, and instructions in the requested language."""
    exercise = BY_ID.get(exercise_id)
    if exercise is None:
        raise ValueError(f"Exercise ID {exercise_id} was not found")
    return {
        key: value for key, value in exercise.items()
        if key not in {"instructions", "instruction_steps", "image", "gif_url"}
    } | {
        "language": language,
        "instructions": exercise["instructions"][language],
        "instruction_steps": exercise["instruction_steps"][language],
        "image": media_url(exercise["image"]),
        "gif_url": media_url(exercise["gif_url"]),
    }


@mcp.tool(annotations=READ_ONLY)
def list_exercise_filters() -> dict:
    """List valid exercise filter values and supported instruction languages."""
    return {
        "exercise_count": len(EXERCISES),
        "body_parts": sorted({exercise["body_part"] for exercise in EXERCISES}),
        "equipment": sorted({exercise["equipment"] for exercise in EXERCISES}),
        "targets": sorted({exercise["target"] for exercise in EXERCISES}),
        "languages": list(LANGUAGES),
    }


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "exercise_count": len(EXERCISES)})


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000, stateless_http=True)
