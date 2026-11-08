from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models import CreateTask, TaskKind
from app.repository import next_cron_time


def test_scheduled_task_requires_cron() -> None:
    with pytest.raises(ValidationError):
        CreateTask(
            name="scheduled without cron",
            kind=TaskKind.SCHEDULED,
            command=["true"],
        )


def test_oneshot_rejects_cron_and_empty_command_parts() -> None:
    with pytest.raises(ValidationError):
        CreateTask(
            name="bad one shot",
            kind=TaskKind.ONESHOT,
            command=["echo", ""],
            schedule_cron="0 * * * *",
        )


def test_cron_next_time_is_timezone_aware() -> None:
    value = next_cron_time(
        "*/5 * * * *",
        "Asia/Taipei",
        datetime(2026, 1, 1, 0, 1, tzinfo=timezone.utc),
    )
    assert value.tzinfo is not None
    assert value.minute == 5

