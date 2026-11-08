import json
from advisor_queries import predicate

def test_classification_filters_are_parameterized_and_composable():
    sql,values=predicate("学校' OR true --",'学院','研究所','视觉')
    assert "学校'" not in sql
    assert values[:3]==["学校' OR true --",'学院','研究所']
    assert json.loads(values[3])==['视觉']
    assert "center" in sql and '@>' in sql

def test_uncategorized_records_are_filterable_without_migration():
    sql,values=predicate(category='未分类')
    assert 'jsonb_array_length' in sql and values==[]
