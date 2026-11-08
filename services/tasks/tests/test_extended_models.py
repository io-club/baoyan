import pytest
from pydantic import ValidationError
from app.models import CreateTask

@pytest.mark.parametrize('value',['invalid/zone','../../etc/passwd'])
def test_task_timezone_is_validated(value):
    with pytest.raises(ValidationError):
        CreateTask(name='timezone',kind='oneshot',command=['true'],timezone=value)

def test_second_precision_cron_is_rejected():
    with pytest.raises(ValidationError):
        CreateTask(name='cron',kind='scheduled',command=['true'],schedule_cron='* * * * * *')

def test_task_response_redacts_cookie_without_mutating_worker_payload():
    from app.models import TaskResponse
    payload={'environment':{'XHS_COOKIE':'private-session','XHS_QUERY':'保研'}}
    task=TaskResponse.model_construct(metadata=payload)
    dumped=task.model_dump(include={'metadata'})
    assert dumped['metadata']['environment']['XHS_COOKIE']=='***'
    assert dumped['metadata']['environment']['XHS_QUERY']=='保研'
    assert payload['environment']['XHS_COOKIE']=='private-session'
