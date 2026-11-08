# Agent API Catalog

The Agent container is connected only to `baoyan-agentnet`. Application
services are connected only to `baoyan-appnet`. The gateway is the only
container attached to both networks.

## Allowed base URL

`http://gateway:8080`

## Allowed endpoints

| Method | Path | Upstream |
|---|---|---|
| GET | `/api/tasks` | Task Center |
| POST | `/api/tasks` | Task Center |
| GET | `/api/tasks/{id}` | Task Center |
| GET | `/api/tasks/{id}/runs` | Task Center |
| GET | `/api/tasks/{id}/logs` | Task Center |
| PATCH | `/api/tasks/{id}/progress` | Task Center |
| POST | `/api/tasks/{id}/cancel` | Task Center |
| DELETE | `/api/tasks/{id}` | Task Center |
| POST | `/api/xhs/notes/search` | XHS Collector |
| POST | `/api/xhs/notes/detail` | XHS Collector |
| GET/POST/PATCH/DELETE | `/api/platform/entities/{resource}[/{id}]` | Platform CRUD |
| POST | `/api/platform/import/{resource}` | Platform bulk import |
| POST | `/api/platform/activity-crawl` | Full activity crawl by default; omit end_page or use null; resume:true resumes an incomplete run |
| POST | `/api/platform/intel/xhs-crawl` | XHS crawl task |
| GET | `/api/platform/advisors[/{id}]` | Flat mentor records; inspect actual fields |
| POST | `/api/platform/mail/preview` | Render draft without saving |
| POST | `/api/platform/mail/compose` | Save draft only |
| POST | `/api/platform/templates/{id}/render` | Outreach template rendering |
| POST | `/api/platform/mail/draft` | Create email draft |
| GET | `/api/platform/advisor-facets` | School, department, institute and category options with counts |
| GET | `/api/platform/calendar` | Date-indexed milestones; event_types, group_activities and database pagination |
| GET/PUT | `/api/platform/calendar-settings` | Untagged calendar/countdown display rules |
| GET | `/api/platform/calendar-countdowns` | Future deadlines selected for emphasis |
| PUT | `/api/platform/relations/activity-tags/{id}` | Atomically replace an activity's tag IDs |

All task requests use:

```http
X-Agent-Key: $BAOYAN_AGENT_API_KEY
```

The Agent must not attempt to access `task-api`, PostgreSQL, Redis, RabbitMQ,
MinIO, NapCat, or any management interface directly. Those names are not
attached to the Agent network and are intentionally unresolved.

Use the agent credential above for **all** platform and task API requests. It
is independent of the human login password and remains valid when that
password is changed in Nacos. Never print the credential or use a literal key
in scripts, command history, generated files, or chat responses.

## Business tools added for the complete local workflow

Read `PLATFORM_API.md` for request bodies. All paths below are prefixed with
`http://gateway:8080/api/platform`:

- `GET /calendar?start=2026-11-01&end=2026-11-30&tag_ids=<uuid,uuid>`:
  real deadlines, associated tags and remaining seconds. Use activity-tag
  relations to select a discipline, then query the calendar to verify it.
- `GET /relations/activity-tags/{activity_id}`; `POST /relations/activity-tags`;
  `DELETE /relations/activity-tags/{activity_id}/{tag_id}`.
- `GET /relations/target-materials/{target_id}`;
  `POST /relations/target-materials`;
  `DELETE /relations/target-materials/{target_id}/{material_id}`.
- `POST /reminders/tick`: evaluates enabled persisted rules; the reminder
  container also evaluates them every 30 seconds. Notifications are database
  records in the `notifications` resource, not chat messages or sent email.
- `POST /intel/buffer`: durable raw storage and source-ID deduplication.
- `POST /intel/consume`: creates a real offline LLM summary task. Fetch the
  task result and then read the `intel-batches` record; do not claim a queued
  task has already succeeded.
- `GET /files?object=<urlencoded-object-key>`: authenticated binary download.
- `POST /mail/compose`: renders an actual MIME EML with attachments and
  optionally appends it to the configured IMAP Drafts folder. **Never sends
  email.** Check `imap_saved` and `imap_error`; local EML creation does not
  imply successful mailbox synchronization.
- `GET /integrations`: actual service connectivity and configuration state.

When asked to add computer-related activities to the calendar: query
activities, identify relevant entries from actual titles/schools/metadata,
create or reuse a tag via `/entities/tags`, link matching activity IDs, and
verify with `/calendar?tag_ids=...`. Do not invent activity IDs or deadlines.
For reminder rules create `/entities/reminders` with `name`, `tag_ids`,
`days_before` and `enabled`. Do not send mail or external messages.

## Deployment watchdog

Each release writes an atomic sentinel to
`.runtime/deploy/release.status`. The server watchdog uses these rules:

- `success` or `failed` is the terminal state.
- 180 seconds without any growth in `release.log` is a failure.
- 600 seconds of total runtime is a failure.
- Timeout reasons are written to `.runtime/deploy/release.reason`.


## Mentor and mail contract

Mentor reads: `GET /api/platform/advisors?q=...&limit=50&offset=0` returns `{items,total}` with flat mentor objects; `GET /api/platform/advisors/{id}` returns a flat object. Field names and available values come from the selected record; preserve source-specific names and use only what the requested content needs. Field examples are not a required parameter list. Write/import business fields at root via `/entities/advisors` or `/import/advisors`; never wrap writes in `data`.

Templates support `subject` and `content`. Update with root fields using PATCH `/entities/templates/{id}`, retaining ID and placeholders. Do not delete/recreate or store a rendered mentor name.

POST `/api/platform/mail/preview` then `/api/platform/mail/compose` with `{advisor_id,template_id,parameters:{},material_ids:[]}`. The server automatically fills mentor parameters and recipient, renders both subject and content, reports missing values and creates a draft only. See PLATFORM_API.md for optional overrides and variable bindings. Do not create separate parameter-extraction scripts.

Creating/updating a template does not imply generating a message for a mentor, writing helper scripts, normalizing mentor data, or attaching mapping metadata. Only perform those actions when the user requests them. Read a current sample before choosing variables. Existing conversations retain their launch context; after a platform-policy update, start a new conversation to use the new policy rather than editing historical events.
