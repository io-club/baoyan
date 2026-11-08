"""Canonical advisor fields and compatibility migration for older imports."""
from copy import deepcopy
from uuid import UUID
from fastapi import Depends,Query
from psycopg.types.json import Jsonb

ALIASES={'title':('职称',),'institute':('center',),'research_directions':('研究方向',),'bio':('简介','个人简介')}
RANKS={'教授','副教授','讲师','助教','助理教授','特聘教授','讲席教授','研究员','副研究员','助理研究员','博士后'}

def normalize_advisor(payload,fill_empty=True):
    outer=deepcopy(payload);nested=outer.pop('data',None)
    inner=normalize_advisor(nested,fill_empty=False) if isinstance(nested,dict) else {}
    result={**inner,**outer}
    if fill_empty:
        for key,value in inner.items():
            if result.get(key) in (None,'',[]) and value not in (None,'',[]):result[key]=value
    if nested is not None and not isinstance(nested,dict):result.setdefault('legacy_data',nested)
    for key,names in ALIASES.items():
        if key not in result or (fill_empty and result[key] in (None,'',[])):
            for name in names:
                if result.get(name) not in (None,'',[]):result[key]=result[name];break
    if ('title' not in result or (fill_empty and not result.get('title'))) and isinstance(result.get('category'),str) and result.get('category') in RANKS:result['title']=result['category']
    if isinstance(result.get('research_directions'),str):result['research_directions']=[result['research_directions']] if result['research_directions'].strip() else []
    return result

def normalize_template(payload):
    result=deepcopy(payload);legacy=result.pop('data',None)
    if isinstance(legacy,dict):
        for key in ('name','description','subject','content'):
            if key in legacy and key not in result:result[key]=legacy[key]
        metadata={**{k:v for k,v in legacy.items() if k not in ('name','description','subject','content')},**(result.get('metadata') or {})}
        result['metadata']=metadata
    elif legacy is not None:result.setdefault('legacy_data',legacy)
    return result

def normalize(resource,payload,patch=False):
    if resource=='advisors':return normalize_advisor(payload,fill_empty=not patch)
    if resource=='templates':return normalize_template(payload)
    return payload

def flat(record):
    return {**normalize_advisor(record['data'],fill_empty=False),'id':record['id'],'created_at':record.get('created_at'),'updated_at':record.get('updated_at')}

def initialize(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS platform.payload_migrations (
      resource TEXT NOT NULL,id UUID NOT NULL,data JSONB NOT NULL,migrated_at TIMESTAMPTZ DEFAULT now(),PRIMARY KEY(resource,id))''')
    rows=conn.execute("SELECT resource,id,data FROM platform.entities WHERE resource IN ('advisors','templates') AND data ? 'data' FOR UPDATE").fetchall()
    for row in rows:
        payload=normalize(row['resource'],row['data'])
        conn.execute('INSERT INTO platform.payload_migrations(resource,id,data) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING',(row['resource'],row['id'],Jsonb(row['data'])))
        conn.execute('UPDATE platform.entities SET data=%s,updated_at=now() WHERE resource=%s AND id=%s',(Jsonb(payload),row['resource'],row['id']))
    # Normalize field mappings as well, so examples never instruct clients to read legacy paths.
    import re
    rows=conn.execute("SELECT id,data FROM platform.entities WHERE resource='templates'").fetchall()
    binding={'name':'advisor.name','school':'advisor.school','title':'advisor.title','department':'advisor.department','institute':'advisor.institute','direction':'advisor.research_directions'}
    for row in rows:
        value=deepcopy(row['data']);meta=value.get('metadata')
        if not isinstance(meta,dict):continue
        meta['placeholders']=list(dict.fromkeys(re.findall(r'\{\{\s*([^{}]+?)\s*\}\}',str(value.get('subject',''))+'\n'+str(value.get('content','')))))
        meta['field_mapping']={k:binding.get(k,v) for k,v in (meta.get('field_mapping') if isinstance(meta.get('field_mapping'),dict) else {}).items()}
        if isinstance(meta.get('tips'),list):meta['tips']=[tip for tip in meta['tips'] if 'data.' not in str(tip)]
        if value!=row['data']:conn.execute('UPDATE platform.entities SET data=%s WHERE resource=\'templates\' AND id=%s',(Jsonb(value),row['id']))

def install(app,core):
    secure=[Depends(core.require_admin)]
    @app.get('/v1/advisors',dependencies=secure)
    def advisors(q:str='',limit:int=Query(default=50,ge=1,le=1000),offset:int=Query(default=0,ge=0),school:str='',department:str='',institute:str='',category:str=''):
        result=core.list_entities('advisors',q,limit,offset,None,None,school,department,institute,category)
        return {**result,'items':[flat(row) for row in result['items']]}
    @app.get('/v1/advisors/{advisor_id}',dependencies=secure)
    def advisor(advisor_id:UUID):return flat(core.get_entity('advisors',advisor_id))
