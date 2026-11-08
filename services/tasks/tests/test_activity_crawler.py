import importlib
import urllib.error
import json
import pytest

def module(monkeypatch):
    monkeypatch.setenv('PLATFORM_API_URL','http://platform')
    return importlib.import_module('app.crawl_activities')

def test_source_deadline_variants(monkeypatch):
    crawler=module(monkeypatch)
    assert crawler.normalize_deadline('2026-11-05 24:00:00')=='2026-11-06T00:00:00'
    assert crawler.normalize_deadline('2026/11/05')=='2026-11-05'
    assert crawler.normalize_deadline('报名时间待定') is None
    assert crawler.normalize_deadline('0') is None
    item=crawler.map_activity({'id':1,'title':'活动','sign_up_end':'时间待定'})
    assert item['deadline'] is None and item['deadline_raw']=='时间待定'
    missing=crawler.map_activity({'id':17221,'title':'','gzh_url':'https://example.test/source'})
    assert missing['source_incomplete'] and missing['title_raw']=='' and missing['source_id']=='17221'
    assert missing['source_url']=='https://example.test/source'

def test_transient_failure_retries(monkeypatch):
    crawler=module(monkeypatch);calls=[]
    class Response:
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def read(self):return b'{"count":1}'
    def send(*args,**kwargs):
        calls.append(1)
        if len(calls)==1:raise urllib.error.URLError('temporary')
        return Response()
    monkeypatch.setattr(crawler.urllib.request,'urlopen',send)
    monkeypatch.setattr(crawler,'current_admin_password',lambda:'test')
    monkeypatch.setattr(crawler.time,'sleep',lambda _:None)
    assert crawler.request_json('http://platform',{'items':[]})=={'count':1}
    assert len(calls)==2

def test_one_invalid_record_does_not_abort_page(monkeypatch):
    crawler=module(monkeypatch)
    def request(url,body,**kwargs):
        if len(body['items'])>1 or body['items'][0]['source_id']=='bad':
            raise urllib.error.HTTPError(url,422,'invalid',None,None)
        return {'count':1}
    monkeypatch.setattr(crawler,'request_json',request)
    assert crawler.import_page([{'source_id':'ok'},{'source_id':'bad'}])==(1,1)

def test_full_crawl_resumes_failed_import_without_skipping_page(monkeypatch,tmp_path):
    crawler=module(monkeypatch)
    monkeypatch.setenv('ACTIVITY_STATE_DIR',str(tmp_path));monkeypatch.setenv('ACTIVITY_PAGE_SIZE','2')
    monkeypatch.delenv('ACTIVITY_END_PAGE',raising=False)
    fetched=[];received=[];fail=[True]
    def request(url,**kwargs):
        page=int(crawler.urllib.parse.parse_qs(crawler.urllib.parse.urlsplit(url).query)['page'][0]);fetched.append(page)
        ids={1:[1,2],2:[3,4],3:[5]}[page]
        return {'success':True,'result':{'content':[{'id':i,'title':str(i)} for i in ids],'total_count':5}}
    def ingest(items):
        if items[0]['source_id']=='3' and fail[0]:
            fail[0]=False;raise ConnectionError('platform unavailable')
        received.extend(i['source_id'] for i in items);return len(items),0
    monkeypatch.setattr(crawler,'request_json',request);monkeypatch.setattr(crawler,'import_page',ingest)
    monkeypatch.setattr(crawler.time,'sleep',lambda _:None)
    with pytest.raises(ConnectionError):crawler.main()
    saved=json.loads((tmp_path/'1-0-2.json').read_text());assert saved['next_page']==2 and saved['status']=='failed'
    crawler.main()
    saved=json.loads((tmp_path/'1-0-2.json').read_text())
    assert saved['status']=='complete' and saved['pages']==3 and saved['imported']==5
    assert fetched==[1,2,3] and received==['1','2','3','4','5']

def test_business_failure_retries_instead_of_treating_as_empty(monkeypatch):
    crawler=module(monkeypatch);calls=[]
    class Response:
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def read(self):return b'{"success":false,"errors":["temporary"]}'
    def send(*args,**kwargs):calls.append(1);return Response()
    monkeypatch.setattr(crawler.urllib.request,'urlopen',send);monkeypatch.setattr(crawler.time,'sleep',lambda _:None)
    with pytest.raises(RuntimeError):crawler.request_json('http://source',source=True)
    assert len(calls)==11

def test_duplicate_source_page_is_failure_not_completion(monkeypatch,tmp_path):
    crawler=module(monkeypatch);monkeypatch.setenv('ACTIVITY_STATE_DIR',str(tmp_path));monkeypatch.setenv('ACTIVITY_PAGE_SIZE','1')
    monkeypatch.delenv('ACTIVITY_END_PAGE',raising=False)
    monkeypatch.setattr(crawler,'request_json',lambda *a,**kw:{'result':{'content':[{'id':1,'title':'活动'}]}})
    monkeypatch.setattr(crawler,'import_page',lambda items:(1,0));monkeypatch.setattr(crawler.time,'sleep',lambda _:None)
    with pytest.raises(RuntimeError,match='重复'):crawler.main()
    saved=json.loads((tmp_path/'1-0-1.json').read_text());assert saved['status']=='failed' and saved['next_page']==2

def test_short_page_with_missing_advertised_items_is_not_success(monkeypatch,tmp_path):
    crawler=module(monkeypatch);monkeypatch.setenv('ACTIVITY_STATE_DIR',str(tmp_path));monkeypatch.setenv('ACTIVITY_PAGE_SIZE','25')
    monkeypatch.delenv('ACTIVITY_END_PAGE',raising=False)
    monkeypatch.setattr(crawler,'request_json',lambda *a,**kw:{'result':{'content':[{'id':1,'title':'活动'}],'total_count':50}})
    monkeypatch.setattr(crawler,'import_page',lambda items:(1,0))
    with pytest.raises(RuntimeError,match='完整性检查'):crawler.main()
    assert json.loads((tmp_path/'1-0-25.json').read_text())['status']=='failed'
