from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from croniter import croniter
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from .config import settings
from .models import CreateTask, TaskKind, TaskStatus


SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS task_center;

CREATE TABLE IF NOT EXISTS task_center.tasks (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL,
    status TEXT NOT NULL,
    command JSONB NOT NULL,
    schedule_cron TEXT,
    timezone TEXT NOT NULL,
    timeout_seconds INTEGER NOT NULL,
    restart_policy TEXT NOT NULL DEFAULT 'none',
    progress INTEGER NOT NULL DEFAULT 0,
    status_message TEXT NOT NULL DEFAULT '',
    result JSONB,
    error TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    next_run_at TIMESTAMPTZ,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    cancel_requested BOOLEAN NOT NULL DEFAULT FALSE,
    lease_owner TEXT,
    lease_expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS tasks_status_idx
    ON task_center.tasks (status);
CREATE INDEX IF NOT EXISTS tasks_due_idx
    ON task_center.tasks (next_run_at)
    WHERE kind = 'scheduled';

ALTER TABLE task_center.tasks
    ADD COLUMN IF NOT EXISTS lease_owner TEXT;
ALTER TABLE task_center.tasks
    ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS task_center.task_runs (
    id UUID PRIMARY KEY,
    task_id UUID NOT NULL REFERENCES task_center.tasks(id) ON DELETE CASCADE,
    attempt INTEGER NOT NULL,
    status TEXT NOT NULL,
    pid INTEGER,
    exit_code INTEGER,
    log_path TEXT NOT NULL DEFAULT '',
    error TEXT,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS task_runs_task_idx
    ON task_center.task_runs (task_id, attempt DESC);
"""


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def next_cron_time(expression: str, timezone_name: str, base: datetime | None = None) -> datetime:
    zone = ZoneInfo(timezone_name)
    base_value = (base or utcnow()).astimezone(zone)
    next_value = croniter(expression, base_value).get_next(datetime)
    if next_value.tzinfo is None:
        next_value = next_value.replace(tzinfo=zone)
    return next_value.astimezone(timezone.utc)


def serialize_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    value = dict(row)
    for key, item in value.items():
        if isinstance(item, datetime):
            value[key] = item.isoformat()
        elif isinstance(item, UUID):
            value[key] = str(item)
    return value


class TaskRepository:
    def __init__(self, database_url: str | None = None) -> None:
        self.pool = ConnectionPool(
            conninfo=database_url or settings.database_url,
            min_size=1,
            max_size=8,
            open=False,
            kwargs={"row_factory": dict_row},
        )
        self._opened = False

    def close(self) -> None:
        self.pool.close()

    @contextmanager
    def connection(self) -> Iterator[Any]:
        if not self._opened:
            self.pool.open(wait=True, timeout=30)
            self._opened = True
        with self.pool.connection() as connection:
            yield connection

    def init_schema(self) -> None:
        with self.connection() as connection:
            connection.execute(SCHEMA_SQL)

    def create(self, spec: CreateTask) -> dict[str, Any]:
        task_id = uuid4()
        now = utcnow()
        effective_timezone = spec.timezone or settings.default_timezone
        if spec.kind is TaskKind.SCHEDULED:
            status = TaskStatus.SCHEDULED.value
            next_run_at = next_cron_time(spec.schedule_cron or "", effective_timezone)
        elif spec.kind is TaskKind.SERVICE:
            status = TaskStatus.STARTING.value
            next_run_at = None
        else:
            status = TaskStatus.QUEUED.value
            next_run_at = None
        with self.pool.connection() as connection:
            row = connection.execute(
                """
                INSERT INTO task_center.tasks (
                    id, name, description, kind, status, command, schedule_cron,
                    timezone, timeout_seconds, restart_policy, metadata,
                    next_run_at, created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                ) RETURNING *
                """,
                (
                    task_id,
                    spec.name,
                    spec.description,
                    spec.kind.value,
                    status,
                    Jsonb(spec.command),
                    spec.schedule_cron,
                    effective_timezone,
                    spec.timeout_seconds,
                    spec.restart_policy,
                    Jsonb(spec.metadata),
                    next_run_at,
                    now,
                    now,
                ),
            ).fetchone()
        return serialize_row(row) or {}

    def get(self, task_id: UUID | str) -> dict[str, Any] | None:
        with self.pool.connection() as connection:
            row = connection.execute(
                "SELECT * FROM task_center.tasks WHERE id = %s", (task_id,)
            ).fetchone()
        return serialize_row(row)

    def list(
        self,
        limit: int,
        offset: int,
        status: str | None = None,
        kind: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        conditions: list[str] = []
        params: list[Any] = []
        if status:
            conditions.append("status = %s")
            params.append(status)
        if kind:
            conditions.append("kind = %s")
            params.append(kind)
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        with self.pool.connection() as connection:
            total = connection.execute(
                f"SELECT COUNT(*) AS count FROM task_center.tasks {where_clause}",
                params,
            ).fetchone()["count"]
            rows = connection.execute(
                f"""
                SELECT * FROM task_center.tasks
                {where_clause}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """,
                [*params, limit, offset],
            ).fetchall()
        return [serialize_row(row) or {} for row in rows], total

    def claim_for_run(
        self, task_id: UUID | str, lease_owner: UUID | str, lease_seconds: int = 60
    ) -> dict[str, Any] | None:
        now = utcnow()
        with self.pool.connection() as connection:
            row = connection.execute(
                """
                UPDATE task_center.tasks
                SET status = 'running', progress = 0, status_message = 'running',
                    error = NULL, cancel_requested = FALSE,
                    lease_owner = %s,
                    lease_expires_at = %s,
                    started_at = %s, finished_at = NULL, updated_at = %s
                WHERE id = %s AND (
                    status = 'queued'
                    OR (status = 'running' AND lease_expires_at < %s)
                )
                RETURNING *
                """,
                (
                    str(lease_owner),
                    now + timedelta(seconds=lease_seconds),
                    now,
                    now,
                    task_id,
                    now,
                ),
            ).fetchone()
            if row:
                attempt = connection.execute(
                    """
                    SELECT COALESCE(MAX(attempt), 0) + 1 AS attempt
                    FROM task_center.task_runs WHERE task_id = %s
                    """,
                    (task_id,),
                ).fetchone()["attempt"]
                run_id = uuid4()
                connection.execute(
                    """
                    INSERT INTO task_center.task_runs (
                        id, task_id, attempt, status, started_at
                    ) VALUES (%s, %s, %s, 'running', %s)
                    """,
                    (run_id, task_id, attempt, now),
                )
        return serialize_row(row)

    def renew_lease(self, task_id: UUID | str, lease_owner: UUID | str) -> None:
        now = utcnow()
        with self.pool.connection() as connection:
            connection.execute(
                """
                UPDATE task_center.tasks
                SET lease_expires_at = %s, updated_at = %s
                WHERE id = %s AND lease_owner = %s AND status = 'running'
                """,
                (
                    now + timedelta(seconds=60),
                    now,
                    task_id,
                    str(lease_owner),
                ),
            )

    def update_progress(
        self, task_id: UUID | str, progress: int, message: str, result: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        with self.pool.connection() as connection:
            row = connection.execute(
                """
                UPDATE task_center.tasks
                SET progress = %s, status_message = %s,
                    result = CASE WHEN %s::jsonb IS NULL THEN result ELSE %s::jsonb END,
                    updated_at = %s
                WHERE id = %s AND status IN ('running', 'starting')
                RETURNING *
                """,
                (
                    progress,
                    message,
                    Jsonb(result) if result is not None else None,
                    Jsonb(result) if result is not None else None,
                    utcnow(),
                    task_id,
                ),
            ).fetchone()
        return serialize_row(row)

    def request_cancel(self, task_id: UUID | str) -> dict[str, Any] | None:
        now = utcnow()
        with self.pool.connection() as connection:
            row = connection.execute(
                """
                UPDATE task_center.tasks
                SET cancel_requested = TRUE,
                    status = CASE
                        WHEN status IN ('queued', 'scheduled') THEN 'canceled'
                        WHEN status IN ('running', 'starting') THEN 'canceling'
                        ELSE status
                    END,
                    finished_at = CASE
                        WHEN status IN ('queued', 'scheduled') THEN %s
                        ELSE finished_at
                    END,
                    updated_at = %s
                WHERE id = %s
                RETURNING *
                """,
                (now, now, task_id),
            ).fetchone()
        return serialize_row(row)

    def finish(
        self,
        task_id: UUID | str,
        status: TaskStatus,
        exit_code: int | None,
        error: str | None,
        log_path: str,
    ) -> None:
        now = utcnow()
        with self.pool.connection() as connection:
            task = connection.execute(
                "SELECT kind, cancel_requested FROM task_center.tasks WHERE id = %s",
                (task_id,),
            ).fetchone()
            if task is None:
                return
            final_status = status.value
            run_status = status.value
            if task["cancel_requested"]:
                final_status = TaskStatus.CANCELED.value
                run_status = TaskStatus.CANCELED.value
            elif task["kind"] == TaskKind.SCHEDULED.value:
                final_status = TaskStatus.SCHEDULED.value
            connection.execute(
                """
                UPDATE task_center.tasks
                SET status = %s, progress = CASE WHEN %s = 'succeeded' THEN 100 ELSE progress END,
                    status_message = %s, error = %s,
                    finished_at = %s, lease_owner = NULL, lease_expires_at = NULL,
                    updated_at = %s
                WHERE id = %s
                """,
                (final_status, final_status, final_status, error, now, now, task_id),
            )
            connection.execute(
                """
                UPDATE task_center.task_runs
                SET status = %s, exit_code = %s, error = %s,
                    log_path = %s, finished_at = %s
                WHERE id = (
                    SELECT id FROM task_center.task_runs
                    WHERE task_id = %s ORDER BY attempt DESC LIMIT 1
                )
                """,
                (run_status, exit_code, error, log_path, now, task_id),
            )

    def claim_due_schedules(self, limit: int = 20) -> list[dict[str, Any]]:
        claimed: list[dict[str, Any]] = []
        with self.pool.connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM task_center.tasks
                WHERE kind = 'scheduled'
                  AND status = 'scheduled'
                  AND next_run_at IS NOT NULL
                  AND next_run_at <= %s
                ORDER BY next_run_at
                FOR UPDATE SKIP LOCKED
                LIMIT %s
                """,
                (utcnow(), limit),
            ).fetchall()
            for row in rows:
                following = next_cron_time(
                    row["schedule_cron"], row["timezone"], utcnow()
                )
                changed = connection.execute(
                    """
                    UPDATE task_center.tasks
                    SET status = 'queued', next_run_at = %s, updated_at = %s
                    WHERE id = %s
                    RETURNING *
                    """,
                    (following, utcnow(), row["id"]),
                ).fetchone()
                claimed.append(serialize_row(changed) or {})
        return claimed

    def list_services(self) -> list[dict[str, Any]]:
        with self.pool.connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM task_center.tasks
                WHERE kind = 'service'
                  AND status IN ('starting', 'running', 'canceling')
                ORDER BY created_at
                """
            ).fetchall()
        return [serialize_row(row) or {} for row in rows]

    def service_running(self, task_id: UUID | str, pid: int) -> None:
        now = utcnow()
        with self.pool.connection() as connection:
            attempt = connection.execute(
                """
                SELECT COALESCE(MAX(attempt), 0) + 1 AS attempt
                FROM task_center.task_runs WHERE task_id = %s
                """,
                (task_id,),
            ).fetchone()["attempt"]
            connection.execute(
                """
                INSERT INTO task_center.task_runs (
                    id, task_id, attempt, status, pid, started_at
                ) VALUES (%s, %s, %s, 'running', %s, %s)
                """,
                (uuid4(), task_id, attempt, pid, now),
            )
            connection.execute(
                """
                UPDATE task_center.tasks
                SET status = 'running', progress = 0, status_message = 'service started',
                    started_at = %s, finished_at = NULL, updated_at = %s
                WHERE id = %s
                """,
                (now, now, task_id),
            )

    def service_stopped(self, task_id: UUID | str, exit_code: int) -> None:
        now = utcnow()
        with self.pool.connection() as connection:
            task = connection.execute(
                "SELECT cancel_requested FROM task_center.tasks WHERE id = %s",
                (task_id,),
            ).fetchone()
            final_status = "canceled" if task and task["cancel_requested"] else ("stopped" if exit_code == 0 else "failed")
            connection.execute(
                """
                UPDATE task_center.tasks
                SET status = %s, status_message = %s, finished_at = %s, updated_at = %s
                WHERE id = %s
                """,
                (final_status, f"service exited with code {exit_code}", now, now, task_id),
            )
            connection.execute(
                """
                UPDATE task_center.task_runs
                SET status = %s, exit_code = %s, finished_at = %s
                WHERE id = (
                    SELECT id FROM task_center.task_runs
                    WHERE task_id = %s ORDER BY attempt DESC LIMIT 1
                )
                """,
                (final_status, exit_code, now, task_id),
            )

    def delete(self, task_id: UUID | str) -> bool:
        terminal = ("succeeded", "failed", "canceled", "stopped")
        with self.pool.connection() as connection:
            result = connection.execute(
                """
                DELETE FROM task_center.tasks
                WHERE id = %s AND status = ANY(%s)
                """,
                (task_id, list(terminal)),
            )
            return result.rowcount == 1

    def runs(self, task_id: UUID | str, limit: int = 50) -> list[dict[str, Any]]:
        with self.pool.connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM task_center.task_runs
                WHERE task_id = %s ORDER BY attempt DESC LIMIT %s
                """,
                (task_id, limit),
            ).fetchall()
        return [serialize_row(row) or {} for row in rows]


repository = TaskRepository()

