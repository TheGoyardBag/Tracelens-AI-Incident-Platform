import time
import uuid
import pytest
from tracelens.store import Store,ConflictError


def start(client,auth,case,mode="offline",key=None):
    return client.post('/api/runs',headers=auth,json={"incident_id":case.id,"mode":mode,"idempotency_key":key or str(uuid.uuid4())})
def wait(client,auth,rid):
    for _ in range(200):
        run=client.get(f'/api/runs/{rid}',headers=auth).json()
        if run['status'] in ['complete','failed']:return run
        time.sleep(.01)
    raise AssertionError('Run did not complete')

def test_health_and_auth(client):
    assert client.get('/health').status_code==200
    assert client.get('/api/incidents').status_code==401
    assert client.get('/api/incidents',headers={'Authorization':'Bearer wrong'}).status_code==401
    assert client.get('/').status_code==200
def test_list_has_no_truth(client,auth):
    res=client.get('/api/incidents',headers=auth)
    assert res.status_code==200 and len(res.json()['incidents'])==16
    for forbidden in ['root_service','fault_family','split']:assert forbidden not in res.text
def test_case_round_trip(client,auth,case):
    assert client.get(f'/api/incidents/{case.id}',headers=auth).json()==case.model_dump()
def test_run_and_event_stream(client,auth,case):
    res=start(client,auth,case);assert res.status_code==202
    run=wait(client,auth,res.json()['id']);assert run['status']=='complete'
    assert 'diagnosis' in run['result']
    stream=client.get(f"/api/runs/{run['id']}/events",headers=auth)
    assert stream.status_code==200 and 'event: done' in stream.text
    assert 'get_service_metrics' in stream.text
    replay=client.get(f"/api/runs/{run['id']}/events?after=99999",headers=auth)
    assert 'event: step' not in replay.text and 'event: done' in replay.text
def test_idempotent_request(client,auth,case):
    key=str(uuid.uuid4());a=start(client,auth,case,key=key);b=start(client,auth,case,key=key)
    assert a.json()['id']==b.json()['id']
    assert len(client.get('/api/runs',headers=auth).json()['runs'])==1
def test_idempotency_mismatch(client,auth,case):
    key=str(uuid.uuid4());start(client,auth,case,key=key)
    another=client.get('/api/incidents',headers=auth).json()['incidents'][1]['id']
    res=client.post('/api/runs',headers=auth,json={'incident_id':another,'idempotency_key':key})
    assert res.status_code==409
def test_unconfigured_llm_rejected(client,auth,case):assert start(client,auth,case,mode='llm').status_code==422
def test_unknown_incident(client,auth):
    assert client.get('/api/incidents/notfound',headers=auth).status_code==404
    assert client.post('/api/runs',headers=auth,json={'incident_id':'absent','idempotency_key':str(uuid.uuid4())}).status_code==404
def test_unknown_run(client,auth):assert client.get('/api/runs/notfound',headers=auth).status_code==404
def test_import_downgrades_trust(client,auth,case):
    data=case.model_dump();data['id']='new-upload'
    res=client.post('/api/incidents',headers=auth,json=data)
    assert res.status_code==201 and res.json()['source']=='imported'
    assert client.post('/api/incidents',headers=auth,json=data).status_code==409
def test_no_ground_truth_import(client,auth,case):
    raw=case.model_dump();raw['root_service']='checkout'
    assert client.post('/api/incidents',headers=auth,json=raw).status_code==422
def test_oversized_body(client,auth):
    assert client.post('/api/incidents',headers={**auth,'Content-Type':'application/json'},content=b'x'*2_000_001).status_code==413
def test_feedback_review(client,auth,case):
    run=wait(client,auth,start(client,auth,case).json()['id']);rid=run['id']
    assert client.post(f'/api/runs/{rid}/feedback',headers=auth,json={'correct':True,'expected_service':'missing'}).status_code==422
    res=client.post(f'/api/runs/{rid}/feedback',headers=auth,json={'correct':False,'note':'Review the dependency timeline'})
    assert res.status_code==200 and res.json()['used_for_training'] is False
    body={'confirmed':True,'note':'Read the evidence; no action requested'}
    a=client.post(f'/api/runs/{rid}/review',headers=auth,json=body).json()
    b=client.post(f'/api/runs/{rid}/review',headers=auth,json=body).json()
    assert a['executes_changes'] is False and a['review']['id']==b['review']['id']
    assert client.post(f'/api/runs/{rid}/review',headers=auth,json={'confirmed':False,'note':'no'}).status_code==422
    assert any(e['action']=='human_review_recorded' for e in client.get('/api/audit',headers=auth).json()['events'])
def test_security_headers(client,auth):
    r=client.get('/api/incidents',headers=auth)
    assert r.headers['cache-control']=='no-store' and r.headers['x-content-type-options']=='nosniff'
def test_cors_rejects_other_origin(client):
    response=client.options('/api/incidents',headers={'Origin':'https://untrusted.invalid','Access-Control-Request-Method':'GET'})
    assert response.status_code==400
def test_invalid_host(client):assert client.get('/health',headers={'Host':'evil.example'}).status_code==400
def test_evaluation_label(client,auth):
    r=client.get('/api/evaluation',headers=auth).json();assert r['source']=='synthetic' and 'results' in r
def test_restart_marks_jobs_interrupted(tmp_path,case):
    s=Store(f"sqlite:///{tmp_path/'db.sqlite'}");s.add_incident(case)
    r,new=s.create_run(case.id,'offline','request-id-12345');s.update_run(r['id'],'running');s.mark_interrupted()
    assert s.get_run(r['id'])['status']=='interrupted';s.engine.dispose()
def test_feedback_pending_rejected(client,auth,case):
    r,_=client.app.state.store.create_run(case.id,'offline','not-submitted-to-worker')
    assert client.post(f"/api/runs/{r['id']}/feedback",headers=auth,json={'correct':True}).status_code==409

def test_non_ascii_invalid_credential_is_rejected(client):
    assert client.get('/api/incidents',headers=[(b'authorization',b'Bearer \xff')]).status_code==401
