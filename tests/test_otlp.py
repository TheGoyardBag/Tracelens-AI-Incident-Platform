import copy
import pytest
from tracelens.integrations.otlp import convert_otlp,attributes

@pytest.fixture
def trace_payload():
    def resource(name,sid,parent=''):
        return {'resource':{'attributes':[{'key':'service.name','value':{'stringValue':name}}]},'scopeSpans':[{'spans':[{'traceId':'a'*32,'spanId':sid,'parentSpanId':parent,'name':'handler','startTimeUnixNano':'1700000000000000000','endTimeUnixNano':'1700000000010000000','status':{'code':2},'events':[{'name':'exception','attributes':[{'key':'exception.message','value':{'stringValue':'timeout token=privatevalue'}}]}]}]}]}
    return {'resourceSpans':[resource('gateway','1'*16),resource('database','2'*16,'1'*16)]}

def test_otlp_conversion(trace_payload):
    case=convert_otlp(trace_payload,'import-001')
    assert len(case.services)==2 and len(case.spans)==3
    assert any(s.target=='database' for s in case.spans)
    assert all('privatevalue' not in l.message for l in case.logs)
    assert case.source=='imported'
def test_otlp_missing_resource():
    with pytest.raises(ValueError):convert_otlp({},'x')
def test_otlp_duplicate_spans(trace_payload):
    trace_payload['resourceSpans'].append(trace_payload['resourceSpans'][0])
    with pytest.raises(ValueError,match='Duplicate'):convert_otlp(trace_payload,'x')
def test_otlp_invalid_hex_id(trace_payload):
    trace_payload['resourceSpans'][0]['scopeSpans'][0]['spans'][0]['traceId']='not-hex'
    with pytest.raises(ValueError,match='hex'):convert_otlp(trace_payload,'x')
def test_otlp_bad_timestamps(trace_payload):
    trace_payload['resourceSpans'][0]['scopeSpans'][0]['spans'][0]['endTimeUnixNano']='0'
    with pytest.raises(ValueError,match='timestamp'):convert_otlp(trace_payload,'x')
def test_otlp_missing_service(trace_payload):
    trace_payload['resourceSpans'][0]['resource']['attributes']=[]
    with pytest.raises(ValueError,match='service.name'):convert_otlp(trace_payload,'x')
def test_otlp_collision(trace_payload):
    trace_payload['resourceSpans'][0]['resource']['attributes'][0]['value']['stringValue']='service/x'
    trace_payload['resourceSpans'][1]['resource']['attributes'][0]['value']['stringValue']='service-x'
    with pytest.raises(ValueError,match='collide'):convert_otlp(trace_payload,'x')
def test_attribute_types():assert attributes([{'key':'v','value':{'intValue':'12'}}])=={'v':'12'}
