from types import SimpleNamespace
import time
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import mail_oauth

def test_oauth_rejects_unconfigured_application_without_network():
    app=FastAPI()
    core=SimpleNamespace(require_admin=lambda:None,config_value=lambda *args:{})
    mail_oauth.install(app,core)
    with TestClient(app) as client:
        response=client.post('/v1/mail/oauth/device')
    assert response.status_code==409

def test_oauth_endpoint_cannot_escape_microsoft_host():
    with pytest.raises(HTTPException):
        mail_oauth.endpoint({'oauth-tenant':'../../evil'},'token')

def test_expired_token_refresh_persists_rotated_refresh_token(monkeypatch):
    document={'baoyan':{'smtp':{'username':'test@example.com'}}}
    saved=[]
    core=SimpleNamespace(read_config=lambda:document,write_config=saved.append)
    monkeypatch.setattr(mail_oauth,'send',lambda *args:{'access_token':'new-token','refresh_token':'rotated-token','expires_in':3600})
    result=mail_oauth.refreshed(core,{'refresh-token':'old-token','oauth-client-id':'client','token-expires-at':0})
    assert result['access-token']=='new-token'
    assert result['refresh-token']=='rotated-token'
    assert result['token-expires-at']>time.time()
    assert saved and saved[0]['baoyan']['smtp']['username']=='test@example.com'
