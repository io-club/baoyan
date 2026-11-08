"""Shared binary-attachment upload and canonical intelligence envelope."""
import os
import httpx
import urllib.parse
from .config import current_admin_password


def upload_attachment(binary, filename, content_type, source_url=''):
    base=os.environ['PLATFORM_API_URL'].rstrip('/')
    with httpx.Client(timeout=60,trust_env=False) as client:
        response=client.post(base+'/v1/intel/attachments',
            headers={'X-Admin-Password':current_admin_password()},
            files={'file':(filename,binary,content_type)})
        response.raise_for_status()
        attachment=response.json()
    return {**attachment,'source_url':source_url}


def message_envelope(source,source_id,title,content,metadata,attachments=None):
    return {'source':source,'source_id':source_id,'title':title,'content':content,
            'metadata':metadata,'attachments':attachments or []}


def download_remote_attachment(url,allowed_hosts):
    original=url
    parsed=urllib.parse.urlsplit(url)
    if parsed.scheme=='http':url=urllib.parse.urlunsplit(parsed._replace(scheme='https'))
    with httpx.Client(timeout=30,trust_env=False) as client:
        for _ in range(5):
            parsed=urllib.parse.urlsplit(url);host=(parsed.hostname or '').lower()
            if parsed.scheme!='https' or parsed.username or parsed.password or parsed.port not in (None,443) or not any(host==h or host.endswith('.'+h) for h in allowed_hosts):
                raise ValueError('Unsupported attachment URL')
            with client.stream('GET',url,headers={'User-Agent':'Mozilla/5.0'}) as response:
                if response.is_redirect:
                    url=urllib.parse.urljoin(url,response.headers['location']);continue
                response.raise_for_status();chunks=[];size=0
                for chunk in response.iter_bytes():
                    size+=len(chunk)
                    if size>25*1024*1024:raise ValueError('Attachment exceeds 25MB')
                    chunks.append(chunk)
                return b''.join(chunks),response.headers.get('content-type','application/octet-stream').split(';')[0]
    raise ValueError('Too many attachment redirects')
