from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app import main


def sample_task() -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": str(uuid4()),
        "name": "test",
        "description": "",
        "kind": "oneshot",
        "status": "queued",
        "command": ["echo", "hello"],
        "schedule_cron": None,
        "timezone": "Asia/Taipei",
        "timeout_seconds": 30,
        "restart_policy": "none",
        "progress": 0,
        "status_message": "",
        "result": None,
        "error": None,
        "metadata": {},
        "next_run_at": None,
        "started_at": None,
        "finished_at": None,
        "created_at": now,
        "updated_at": now,
    }


def test_tasks_require_admin_password(monkeypatch) -> None:
    monkeypatch.setattr(main, "current_admin_password", lambda: "password")
    monkeypatch.setattr(
        main,
        "repository",
        SimpleNamespace(init_schema=lambda: None),
    )
    client = TestClient(main.app)
    response = client.get("/v1/tasks", headers={"X-Admin-Password": "wrong"})
    assert response.status_code == 401


def test_create_task_enqueues(monkeypatch) -> None:
    monkeypatch.setattr(main, "current_admin_password", lambda: "password")
    task = sample_task()
    sent: list[str] = []
    monkeypatch.setattr(
        main,
        "repository",
        SimpleNamespace(init_schema=lambda: None, create=lambda _spec: task),
    )
    monkeypatch.setattr(main, "enqueue_task", sent.append)
    client = TestClient(main.app)
    response = client.post(
        "/v1/tasks",
        headers={"X-Admin-Password": "password"},
        json={"name": "test", "kind": "oneshot", "command": ["echo", "hello"]},
    )
    assert response.status_code == 201
    assert sent == [task["id"]]

