from contextlib import contextmanager
from types import SimpleNamespace
from app.repository import TaskRepository
from app.models import TaskStatus

def test_recurring_task_keeps_actual_attempt_result():
    statements=[]
    class Connection:
        def execute(self,sql,params):
            statements.append((sql,params))
            return SimpleNamespace(fetchone=lambda:{'kind':'scheduled','cancel_requested':False})
    class Pool:
        @contextmanager
        def connection(self):yield Connection()
    repo=TaskRepository('postgresql://unused/unused');repo.pool=Pool()
    repo.finish('00000000-0000-0000-0000-000000000001',TaskStatus.SUCCEEDED,0,None,'run.log')
    updates=[(sql,p) for sql,p in statements if 'UPDATE' in sql]
    assert updates[0][1][0]=='scheduled'
    assert updates[1][1][0]=='succeeded'
