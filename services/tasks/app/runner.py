from __future__ import annotations

import os
from pathlib import Path
import signal
import subprocess
import time
from uuid import UUID, uuid4

from .config import settings, current_admin_password
from .models import TaskStatus
from .repository import repository


def _safe_cwd(task: dict) -> str:
    work_root = Path(settings.work_dir).resolve()
    requested = task.get("metadata", {}).get("cwd") or str(work_root)
    candidate = Path(requested).resolve()
    if candidate != work_root and work_root not in candidate.parents:
        raise ValueError("task cwd must stay inside the shared workspace")
    candidate.mkdir(parents=True, exist_ok=True)
    return str(candidate)


def _task_environment(task: dict) -> dict[str, str]:
    environment = dict(os.environ)
    environment['PLATFORM_ADMIN_PASSWORD'] = current_admin_password()
    environment['TASK_ADMIN_PASSWORD'] = current_admin_password()
    environment['TASK_ID'] = str(task.get('id',''))
    supplied = task.get("metadata", {}).get("environment", {})
    if supplied:
        if not isinstance(supplied, dict):
            raise ValueError("metadata.environment must be an object")
        environment.update({str(key): str(value) for key, value in supplied.items()})
    return environment


def run_task(task_id: UUID) -> None:
    lease_owner = uuid4()
    repository.init_schema()
    task = repository.claim_for_run(task_id, lease_owner)
    if task is None:
        return

    Path(settings.log_dir).mkdir(parents=True, exist_ok=True)
    log_path = str(Path(settings.log_dir) / f"{task_id}.log")
    exit_code: int | None = None
    error: str | None = None
    status = TaskStatus.FAILED

    try:
        command = task["command"]
        if not isinstance(command, list) or not command:
            raise ValueError("task command is empty")
        with Path(log_path).open("ab", buffering=0) as log_file:
            process = subprocess.Popen(
                command,
                cwd=_safe_cwd(task),
                env=_task_environment(task),
                stdin=subprocess.DEVNULL,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            deadline = time.monotonic() + task["timeout_seconds"]
            canceled = False
            while process.poll() is None:
                current = repository.get(task_id)
                if current is None:
                    error = "task disappeared while running"
                    os.killpg(process.pid, signal.SIGTERM)
                    break
                if current.get("status") == TaskStatus.CANCELING.value:
                    canceled = True
                    os.killpg(process.pid, signal.SIGTERM)
                    break
                repository.renew_lease(task_id, lease_owner)
                if time.monotonic() >= deadline:
                    error = "task timed out"
                    os.killpg(process.pid, signal.SIGTERM)
                    break
                time.sleep(1)
            try:
                exit_code = process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                exit_code = process.wait()
        if canceled:
            status = TaskStatus.CANCELED
        elif exit_code == 0:
            status = TaskStatus.SUCCEEDED
        elif error is None:
            error = f"command exited with code {exit_code}"
    except Exception as exc:  # noqa: BLE001 - persisted as task failure
        error = str(exc)

    repository.finish(task_id, status, exit_code, error, log_path)

