from __future__ import annotations

import logging
import signal
import time

from .actors import enqueue_task
from .config import settings
from .repository import repository


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("task-scheduler")
running = True


def stop(_signum: int, _frame: object) -> None:
    global running
    running = False


def main() -> None:
    repository.init_schema()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    logger.info("scheduler started, poll interval=%ss", settings.poll_seconds)
    while running:
        try:
            for task in repository.claim_due_schedules():
                enqueue_task(task["id"])
                logger.info("scheduled task enqueued: %s", task["id"])
        except Exception:
            logger.exception("scheduler iteration failed")
        time.sleep(settings.poll_seconds)


if __name__ == "__main__":
    main()

