from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from .config import TaskType


class TaskRequest(BaseModel):
    task_type: TaskType
    instructions: str = Field(min_length=1, max_length=8000)
    input_paths: list[str] = Field(default_factory=list, max_length=200)
    profile: str
    output_schema: str
    max_steps: int = Field(8, ge=1, le=12)

    @field_validator("input_paths")
    @classmethod
    def no_empty_paths(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("input_paths cannot contain empty paths")
        return values


class SemanticRecord(BaseModel):
    record_id: str = Field(default_factory=lambda: str(uuid4()))
    source_path: str
    category: str
    summary: str
    confidence: float = Field(ge=0, le=1)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    needs_review: bool = False
    worker_profile: str
    model: str
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class QueryFilters(BaseModel):
    job_id: str | None = None
    low_confidence: bool | None = None
    label: str | None = None
    path_contains: str | None = None
    function_address: str | None = None
    needs_review: bool | None = None
    conflict: bool | None = None
    limit: int = Field(20, ge=1, le=100)


class TrustedFullTaskRequest(BaseModel):
    instructions: str = Field(min_length=1, max_length=16000)
    working_directory: str = Field(default=".", min_length=1, max_length=1024)
    toolsets: list[str] = Field(default_factory=list, max_length=32)
    allow_network: bool = False
    include_optional_tools: bool = False
    max_steps: int = Field(20, ge=1, le=50)
    timeout_seconds: int = Field(600, ge=5, le=3600)
    authorization: Literal["explicit_user_authorized"]

    @field_validator("toolsets")
    @classmethod
    def no_empty_toolsets(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("toolsets cannot contain empty names")
        return list(dict.fromkeys(value.strip() for value in values))
