"""Keep QQ message pictures with their original source and verified image bytes."""
import hashlib
import html
from io import BytesIO
import re
import urllib.parse
import urllib.request
import urllib.error
import json
from uuid import uuid4
import mimetypes

MAX_IMAGE_BYTES = 20 * 1024 * 1024


def image_segments(metadata, content=''):
    segments = []
    raw = metadata.get('raw') or {}
    for part in raw.get('message', []) if isinstance(raw.get('message'), list) else []:
        if isinstance(part, dict) and part.get('type') == 'image':
            segments.append(dict(part.get('data') or {}))
    for match in re.finditer(r'\[CQ:image,([^\]]*)\]', content or ''):
        data = {}
        for entry in match.group(1).split(','):
            key, sep, value = entry.partition('=')
            if sep:
                data[key] = html.unescape(value.replace('&#44;', ','))
        segments.append(data)
    unique = {}
    for data in segments:
        key = data.get('file') or data.get('url')
        if key:
            if key in unique:
                unique[key].update({k: v for k, v in data.items() if v})
            else:
                unique[key] = data
    return list(unique.values())


def checked_url(url):
    parsed = urllib.parse.urlsplit(url)
    host = (parsed.hostname or '').lower()
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('invalid QQ image URL')
    if not any(host == suffix or host.endswith('.' + suffix) for suffix in ('qq.com', 'qq.com.cn', 'qpic.cn', 'gtimg.cn')):
        raise ValueError('unsupported QQ image host')
    return url


class ImageRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        checked_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download_image(url):
    request = urllib.request.Request(checked_url(url), headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.build_opener(ImageRedirect()).open(request, timeout=12) as response:
        value = response.read(MAX_IMAGE_BYTES + 1)
    if len(value) > MAX_IMAGE_BYTES:
        raise ValueError('image too large')
    if value.startswith(b'\x89PNG\r\n\x1a\n'):
        mime, suffix = 'image/png', 'png'
    elif value.startswith(b'\xff\xd8\xff'):
        mime, suffix = 'image/jpeg', 'jpg'
    elif value.startswith((b'GIF87a', b'GIF89a')):
        mime, suffix = 'image/gif', 'gif'
    elif value.startswith(b'RIFF') and value[8:12] == b'WEBP':
        mime, suffix = 'image/webp', 'webp'
    else:
        raise ValueError('unsupported image bytes')
    return value, mime, suffix


def refreshed_image(file):
    """Ask the logged-in OneBot connection for a refreshed URL, never a local path."""
    from websockets.sync.client import connect
    identity = 'qq-image-' + uuid4().hex
    with connect('ws://napcat:3001', open_timeout=3, close_timeout=1, max_size=2*1024*1024) as ws:
        ws.send(json.dumps({'action': 'get_image', 'params': {'file': file}, 'echo': identity}))
        for _ in range(20):
            result = json.loads(ws.recv(timeout=4))
            if result.get('echo') == identity:
                value = (result.get('data') or {}).get('url', '')
                return checked_url(value)
    raise ValueError('QQ image URL unavailable')


def onebot_file_url(part,group_id):
    from websockets.sync.client import connect
    identity='qq-file-'+uuid4().hex
    params={'group_id':group_id,'file_id':part.get('file_id') or part.get('id') or part.get('file'),
            'busid':part.get('busid',part.get('bus_id',0))}
    with connect('ws://napcat:3001',open_timeout=3,close_timeout=1) as ws:
        ws.send(json.dumps({'action':'get_group_file_url','params':params,'echo':identity}))
        for _ in range(20):
            result=json.loads(ws.recv(timeout=4))
            if result.get('echo')==identity:
                return checked_url((result.get('data') or {}).get('url',''))
    raise ValueError('QQ file URL unavailable')


def message_parts(event):
    raw=event.get('raw') or {}
    if isinstance(raw.get('message'),list):return raw['message']
    if raw.get('notice_type')=='group_upload':return [{'type':'file','data':raw.get('file',{})}]
    parts=[];value=event.get('message','');start=0
    for match in re.finditer(r'\[CQ:([^,\]]+)(?:,([^\]]*))?\]',value):
        if match.start()>start:parts.append({'type':'text','data':{'text':html.unescape(value[start:match.start()])}})
        data={}
        for entry in (match.group(2) or '').split(','):
            key,sep,content=entry.partition('=')
            if sep:data[key]=html.unescape(content.replace('&#44;',','))
        parts.append({'type':match.group(1),'data':data});start=match.end()
    if start<len(value):parts.append({'type':'text','data':{'text':html.unescape(value[start:])}})
    return parts


def message_text(event):
    values=[]
    for part in message_parts(event):
        kind=part.get('type');data=part.get('data') or {}
        if kind=='text':values.append(inline_text(data.get('text','')))
        elif kind=='at':values.append('@'+str(data.get('qq','群成员')))
        elif kind=='face':values.append(face_label(data))
    return ''.join(values).strip()


def face_label(data):
    raw=data.get('raw') or {}
    if isinstance(raw,str):
        try:raw=json.loads(html.unescape(raw.replace('&#44;',',')))
        except (ValueError,TypeError):raw={}
    name=(raw.get('faceText') if isinstance(raw,dict) else None) or data.get('name') or {'302':'左拜年'}.get(str(data.get('id')))
    return '['+str(name).strip().lstrip('/')+']' if name else '[表情 '+str(data.get('id',''))+']'


def inline_text(value):
    def replace(match):
        params={}
        for part in match.group(1).split(','):
            key,sep,content=part.partition('=')
            if sep:params[key]=html.unescape(content.replace('&#44;',','))
        return face_label(params)
    return re.sub(r'\[CQ:face,([^\]]*)\]',replace,str(value))


def media_parts(event):
    seen=set();result=[]
    for index,part in enumerate(message_parts(event)):
        if part.get('type') not in {'image','file'}:continue
        data=part.get('data') or {}
        identity=str(data.get('file_id') or data.get('id') or data.get('file') or data.get('url') or index)
        key=part['type']+':'+identity
        if key not in seen:result.append({**part,'key':key});seen.add(key)
    return result


def download_part(part,group_id):
    data=part['data'];kind=part['type'];url=data.get('url') or ''
    original_url=url
    if kind=='image':
        if not url:url=refreshed_image(data.get('file') or data.get('file_id'))
        try:binary,mime,extension=download_image(url)
        except urllib.error.HTTPError:
            url=refreshed_image(data.get('file') or data.get('file_id'));binary,mime,extension=download_image(url)
        filename=data.get('name') or data.get('file') or ('image.'+extension)
    else:
        if not url:url=onebot_file_url(data,group_id)
        def fetch(value):
            request=urllib.request.Request(checked_url(value),headers={'User-Agent':'Mozilla/5.0'})
            with urllib.request.build_opener(ImageRedirect()).open(request,timeout=20) as r:return r.read(25*1024*1024+1)
        try:binary=fetch(url)
        except urllib.error.HTTPError:url=onebot_file_url(data,group_id);binary=fetch(url)
        if len(binary)>25*1024*1024:raise ValueError('QQ attachment exceeds 25MB')
        filename=data.get('name') or data.get('file_name') or data.get('file') or 'attachment'
        mime=mimetypes.guess_type(filename)[0] or 'application/octet-stream'
    return binary,str(filename).replace('/','_').replace('\\','_'),mime,original_url or url


