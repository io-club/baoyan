import json
import os
import urllib.request

def main():
    req=urllib.request.Request(os.environ['PLATFORM_API_URL'].rstrip('/')+'/v1/intel/process',
        data=json.dumps({'ids':os.environ['INTEL_IDS'].split(','),'instruction':os.environ.get('INTEL_INSTRUCTION','请总结来源内容')}).encode(),
        headers={'Content-Type':'application/json','X-Admin-Password':os.environ['PLATFORM_ADMIN_PASSWORD']})
    with urllib.request.urlopen(req,timeout=180) as r: result=json.loads(r.read())
    print('Summary saved, batch ID:',result['id'])

if __name__=='__main__': main()
