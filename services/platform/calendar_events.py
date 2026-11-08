"""Date-indexed calendar milestones; an activity is never expanded across its duration."""
from datetime import date,datetime,timedelta,timezone
from uuid import UUID
from fastapi import HTTPException

ZONE=timezone(timedelta(hours=8))
LABELS={'registration_start':'报名开始','deadline':'报名截止','activity_start':'活动开始'}
FIELDS={'registration_start':('registration_start','sign_up_start'),'deadline':('deadline','sign_up_end'),'activity_start':('activity_start','start_time')}
SCHEMA='''
CREATE TABLE IF NOT EXISTS platform.activity_events (
 activity_id UUID REFERENCES platform.entities(id) ON DELETE CASCADE,
 event_type TEXT NOT NULL,event_at TIMESTAMPTZ NOT NULL,local_date DATE NOT NULL,
 PRIMARY KEY(activity_id,event_type)
);
CREATE INDEX IF NOT EXISTS activity_events_date_idx ON platform.activity_events(local_date,event_at,activity_id,event_type);
CREATE TABLE IF NOT EXISTS platform.calendar_preferences (
 singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK(singleton),
 show_untagged BOOLEAN NOT NULL DEFAULT TRUE,countdown_untagged BOOLEAN NOT NULL DEFAULT FALSE
);
INSERT INTO platform.calendar_preferences(singleton) VALUES(TRUE) ON CONFLICT DO NOTHING;
'''

def milestones(data):
    from features import parse_deadline
    raw=data.get('raw') or {};result={}
    for kind,fields in FIELDS.items():
        explicit=fields[0] in data
        for container in ((data,) if explicit else (data,raw)):
            for field in ((fields[0],) if explicit else fields):
                value=container.get(field)
                if value:
                    text=str(value).strip().replace('/','-').replace('年','-').replace('月','-').replace('日','')
                    rollover=' 24:' in text or 'T24:' in text
                    parsed=parse_deadline(text.replace(' 24:',' 00:').replace('T24:','T00:'))
                    if parsed:
                        if rollover:parsed+=timedelta(days=1)
                        if len(text)==10 and kind!='deadline':parsed=parsed.replace(hour=0,minute=0,second=0)
                        result[kind]=parsed;break
            if kind in result:break
    return result

def sync(conn,identity,data):
    values=milestones(data)
    conn.execute('DELETE FROM platform.activity_events WHERE activity_id=%s AND NOT(event_type=ANY(%s::text[]))',(identity,list(values)))
    for kind,value in values.items():
        conn.execute('INSERT INTO platform.activity_events VALUES(%s,%s,%s,%s) ON CONFLICT(activity_id,event_type) DO UPDATE SET event_at=excluded.event_at,local_date=excluded.local_date',(identity,kind,value,value.astimezone(ZONE).date()))

def initialize(conn):
    conn.execute(SCHEMA)
    # A schema migration marker permits exactly one backfill, including activities without dates.
    conn.execute('CREATE TABLE IF NOT EXISTS platform.calendar_migrations(version INTEGER PRIMARY KEY)')
    if conn.execute('SELECT 1 FROM platform.calendar_migrations WHERE version=1').fetchone():return
    keys=list(dict.fromkeys(f for fields in FIELDS.values() for f in fields))
    raw_pairs=','.join("'%s',data#>'{raw,%s}'"%(key,key) for key in keys)
    rows=conn.execute("SELECT id,(data-'raw') || jsonb_build_object('raw',jsonb_build_object("+raw_pairs+")) AS data FROM platform.entities WHERE resource='activities'").fetchall()
    values=[]
    for row in rows:
        values.extend((row['id'],kind,value,value.astimezone(ZONE).date()) for kind,value in milestones(row['data']).items())
    if values:
        with conn.cursor() as cursor:cursor.executemany('INSERT INTO platform.activity_events VALUES(%s,%s,%s,%s) ON CONFLICT(activity_id,event_type) DO NOTHING',values)
    conn.execute('INSERT INTO platform.calendar_migrations VALUES(1) ON CONFLICT DO NOTHING')
    conn.execute('ANALYZE platform.activity_events')

def linked_tag():
    return "t.resource='tags' AND (EXISTS(SELECT 1 FROM platform.activity_tags link WHERE link.activity_id=e.id AND link.tag_id=t.id) OR COALESCE(e.data->'tags','[]'::jsonb) ? t.id::text)"

def preference_filter(countdown=False):
    match=linked_tag();flag='show_countdown' if countdown else 'show_calendar';default='false' if countdown else 'true'
    setting='countdown_untagged' if countdown else 'show_untagged'
    return f"(CASE WHEN EXISTS(SELECT 1 FROM platform.entities t WHERE {match}) THEN EXISTS(SELECT 1 FROM platform.entities t WHERE {match} AND COALESCE(t.data->>'{flag}','{default}')='true') ELSE (SELECT {setting} FROM platform.calendar_preferences WHERE singleton) END)"

def query(core,start='',end='',tag_ids='',q='',limit=100,offset=0,per_day=0,event_types='deadline',countdown=False,group_activities=False):
    today=datetime.now(ZONE).date()
    try:
        first=date.fromisoformat(start) if start else today.replace(day=1)
        last=date.fromisoformat(end) if end else (first.replace(day=28)+timedelta(days=4)).replace(day=1)-timedelta(days=1)
        selected=list(filter(None,tag_ids.split(',')))
        for tag in selected:UUID(tag)
    except ValueError as exc:raise HTTPException(422,'日期或标签格式无效') from exc
    kinds=list(dict.fromkeys(filter(None,event_types.split(','))))
    if not kinds or any(k not in LABELS for k in kinds):raise HTTPException(422,'活动节点无效')
    if last<first or (last-first).days>3660:raise HTTPException(422,'日期范围无效')
    where="e.resource='activities' AND s.local_date BETWEEN %s AND %s AND s.event_type=ANY(%s::text[])";params=[first,last,kinds]
    where+=' AND '+preference_filter(countdown)
    if countdown:where+=' AND s.event_at>=now()'
    if q:where+=' AND e.data::text ILIKE %s';params.append('%'+q+'%')
    if selected:
        where+=" AND (EXISTS(SELECT 1 FROM platform.activity_tags t WHERE t.activity_id=e.id AND t.tag_id::text=ANY(%s)) OR COALESCE(e.data->'tags','[]'::jsonb) ?| %s)";params.extend([selected,selected])
    join=' FROM platform.activity_events s JOIN platform.entities e ON e.id=s.activity_id '
    columns="e.id,e.data-'raw' AS data,e.created_at,e.updated_at,s.event_at,s.local_date,s.event_type"
    with core.pool.connection() as conn:
        counts=conn.execute('SELECT s.local_date,count(*) AS n,count(DISTINCT e.id) AS activities'+join+'WHERE '+where+' GROUP BY s.local_date',params).fetchall()
        activity_count=conn.execute('SELECT count(DISTINCT e.id) AS n'+join+'WHERE '+where,params).fetchone()['n']
        if group_activities:
            grouped="e.id,e.data-'raw' AS data,e.created_at,e.updated_at,min(s.event_at) AS event_at,min(s.local_date) AS local_date,(array_agg(s.event_type ORDER BY s.event_at,s.event_type))[1] AS event_type,jsonb_agg(jsonb_build_object('event_type',s.event_type,'event_at',s.event_at) ORDER BY s.event_at,s.event_type) AS events"
            rows=conn.execute('SELECT '+grouped+join+'WHERE '+where+' GROUP BY e.resource,e.id ORDER BY min(s.event_at),e.id LIMIT %s OFFSET %s', [*params,limit,offset]).fetchall()
        elif per_day:
            sql='SELECT * FROM (SELECT '+columns+',row_number() OVER(PARTITION BY s.local_date ORDER BY s.event_at,e.id,s.event_type) AS day_rank'+join+'WHERE '+where+') ranked WHERE day_rank<=%s ORDER BY local_date,event_at,id,event_type'
            rows=conn.execute(sql,[*params,per_day]).fetchall()
        else:
            ordering='s.event_at,e.id,s.event_type'
            rows=conn.execute('SELECT '+columns+join+'WHERE '+where+' ORDER BY '+ordering+' LIMIT %s OFFSET %s', [*params,limit,offset]).fetchall()
        ids=list({row['id'] for row in rows})
        links=conn.execute('SELECT activity_id,tag_id FROM platform.activity_tags WHERE activity_id=ANY(%s::uuid[])',(ids,)).fetchall() if ids else []
        tags=conn.execute("SELECT id,data FROM platform.entities WHERE resource='tags'").fetchall()
    tagmap={str(t['id']):t['data'] for t in tags};relations={}
    for link in links:relations.setdefault(str(link['activity_id']),[]).append(str(link['tag_id']))
    now=datetime.now(timezone.utc);items=[]
    for row in rows:
        event_at=row.pop('event_at');local=row.pop('local_date');kind=row.pop('event_type');events=row.pop('events',None);row.pop('day_rank',None)
        item=core.row_dict(row);linked=list(dict.fromkeys(relations.get(item['id'],[])+[str(t) for t in (item['data'].get('tags') or []) if str(t) in tagmap]))
        items.append({**item,'events':events or [{'event_type':kind,'event_at':event_at.isoformat()}],'date':local.isoformat(),'event_type':kind,'event_label':LABELS[kind],'event_at':event_at.isoformat(),'deadline':event_at.isoformat(),'seconds_remaining':int((event_at-now).total_seconds()),'tag_ids':linked,'tags':[dict(id=t,**tagmap[t]) for t in linked if t in tagmap]})
    day_counts={r['local_date'].isoformat():r['n'] for r in counts}
    return {'items':items,'tags':tagmap,'total':activity_count if group_activities else sum(day_counts.values()),'activity_count':activity_count,'day_counts':day_counts,'day_activity_counts':{r['local_date'].isoformat():r['activities'] for r in counts},'limit':limit,'offset':offset}
