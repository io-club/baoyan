import json
import logging
import os
import time
import urllib.request
from .config import current_admin_password

logging.basicConfig(level=logging.INFO)
while True:
    try:
        req=urllib.request.Request(os.getenv('PLATFORM_API_URL','http://platform-api:8080').rstrip('/')+'/v1/reminders/tick',data=b'{}',headers={'Content-Type':'application/json','X-Admin-Password':current_admin_password()})
        with urllib.request.urlopen(req,timeout=20) as r: result=json.loads(r.read())
        if result['created']: logging.info('Persisted %s deadline notifications',result['created'])
    except Exception as exc:
        logging.warning('Reminder check failed: %s',type(exc).__name__)
    time.sleep(30)
