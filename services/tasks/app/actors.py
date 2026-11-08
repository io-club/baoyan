from __future__ import annotations

from uuid import UUID

import dramatiq
from dramatiq.brokers.rabbitmq import RabbitmqBroker

from .config import settings
from .repository import repository
from .runner import run_task


broker = RabbitmqBroker(url=settings.rabbitmq_url)
dramatiq.set_broker(broker)


@dramatiq.actor(
    queue_name="baoyan-offline",
    max_retries=100,
    min_backoff=5_000,
    max_backoff=60_000,
    # run_task enforces each task's own deadline (up to seven days).
    # Dramatiq's default ten-minute limit would orphan long crawler subprocesses.
    time_limit=(7 * 24 * 3600 + 60) * 1000,
)
def execute_task(task_id: str) -> None:
    run_task(UUID(task_id))
    current = repository.get(task_id)
    if current and current["status"] == "running":
        raise dramatiq.Retry(message="task is still leased by another worker", delay=10_000)


def enqueue_task(task_id: str) -> None:
    execute_task.send(task_id)

