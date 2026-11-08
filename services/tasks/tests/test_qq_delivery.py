import asyncio
import json
import sqlite3
from app import qq_watcher as qq
from app.qq_media import message_text,media_parts

def setup(monkeypatch,tmp_path):
    monkeypatch.setattr(qq,'BUFFER_DIR',tmp_path)
    monkeypatch.setattr(qq,'current_admin_password',lambda:'test')
    monkeypatch.setenv('PLATFORM_API_URL','http://platform.test')
    return {'group_id':'g','message_id':'m','sender':'user','message':'原文[CQ:image,file=pic,url=https://a.qpic.cn/pic]',
            'raw':{'message':[{'type':'text','data':{'text':'原文'}},{'type':'image','data':{'file':'pic','url':'https://a.qpic.cn/pic'}}]}}

def result(payload):
    class Response:
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def read(self):return json.dumps({'data':payload}).encode()
    return Response()

def test_receive_wakes_sender_immediately(monkeypatch,tmp_path):
    event=setup(monkeypatch,tmp_path);wake=asyncio.Event();monkeypatch.setattr(qq,'WAKE',wake)
    qq.enqueue(event);assert wake.is_set()

def test_receiver_uploads_before_message_and_preserves_raw(monkeypatch,tmp_path):
    event=setup(monkeypatch,tmp_path);order=[]
    monkeypatch.setattr(qq,'download_part',lambda *_:(b'image','pic.png','image/png','https://a.qpic.cn/pic'))
    def upload(*args):order.append('upload');return {'object':'intel/attachments/hash','size':5}
    monkeypatch.setattr(qq,'upload_attachment',upload)
    def commit(req,**kwargs):
        order.append('commit');p=json.loads(req.data)
        assert p['content']=='原文' and p['metadata']['raw']==event['raw']
        assert len(p['attachments'])==1
        return result(p)
    monkeypatch.setattr(qq.urllib.request,'urlopen',commit)
    qq.enqueue(event);qq.flush()
    assert order==['upload','commit']
    with qq.outbox() as db:assert db.execute('SELECT count(*) FROM outbox').fetchone()[0]==0

def test_commit_failure_keeps_uploaded_attachments_for_retry(monkeypatch,tmp_path):
    event=setup(monkeypatch,tmp_path);uploads=[]
    monkeypatch.setattr(qq,'download_part',lambda *_:(b'image','pic.png','image/png','url'))
    monkeypatch.setattr(qq,'upload_attachment',lambda *args:uploads.append(1) or {'object':'intel/attachments/hash','size':5})
    def fail(*args,**kwargs):raise TimeoutError()
    monkeypatch.setattr(qq.urllib.request,'urlopen',fail)
    qq.enqueue(event);qq.flush()
    with qq.outbox() as db:
        row=db.execute('SELECT payload,attempts FROM outbox').fetchone()
        assert row[1]==1 and len(json.loads(row[0])['attachments'])==1
        db.execute('UPDATE outbox SET next_attempt=0')
    monkeypatch.setattr(qq.urllib.request,'urlopen',lambda req,**kwargs:result(json.loads(req.data)))
    qq.flush();assert len(uploads)==1
    with qq.outbox() as db:assert db.execute('SELECT count(*) FROM outbox').fetchone()[0]==0

def test_file_notice_and_old_schema(monkeypatch,tmp_path):
    event=setup(monkeypatch,tmp_path)
    with sqlite3.connect(tmp_path/'outbox.sqlite3') as db:db.execute('CREATE TABLE outbox (id TEXT PRIMARY KEY,payload TEXT NOT NULL)')
    qq.enqueue(event)
    event['raw']={'notice_type':'group_upload','file':{'id':'f','name':'notes.pdf'}}
    assert media_parts(event)[0]['type']=='file'
    assert message_text(event)==''
