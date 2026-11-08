# Platform HTTP API

Endpoints accept the credentials described under Authentication and are available through
`http://gateway:8080/api/platform`.

- `GET /entities/{resource}` and `POST /entities/{resource}`
- `GET|PATCH|DELETE /entities/{resource}/{id}`
- `POST /import/{resource}`
- `POST /relations/activity-tags`
- `POST /relations/target-materials`
- `GET /relations/target-materials/{target_id}`
- `GET /advisors` and `GET /advisors/{id}`
- `POST /templates/{id}/render`
- `POST /mail/preview` and `POST /mail/compose`
- `POST /files`
- `POST /mail/draft` (creates a draft only; never sends)
- `POST /activity-crawl`
- `POST /intel/xhs-crawl`
- `GET /napcat/webui`
- `POST /intel/qq-monitor`
- `GET /config` and `PATCH /config`

Resources: `activities`, `tags`, `reminders`, `intel-items`,
`intel-sources`, `advisors`, `templates`, `outreach-records`, `materials`,
and `targets`.

## Authentication

The browser uses `X-Admin-Password`; tools inside the actual Agent container
use `X-Agent-Key: $BAOYAN_AGENT_API_KEY`. Both credentials must stay private.
Human password changes are read from Nacos by both APIs.

## Entity structure and PATCH

Generic `/entities` responses are `{id,data,created_at,updated_at}`. The dedicated
`/advisors` reads described below return flat records. Generic list responses
are `{items,total}` and accept `q`, `limit` (up to 1000), and `offset`.
PATCH merges provided keys and preserves omitted fields. Source imports use
`{items:[...]}` and upsert entries with the same `source` and `source_id`,
preserving user tags and notes. Imports without source IDs create new entries.

### Mentor classification

`GET /entities/advisors` additionally accepts exact `school`, `department`,
`institute`, `category` filters, combined with `q`, `limit`, `offset` in SQL.
`GET /advisor-facets?school=...&department=...&institute=...` returns cascading
options with counts. Classification uses the business payload fields `institute`
(with `center` fallback), `category` and `categories[]`; older nested category
values remain readable for compatibility. These are filter capabilities, not
instructions to fill fields or change source records. Missing values appear under `未分类`.

### Calendar milestones and display rules

`GET /calendar?start=...&end=...&event_types=registration_start,deadline,activity_start`
returns **only the dates of those nodes**, never every day of a date interval.
The default node is `deadline`. Node dates are projected into the indexed
`platform.activity_events` table, including legacy source fields
`raw.sign_up_start`, `raw.sign_up_end`, and `raw.start_time`.
Explicit null on a normalized node field clears it, without reviving the raw value.

Use `per_day=3` for bounded month previews. `day_counts` counts nodes;
`day_activity_counts` and `activity_count` count distinct activities.
The day drawer calls the same endpoint with `start=end`,
`group_activities=true`, `limit=10`, and `offset`. Each returned activity has
an `events[]` array, so multiple same-day nodes do not create duplicate cards.
Calendar summaries omit the archived `data.raw` article body; activity detail
fetches `/entities/activities/{id}` for the full unchanged record.

Tags support `name`, `color`, `show_calendar` (default true),
and `show_countdown` (default false). These rules apply in SQL before paging.
When multiple tags are assigned, any tag allowing a display enables that display.
`GET|PUT /calendar-settings` reads/writes exactly two boolean preferences:
`show_untagged` (default true) and `countdown_untagged` (default false).
`GET /calendar-countdowns?limit=5&offset=0` pages future registration deadlines
selected for emphasis, independently of calendar visibility.

`PUT /relations/activity-tags/{activity_id}` with `{"tag_ids":["uuid",...]}`
atomically replaces tag links and the legacy `data.tags` IDs. All IDs are
validated before changing links; invalid selections preserve the original set.

### Activity collection execution

`POST /activity-crawl` with `{"start_page":1,"page_size":25,"resume":true}`
crawls the entire source. Omit `end_page` or set it to null for all pages;
an explicit positive end page limits the range. Runs have a 24-hour deadline.
Each source request uses a fresh nonce/signature, 30-second timeout, up to ten
retries after the first attempt, exponential backoff from 2 to 60 seconds with
jitter, and respects numeric Retry-After. Pages are spaced by 0.5 seconds.
API business failures are retried rather than mistaken for an empty page.

Raw responses and progress are persisted under `/workspace/activity-crawl`
(local host `.runtime/local-data/workspace/activity-crawl`, inside this D-drive
project). The checkpoint advances only after import succeeds. Rerunning the
same range resumes incomplete progress and reuses its cached pending page;
`resume:false` starts a fresh run. Source IDs upsert existing records and keep
user notes/tags. Concurrent runs of the same range are rejected. Repeated
pages or invalid rows fail explicitly, preserving the page for investigation.
Task logs show page counts and retry delays. Full runs verify unique source
IDs against the advertised total; raw pages and summary support readback audits.

| Resource | Typical data fields |
|---|---|
| activities | title*, school, college, deadline (ISO date/time), source_url, notes |
| tags | name*, color |
| reminders | name*, enabled, days_before (0..3650), tag_ids[], optional activity_id |
| advisors | name*, school, department, institute, category, categories[], photo, homepage, email, title, research_directions[], bio (additional fields at root) |
| templates | name*, description, subject, content* (`{{name}}`, `{{profile.field}}`) |
| outreach-records | advisor_id, status, tags[], notes, draft_object |
| materials | name*, description, type, content, files[] |
| targets | name*, description |
| intel-items | source, source_id, title, content, buffer_object, processing_status |
| intel-batches | source_ids[], summary, instruction |
| notifications | activity_id, deadline, message, read |

Fields marked * are required for new entities. Advisor references in outreach
records and both ends of material/tag relations are checked before writing.
Delete automatically removes material/tag junction rows.

## Calendar and reminders

`GET /calendar?start=YYYY-MM-DD&end=YYYY-MM-DD&tag_ids=id,id` returns
`{items,tags}`. Each event contains `date`, `deadline`, `seconds_remaining`,
`tag_ids`, and original `data`. Invalid upstream date strings are omitted.
Date-only deadlines refer to 23:59:59 in Asia/Shanghai.

Create tag links with `{entity_id:<activity UUID>,related_id:<tag UUID>,note}`.
Fetch links with `GET /relations/activity-tags/{id}` and unlink with
`DELETE /relations/activity-tags/{activity_id}/{tag_id}`.

Reminder rules are stored with the ordinary reminders CRUD. The persistent
reminder worker runs every 30 seconds and creates idempotent notifications.
`POST /reminders/tick` provides an explicit check. Mark a notification read
with `PATCH /entities/notifications/{id}` body `{read:true}`.

## Materials and draft mail

`POST /files` accepts multipart form field `file` (max 25MiB), returning
`{object,filename,content_type,size}`. Store this object in material `files`.
`GET /files?object=...` downloads the binary with the same auth header.

Material links use `{entity_id:<target UUID>,related_id:<material UUID>,note}`.
Posting an existing pair updates its note. Delete a pair with
`DELETE /relations/target-materials/{target_id}/{material_id}`.

Mentor reads use `GET /advisors?q=...&limit=50&offset=0` (paged
`{items,total}`) and `GET /advisors/{id}` (a flat object containing
`id,name,title,school,department,institute,email,research_directions,bio`).
No nested business `data` field is needed. Existing legacy records were flattened
with originals backed up. Additional original source fields, including Chinese
field names, are preserved. Read the actual record before choosing template
variables; the typical-field list is not a required template schema. Generic `/entities` reads still
return the standard `{id,data,created_at,updated_at}` envelope; its `data`
is the business payload, not a field to send in POST/PATCH requests.

Update in place: `PATCH /entities/templates/{id}` with
`{"subject":"申请交流 · {{name}} 老师","content":"{{name}} 老师您好……"}`.
Omitted fields remain unchanged. Do not DELETE/recreate a template to update it.
Keep placeholders in the stored template; do not save a rendered mentor name.

`POST /templates/{id}/render` takes `{advisor_id,parameters:{...}}`.
Both subject and content are rendered. Missing variables return 422.

`POST /mail/preview` and `POST /mail/compose` share this request:

```json
{"advisor_id":"mentor UUID","template_id":"template UUID",
 "parameters":{},"material_ids":[]}
```

The server loads the mentor on every request and fills the recipient name/email
and parameters using the selected record's actual business field names, including
source-specific fields such as `center` or `研究方向`. `{{field}}` and
`{{advisor.field}}` read that field; arrays are displayed joined with `、`.
Use only fields needed by the requested content and verified in a sample. Do not
rename fields or require the same parameters for different schools. No lookup
script or field mapping must be stored with a template. The old `direction` alias
remains accepted only for existing templates; do not introduce it in new ones.
Mentor fields take precedence over stale custom parameter values. Extra variables
are supplied in parameters (including nested objects). Optional recipient_name,
recipient_email, subject, content explicitly override those values. Manual drafts
can omit both IDs and supply these four fields directly. An absent template
subject requires an explicit subject; no subject is invented during migration.
Preview returns rendered subject/content, variables with source and missing flags,
missing[], errors[], and the resolved recipient. Compose validates the same values
before creating any object/draft, and uses exactly those rendered fields.

Binary and text materials can be attachments. The response includes `object`
(downloadable EML), `imap_saved`, `imap_error`, `record_id` and `sent:false`.
An outreach record is created in 未套磁 state because a draft is not a sent
message. No SMTP send operation exists.

IMAP accepts ordinary mailbox authorization codes or OAuth XOAUTH2. Outlook
device login requires your own Entra public-client application ID in SMTP
settings (`oauth-client-id`, optional `oauth-tenant`, normally `common`).
`POST /mail/oauth/device` returns a Microsoft verification URL, user code and
local session ID; the human completes sign-in. Poll
`POST /mail/oauth/device/{session_id}` until authorized. Refresh tokens are
stored privately in Nacos and refreshed before IMAP draft synchronization.
No `SMTP.Send` permission is requested.

## Cold buffer and summaries

Calendar reads use `platform.activity_schedule`, maintained in the same
transaction as activity creates, edits, imports and deletes. Its date index
supports `GET /calendar?start=YYYY-MM-DD&end=YYYY-MM-DD&limit=10&offset=0`.
The database applies date, keyword and tag predicates before `LIMIT/OFFSET`.
`per_day=3` returns up to three preview events per date plus `day_counts` and
`total`. Foreground page loads do not run the reminder worker.

`POST /intel/attachments` accepts one multipart `file` (maximum 25 MB), writes
it to `intel/attachments/<sha256>` and returns
`{object,filename,content_type,size,sha256}`. Uploading identical bytes reuses
the same object. This endpoint is source-independent.

`POST /intel/buffer` body:
`{source,source_id,title,content,metadata:{},attachments:[]}`.
Each attachment is the upload response plus an optional `source_url`.
All referenced objects must exist before the message manifest is committed.
The platform never interprets QQ/CQ message segments or downloads remote media.
The raw payload is written to MinIO and deduplicated by source plus source ID.
XHS and QQ collectors use this endpoint. The QQ watcher additionally uses a
SQLite WAL outbox in the persistent workspace until delivery succeeds.
The QQ source adapter extracts plain text and image/file segments, uploads
each attachment immediately, persists partial progress, then commits the
message and attachment manifest together. Raw events and original links remain
in source metadata. Failed downloads/uploads keep the outbox entry for retry.
Companion QQ file messages and group-upload notices are correlated by group,
sender, file hash and a five-second event window. Both raw events remain in
`metadata.source_events`; ordinary repeated sends remain separate records.
XHS collectors attach the complete crawled post JSON (including raw detail and
search results when available) and downloaded post images through the same
attachment interface. Image text is not OCR-processed.

`POST /intel/consume` body: `{ids:[<intel UUID>],instruction:"..."}` returns a
Task Center task. A real model call stores `intel-batches` and marks source
items processed after success. Missing LLM config returns 409; provider
failures do not mark sources processed.

