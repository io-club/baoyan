# Task Center HTTP API

Agent base URL inside the Docker network: `http://gateway:8080/api/tasks`
Direct service URL for platform-internal services: `http://task-api:8080`

All `/v1` endpoints require:

```http
X-Admin-Password: <Nacos application.admin-password>
```

## Create a one-shot task

```http
POST /v1/tasks
Content-Type: application/json

{
  "name": "crawl activities",
  "kind": "oneshot",
  "command": ["python", "-c", "print('crawl activities')"],
  "timeout_seconds": 1800,
  "metadata": {"source": "frontend"}
}
```

## Create a scheduled task

```json
{
  "name": "daily activity crawl",
  "kind": "scheduled",
  "command": ["python", "-c", "print('crawl activities')"],
  "schedule_cron": "0 8 * * *",
  "timezone": "Asia/Taipei"
}
```

## Create a long-running service

```json
{
  "name": "QQ watcher",
  "kind": "service",
  "command": ["python", "-c", "import time; time.sleep(3600)"],
  "restart_policy": "on-failure"
}
```

## Operations

- `GET /v1/tasks?limit=50&offset=0&status=running&kind=service`
- `GET /v1/tasks/{id}`
- `GET /v1/tasks/{id}/runs`
- `GET /v1/tasks/{id}/logs?tail=200`
- `PATCH /v1/tasks/{id}/progress`
- `POST /v1/tasks/{id}/cancel`
- `DELETE /v1/tasks/{id}` (terminal tasks only)

