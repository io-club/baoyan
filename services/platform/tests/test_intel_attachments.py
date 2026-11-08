from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4
from fastapi.testclient import TestClient
import app as core


def test_generic_attachment_upload_and_message_commit_for_every_source(monkeypatch):
    objects={};saved=[]
    class Storage:
        def bucket_exists(self,*args):return True
        def put_object(self,bucket,key,stream,size,mime):objects[key]=stream.read()
        def stat_object(self,bucket,key):return SimpleNamespace(size=len(objects[key]))
    monkeypatch.setattr(core,'minio_client',lambda:Storage())
    def save(resource,payload):
        saved.append(payload.items[0]);return {'items':[{'id':str(uuid4()),'data':payload.items[0]}]}
    monkeypatch.setattr(core,'import_entities',save)
    core.app.dependency_overrides[core.require_admin]=lambda:None
    try:
        client=TestClient(core.app)
        uploaded=client.post('/v1/intel/attachments',files={'file':('notes.pdf',b'%PDF-example','application/pdf')})
        assert uploaded.status_code==200
        attachment=uploaded.json();assert objects[attachment['object']]==b'%PDF-example'
        for source in ['qq','xiaohongshu','manual','other']:
            response=client.post('/v1/intel/buffer',json={'source':source,'source_id':'one','content':'正文','metadata':{},'attachments':[attachment]})
            assert response.status_code==200
            assert response.json()['data']['attachments']==[attachment]
        manifest=[raw for key,raw in objects.items() if key.endswith('.json')][-1]
        import json
        assert json.loads(manifest)['attachments']==[attachment]
        invalid=client.post('/v1/intel/buffer',json={'source':'qq','source_id':'two','content':'正文','attachments':[{'object':'intel/attachments/not-uploaded','size':1}]})
        assert invalid.status_code==422
    finally:core.app.dependency_overrides.pop(core.require_admin,None)
