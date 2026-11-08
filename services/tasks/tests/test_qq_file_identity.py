import sqlite3
from copy import deepcopy
from app.qq_file_identity import canonical_file_payload

def fixture(kind,stamp,message_id):
    raw={'post_type':kind,'time':stamp,'message_id':message_id}
    if kind=='message':raw['message']=[{'type':'file','data':{'file_id':'different-msg-id'}}]
    else:raw.update(notice_type='group_upload',file={'id':'different-upload-id'})
    event={'group_id':'group','sender_id':'sender','raw':raw,'message':''}
    payload={'source':'qq','source_id':'group:'+message_id,'content':'','attachments':[{'object':'intel/attachments/digest','sha256':'digest','filename':'name.pdf'}],'metadata':{'raw':raw}}
    return event,payload

def test_companion_notice_is_one_record_but_repeated_send_is_not(tmp_path):
    with sqlite3.connect(tmp_path/'correlation.db') as db:
        e,a=fixture('notice',100,'notice');first=canonical_file_payload(db,'notice',e,a)
        e,b=fixture('message',101,'message');second=canonical_file_payload(db,'message',e,b)
        assert first['source_id']==second['source_id']
        assert len(second['metadata']['source_events'])==2
        e,c=fixture('message',102,'resent-message');third=canonical_file_payload(db,'resent-message',e,c)
        assert third['source_id']!=first['source_id']
        e,d=fixture('notice',103,'resent-notice');fourth=canonical_file_payload(db,'resent-notice',e,d)
        assert fourth['source_id']==third['source_id']
        e,retry=fixture('message',101,'message');again=canonical_file_payload(db,'message',e,retry)
        assert again['source_id']==first['source_id'] and len(again['metadata']['source_events'])==2
