"""One rendering path for the browser, Agent previews and MIME drafts."""
import json
import re
from copy import deepcopy
from fastapi import HTTPException
from advisor_contract import flat

TOKEN=re.compile(r'\{\{\s*([^{}]+?)\s*\}\}')
BINDINGS={key:key for key in ('name','title','school','department','institute','email','homepage','photo','bio','category','research_directions')}
BINDINGS['direction']='research_directions'  # Compatibility with already-saved templates only.

def lookup(parameters,key):
    if key in parameters:return parameters[key]
    value=parameters
    for part in key.split('.'):
        if not isinstance(value,dict) or part not in value:return None
        value=value[part]
    return value

def display(value):
    if isinstance(value,list):return '、'.join(display(item) for item in value)
    if isinstance(value,dict):return json.dumps(value,ensure_ascii=False)
    return '' if value is None else str(value)

def empty(value):return value is None or value==[] or (isinstance(value,str) and not value.strip())

def context_for(advisor,parameters,recipient_name=None,recipient_email=None):
    result=deepcopy(parameters)
    if advisor:
        result={k:v for k,v in result.items() if k!='advisor' and not k.startswith('advisor.') and k not in BINDINGS}
        result.update({k:v for k,v in advisor.items() if k not in ('metadata','raw','raw_list','raw_detail')})
        result['advisor']=advisor
        for name,key in BINDINGS.items():result[name]=advisor.get(key)
    result['recipient_name']=recipient_name if recipient_name is not None else (advisor or {}).get('name','')
    result['recipient_email']=recipient_email if recipient_email is not None else (advisor or {}).get('email','')
    return result

def render_fields(subject,content,parameters,advisor=None,strict=False):
    names=list(dict.fromkeys(TOKEN.findall(subject+'\n'+content)))
    variables=[];missing=[]
    for name in names:
        value=lookup(parameters,name);absent=empty(value)
        field=name[8:] if name.startswith('advisor.') else (name if advisor and name in advisor else BINDINGS.get(name))
        automatic=bool(advisor) and field is not None
        variables.append({'name':name,'value':value,'display':display(value),'automatic':automatic,'source':'advisor.'+field if automatic else None,'missing':absent})
        if absent:missing.append(name)
    if strict and missing:raise HTTPException(422,{'message':'模板参数未齐全','parameters':missing})
    def replace(match):
        value=lookup(parameters,match.group(1).strip())
        return match.group(0) if empty(value) else display(value)
    return {'subject':TOKEN.sub(replace,subject),'content':TOKEN.sub(replace,content),'variables':variables,'missing':missing,'parameters':{v['name']:v['value'] for v in variables}}

def prepare(core,request,strict=False,require_recipient=True):
    advisor=flat(core.get_entity('advisors',request.advisor_id)) if request.advisor_id else None
    template=core.get_entity('templates',request.template_id)['data'] if request.template_id else {}
    parameters=context_for(advisor,request.parameters,request.recipient_name,request.recipient_email)
    subject=request.subject if request.subject is not None else str(template.get('subject') or '')
    content=request.content if request.content is not None else str(template.get('content') or '')
    result=render_fields(subject,content,parameters,advisor,strict)
    name=parameters['recipient_name'];email=parameters['recipient_email'];errors=[]
    if require_recipient:
        if not str(name).strip():errors.append('请填写收件人姓名或选择导师')
        if not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+',str(email)):errors.append('导师邮箱缺失或收件邮箱格式不正确')
    if not result['subject'].strip():errors.append('请填写邮件主题，或在模板中设置主题')
    if not result['content'].strip():errors.append('请填写邮件正文，或选择正文模板')
    if len(result['subject'])>500:errors.append('邮件主题不能超过 500 字符')
    if len(result['content'])>200000:errors.append('邮件正文过长')
    if any('\n' in str(value) or '\r' in str(value) for value in (name,email,result['subject'])):errors.append('邮件头不能含换行符')
    if strict and errors:raise HTTPException(422,'；'.join(errors))
    return {**result,'recipient_name':name,'recipient_email':email,'advisor_id':str(request.advisor_id) if request.advisor_id else None,'template_id':str(request.template_id) if request.template_id else None,'errors':errors}
