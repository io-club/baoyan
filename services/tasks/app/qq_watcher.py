from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import time
import sqlite3
import urllib.request
from .config import current_admin_password
from .qq_media import message_text, media_parts, download_part
from .intel_ingest import upload_attachment, message_envelope

import websockets


GROUP_IDS = {item.strip() for item in os.environ.get("QQ_GROUP_IDS", "").split(",") if item.strip()}
BUFFER_DIR = Path(os.environ.get("QQ_BUFFER_DIR", "/workspace/intel-buffer/qq"))
WS_URL = os.environ.get("QQ_ONEBOT_WS_URL", "ws://napcat:3001")
WAKE = None


def outbox():
    BUFFER_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(BUFFER_DIR/'outbox.sqlite3')
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('CREATE TABLE IF NOT EXISTS outbox (id TEXT PRIMARY KEY,payload TEXT NOT NULL)')
    columns = {row[1] for row in db.execute('PRAGMA table_info(outbox)')}
    if 'next_attempt' not in columns:
        db.execute('ALTER TABLE outbox ADD COLUMN next_attempt REAL NOT NULL DEFAULT 0')
    if 'attempts' not in columns:
        db.execute('ALTER TABLE outbox ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0')
    db.commit()
    return db


def enqueue(event):
    with outbox() as db:
        key=f"{event['group_id']}:{event['message_id']}"
        db.execute('INSERT OR IGNORE INTO outbox(id,payload) VALUES (?,?)',(key,json.dumps(event,ensure_ascii=False)))
    if WAKE is not None:
        WAKE.set()


def flush():
    with outbox() as db:
        pending=db.execute('SELECT id,payload,attempts FROM outbox WHERE next_attempt<=? ORDER BY rowid LIMIT 100',(time.time(),)).fetchall()
    for key,raw,attempts in pending:
        event=json.loads(raw)
        try:
            attachments=event.setdefault('attachments',[])
            for part in media_parts(event):
                if any(a.get('source_key')==part['key'] for a in attachments):continue
                binary,name,mime,url=download_part(part,event['group_id'])
                attachment=upload_attachment(binary,name,mime,url)
                attachments.append({**attachment,'source_key':part['key']})
                # Persist each uploaded object before committing the message.
                with outbox() as db:db.execute('UPDATE outbox SET payload=? WHERE id=?',(json.dumps(event,ensure_ascii=False),key))
            payload=message_envelope('qq',key,f"QQ群 {event['group_id']} · {event['sender']}",message_text(event),
                {k:v for k,v in event.items() if k not in {'attachments','images'}},attachments)
            from .qq_file_identity import canonical_file_payload
            with outbox() as db:payload=canonical_file_payload(db,key,event,payload)
            request=urllib.request.Request(os.environ['PLATFORM_API_URL'].rstrip('/')+'/v1/intel/buffer',data=json.dumps(payload,ensure_ascii=False).encode(),headers={'Content-Type':'application/json','X-Admin-Password':current_admin_password()})
            with urllib.request.urlopen(request,timeout=180) as response:
                saved=json.loads(response.read())
            if len(saved.get('data',{}).get('attachments',[]))!=len(payload['attachments']):
                raise RuntimeError('Attachment manifest incomplete')
            with outbox() as db:
                db.execute('DELETE FROM outbox WHERE id=?',(key,))
            print(f'Archived QQ message: id={key}, attachments={len(attachments)}',flush=True)
        except Exception as exc:
            delay=min(300,3*(2**min(attempts,7)))
            with outbox() as db:
                db.execute('UPDATE outbox SET payload=?,attempts=attempts+1,next_attempt=? WHERE id=?',
                    (json.dumps(event,ensure_ascii=False),time.time()+delay,key))
            print(f'QQ archive retry scheduled: id={key}, reason={type(exc).__name__}',flush=True)


async def sender():
    while True:
        WAKE.clear()
        try: await asyncio.to_thread(flush)
        except Exception as exc: print('Cold-storage delivery pending:',type(exc).__name__,flush=True)
        try:
            await asyncio.wait_for(WAKE.wait(),timeout=3)
        except asyncio.TimeoutError:
            pass


async def run() -> None:
    global WAKE
    WAKE = asyncio.Event()
    BUFFER_DIR.mkdir(parents=True, exist_ok=True)
    asyncio.create_task(sender())
    async for connection in websockets.connect(WS_URL):
        try:
            async for raw in connection:
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                is_message=payload.get('post_type')=='message' and payload.get('message_type')=='group'
                is_file=payload.get('post_type')=='notice' and payload.get('notice_type')=='group_upload'
                if not (is_message or is_file):
                    continue
                group_id = str(payload.get("group_id", ""))
                if group_id not in GROUP_IDS:
                    continue
                event = {
                    "source": "qq",
                    "received_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    "group_id": group_id,
                    "sender": payload.get("sender", {}).get("nickname", ""),
                    "sender_id": payload.get("user_id"),
                    "message": payload.get("raw_message", ""),
                    "message_id": payload.get("message_id") or ('upload:'+str(payload.get('file',{}).get('id'))),
                    "raw": payload,
                }
                enqueue(event)
                print(f"Buffered QQ message: group={group_id}, id={event['message_id']}",flush=True)
        except Exception as exc:
            print(f"QQ watcher connection lost: {exc}", flush=True)
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(run())

