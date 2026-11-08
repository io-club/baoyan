from datetime import datetime, timedelta, timezone
import pytest
from fastapi import HTTPException
from features import fill_template, parse_deadline

def test_template_supports_arbitrary_json_and_nested_keys():
    assert fill_template('你好 {{ name }}，{{profile.field}}，{{items}}', {'name':'张三','profile':{'field':'计算机视觉'},'items':[1,2]}) == '你好 张三，计算机视觉，[1, 2]'

def test_template_missing_parameter_is_explicit():
    with pytest.raises(HTTPException) as exc:
        fill_template('{{missing}}',{})
    assert exc.value.status_code == 422
    assert exc.value.detail['parameters']==['missing']

def test_date_only_deadline_is_end_of_day_in_local_timezone():
    value=parse_deadline('2026-11-06')
    assert value.hour==23 and value.minute==59
    assert value.utcoffset()==timedelta(hours=8)

@pytest.mark.parametrize('value',['',None,'not-a-date','2026-99-99'])
def test_invalid_deadlines_do_not_break_calendar(value):
    assert parse_deadline(value) is None
