from __future__ import annotations
import hashlib,json,os,time,urllib.parse,urllib.request,urllib.error,uuid,random,socket,http.client
from pathlib import Path
from datetime import datetime,timedelta,timezone
from .config import current_admin_password

SOURCE="http://api.baoyanwang.com.cn/api/v1/articles"
SECRET='e3fa66d113ae5dd8f291e10209e57bcf'
PLATFORM=os.environ["PLATFORM_API_URL"].rstrip("/")
# Source and internal platform requests are direct; never inherit host proxy settings.
urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))

def request_json(url,payload=None,source=False):
    for attempt in range(11):
        retry_after=0
        headers={"User-Agent":"BaoyanPlatform/1.0"}
        if source:
            nonce=f"{uuid.uuid4()}-{int(time.time()*1000)}"
            headers.update({"X-Auth-Nonce":nonce,"X-Auth-Sign":hashlib.md5(f"nonce={nonce}&secret={SECRET}".encode()).hexdigest(),"X-Auth-Device":"web"})
        else:headers['X-Admin-Password']=current_admin_password()
        if payload is not None:headers['Content-Type']='application/json'
        req=urllib.request.Request(url,headers=headers,data=None if payload is None else json.dumps(payload,ensure_ascii=False).encode())
        try:
            with urllib.request.urlopen(req,timeout=30) as response:result=json.loads(response.read())
            if source and (result.get('success') is not True or not isinstance(result.get('result'),dict) or not isinstance(result['result'].get('content'),list)):
                raise ValueError('来源返回业务失败或无效分页结构，不能判作空页')
            return result
        except urllib.error.HTTPError as exc:
            if (not source and exc.code not in {401,408,429,500,502,503,504}) or attempt==10:raise
            try:retry_after=min(300,max(0,float(exc.headers.get('Retry-After','0'))))
            except (ValueError,AttributeError):pass
            reason=f'HTTP {exc.code}'
        except (urllib.error.URLError,TimeoutError,ConnectionError,socket.timeout,http.client.HTTPException,ValueError) as exc:
            if attempt==10:raise RuntimeError('连续重试失败；本页进度未推进，请从断点继续') from exc
            reason=type(exc).__name__
        delay=max(retry_after,min(60,2*2**attempt)+random.uniform(0,0.5))
        print(f'请求失败（{reason}），{delay:.1f} 秒后重试 {attempt+1}/10',flush=True)
        time.sleep(delay)

def normalize_deadline(value):
    if value in (None,'',0,'0','0000-00-00','0000-00-00 00:00:00'):return None
    raw=str(value).strip()
    try:
        if raw.isdigit() and len(raw) in (10,13):return datetime.fromtimestamp(int(raw)/(1000 if len(raw)==13 else 1),timezone.utc).isoformat()
        adjusted=raw.replace('年','-').replace('月','-').replace('日','').replace('/','-').replace('Z','+00:00')
        rollover=' 24:' in adjusted or 'T24:' in adjusted
        if rollover:adjusted=adjusted.replace(' 24:',' 00:').replace('T24:','T00:')
        result=datetime.fromisoformat(adjusted)
        if rollover:result+=timedelta(days=1)
        return result.isoformat() if len(adjusted)>10 else result.date().isoformat()
    except (ValueError,OverflowError,OSError):return None

def map_activity(item):
    if item.get('id') is None:return None
    raw=item.get('sign_up_end');deadline=normalize_deadline(raw)
    title=str(item.get('title') or '').strip()
    return {'source':'baoyanwang','source_id':str(item['id']),'title':title or f"未提供标题（来源 ID {item['id']}）",'title_raw':item.get('title'),'source_incomplete':not bool(title),
        'school':item.get('college') or '','college':item.get('academy') or '',
        'category':item.get('category') or '','published_at':item.get('created_at') or '',
        'deadline':deadline,'deadline_raw':raw,'deadline_status':'parsed' if deadline else 'not_provided_or_unparsed',
        'registration_start':normalize_deadline(item.get('sign_up_start')),'activity_start':normalize_deadline(item.get('start_time')),
        'source_url':item.get('office_url') or item.get('gzh_url') or item.get('url') or item.get('sign_up_url') or '','tags':[],'notes':'','raw':item}

def import_page(items):
    try:return int(request_json(PLATFORM+'/v1/import/activities',{'items':items})['count']),0
    except urllib.error.HTTPError as exc:
        if exc.code!=422:raise
    imported=skipped=0
    for item in items:
        try:imported+=int(request_json(PLATFORM+'/v1/import/activities',{'items':[item]})['count'])
        except urllib.error.HTTPError as exc:
            if exc.code!=422:raise
            skipped+=1
            print(f"来源记录 {item['source_id']} 校验失败，已跳过该条，其余记录继续导入",flush=True)
    return imported,skipped

def atomic_json(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
    temp.replace(path)

def main():
    import fcntl
    start=int(os.getenv('ACTIVITY_START_PAGE','1'));end=int(os.getenv('ACTIVITY_END_PAGE','0') or 0);size=int(os.getenv('ACTIVITY_PAGE_SIZE','25'))
    if start<1 or size<1 or (end and end<start):raise ValueError('页码范围无效')
    root=Path(os.getenv('ACTIVITY_STATE_DIR','/workspace/activity-crawl'))
    root.mkdir(parents=True,exist_ok=True)
    key=f'{start}-{end}-{size}'
    with (root/(key+'.lock')).open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('同一页码范围已有采集任务运行，请查看任务日志')
        checkpoint=root/(key+'.json')
        saved=json.loads(checkpoint.read_text()) if checkpoint.exists() else {}
        if os.getenv('ACTIVITY_RESUME','true').lower()!='true' or saved.get('status') in ('complete','range_complete'):saved={}
        run=saved.get('run_id') or str(uuid.uuid4());archive=root/run
        page=saved.get('next_page',start);imported=saved.get('imported',0);pages=saved.get('pages',0)
        previous=saved.get('fingerprint');expected=saved.get('source_total');status='running'
        print(f'开始采集：第 {page} 页起，每页 {size} 条，结束页 {end or "自动到末尾"}；归档 {run}',flush=True)
        def save():
            atomic_json(checkpoint,dict(run_id=run,next_page=page,imported=imported,pages=pages,fingerprint=previous,source_total=expected,status=status,updated_at=datetime.now(timezone.utc).isoformat()))
        save()
        try:
            while not end or page<=end:
                url=SOURCE+'?'+urllib.parse.urlencode({'page':page,'size':size,'all':1})
                raw_path=archive/f'page-{page}.json'
                payload=json.loads(raw_path.read_text()) if raw_path.exists() else request_json(url,source=True)
                atomic_json(raw_path,payload)
                result=payload['result'];items=result['content'];total=result.get('total_count')
                if isinstance(total,int) and total>=0:expected=total
                if not items:
                    status='verifying';print(f'第 {page} 页为空，已到来源末尾',flush=True);break
                fingerprint=[str(item.get('id')) for item in items]
                if fingerprint==previous:raise RuntimeError('来源重复返回上一页，进度已保留；不能将重复页视为全量完成')
                mapped=[map_activity(item) for item in items]
                invalid=[item for item,value in zip(items,mapped) if value is None]
                if invalid:
                    atomic_json(archive/f'rejected-{page}.json',invalid)
                    raise RuntimeError(f'第 {page} 页有 {len(invalid)} 条无效记录，已归档，本页未推进')
                count,rejected=import_page(mapped)
                if rejected:raise RuntimeError(f'第 {page} 页有 {rejected} 条入库失败；原页已保留，修复后重跑')
                imported+=count;pages+=1;previous=fingerprint
                print(f'第 {page} 页：读取 {len(items)} 条，入库/更新 {count} 条；累计 {imported} 条；来源总数 {expected if expected is not None else "未知"}',flush=True)
                with (archive/'progress.jsonl').open('a',encoding='utf-8') as log:
                    log.write(json.dumps(dict(page=page,count=count,source_total=expected,time=datetime.now(timezone.utc).isoformat()),ensure_ascii=False)+'\n')
                last=result.get('last') is True or len(items)<size
                total_pages=result.get('totalPages',result.get('total_pages'))
                if isinstance(total_pages,int) and page>=total_pages:last=True
                if expected is not None and page*size>=expected:last=True
                page+=1
                if last:status='verifying'
                elif end and page>end:status='range_complete'
                save()
                if status!='running':break
                time.sleep(0.5)
        except Exception:
            status='failed';save();raise
        if status=='verifying' and start==1:
            unique_ids=set()
            for raw_page in archive.glob('page-*.json'):
                unique_ids.update(str(item['id']) for item in json.loads(raw_page.read_text())['result']['content'])
            atomic_json(archive/'summary.json',dict(unique_count=len(unique_ids),processed_count=imported,source_total=expected,pages=pages))
            if expected is not None and len(unique_ids)<expected:
                status='failed';save()
                raise RuntimeError(f'完整性检查不通过：来源 {expected} 条，实际唯一记录 {len(unique_ids)} 条；可能发生分页漂移，请取消续跑后重新采集')
        if status=='verifying':status='complete'
        save()
        print(f'活动采集结束：状态 {status}，处理 {pages} 页，入库/更新 {imported} 条，来源总数 {expected}；下次页码 {page}',flush=True)

if __name__=='__main__':main()
