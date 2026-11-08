from __future__ import annotations

import os
import time

import httpx


base_url = os.getenv("TASK_API_URL", "http://task-api:8080")
headers = {"X-Admin-Password": os.getenv("TASK_ADMIN_PASSWORD", "password")}
client = httpx.Client(base_url=base_url, headers=headers, timeout=15)


def wait_for(task_id: str, wanted: set[str], timeout: float = 40) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/v1/tasks/{task_id}")
        response.raise_for_status()
        task = response.json()
        if task["status"] in wanted:
            return task
        time.sleep(1)
    raise AssertionError(f"task {task_id} did not reach {wanted}: {task}")


def main() -> None:
    health = client.get("/health")
    health.raise_for_status()

    created = client.post(
        "/v1/tasks",
        json={
            "name": "integration one-shot",
            "kind": "oneshot",
            "command": ["python", "-c", "print('task-integration-ok')"],
            "timeout_seconds": 20,
        },
    )
    created.raise_for_status()
    oneshot = wait_for(created.json()["id"], {"succeeded", "failed"})
    assert oneshot["status"] == "succeeded", oneshot
    logs = client.get(f"/v1/tasks/{oneshot['id']}/logs")
    logs.raise_for_status()
    assert "task-integration-ok" in logs.text

    scheduled = client.post(
        "/v1/tasks",
        json={
            "name": "integration scheduled",
            "kind": "scheduled",
            "command": ["python", "-c", "print('scheduled')"],
            "schedule_cron": "0 0 1 1 *",
            "timezone": "Asia/Taipei",
        },
    )
    scheduled.raise_for_status()
    assert scheduled.json()["status"] == "scheduled"
    canceled_schedule = client.post(
        f"/v1/tasks/{scheduled.json()['id']}/cancel"
    )
    canceled_schedule.raise_for_status()
    assert canceled_schedule.json()["status"] == "canceled"

    due_schedule = client.post(
        "/v1/tasks",
        json={
            "name": "integration due schedule",
            "kind": "scheduled",
            "command": ["python", "-c", "print('due-schedule-ran')"],
            "schedule_cron": "* * * * *",
            "timezone": "Asia/Taipei",
        },
    )
    due_schedule.raise_for_status()
    due_id = due_schedule.json()["id"]
    completed_schedule = wait_for(due_id, {"scheduled", "failed"}, timeout=75)
    deadline = time.monotonic() + 70
    while time.monotonic() < deadline:
        current = client.get(f"/v1/tasks/{due_id}")
        current.raise_for_status()
        if current.json().get("finished_at"):
            completed_schedule = current.json()
            break
        time.sleep(1)
    assert completed_schedule["status"] == "scheduled", completed_schedule
    assert completed_schedule.get("finished_at"), completed_schedule
    canceled_due = client.post(f"/v1/tasks/{due_id}/cancel")
    canceled_due.raise_for_status()
    assert canceled_due.json()["status"] == "canceled"

    service = client.post(
        "/v1/tasks",
        json={
            "name": "integration service",
            "kind": "service",
            "command": ["python", "-c", "import time; time.sleep(120)"],
            "restart_policy": "none",
        },
    )
    service.raise_for_status()
    service_id = service.json()["id"]
    running = wait_for(service_id, {"running", "failed"})
    assert running["status"] == "running", running
    progress = client.patch(
        f"/v1/tasks/{service_id}/progress",
        json={"progress": 42, "message": "integration progress"},
    )
    progress.raise_for_status()
    assert progress.json()["progress"] == 42
    canceled_service = client.post(f"/v1/tasks/{service_id}/cancel")
    canceled_service.raise_for_status()
    stopped = wait_for(service_id, {"canceled", "failed"})
    assert stopped["status"] == "canceled", stopped

    for task_id in (oneshot["id"], scheduled.json()["id"], due_id, service_id):
        deleted = client.delete(f"/v1/tasks/{task_id}")
        deleted.raise_for_status()

    print("task center integration checks passed")


if __name__ == "__main__":
    main()

