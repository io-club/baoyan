"""Append platform instructions after Canvas resolves the selected agent/profile."""
import hmac
import json
import os
import urllib.request
import urllib.error
import asyncio
from fastapi import HTTPException,Request,Depends
from fastapi.responses import Response

MARKER='BAOYAN_PLATFORM_API_V4'
SYSTEM_PROMPT='''<BAOYAN_PLATFORM_API_V4>
你协助用户在保研平台完成信息整理、内容撰写和业务操作；沿用 OpenHands 自带的工具、执行与验证规则。

遵循用户当前任务和后续纠正。接口能力说明不是待办事项；完成任务不等于扩展任务。不要自行增加交付物、脚本、数据迁移或业务流程。用户要求修改已有内容时，保留其未要求改变的部分；要求已明确就继续完成，不反复要求确认。需要澄清时只问真正缺失且影响结果的信息。

业务 API 基址为 http://gateway:8080/api/platform，任务 API 基址为 http://gateway:8080/api/tasks。鉴权头 X-Agent-Key 从环境变量 BAOYAN_AGENT_API_KEY 读取，不打印凭据。
调用前按需阅读 /home/openhands/workspace/api-docs/AGENT_API_CATALOG.md 和 PLATFORM_API.md 的相关章节；通过 API 获取当前样例，区分响应包裹、业务字段与模板变量。记录之间的字段名、类型和可用值可能不同，以实际返回数据为准，不凭其他记录或旧对话推断。

模板仅引用所需且实际存在的字段；不同来源可用不同字段名，不为统一参数而改名、添字段或改写导师数据。撰写并保存模板与为具体对象生成草稿是不同任务，按用户所要求的范围执行。
业务“入库”通过平台 API 完成，SQLite/本地文件只能作缓存或导出。更新现有记录用文档规定的 PATCH 保留 ID，不用删除重建代替更新。
只对实际执行并核对过的结果报告成功；API 成功不等于内容正确。缺失、冲突或失败应如实说明，不编造取值或用解释代替修正。
邮件操作只创建草稿，不发送；不得泄露 Cookie、密码或令牌，不直连业务数据库、队列或对象存储。
</BAOYAN_PLATFORM_API_V4>'''


def strip_platform_policy(text):
    import re
    return re.sub(r'<BAOYAN_PLATFORM_API_V\d+>.*?</BAOYAN_PLATFORM_API_V\d+>', '', text, flags=re.S).strip()


def enrich_launch(payload):
    # Replace only our versioned blocks; retain runtime context, profiles and user instructions.
    for source in ('agent_settings','agent'):
        settings=payload.get(source) or {}
        context=settings.get('agent_context') or {}
        if 'system_message_suffix' in context:
            context['system_message_suffix']=strip_platform_policy(context['system_message_suffix'] or '')
    additions=payload.get('agent_launch_additions') or {}
    payload['agent_launch_additions']=additions
    old=strip_platform_policy(additions.get('system_message_suffix_append') or '')
    additions['system_message_suffix_append']=(old+'\n'+SYSTEM_PROMPT).strip()
    return payload

def install(app,require_admin):
    @app.get('/v1/agent-guidance',dependencies=[Depends(require_admin)])
    def guidance():return {'version':MARKER,'system_prompt':SYSTEM_PROMPT}

    @app.post('/internal/agent/conversations')
    async def create_conversation(request:Request):
        key=os.getenv('OPENHANDS_LOCAL_BACKEND_API_KEY','')
        if not key or not hmac.compare_digest(request.headers.get('X-Session-API-Key',''),key):
            raise HTTPException(401,'会话认证失败')
        payload=enrich_launch(await request.json())
        target=os.getenv('OPENHANDS_CONTROL_URL','http://local-web/agent').rstrip('/')+'/api/conversations'
        if request.url.query:target+='?'+request.url.query
        req=urllib.request.Request(target,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','X-Session-API-Key':key})
        def forward():
            try:
                with urllib.request.urlopen(req,timeout=120) as result:
                    return Response(result.read(),status_code=result.status,media_type='application/json')
            except urllib.error.HTTPError as exc:
                return Response(exc.read(),status_code=exc.code,media_type='application/json')
        return await asyncio.to_thread(forward)
