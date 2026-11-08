from app.qq_media import message_text,inline_text

def test_face_segments_preserve_names_and_order():
    event={'raw':{'message':[{'type':'text','data':{'text':'你好'}},{'type':'face','data':{'id':'302','raw':{'faceText':'/左拜年'}}},{'type':'text','data':{'text':'大家'}}]}}
    assert message_text(event)=='你好[左拜年]大家'

def test_inline_face_escaped_json_does_not_leak_protocol():
    raw='前[CQ:face,id=302,raw={"faceIndex":302&#44;"faceText":"/左拜年"&#44;"faceType":2}]后'
    assert inline_text(raw)=='前[左拜年]后'
    event={'raw':{'message':[{'type':'text','data':{'text':raw}}]}}
    assert message_text(event)=='前[左拜年]后'

def test_unknown_face_has_compact_fallback():
    assert message_text({'raw':{'message':[{'type':'face','data':{'id':'99999'}}]}})=='[表情 99999]'
