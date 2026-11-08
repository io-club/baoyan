"""Correlate a file message with its companion group_upload notification."""
import json

def canonical_file_payload(db,event_id,event,payload):
    from .qq_media import media_parts
    parts=media_parts(event)
    if not parts or any(part['type']!='file' for part in parts):return payload
    attachments=payload['attachments']
    if not attachments:return payload
    raw=event.get('raw',{});kind=raw.get('post_type','message')
    stamp=int(raw.get('time') or 0)
    if not stamp:return payload
    digest='|'.join(sorted(a.get('sha256') or a['object'] for a in attachments))
    db.executescript('''CREATE TABLE IF NOT EXISTS file_deliveries(
        identity TEXT PRIMARY KEY,group_id TEXT,sender_id TEXT,digest TEXT,stamp INTEGER,kind TEXT,paired INTEGER NOT NULL DEFAULT 0,payload TEXT);
        CREATE TABLE IF NOT EXISTS file_event_aliases(event_id TEXT PRIMARY KEY,identity TEXT);
        CREATE INDEX IF NOT EXISTS file_delivery_match ON file_deliveries(group_id,sender_id,digest,stamp);''')
    db.execute('BEGIN IMMEDIATE')
    alias=db.execute('SELECT identity FROM file_event_aliases WHERE event_id=?',(event_id,)).fetchone()
    existing=None
    if alias:existing=db.execute('SELECT identity,payload FROM file_deliveries WHERE identity=?',alias).fetchone()
    else:
        existing=db.execute('''SELECT identity,payload FROM file_deliveries WHERE group_id=? AND sender_id=? AND digest=?
            AND kind<>? AND paired=0 AND abs(stamp-?)<=5 ORDER BY abs(stamp-?) LIMIT 1''',
            (str(event['group_id']),str(event.get('sender_id')),digest,kind,stamp,stamp)).fetchone()
        if existing:db.execute('UPDATE file_deliveries SET paired=1 WHERE identity=?',(existing[0],))
    identity=existing[0] if existing else payload['source_id']
    previous=json.loads(existing[1]) if existing else None
    events=(previous or {}).get('metadata',{}).get('source_events',[])
    if raw not in events:events.append(raw)
    payload['source_id']=identity
    payload['metadata']['source_events']=events
    if previous:
        by_object={a['object']:a for a in previous['attachments']}
        for attachment in attachments:
            old=by_object.get(attachment['object'])
            if old and old.get('filename') not in (None,'','attachment'):
                attachment['filename']=old['filename']
            by_object[attachment['object']]=attachment
        payload['attachments']=list(by_object.values())
    db.execute('INSERT INTO file_deliveries(identity,group_id,sender_id,digest,stamp,kind,payload) VALUES(?,?,?,?,?,?,?) ON CONFLICT(identity) DO UPDATE SET payload=excluded.payload',
        (identity,str(event['group_id']),str(event.get('sender_id')),digest,stamp,kind,json.dumps(payload,ensure_ascii=False)))
    db.execute('INSERT OR IGNORE INTO file_event_aliases VALUES(?,?)',(event_id,identity))
    db.commit()
    return payload
