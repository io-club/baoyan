from __future__ import annotations

import os
from pathlib import Path
import signal
import subprocess
import time

from .config import settings
from .repository import repository
from .runner import _safe_cwd, _task_environment


processes: dict[str, subprocess.Popen[bytes]] = {}
running = True


def stop(_signum: int, _frame: object) -> None:
    global running
    running = False


def terminate(task_id: str) -> int:
    process = processes.pop(task_id, None)
    if process is None:
        return -1
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            return process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            return process.wait()
    return process.returncode


def start(task: dict) -> None:
    task_id = task["id"]
    Path(settings.log_dir).mkdir(parents=True, exist_ok=True)
    log_path = Path(settings.log_dir) / f"{task_id}-service.log"
    log_file = log_path.open("ab", buffering=0)
    process = subprocess.Popen(
        task["command"],
        cwd=_safe_cwd(task),
        env=_task_environment(task),
        stdin=subprocess.DEVNULL,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    log_file.close()
    processes[task_id] = process
    repository.service_running(task_id, process.pid)


def main() -> None:
    repository.init_schema()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while running:
        try:
            tasks = repository.list_services()
            active_ids = {task["id"] for task in tasks}
            for task_id in list(processes):
                if task_id not in active_ids:
                    terminate(task_id)

            for task in tasks:
                task_id = task["id"]
                process = processes.get(task_id)
                if task["status"] == "canceling":
                    terminate(task_id)
                    repository.service_stopped(task_id, -15)
                    continue
                if process is not None and process.poll() is None:
                    continue
                if process is not None:
                    exit_code = process.wait()
                    processes.pop(task_id, None)
                    # Close the previous run even when the service will restart.
                    # Task state and per-attempt state must not be conflated.
                    repository.service_stopped(task_id, exit_code)
                    current = repository.get(task_id)
                    if current and current.get('cancel_requested'):
                        continue
                    if task["restart_policy"] == "always":
                        start(task)
                        continue
                    if task["restart_policy"] == "on-failure" and exit_code != 0:
                        start(task)
                        continue
                    continue
                start(task)
        except Exception:
            import logging

            logging.exception("service supervisor iteration failed")
        time.sleep(settings.poll_seconds)

    for task_id in list(processes):
        terminate(task_id)


if __name__ == "__main__":
    main()

