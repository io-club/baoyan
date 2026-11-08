"""Microsoft device authorization and offline refresh for IMAP drafts only."""
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from uuid import uuid4
from fastapi import Depends, HTTPException

SCOPE='https://outlook.office.com/IMAP.AccessAsUser.All offline_access'

def endpoint(settings,action):
    tenant=str(settings.get('oauth-tenant') or 'common')
    if not re.fullmatch(r'[A-Za-z0-9.-]+',tenant): raise HTTPException(422,'Microsoft 租户格式错误')
    return f'https://login.microsoftonline.com/{tenant}/oauth2/v2.0/{action}'

def send(settings,action,payload):
    req=urllib.request.Request(endpoint(settings,action),data=urllib.parse.urlencode(payload).encode(),headers={'Content-Type':'application/x-www-form-urlencoded'})
    try:
        with urllib.request.urlopen(req,timeout=20) as r: return json.loads(r.read())
    except urllib.error.HTTPError as exc:
        try: return json.loads(exc.read())
        except Exception: raise HTTPException(502,'Microsoft 授权服务请求失败') from exc
    except OSError as exc: raise HTTPException(502,'无法连接 Microsoft 授权服务') from exc

def persist(core,token):
    document=core.read_config();smtp=document.setdefault('baoyan',{}).setdefault('smtp',{})
    smtp['access-token']=token['access_token']
    if token.get('refresh_token'):smtp['refresh-token']=token['refresh_token']
    smtp['token-expires-at']=int(time.time())+int(token.get('expires_in',3600))
    if not smtp.get('imap-host'):smtp['imap-host']='outlook.office365.com'
    if not smtp.get('imap-port'):smtp['imap-port']=993
    core.write_config(document)
    return smtp

def refreshed(core,settings):
    if settings.get('refresh-token') and settings.get('oauth-client-id') and float(settings.get('token-expires-at',0))<time.time()+120:
        token=send(settings,'token',{'client_id':settings['oauth-client-id'],'grant_type':'refresh_token','refresh_token':settings['refresh-token'],'scope':SCOPE})
        if 'access_token' not in token: raise HTTPException(409,'Outlook 授权已失效，请重新授权')
        return persist(core,token)
    return settings

def install(app,core):
    sessions={}
    @app.post('/v1/mail/oauth/device',dependencies=[Depends(core.require_admin)])
    def device():
        settings=core.config_value('baoyan.smtp',{})
        if not settings.get('oauth-client-id'): raise HTTPException(409,'请先填写你在 Microsoft Entra 注册的公共客户端 Client ID，并开启设备代码授权')
        result=send(settings,'devicecode',{'client_id':settings['oauth-client-id'],'scope':SCOPE})
        if 'device_code' not in result: raise HTTPException(502,'Microsoft 未接受此应用的设备授权请求，请检查 Client ID 与租户')
        now=time.time()
        for sid in list(sessions):
            if sessions[sid]['expires']<now: del sessions[sid]
        sid=str(uuid4());sessions[sid]={'settings':settings,'code':result['device_code'],'expires':now+int(result['expires_in']),'interval':int(result.get('interval',5)),'next_poll':now}
        return {'session_id':sid,'verification_uri':result['verification_uri'],'user_code':result['user_code'],'expires_in':result['expires_in'],'interval':result.get('interval',5)}

    @app.post('/v1/mail/oauth/device/{session_id}',dependencies=[Depends(core.require_admin)])
    def poll(session_id:str):
        session=sessions.get(session_id)
        if not session or session['expires']<time.time():
            sessions.pop(session_id,None);raise HTTPException(410,'授权请求已过期，请重新开始')
        if time.time()<session['next_poll']: return {'status':'pending','interval':session['interval']}
        session['next_poll']=time.time()+session['interval']
        token=send(session['settings'],'token',{'client_id':session['settings']['oauth-client-id'],'grant_type':'urn:ietf:params:oauth:grant-type:device_code','device_code':session['code']})
        if token.get('error') in {'authorization_pending','slow_down'}:
            if token['error']=='slow_down':session['interval']+=5
            return {'status':'pending','interval':session['interval']}
        if 'access_token' not in token:
            sessions.pop(session_id,None);raise HTTPException(409,'Microsoft 授权未完成或被拒绝，请重新授权')
        persist(core,token);sessions.pop(session_id,None)
        return {'status':'authorized'}
