from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel, Field, field_validator

from apis.xhs_pc_apis import XHS_Apis
from xhs_utils.data_util import handle_note_info
from xhs_utils.cookie_util import trans_cookies


app = FastAPI(
    title="Baoyan XHS Collector",
    version="1.0.0",
    description="HTTP adapter around the pinned Spider_XHS implementation.",
)
xhs_api = XHS_Apis()


@app.exception_handler(RequestValidationError)
async def invalid_request(_request, exc):
    # Pydantic's default response includes the rejected Cookie value.
    return JSONResponse(status_code=422, content={'detail': [
        {'loc': list(error['loc']), 'msg': error['msg'], 'type': error['type']}
        for error in exc.errors()
    ]})


class CookieRequest(BaseModel):
    cookie: str = Field(min_length=20, repr=False)

    @field_validator('cookie')
    @classmethod
    def validate_cookie(cls, value: str) -> str:
        cookies = trans_cookies(value)
        if not cookies.get('a1') or not cookies.get('web_session'):
            raise ValueError('Cookie 必须包含 a1 和 web_session，请复制已登录网页请求的完整 Cookie')
        return '; '.join(f'{name}={content}' for name, content in cookies.items())


class SearchRequest(CookieRequest):
    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=10, ge=1, le=100)
    sort: int = Field(default=0, ge=0, le=4)
    note_type: int = Field(default=0, ge=0, le=2)
    time_range: int = Field(default=0, ge=0, le=3)


class NoteRequest(CookieRequest):
    url: str = Field(min_length=10)


def search_failure(message: str) -> HTTPException:
    if any(text in message for text in ('没有权限', '登录', '登陆', '权限不足')):
        return HTTPException(status_code=403, detail={
            'code': 'XHS_ACCESS_DENIED',
            'message': '小红书拒绝访问。请先确认浏览器内能正常搜索，再复制该搜索请求的完整 Cookie；若仍失败，可能是会话或接口限制。',
        })
    return HTTPException(status_code=502, detail={
        'code': 'XHS_UPSTREAM_FAILED', 'message': '小红书搜索请求失败，请检查登录状态和采集服务连接。',
    })


def _note_info(url: str, cookie: str) -> dict[str, Any]:
    success, message, data = xhs_api.get_note_info(url, cookie)
    if not success or not data:
        raise RuntimeError(str(message))
    item = (data.get("data") or {}).get("items") or []
    if not item:
        raise RuntimeError("note response did not contain an item")
    # The feed API provides note_card but no URL; the converter expects one.
    note = handle_note_info({**item[0], 'url': url})
    note['id'] = str(item[0].get('id') or note['note_id'])
    note['author'] = note.get('nickname', '')
    note['content_status'] = 'complete'
    note['raw_response'] = data
    note["url"] = url
    return note


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "xhs"}


@app.post("/v1/notes/search")
def search_notes(request: SearchRequest) -> dict[str, Any]:
    success, message, notes = xhs_api.search_some_note(
        request.query,
        request.limit,
        request.cookie,
        request.sort,
        request.note_type,
        request.time_range,
    )
    if not success:
        raise search_failure(str(message))

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for note in notes or []:
        if note.get("model_type") != "note" or not note.get("id"):
            continue
        note_id = str(note["id"])
        if note_id in seen:
            continue
        seen.add(note_id)
        url = (
            f"https://www.xiaohongshu.com/explore/{note_id}"
            f"?xsec_token={note.get('xsec_token', '')}"
        )
        try:
            detail = _note_info(url, request.cookie)
            detail['search_result'] = note
            items.append(detail)
        except Exception as exc:
            logger.warning("XHS note detail failed for {} ({})", note_id, type(exc).__name__)
            items.append(
                {
                    "id": note_id,
                    "title": (note.get('note_card') or {}).get("display_title") or note.get("display_title") or "",
                    "url": url,
                    "detail_error": str(exc),
                    "content_status": "detail_failed",
                }
            )
        if len(items) >= request.limit:
            break
    return {"query": request.query, "count": len(items), "items": items}


@app.post("/v1/notes/detail")
def note_detail(request: NoteRequest) -> dict[str, Any]:
    try:
        return _note_info(request.url, request.cookie)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"XHS note failed: {exc}") from exc

