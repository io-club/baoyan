from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.repository import TaskRepository


def test_expired_lease_can_be_reclaimed() -> None:
    task_id = uuid4()
    now = datetime.now(timezone.utc)
    row = {
        "id": task_id,
        "status": "running",
        "lease_owner": "old-worker",
        "lease_expires_at": now - timedelta(seconds=1),
    }

    class Connection:
        def execute(self, sql: str, _params: object) -> SimpleNamespace:
            result = {"attempt": 1} if "COALESCE(MAX(attempt)" in sql else row
            return SimpleNamespace(fetchone=lambda: result)

    class Pool:
        def connection(self) -> object:
            class Manager:
                def __enter__(self) -> Connection:
                    return Connection()

                def __exit__(self, *_args: object) -> None:
                    return None

            return Manager()

    repository = TaskRepository.__new__(TaskRepository)
    repository.pool = Pool()
    repository._opened = True
    claimed = repository.claim_for_run(task_id, uuid4())
    assert claimed is not None
    assert claimed["id"] == str(task_id)
