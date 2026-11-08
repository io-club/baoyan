from calendar_events import milestones

def test_raw_source_nodes_are_individual_dates_not_a_duration():
    nodes=milestones({'raw':{'sign_up_start':'2040/05/01','sign_up_end':'2040/05/20 24:00:00','start_time':'2040/06/01'}})
    assert set(nodes)=={'registration_start','deadline','activity_start'}
    assert nodes['registration_start'].isoformat()=='2040-05-01T00:00:00+08:00'
    assert nodes['deadline'].date().isoformat()=='2040-05-21'
    assert nodes['activity_start'].hour==0

def test_explicitly_cleared_node_does_not_resurface_from_raw_archive():
    assert milestones({'registration_start':None,'deadline':None,'activity_start':None,'raw':{'sign_up_start':'2040-05-01','sign_up_end':'2040-05-20','start_time':'2040-06-01'}})=={}

def test_bad_source_dates_do_not_fabricate_nodes():
    assert milestones({'raw':{'sign_up_start':'待定','sign_up_end':'0','start_time':''}})=={}
