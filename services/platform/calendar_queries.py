"""Indexed date projection and database-bounded activity queries."""
from datetime import date, datetime, timedelta, timezone
from uuid import UUID
from fastapi import HTTPException

ZONE=timezone(timedelta(hours=8))
SCHEMA='''
CREATE TABLE IF NOT EXISTS platform.activity_schedule (
 activity_id UUID PRIMARY KEY REFERENCES platform.entities(id) ON DELETE CASCADE,
 deadline_at TIMESTAMPTZ, local_date DATE
);
CREATE INDEX IF NOT EXISTS activity_schedule_date_idx ON platform.activity_schedule(local_date,deadline_at,activity_id);
'''

def sync(conn,resource,identity,data):
    if resource!='activities':return
    from calendar_events import sync as sync_events
    sync_events(conn,identity,data)
    from features import parse_deadline
    deadline=parse_deadline(data.get('deadline'))
    conn.execute('INSERT INTO platform.activity_schedule(activity_id,deadline_at,local_date) VALUES(%s,%s,%s) ON CONFLICT(activity_id) DO UPDATE SET deadline_at=excluded.deadline_at,local_date=excluded.local_date',
        (identity,deadline,deadline.astimezone(ZONE).date() if deadline else None))

def initialize(conn):
    from features import parse_deadline
    conn.execute(SCHEMA)
    from calendar_events import initialize as initialize_events
    initialize_events(conn)
    rows=conn.execute("SELECT id,data->>'deadline' AS deadline FROM platform.entities e WHERE resource='activities' AND NOT EXISTS(SELECT 1 FROM platform.activity_schedule s WHERE s.activity_id=e.id)").fetchall()
    values=[]
    for row in rows:
        value=parse_deadline(row['deadline'])
        values.append((row['id'],value,value.astimezone(ZONE).date() if value else None))
    if values:
        with conn.cursor() as cursor:cursor.executemany('INSERT INTO platform.activity_schedule(activity_id,deadline_at,local_date) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING',values)
        conn.execute('ANALYZE platform.activity_schedule')

def query(*args,**kwargs):
    from calendar_events import query as query_events
    return query_events(*args,**kwargs)
