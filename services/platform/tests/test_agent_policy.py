from copy import deepcopy
from agent_policy import enrich_launch,SYSTEM_PROMPT,MARKER

def test_runtime_context_and_platform_policy_are_both_kept():
    request={'agent_settings':{'agent_context':{'system_message_suffix':'<RUNTIME_SERVICES>runtime</RUNTIME_SERVICES>'}},'agent_launch_additions':{'system_message_suffix_append':'custom'}}
    result=enrich_launch(deepcopy(request))
    assert result['agent_settings']==request['agent_settings']
    assert result['agent_launch_additions']['system_message_suffix_append'].startswith('custom')
    assert SYSTEM_PROMPT in result['agent_launch_additions']['system_message_suffix_append']
    assert enrich_launch(deepcopy(result))==result

def test_profile_launch_gets_same_platform_policy():
    result=enrich_launch({'agent_profile_id':'stored-profile'})
    assert result['agent_profile_id']=='stored-profile'
    assert MARKER in result['agent_launch_additions']['system_message_suffix_append']
    assert 'SQLite' in SYSTEM_PROMPT and 'PLATFORM_API.md' in SYSTEM_PROMPT

def test_replaces_only_owned_old_policies_and_does_not_accumulate():
    old='<BAOYAN_PLATFORM_API_V2>obsolete</BAOYAN_PLATFORM_API_V2>'
    request={'agent_settings':{'agent_context':{'system_message_suffix':'<RUNTIME_SERVICES>runtime</RUNTIME_SERVICES>\n'+old+'\nuser preference'}},'agent_launch_additions':{'system_message_suffix_append':old+'\ncustom'}}
    result=enrich_launch(deepcopy(request))
    context=result['agent_settings']['agent_context']['system_message_suffix']
    assert '<RUNTIME_SERVICES>runtime</RUNTIME_SERVICES>' in context and 'user preference' in context
    assert 'obsolete' not in context
    suffix=result['agent_launch_additions']['system_message_suffix_append']
    assert 'obsolete' not in suffix and suffix.startswith('custom')
    assert suffix.count('<'+MARKER+'>')==1
    assert enrich_launch(deepcopy(result))==result

def test_direct_agent_and_null_launch_additions_are_supported():
    request={'agent':{'agent_context':{'system_message_suffix':'<BAOYAN_PLATFORM_API_V3>old</BAOYAN_PLATFORM_API_V3>\ncustom context'}},'agent_launch_additions':None}
    result=enrich_launch(deepcopy(request))
    assert result['agent']['agent_context']['system_message_suffix']=='custom context'
    assert result['agent_launch_additions']['system_message_suffix_append']==SYSTEM_PROMPT
