from __future__ import annotations

import io
import os
import time

import httpx


HEADERS = {"X-Admin-Password": os.getenv("PLATFORM_ADMIN_PASSWORD", "password")}
PLATFORM = os.getenv("PLATFORM_API_URL", "http://gateway:8080/api/platform")
TASKS = os.getenv("TASK_API_URL", "http://gateway:8080/api/tasks")
client = httpx.Client(timeout=60)


def create(resource: str, payload: dict) -> dict:
    response = client.post(f"{PLATFORM}/entities/{resource}", headers=HEADERS, json=payload)
    response.raise_for_status()
    return response.json()


def delete(resource: str, item_id: str) -> None:
    response = client.delete(f"{PLATFORM}/entities/{resource}/{item_id}", headers=HEADERS)
    response.raise_for_status()


def wait_task(task_id: str) -> dict:
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        response = client.get(f"{TASKS}/{task_id}", headers=HEADERS)
        response.raise_for_status()
        task = response.json()
        if task["status"] in {"succeeded", "failed"}:
            return task
        time.sleep(1)
    raise AssertionError(f"task did not finish: {task_id}")


def main() -> None:
    config = client.get(f"{PLATFORM}/config", headers=HEADERS)
    config.raise_for_status()
    assert "llm" in config.json()

    activity = create(
        "activities",
        {"title": "集成测试活动", "school": "测试大学", "deadline": "2027-01-01", "tags": []},
    )
    update = client.patch(
        f"{PLATFORM}/entities/activities/{activity['id']}",
        headers=HEADERS,
        json={**activity["data"], "notes": "updated"},
    )
    update.raise_for_status()
    search = client.get(f"{PLATFORM}/entities/activities", headers=HEADERS, params={"q": "集成测试"})
    search.raise_for_status()
    assert search.json()["total"] >= 1

    template = create(
        "templates", {"name": "测试模板", "description": "", "content": "老师 {{name}}，{{interest}}"}
    )
    rendered = client.post(
        f"{PLATFORM}/templates/{template['id']}/render",
        headers=HEADERS,
        json={"parameters": {"name": "张三", "interest": "CV"}},
    )
    rendered.raise_for_status()
    assert rendered.json()["content"] == "老师 张三，CV"

    material = create(
        "materials", {"name": "成绩单", "description": "测试", "type": "text", "content": "1/100"}
    )
    target = create("targets", {"name": "测试夏令营", "description": "", "materials": []})
    relation = client.post(
        f"{PLATFORM}/relations/target-materials",
        headers=HEADERS,
        json={"entity_id": target["id"], "related_id": material["id"], "note": "测试口径"},
    )
    relation.raise_for_status()
    linked = client.get(
        f"{PLATFORM}/relations/target-materials/{target['id']}", headers=HEADERS
    )
    linked.raise_for_status()
    assert linked.json()[0]["material_id"] == material["id"]

    advisor = create(
        "advisors", {"name": "测试导师", "email": "test@example.com", "homepage": "", "data": {}}
    )
    record = create(
        "outreach-records",
        {"advisor_id": advisor["id"], "status": "未套磁", "tags": []},
    )

    upload = client.post(
        f"{PLATFORM}/files",
        headers=HEADERS,
        files={"file": ("note.txt", io.BytesIO("test material".encode()), "text/plain")},
    )
    upload.raise_for_status()
    assert upload.json()["size"] == 13

    draft = client.post(
        f"{PLATFORM}/mail/draft",
        headers=HEADERS,
        json={
            "recipient_name": "测试导师",
            "recipient_email": "test@example.com",
            "subject": "测试套磁",
            "content": "不会真正发送",
            "attachments": [],
        },
    )
    draft.raise_for_status()
    assert draft.json()["eml_base64"]

    crawl = client.post(
        f"{PLATFORM}/activity-crawl",
        headers=HEADERS,
        json={"start_page": 1, "end_page": 1, "page_size": 25},
    )
    crawl.raise_for_status()
    crawl_result = wait_task(crawl.json()["id"])
    assert crawl_result["status"] == "succeeded", crawl_result
    assert client.get(f"{PLATFORM}/entities/activities", headers=HEADERS).json()["total"] >= 1

    xhs = client.post(
        f"{PLATFORM}/intel/xhs-crawl",
        headers=HEADERS,
        json={"query": "保研", "cookie": "a1=12345678901234567890", "limit": 1},
    )
    xhs.raise_for_status()
    xhs_result = wait_task(xhs.json()["id"])
    assert xhs_result["status"] in {"succeeded", "failed"}

    for resource, item in (
        ("activities", activity),
        ("templates", template),
        ("materials", material),
        ("targets", target),
        ("advisors", advisor),
        ("outreach-records", record),
    ):
        delete(resource, item["id"])

    print("platform CRUD and crawler integration checks passed")


if __name__ == "__main__":
    main()

