import importlib
import json

def test_complete_post_snapshot_and_images_share_attachment_contract(monkeypatch):
    monkeypatch.setenv('XHS_API_URL','http://xhs')
    monkeypatch.setenv('PLATFORM_API_URL','http://platform')
    monkeypatch.setenv('PLATFORM_ADMIN_PASSWORD','test')
    module=importlib.import_module('app.crawl_xhs')
    uploaded=[]
    def upload(binary,name,mime,url):
        uploaded.append((binary,name,mime,url));return {'object':'intel/attachments/'+str(len(uploaded)),'filename':name,'content_type':mime}
    monkeypatch.setattr(module,'upload_attachment',upload)
    monkeypatch.setattr(module,'download_remote_attachment',lambda *_:(b'image','image/jpeg'))
    note={'id':'n1','desc':'完整正文','raw_response':{'data':{'custom':'保留'}},'image_list':['https://x.xhscdn.com/pic']}
    attachments=module.note_attachments(note)
    assert len(attachments)==2
    assert json.loads(uploaded[0][0])==note
    assert attachments[0]['content_type']=='application/json' and attachments[1]['content_type']=='image/jpeg'
