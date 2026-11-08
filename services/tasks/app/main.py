from __future__ import annotations

from contextlib import asynccontextmanager
import hmac
import os
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response, status

from .actors import enqueue_task
from .config import settings, current_admin_password
from .models import (
    CreateTask,
    ProgressUpdate,
    RunResponse,
    TaskKind,
    TaskList,
    TaskResponse,
    TaskStatus,
)
from .repository import repository


@asynccontextmanager
async def lifespan(_app: FastAPI):
    repository.init_schema()
    yield


app = FastAPI(
    title="Baoyan Task Center",
    version="1.0.0",
    description="Durable one-shot, scheduled, and long-running user-space tasks.",
    lifespan=lifespan,
)


def require_admin(x_admin_password: Annotated[str | None, Header()] = None, x_agent_key: Annotated[str | None, Header()] = None) -> None:
    agent_key=os.getenv('BAOYAN_AGENT_API_KEY','')
    if agent_key and x_agent_key and hmac.compare_digest(x_agent_key,agent_key):
        return
    if x_admin_password is None or not hmac.compare_digest(
        x_admin_password, current_admin_password()
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid password")


def task_or_404(task_id: UUID) -> dict:
    task = repository.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return task


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "tasks"}


@app.post(
    "/v1/tasks",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_task(spec: CreateTask) -> dict:
    task = repository.create(spec)
    if spec.kind is TaskKind.ONESHOT:
        try:
            enqueue_task(task["id"])
        except Exception as exc:
            repository.finish(
                task["id"], TaskStatus.FAILED, None, f"queue unavailable: {exc}", ""
            )
            raise HTTPException(status_code=503, detail="task queue unavailable") from exc
    return task


@app.get(
    "/v1/tasks",
    response_model=TaskList,
    dependencies=[Depends(require_admin)],
)
def list_tasks(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    status_filter: Annotated[TaskStatus | None, Query(alias="status")] = None,
    kind: Annotated[TaskKind | None, Query()] = None,
) -> dict:
    items, total = repository.list(
        limit,
        offset,
        status_filter.value if status_filter else None,
        kind.value if kind else None,
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@app.get(
    "/v1/tasks/{task_id}",
    response_model=TaskResponse,
    dependencies=[Depends(require_admin)],
)
def get_task(task_id: UUID) -> dict:
    return task_or_404(task_id)


@app.get(
    "/v1/tasks/{task_id}/runs",
    response_model=list[RunResponse],
    dependencies=[Depends(require_admin)],
)
def list_runs(task_id: UUID) -> list[dict]:
    task_or_404(task_id)
    return repository.runs(task_id)


@app.get(
    "/v1/tasks/{task_id}/logs",
    dependencies=[Depends(require_admin)],
)
def get_log(task_id: UUID, tail: Annotated[int, Query(ge=1, le=5000)] = 200) -> Response:
    task = task_or_404(task_id)
    runs = repository.runs(task_id, limit=1)
    log_path = runs[0]["log_path"] if runs else ""
    candidates = [
        log_path,
        str(settings.log_dir) + f"/{task_id}.log",
        str(settings.log_dir) + f"/{task_id}-service.log",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            with open(candidate, "rb") as handle:
                lines = handle.readlines()[-tail:]
            return Response(b"".join(lines), media_type="text/plain")
        except FileNotFoundError:
            continue
    return Response("", media_type="text/plain")


@app.patch(
    "/v1/tasks/{task_id}/progress",
    response_model=TaskResponse,
    dependencies=[Depends(require_admin)],
)
def update_progress(task_id: UUID, update: ProgressUpdate) -> dict:
    task_or_404(task_id)
    changed = repository.update_progress(
        task_id, update.progress, update.message, update.result
    )
    if changed is None:
        raise HTTPException(status_code=409, detail="task is not running")
    return changed


@app.post(
    "/v1/tasks/{task_id}/cancel",
    response_model=TaskResponse,
    dependencies=[Depends(require_admin)],
)
def cancel_task(task_id: UUID) -> dict:
    task_or_404(task_id)
    changed = repository.request_cancel(task_id)
    return changed or task_or_404(task_id)


@app.delete(
    "/v1/tasks/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
def delete_task(task_id: UUID) -> Response:
    task_or_404(task_id)
    if not repository.delete(task_id):
        raise HTTPException(status_code=409, detail="only finished tasks can be deleted")
    return Response(status_code=status.HTTP_204_NO_CONTENT)

