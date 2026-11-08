from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
from pathlib import Path
import time
from .intel_ingest import upload_attachment, download_remote_attachment, message_envelope


def note_attachments(note):
    snapshot=json.dumps(note,ensure_ascii=False,indent=2).encode()
    identity=str(note.get('id') or note.get('note_id') or 'note')
    result=[upload_attachment(snapshot,identity+'-完整帖子.json','application/json',note.get('url') or note.get('note_url') or '')]
    for index,url in enumerate(dict.fromkeys(note.get('image_list') or [])):
        binary,mime=download_remote_attachment(url,('xhscdn.com','xiaohongshu.com'))
        extension={'image/jpeg':'jpg','image/png':'png','image/webp':'webp','image/gif':'gif'}.get(mime,'bin')
        result.append(upload_attachment(binary,identity+f'-图片{index+1}.'+extension,mime,url))
    return result


XHS_API = os.environ["XHS_API_URL"].rstrip("/")
PLATFORM = os.environ["PLATFORM_API_URL"].rstrip("/")
PASSWORD = os.environ["PLATFORM_ADMIN_PASSWORD"]


def post_json(url: str, payload: dict):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 403:
            raise RuntimeError('小红书拒绝访问：请确认浏览器可以正常搜索，并重新复制该搜索请求的完整 Cookie。若仍失败，可能是会话或接口限制。') from None
        if exc.code == 422:
            raise RuntimeError('小红书采集参数无效：Cookie 必须包含 a1 和 web_session，关键词不能为空。') from None
        raise RuntimeError(f'小红书采集服务请求失败（HTTP {exc.code}）') from None


def main() -> None:
    result = post_json(
        XHS_API + "/v1/notes/search",
        {
            "query": os.environ["XHS_QUERY"],
            "cookie": os.environ["XHS_COOKIE"],
            "limit": int(os.getenv("XHS_LIMIT", "10")),
        },
    )
    items = []
    buffer_dir = Path(os.getenv("XHS_BUFFER_DIR", "/workspace/intel-buffer/xhs"))
    buffer_dir.mkdir(parents=True, exist_ok=True)
    for note in result.get("items", []):
        items.append(
            {
                "source": "xiaohongshu",
                "source_id": str(note.get("id") or note.get('note_id') or ""),
                "title": note.get("title") or "",
                "content": note.get("desc") or "",
                "author": note.get("author") or "",
                "url": note.get("url") or "",
                "buffer_key": note.get("url") or "",
                "metadata": note,
            }
        )
    (buffer_dir / f"{time.strftime('%Y%m%d-%H%M%S')}.json").write_text(
        json.dumps(result.get("items", []), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    count=0
    for item in items:
        if not item['source_id']: item['source_id']=item['url']
        payload=message_envelope(item['source'],item['source_id'],item['title'],item['content'],item['metadata'],note_attachments(item['metadata']))
        req=urllib.request.Request(PLATFORM+'/v1/intel/buffer',data=json.dumps(payload,ensure_ascii=False).encode(),headers={'Content-Type':'application/json','X-Admin-Password':PASSWORD})
        with urllib.request.urlopen(req,timeout=60) as response: json.loads(response.read())
        count+=1
    print(f'xhs crawl imported {count} items into persistent cold storage')


if __name__ == "__main__":
    main()

