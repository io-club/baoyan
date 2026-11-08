from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from croniter import croniter
from pydantic import BaseModel, Field, field_validator, field_serializer, model_validator


class TaskKind(str, Enum):
    ONESHOT = "oneshot"
    SCHEDULED = "scheduled"
    SERVICE = "service"


class TaskStatus(str, Enum):
    QUEUED = "queued"
    SCHEDULED = "scheduled"
    STARTING = "starting"
    RUNNING = "running"
    CANCELING = "canceling"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"
    STOPPED = "stopped"


class CreateTask(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=4000)
    kind: TaskKind
    command: list[str] = Field(min_length=1, max_length=128)
    schedule_cron: str | None = None
    timezone: str | None = None
    timeout_seconds: int = Field(default=3600, ge=1, le=7 * 24 * 3600)
    restart_policy: Literal["none", "always", "on-failure"] = "none"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("command")
    @classmethod
    def validate_command(cls, value: list[str]) -> list[str]:
        if any(not part for part in value):
            raise ValueError("command entries cannot be empty")
        return value

    @field_validator("schedule_cron")
    @classmethod
    def validate_cron(cls, value: str | None) -> str | None:
        if value is not None and not croniter.is_valid(value):
            raise ValueError("schedule_cron must be a valid five-field cron expression")
        if value is not None and len(value.split()) != 5:
            raise ValueError("schedule_cron must contain exactly five fields")
        return value

    @field_validator('timezone')
    @classmethod
    def validate_timezone(cls, value):
        if value:
            from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
            try: ZoneInfo(value)
            except (ZoneInfoNotFoundError,ValueError) as exc: raise ValueError('timezone must be a valid IANA timezone') from exc
        return value

    @model_validator(mode="after")
    def validate_kind_options(self) -> "CreateTask":
        if self.kind is TaskKind.SCHEDULED and not self.schedule_cron:
            raise ValueError("scheduled tasks require schedule_cron")
        if self.kind is not TaskKind.SCHEDULED and self.schedule_cron:
            raise ValueError("schedule_cron is only valid for scheduled tasks")
        return self


class ProgressUpdate(BaseModel):
    progress: int = Field(ge=0, le=100)
    message: str = Field(default="", max_length=4000)
    result: dict[str, Any] | None = None


class TaskResponse(BaseModel):
    id: str
    name: str
    description: str
    kind: TaskKind
    status: TaskStatus
    command: list[str]
    schedule_cron: str | None
    timezone: str
    timeout_seconds: int
    restart_policy: str
    progress: int
    status_message: str
    result: dict[str, Any] | None
    error: str | None
    metadata: dict[str, Any]
    next_run_at: str | None
    started_at: str | None
    finished_at: str | None
    created_at: str
    updated_at: str

    @field_serializer('metadata')
    def redact_metadata(self,value):
        def mask(item):
            if isinstance(item,dict):
                return {key:('***' if any(word in key.lower() for word in ('cookie','password','token','secret','api_key','api-key','authorization')) else mask(val)) for key,val in item.items()}
            if isinstance(item,list):return [mask(val) for val in item]
            return item
        return mask(value)


class TaskList(BaseModel):
    items: list[TaskResponse]
    total: int
    limit: int
    offset: int


class RunResponse(BaseModel):
    id: str
    task_id: str
    attempt: int
    status: str
    exit_code: int | None
    log_path: str
    error: str | None
    started_at: str | None
    finished_at: str | None

