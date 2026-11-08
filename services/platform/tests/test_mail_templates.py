from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from advisor_contract import normalize_advisor,normalize_template,flat
from mail_templates import prepare
from features import ComposeMail


def test_legacy_normalization_preserves_nonempty_nested_values_and_custom_fields():
    old={'name':'张老师','research_directions':[],'data':{'title':'教授','center':'智能中心','研究方向':'计算机视觉','research_directions':['系统'],'custom':{'x':1}}}
    new=normalize_advisor(old)
    assert new['title']=='教授' and new['institute']=='智能中心'
    assert new['research_directions']==['系统'] and new['custom']=={'x':1}
    assert 'data' not in new and 'data' in old
    assert normalize_advisor({'research_directions':[]},fill_empty=False)=={'research_directions':[]}


def test_template_normalization_retains_body_and_subject_and_metadata():
    old={'name':'测试','content':'{{name}} 老师','data':{'field_mapping':{'name':'advisor.data.name'},'subject':'联系 {{name}}'}}
    value=normalize_template(old)
    assert value['content']==old['content'] and value['subject']=='联系 {{name}}'
    assert 'field_mapping' in value['metadata'] and 'data' not in value


class Core:
    def __init__(self):
        self.rows={('advisors','a'):{'id':'a','data':{'name':'甲','email':'a@example.com','school':'甲校','title':'教授','research_directions':['系统','视觉']}},('advisors','b'):{'id':'b','data':{'name':'乙','email':'b@example.com','school':'乙校','title':'副教授','research_directions':['图形']}},('templates','t'):{'id':'t','data':{'subject':'{{school}} · {{name}}','content':'{{advisor.name}} {{title}}，关注 {{direction}}。{{profile.interest}}'}}}
    def get_entity(self,resource,id):return self.rows[(resource,id)]


def request(**kwargs):
    return SimpleNamespace(advisor_id='a',template_id='t',parameters={'name':'旧导师','advisor.name':'旧导师','profile':{'interest':'交流'}},recipient_name=None,recipient_email=None,subject=None,content=None,**kwargs)


def test_one_contract_renders_subject_and_body_and_refetches_selected_mentor():
    core=Core();req=request();first=prepare(core,req,strict=True)
    assert first['subject']=='甲校 · 甲' and first['content']=='甲 教授，关注 系统、视觉。交流'
    assert first['recipient_email']=='a@example.com'
    req.advisor_id='b';second=prepare(core,req,strict=True)
    assert second['subject']=='乙校 · 乙' and second['content']=='乙 副教授，关注 图形。交流'
    assert all(v['automatic'] for v in second['variables'] if v['name']!='profile.interest')
    assert first['parameters']['name']=='甲' and second['parameters']['name']=='乙'


def test_missing_fields_reported_and_prevent_draft_creation():
    core=Core();del core.rows[('advisors','a')]['data']['title']
    preview=prepare(core,request())
    assert preview['missing']==['title']
    with pytest.raises(HTTPException) as exc:prepare(core,request(),strict=True)
    assert exc.value.status_code==422


def test_manual_draft_and_explicit_override_and_header_injection():
    req=ComposeMail(recipient_name='张',recipient_email='a@example.com',subject='主题',content='正文')
    assert prepare(Core(),req,strict=True)['content']=='正文'
    req.subject='主题\nBcc: other@example.com'
    with pytest.raises(HTTPException):prepare(Core(),req,strict=True)


def test_legacy_template_missing_subject_is_not_invented():
    core=Core();del core.rows[('templates','t')]['data']['subject']
    preview=prepare(core,request());assert preview['subject']=='' and preview['errors']
    with pytest.raises(HTTPException):prepare(core,request(),strict=True)

def test_source_specific_parameter_names_are_automatic_without_a_mapping():
    core=Core()
    core.rows[('advisors','a')]['data'].update({'center':'安全中心','research_directions':['安全']})
    core.rows[('advisors','b')]['data'].update({'研究方向':['多模态','图形']})
    template=core.rows[('templates','t')]['data']
    template.update(subject='致{{name}}',content='{{center}}：{{research_directions}}')
    first=prepare(core,request(),strict=True)
    assert first['content']=='安全中心：安全' and all(v['automatic'] for v in first['variables'])
    template['content']='{{研究方向}}'
    req=request();req.advisor_id='b'
    second=prepare(core,req,strict=True)
    assert second['content']=='多模态、图形' and second['variables'][-1]['source']=='advisor.研究方向'
    assert template['content']=='{{研究方向}}'
