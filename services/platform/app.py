from __future__ import annotations

import base64
import hmac
import imaplib
import json
import os
import time
from datetime import datetime
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from io import BytesIO
from typing import Any
from uuid import UUID, uuid4

import urllib.parse
import urllib.request
import yaml
from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, UploadFile
from minio import Minio
from pydantic import BaseModel, Field
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool


DB_URL = os.getenv(
    "DATABASE_URL", "postgresql://baoyan:baoyan@postgres:5432/baoyan"
)
NACOS_URL = os.getenv("NACOS_URL", "http://nacos:8848/nacos")
GROUP = os.getenv("NACOS_GROUP", "BAOYAN_GROUP")
CONFIG_ID = os.getenv("NACOS_DATA_ID", "baoyan-platform.yaml")
TASK_API = os.getenv("TASK_API_URL", "http://task-api:8080")
XHS_API = os.getenv("XHS_API_URL", "http://xhs:5000")

RESOURCE_TYPES = {
    "activities",
    "tags",
    "reminders",
    "intel-items",
    "intel-sources",
    "advisors",
    "templates",
    "outreach-records",
    "materials",
    "targets",
    "notifications",
    "intel-batches",
}

SCHEMA = """
CREATE SCHEMA IF NOT EXISTS platform;
CREATE TABLE IF NOT EXISTS platform.entities (
    resource TEXT NOT NULL,
    id UUID NOT NULL,
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (resource, id)
);
CREATE TABLE IF NOT EXISTS platform.target_materials (
    target_id UUID NOT NULL,
    material_id UUID NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (target_id, material_id)
);
CREATE TABLE IF NOT EXISTS platform.activity_tags (
    activity_id UUID NOT NULL,
    tag_id UUID NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (activity_id, tag_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS platform_entity_uuid ON platform.entities(id);
CREATE INDEX IF NOT EXISTS platform_entity_source_lookup_idx ON platform.entities (resource,(data->>'source'),(data->>'source_id'));
CREATE INDEX IF NOT EXISTS platform_advisor_school_department_idx ON platform.entities ((data->>'school'),(data->>'department')) WHERE resource='advisors';
CREATE TABLE IF NOT EXISTS platform.outreach_advisors (
    record_id UUID PRIMARY KEY REFERENCES platform.entities(id) ON DELETE CASCADE,
    advisor_id UUID NOT NULL REFERENCES platform.entities(id) ON DELETE RESTRICT
);
INSERT INTO platform.outreach_advisors(record_id,advisor_id)
SELECT record.id,advisor.id FROM platform.entities record
JOIN platform.entities advisor ON advisor.resource='advisors' AND advisor.id::text=record.data->>'advisor_id'
WHERE record.resource='outreach-records' ON CONFLICT(record_id) DO NOTHING;
DO $$ BEGIN
    IF NOT EXISTS(SELECT 1 FROM pg_constraint WHERE conname='platform_activity_parent_fk') THEN
        ALTER TABLE platform.activity_tags ADD CONSTRAINT platform_activity_parent_fk FOREIGN KEY(activity_id) REFERENCES platform.entities(id) ON DELETE CASCADE NOT VALID;
        ALTER TABLE platform.activity_tags ADD CONSTRAINT platform_activity_tag_fk FOREIGN KEY(tag_id) REFERENCES platform.entities(id) ON DELETE CASCADE NOT VALID;
        ALTER TABLE platform.target_materials ADD CONSTRAINT platform_target_parent_fk FOREIGN KEY(target_id) REFERENCES platform.entities(id) ON DELETE CASCADE NOT VALID;
        ALTER TABLE platform.target_materials ADD CONSTRAINT platform_material_fk FOREIGN KEY(material_id) REFERENCES platform.entities(id) ON DELETE CASCADE NOT VALID;
    END IF;
END $$;
"""

pool = ConnectionPool(
    DB_URL,
    min_size=1,
    max_size=10,
    kwargs={"row_factory": dict_row},
    open=False,
)


def ensure_pool() -> None:
    if pool.closed:
        pool.open(wait=True, timeout=30)


def init_schema() -> None:
    ensure_pool()
    with pool.connection() as conn:
        conn.execute(SCHEMA)
        from advisor_contract import initialize as initialize_advisor_contract
        initialize_advisor_contract(conn)
        from calendar_queries import initialize
        initialize(conn)
        conn.execute("""
            UPDATE platform.entities
            SET data=jsonb_set(data,'{attachments}',
                COALESCE(jsonb_path_query_array(data,'$.metadata.images[*] ? (@.status == "stored")'),'[]'::jsonb))
            WHERE resource='intel-items' AND (NOT data ? 'attachments' OR data->'attachments'='null'::jsonb)
        """)


def nacos_url(path: str) -> str:
    return NACOS_URL.rstrip("/") + path


def read_config() -> dict[str, Any]:
    query = urllib.parse.urlencode({"dataId": CONFIG_ID, "group": GROUP})
    with urllib.request.urlopen(nacos_url(f"/v1/cs/configs?{query}"), timeout=20) as r:
        return yaml.safe_load(r.read().decode("utf-8")) or {}


def write_config(document: dict[str, Any]) -> None:
    body = urllib.parse.urlencode(
        {
            "dataId": CONFIG_ID,
            "group": GROUP,
            "type": "yaml",
            "content": yaml.safe_dump(document, allow_unicode=True, sort_keys=False),
        }
    ).encode()
    req = urllib.request.Request(nacos_url("/v1/cs/configs"), data=body, method="POST")
    with urllib.request.urlopen(req, timeout=20) as response:
        if response.read().decode().strip() != "true":
            raise RuntimeError("Nacos rejected configuration")


def config_value(path: str, default: Any = "") -> Any:
    value: Any = read_config()
    for part in path.split("."):
        value = (value or {}).get(part, default) if isinstance(value, dict) else default
    return value


def require_admin(x_admin_password: str | None = Header(default=None), x_agent_key: str | None = Header(default=None)) -> None:
    agent_key=os.getenv('BAOYAN_AGENT_API_KEY','')
    if agent_key and isinstance(x_agent_key,str) and hmac.compare_digest(x_agent_key,agent_key):
        return
    expected = str(config_value("baoyan.application.admin-password", "password"))
    if not x_admin_password or not hmac.compare_digest(x_admin_password, expected):
        raise HTTPException(401, "invalid password")


def public_config(document: dict[str, Any]) -> dict[str, Any]:
    def mask(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: ("***" if any(s in key.lower() for s in ("password", "key", "cookie", "token", "secret", "authorization")) else mask(item))
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [mask(item) for item in value]
        return value

    return mask(document.get("baoyan", {}))


def preserve_masked(new_value: Any, old_value: Any) -> Any:
    if isinstance(new_value, dict) and isinstance(old_value, dict):
        return {
            key: preserve_masked(item, old_value.get(key))
            for key, item in new_value.items()
        }
    if new_value == "***":
        return old_value
    return new_value


def row_dict(row) -> dict[str, Any]:
    data = dict(row)
    data["id"] = str(data["id"])
    for key in ("created_at", "updated_at"):
        if data.get(key) is not None:
            data[key] = data[key].isoformat()
    return data


class ConfigUpdate(BaseModel):
    section: str
    value: dict[str, Any]


class LoginRequest(BaseModel):
    password: str


class BulkImport(BaseModel):
    items: list[dict[str, Any]]


class TemplateRender(BaseModel):
    advisor_id: UUID | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class Attachment(BaseModel):
    filename: str
    content_base64: str


class DraftRequest(BaseModel):
    recipient_name: str
    recipient_email: str
    subject: str
    content: str
    attachments: list[Attachment] = Field(default_factory=list)


class ActivityCrawlRequest(BaseModel):
    start_page: int = Field(default=1, ge=1)
    end_page: int | None = Field(default=None, ge=1)
    page_size: int = Field(default=25, ge=1, le=100)
    resume: bool = True


class XhsCrawlRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    cookie: str = Field(min_length=20)
    limit: int = Field(default=10, ge=1, le=100)


class QqMonitorRequest(BaseModel):
    group_ids: list[str] = Field(min_length=1, max_length=50)
    restart_policy: str = Field(default="always", pattern="^(none|always|on-failure)$")


class RelationRequest(BaseModel):
    entity_id: UUID
    related_id: UUID
    note: str = ""


app = FastAPI(title="Baoyan Platform API", version="1.0.0")


@app.on_event("startup")
def startup() -> None:
    init_schema()


@app.get("/health")
def health():
    with pool.connection() as conn:
        conn.execute("SELECT 1")
    return {"status": "ok", "service": "platform"}


@app.post("/v1/auth")
def login(request: LoginRequest):
    expected = str(config_value("baoyan.application.admin-password", "password"))
    if not hmac.compare_digest(request.password, expected):
        raise HTTPException(401, "invalid password")
    return {"ok": True}


@app.get("/v1/config", dependencies=[Depends(require_admin)])
def get_config():
    return public_config(read_config())


@app.patch("/v1/config", dependencies=[Depends(require_admin)])
def update_config(update: ConfigUpdate):
    document = read_config()
    baoyan = document.setdefault("baoyan", {})
    old=baoyan.get(update.section,{})
    if update.section=='application' and 'admin-password' in update.value and not str(update.value['admin-password']).strip():
        raise HTTPException(422,'口令不能为空')
    baoyan[update.section] = preserve_masked({**old,**update.value},old)
    write_config(document)
    result={"ok":True,"section":update.section}
    if update.section=='llm':
        from features import sync_agent
        result.update(sync_agent(sys.modules[__name__]))
    return result


def resource_name(resource: str) -> str:
    if resource not in RESOURCE_TYPES:
        raise HTTPException(404, "unknown resource")
    return resource


def validate_entity(resource: str, data: dict):
    from advisor_contract import normalize
    normalized=normalize(resource,data)
    if normalized is not data:data.clear();data.update(normalized)
    if resource == 'intel-items':
        data.setdefault('attachments', [])
    if resource == 'intel-items':
        data.setdefault('attachments', [])
    required={'activities':'title','tags':'name','templates':'name','advisors':'name','materials':'name','targets':'name','reminders':'name'}
    key=required.get(resource)
    if key and not str(data.get(key,'')).strip(): raise HTTPException(422,f'{key} 不能为空')
    if resource=='templates' and not str(data.get('content','')).strip(): raise HTTPException(422,'模板正文不能为空')
    if resource=='outreach-records' and data.get('advisor_id'):
        try: advisor_id=UUID(str(data['advisor_id']))
        except ValueError as exc: raise HTTPException(422,'导师 ID 无效') from exc
        get_entity('advisors',advisor_id)
    if resource=='reminders':
        try:
            days=float(data.get('days_before',3))
            if not 0<=days<=3650: raise ValueError()
        except (TypeError,ValueError) as exc: raise HTTPException(422,'提醒天数应在 0 到 3650 之间') from exc
    if resource=='activities':
        from features import parse_deadline
        for key in ('registration_start','deadline','activity_start'):
            if data.get(key) and parse_deadline(data[key]) is None:raise HTTPException(422,f'{key} 日期格式无效')
    if resource=='tags':
        for key in ('show_calendar','show_countdown'):
            if key in data and type(data[key]) is not bool:raise HTTPException(422,'标签展示开关必须是布尔值')


def sync_advisor_link(conn,resource,entity_id,payload):
    from calendar_queries import sync
    sync(conn,resource,entity_id,payload)
    if resource!='outreach-records':return
    if payload.get('advisor_id'):
        conn.execute('INSERT INTO platform.outreach_advisors(record_id,advisor_id) VALUES(%s,%s) ON CONFLICT(record_id) DO UPDATE SET advisor_id=excluded.advisor_id',(entity_id,UUID(str(payload['advisor_id']))))
    else:
        conn.execute('DELETE FROM platform.outreach_advisors WHERE record_id=%s',(entity_id,))


@app.get('/v1/advisor-facets', dependencies=[Depends(require_admin)])
def advisor_facets(school: str='',department: str='',institute: str=''):
    from advisor_queries import facets
    with pool.connection() as conn:
        return facets(conn,school,department,institute)

@app.get("/v1/entities/{resource}", dependencies=[Depends(require_admin)])
def list_entities(
    resource: str,
    q: str = Query(default="", max_length=200),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    created_from: datetime | None = None,
    created_before: datetime | None = None,
    school: str = Query(default='',max_length=200),
    department: str = Query(default='',max_length=200),
    institute: str = Query(default='',max_length=200),
    category: str = Query(default='',max_length=200),
):
    resource = resource_name(resource)
    where = "resource=%s"
    params: list[Any] = [resource]
    if resource=='advisors':
        from advisor_queries import predicate
        extra,values=predicate(school,department,institute,category)
        where+=extra;params.extend(values)
    if created_from is not None and created_from.utcoffset() is None:
        raise HTTPException(422, '开始时间必须包含时区')
    if created_before is not None and created_before.utcoffset() is None:
        raise HTTPException(422, '结束时间必须包含时区')
    if created_from is not None and created_before is not None and created_from >= created_before:
        raise HTTPException(422, '结束时间必须晚于开始时间')
    if created_from is not None:
        where += ' AND created_at >= %s'
        params.append(created_from)
    if created_before is not None:
        where += ' AND created_at < %s'
        params.append(created_before)
    if q:
        where += " AND data::text ILIKE %s"
        params.append(f"%{q}%")
    with pool.connection() as conn:
        total = conn.execute(
            f"SELECT count(*) AS n FROM platform.entities WHERE {where}", params
        ).fetchone()["n"]
        rows = conn.execute(
            f"SELECT id,data,created_at,updated_at FROM platform.entities "
            f"WHERE {where} ORDER BY created_at DESC,id DESC LIMIT %s OFFSET %s",
            [*params, limit, offset],
        ).fetchall()
    return {"items": [row_dict(row) for row in rows], "total": total}


@app.post("/v1/entities/{resource}", status_code=201, dependencies=[Depends(require_admin)])
def create_entity(resource: str, payload: dict[str, Any]):
    resource = resource_name(resource)
    validate_entity(resource,payload)
    entity_id = uuid4()
    with pool.connection() as conn:
        row = conn.execute(
            "INSERT INTO platform.entities(resource,id,data) VALUES(%s,%s,%s) "
            "RETURNING id,data,created_at,updated_at",
            (resource, entity_id, Jsonb(payload)),
        ).fetchone()
        sync_advisor_link(conn,resource,entity_id,payload)
    return row_dict(row)


@app.get("/v1/entities/{resource}/{entity_id}", dependencies=[Depends(require_admin)])
def get_entity(resource: str, entity_id: UUID):
    resource = resource_name(resource)
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT id,data,created_at,updated_at FROM platform.entities "
            "WHERE resource=%s AND id=%s",
            (resource, entity_id),
        ).fetchone()
    if not row:
        raise HTTPException(404, "entity not found")
    return row_dict(row)


@app.patch("/v1/entities/{resource}/{entity_id}", dependencies=[Depends(require_admin)])
def update_entity(resource: str, entity_id: UUID, payload: dict[str, Any]):
    resource = resource_name(resource)
    previous=get_entity(resource,entity_id)
    from advisor_contract import normalize
    payload=normalize(resource,payload,patch=True)
    validate_entity(resource,{**previous['data'],**payload})
    with pool.connection() as conn:
        row = conn.execute(
            "UPDATE platform.entities SET data=data || %s,updated_at=now() "
            "WHERE resource=%s AND id=%s RETURNING id,data,created_at,updated_at",
            (Jsonb(payload), resource, entity_id),
        ).fetchone()
        if row: sync_advisor_link(conn,resource,entity_id,row['data'])
    if not row:
        raise HTTPException(404, "entity not found")
    return row_dict(row)


@app.delete("/v1/entities/{resource}/{entity_id}", status_code=204, dependencies=[Depends(require_admin)])
def delete_entity(resource: str, entity_id: UUID):
    resource = resource_name(resource)
    with pool.connection() as conn:
        if resource=='advisors':
            linked=conn.execute('SELECT 1 FROM platform.outreach_advisors WHERE advisor_id=%s LIMIT 1',(entity_id,)).fetchone()
            if linked: raise HTTPException(409,'导师存在套磁记录，请先处理关联记录再删除')
        if resource == "activities":
            conn.execute("DELETE FROM platform.activity_tags WHERE activity_id=%s", (entity_id,))
        elif resource == "tags":
            conn.execute("DELETE FROM platform.activity_tags WHERE tag_id=%s", (entity_id,))
        elif resource == "materials":
            conn.execute("DELETE FROM platform.target_materials WHERE material_id=%s", (entity_id,))
        elif resource == "targets":
            conn.execute("DELETE FROM platform.target_materials WHERE target_id=%s", (entity_id,))
        result = conn.execute(
            "DELETE FROM platform.entities WHERE resource=%s AND id=%s",
            (resource, entity_id),
        )
    if result.rowcount != 1:
        raise HTTPException(404, "entity not found")


@app.post("/v1/import/{resource}", dependencies=[Depends(require_admin)])
def import_entities(resource: str, payload: BulkImport):
    resource = resource_name(resource)
    rows = []
    with pool.connection() as conn:
        for item in payload.items:
            validate_entity(resource,item)
            if item.get("source") and item.get("source_id"):
                # Serialize importers for this source key, without merging unrelated items.
                conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (resource + ':' + str(item['source']) + ':' + str(item['source_id']),))
                existing = conn.execute("SELECT id FROM platform.entities WHERE resource=%s AND data->>'source'=%s AND data->>'source_id'=%s LIMIT 1", (resource, str(item['source']), str(item['source_id']))).fetchone()
                if existing:
                    # Preserve user-maintained tags and annotations when crawling again.
                    refreshed = {k:v for k,v in item.items() if k not in {"tags", "notes"}}
                    row = conn.execute("UPDATE platform.entities SET data=data || %s,updated_at=now() WHERE resource=%s AND id=%s RETURNING id,data,created_at,updated_at", (Jsonb(refreshed),resource,existing['id'])).fetchone()
                    rows.append(row_dict(row))
                    sync_advisor_link(conn,resource,row['id'],row['data'])
                    continue
            row = conn.execute(
                "INSERT INTO platform.entities(resource,id,data) VALUES(%s,%s,%s) "
                "RETURNING id,data,created_at,updated_at",
                (resource, uuid4(), Jsonb(item)),
            ).fetchone()
            rows.append(row_dict(row))
            sync_advisor_link(conn,resource,row['id'],row['data'])
    return {"count": len(rows), "items": rows}


@app.post("/v1/relations/activity-tags", dependencies=[Depends(require_admin)])
def link_activity_tag(link: RelationRequest):
    get_entity("activities", link.entity_id)
    get_entity("tags", link.related_id)
    with pool.connection() as conn:
        conn.execute(
            "INSERT INTO platform.activity_tags(activity_id,tag_id,note) VALUES(%s,%s,%s) "
            "ON CONFLICT(activity_id,tag_id) DO UPDATE SET note=excluded.note",
            (link.entity_id, link.related_id, link.note),
        )
    return {"ok": True}


@app.post("/v1/relations/target-materials", dependencies=[Depends(require_admin)])
def link_target_material(link: RelationRequest):
    get_entity("targets", link.entity_id)
    get_entity("materials", link.related_id)
    with pool.connection() as conn:
        conn.execute(
            "INSERT INTO platform.target_materials(target_id,material_id,note) VALUES(%s,%s,%s) "
            "ON CONFLICT(target_id,material_id) DO UPDATE SET note=excluded.note",
            (link.entity_id, link.related_id, link.note),
        )
    return {"ok": True}


@app.get("/v1/relations/target-materials/{target_id}", dependencies=[Depends(require_admin)])
def target_materials(target_id: UUID):
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT tm.material_id,e.data,tm.note FROM platform.target_materials tm "
            "LEFT JOIN platform.entities e ON e.resource='materials' AND e.id=tm.material_id "
            "WHERE tm.target_id=%s ORDER BY tm.created_at",
            (target_id,),
        ).fetchall()
    return [
        {"material_id": str(row["material_id"]), "material": row["data"], "note": row["note"]}
        for row in rows
    ]


@app.post("/v1/templates/{template_id}/render", dependencies=[Depends(require_admin)])
def render_template(template_id: UUID, request: TemplateRender):
    entity = get_entity("templates", template_id)
    from advisor_contract import flat
    from mail_templates import context_for,render_fields
    advisor=flat(get_entity('advisors',request.advisor_id)) if request.advisor_id else None
    context=context_for(advisor,request.parameters)
    return render_fields(str(entity['data'].get('subject') or ''),str(entity['data'].get('content') or ''),context,advisor,strict=True)


def task_request(payload: dict[str, Any]) -> dict[str, Any]:
    password = str(config_value("baoyan.application.admin-password", "password"))
    req = urllib.request.Request(
        TASK_API.rstrip("/") + "/v1/tasks",
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Content-Type": "application/json", "X-Admin-Password": password},
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read())


@app.post("/v1/activity-crawl", dependencies=[Depends(require_admin)])
def activity_crawl(request: ActivityCrawlRequest):
    if request.end_page is not None and request.end_page<request.start_page:
        raise HTTPException(422,'结束页不能小于起始页')
    return task_request(
        {
            "name": "保研活动全量采集" if request.end_page is None else "保研活动范围采集",
            "kind": "oneshot",
            "command": ["python", "-m", "app.crawl_activities"],
            "timeout_seconds": 86400,
            "metadata": {
                "environment": {
                    "ACTIVITY_START_PAGE": str(request.start_page),
                    "ACTIVITY_END_PAGE": str(request.end_page or 0),
                    "ACTIVITY_PAGE_SIZE": str(request.page_size),
                    "ACTIVITY_RESUME": str(request.resume).lower(),
                }
            },
        }
    )


@app.post("/v1/intel/xhs-crawl", dependencies=[Depends(require_admin)])
def xhs_crawl(request: XhsCrawlRequest):
    return task_request(
        {
            "name": "xhs crawl",
            "kind": "oneshot",
            "command": ["python", "-m", "app.crawl_xhs"],
            "timeout_seconds": 1800,
            "metadata": {
                "environment": {
                    "XHS_QUERY": request.query,
                    "XHS_COOKIE": request.cookie,
                    "XHS_LIMIT": str(request.limit),
                }
            },
        }
    )


@app.get("/v1/napcat/webui", dependencies=[Depends(require_admin)])
def napcat_webui():
    token = os.getenv("NAPCAT_WEBUI_TOKEN", "")
    return {"url": f"/webui/?token={urllib.parse.quote(token)}"}


@app.post("/v1/intel/qq-monitor", dependencies=[Depends(require_admin)])
def qq_monitor(request: QqMonitorRequest):
    return task_request(
        {
            "name": "QQ group monitor",
            "kind": "service",
            "command": ["python", "-m", "app.qq_watcher"],
            "restart_policy": request.restart_policy,
            "metadata": {
                "environment": {
                    "QQ_GROUP_IDS": ",".join(request.group_ids),
                    "QQ_BUFFER_DIR": "/workspace/intel-buffer/qq",
                }
            },
        }
    )


def minio_client() -> Minio:
    return Minio(
        os.getenv("MINIO_ENDPOINT", "minio:9000"),
        access_key=os.getenv("MINIO_ROOT_USER", "baoyan"),
        secret_key=os.getenv("MINIO_ROOT_PASSWORD", ""),
        secure=False,
    )


def ensure_bucket(client: Minio, bucket: str) -> None:
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)


@app.post("/v1/files", dependencies=[Depends(require_admin)])
async def upload_file(file: UploadFile = File(...)):
    client = minio_client()
    ensure_bucket(client, "baoyan")
    name = f"materials/{uuid4()}-{file.filename}"
    content = await file.read(25*1024*1024+1)
    if len(content)>25*1024*1024:
        raise HTTPException(413,'单个文件不能超过 25MB')
    client.put_object("baoyan", name, BytesIO(content), len(content), file.content_type)
    return {
        "object": name,
        "filename": file.filename,
        "content_type": file.content_type,
        "size": len(content),
    }


@app.post("/v1/mail/draft", dependencies=[Depends(require_admin)])
def create_draft(request: DraftRequest):
    message = EmailMessage()
    message["From"] = str(config_value("baoyan.smtp.from"))
    message["To"] = f"{request.recipient_name} <{request.recipient_email}>"
    message["Subject"] = request.subject
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid()
    message.set_content(request.content)
    for attachment in request.attachments:
        message.add_attachment(
            base64.b64decode(attachment.content_base64),
            maintype="application",
            subtype="octet-stream",
            filename=attachment.filename,
        )
    raw = message.as_bytes()
    client = minio_client()
    ensure_bucket(client, "baoyan")
    object_name = f"drafts/{uuid4()}.eml"
    client.put_object("baoyan", object_name, BytesIO(raw), len(raw), "message/rfc822")

    imap_host = str(config_value("baoyan.smtp.imap-host"))
    if imap_host:
        mail = imaplib.IMAP4_SSL(imap_host, int(config_value("baoyan.smtp.imap-port", 993)))
        mail.login(
            str(config_value("baoyan.smtp.username")),
            str(config_value("baoyan.smtp.password")),
        )
        folder = str(config_value("baoyan.smtp.draft-folder", "Drafts"))
        mail.append(folder, r"(\Draft)", imaplib.Time2Internaldate(time.time()), raw)
        mail.logout()
    return {"ok": True, "object": object_name, "eml_base64": base64.b64encode(raw).decode()}


import sys
from features import install_features
install_features(app, sys.modules[__name__])

