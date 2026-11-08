from __future__ import annotations

from fastapi.testclient import TestClient

from server import app


class FakeXhsApi:
    def search_some_note(self, *_args, **_kwargs):
        return True, "ok", [
            {"id": "n1", "model_type": "note", "xsec_token": "t1", "display_title": "A"},
            {"id": "n1", "model_type": "note", "xsec_token": "t1", "display_title": "duplicate"},
        ]


def test_health() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "xhs"


def test_search_deduplicates(monkeypatch) -> None:
    monkeypatch.setattr("server.xhs_api", FakeXhsApi())
    monkeypatch.setattr(
        "server._note_info",
        lambda url, _cookie: {"id": "n1", "title": "A", "url": url},
    )
    response = TestClient(app).post(
        "/v1/notes/search",
        json={"query": "保研", "cookie": "a1=12345678901234567890; web_session=test-session", "limit": 5},
    )
    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["items"][0]["url"].startswith(
        "https://www.xiaohongshu.com/explore/n1"
    )


def test_cookie_parser_handles_mixed_spacing_and_equals():
    from xhs_utils.cookie_util import trans_cookies
    assert trans_cookies('Cookie: a1=one;web_session=two==; gid=three; ') == {
        'a1': 'one', 'web_session': 'two==', 'gid': 'three',
    }


def test_missing_session_rejected_before_upstream():
    response = TestClient(app).post('/v1/notes/search', json={
        'query': '保研', 'cookie': 'a1=12345678901234567890',
    })
    assert response.status_code == 422
    assert '12345678901234567890' not in response.text


def test_access_denied_is_explicit(monkeypatch):
    class DeniedApi:
        def search_some_note(self, *args):
            return False, '您当前登录的账号没有权限访问', []
    monkeypatch.setattr('server.xhs_api', DeniedApi())
    response = TestClient(app).post('/v1/notes/search', json={
        'query': '保研', 'cookie': 'a1=12345678901234567890; web_session=test-session',
    })
    assert response.status_code == 403
    assert response.json()['detail']['code'] == 'XHS_ACCESS_DENIED'


def test_real_feed_shape_without_url_keeps_full_text(monkeypatch):
    from server import _note_info
    body = '完整正文\n' * 200
    card = {
        'type': 'normal', 'user': {'user_id': 'u1', 'nickname': '作者', 'avatar': ''},
        'title': '标题', 'desc': body, 'interact_info': {
            'liked_count': '1', 'collected_count': '0', 'comment_count': '0', 'share_count': '0',
        }, 'image_list': [], 'tag_list': [], 'time': 1793887577376,
    }
    class FeedApi:
        def get_note_info(self, *_args):
            return True, 'ok', {'data': {'items': [{'id': 'n1', 'note_card': card}]}}
    monkeypatch.setattr('server.xhs_api', FeedApi())
    result = _note_info('https://www.xiaohongshu.com/explore/n1', 'unused')
    assert result['desc'] == body
    assert result['id'] == 'n1'
    assert result['content_status'] == 'complete'
    assert result['author'] == '作者'

