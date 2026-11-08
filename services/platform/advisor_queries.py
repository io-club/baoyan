"""Shared SQL classification for list pagination and cascading facet counts."""
import json
EXPRESSIONS = {
    'school': "COALESCE(NULLIF(btrim(data->>'school'),''),'未分类')",
    'department': "COALESCE(NULLIF(btrim(data->>'department'),''),'未分类')",
    'institute': "COALESCE(NULLIF(btrim(data->>'institute'),''),NULLIF(btrim(data->>'center'),''),'未分类')",
}
CATEGORIES = """(CASE WHEN jsonb_typeof(data->'categories')='array' THEN data->'categories' ELSE '[]'::jsonb END
    || CASE WHEN jsonb_typeof(data#>'{data,categories}')='array' THEN data#>'{data,categories}' ELSE '[]'::jsonb END
    || CASE WHEN COALESCE(data->>'category','')<>'' THEN jsonb_build_array(data->>'category') ELSE '[]'::jsonb END)"""

def predicate(school='',department='',institute='',category=''):
    clauses=[];params=[]
    for key,value in [('school',school),('department',department),('institute',institute)]:
        if value:
            clauses.append(EXPRESSIONS[key]+'=%s');params.append(value)
    if category:
        if category=='未分类':clauses.append(f"jsonb_array_length({CATEGORIES})=0")
        else:clauses.append(f"{CATEGORIES} @> %s::jsonb");params.append(json.dumps([category],ensure_ascii=False))
    return ''.join(' AND '+clause for clause in clauses),params

def facets(conn,school='',department='',institute=''):
    result={}
    for key in ('school','department','institute','category'):
        where,params=predicate(school if key!='school' else '',department if key in ('institute','category') else '',institute if key=='category' else '')
        expression=EXPRESSIONS.get(key)
        if expression:
            sql=f"SELECT {expression} AS value,count(*) AS count FROM platform.entities WHERE resource='advisors'{where} GROUP BY 1 ORDER BY 1"
        else:
            sql=f"""SELECT category.value,count(DISTINCT id) AS count FROM platform.entities
                CROSS JOIN LATERAL jsonb_array_elements_text(CASE WHEN jsonb_array_length({CATEGORIES})=0 THEN '[\"未分类\"]'::jsonb ELSE {CATEGORIES} END) category(value)
                WHERE resource='advisors'{where} GROUP BY 1 ORDER BY 1"""
        result[key]=[dict(row) for row in conn.execute(sql,params).fetchall()]
    return result
