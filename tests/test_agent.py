import json
import httpx
import pytest
from tracelens.agents.tools import ToolBox,redact
from tracelens.agents.investigate import investigate,validate_diagnosis
from tracelens.agents.provider import AnthropicInvestigator
from tracelens.schema import Diagnosis,Claim


def test_offline_complete_citations(case,predictor):
    events=[];result=investigate(case,predictor,lambda k,v:events.append((k,v)))
    ids={e["id"] for e in result["evidence"]}
    assert result["provider"]["effective_mode"]=="offline" and result["tool_calls"]==8
    assert all(set(c["evidence_ids"])<=ids for c in result["diagnosis"]["claims"])
    assert result["remediation"]["executes_infrastructure_changes"] is False
    assert any(k=="validation" for k,v in events)
def test_unknown_tool_rejected(case):
    with pytest.raises(ValueError,match="allowlisted"):ToolBox(case).execute("run_shell",{"command":"id"})
def test_unknown_service_rejected(case):
    with pytest.raises(ValueError,match="Unknown service"):ToolBox(case).execute("search_logs",{"service":"../../etc/passwd"})
def test_tool_budget(case):
    box=ToolBox(case,max_calls=1);box.execute("get_service_metrics",{"service":case.services[0].name})
    with pytest.raises(ValueError,match="budget"):box.execute("get_service_metrics",{"service":case.services[0].name})
@pytest.mark.parametrize("text,secret",[("api_key=supersecret","supersecret"),("contact john@example.org","john@example.org"),("Authorization: Bearer abcdefghijk","abcdefghijk"),("token=superduper123","superduper123")])
def test_redaction(text,secret):assert secret not in redact(text)
def test_citation_fabrication_rejected(case):
    box=ToolBox(case)
    d=Diagnosis(status="supported",likely_service=case.services[0].name,summary="Claim",claims=[Claim(text="Unsupported",evidence_ids=["invented"])])
    with pytest.raises(ValueError,match="not retrieved"):validate_diagnosis(d,box)
def test_runbook_not_proof(case):
    box=ToolBox(case);box.execute("retrieve_runbook",{"query":"cpu queue"})
    d=Diagnosis(status="supported",likely_service=case.services[0].name,summary="Claim",claims=[Claim(text="This advice proves a failure",evidence_ids=["runbook:cpu"])])
    with pytest.raises(ValueError,match="telemetry"):validate_diagnosis(d,box)
def test_nonexistent_service_rejected(case):
    d=Diagnosis(status="inconclusive",likely_service="other",summary="No")
    with pytest.raises(ValueError,match="outside"):validate_diagnosis(d,ToolBox(case))
def test_evidence_namespace_collision_blocked(case):
    raw=case.model_dump();raw["logs"][0]["id"]="metrics:"+raw["logs"][0]["service"]
    from tracelens.schema import Incident
    box=ToolBox(Incident.model_validate(raw));service=raw["logs"][0]["service"]
    box.execute("get_service_metrics",{"service":service});box.execute("search_logs",{"service":service})
    assert box.registry.items[f"metrics:{service}"]["kind"]=="metrics"
def test_provider_tool_call_round_trip(case,predictor):
    top=predictor.rank(case)["candidates"][0]["service"];requests=[]
    def handler(request):
        body=json.loads(request.content);requests.append(body)
        if len(requests)==1:content=[{"type":"tool_use","id":"t1","name":"get_service_metrics","input":{"service":top}}]
        else:content=[{"type":"tool_use","id":"t2","name":"submit_diagnosis","input":{"status":"supported","likely_service":top,"summary":"Metrics warrant investigation, not a proven cause.","claims":[{"text":"The cited metrics compare baseline and recent observations.","evidence_ids":[f"metrics:{top}"]}],"next_steps":["Inspect traces"],"limitations":["No causal proof"]}}]
        return httpx.Response(200,json={"content":content,"usage":{"input_tokens":20,"output_tokens":15}})
    provider=AnthropicInvestigator("test-key","mock-model",transport=httpx.MockTransport(handler))
    result=investigate(case,predictor,lambda *_:None,"llm",provider)
    assert result["provider"]["calls"]==2 and result["provider"]["effective_mode"]=="llm"
    assert "tool_result" in json.dumps(requests[1])
def test_provider_invalid_citation_falls_back(case,predictor):
    top=case.services[0].name
    def handler(request):return httpx.Response(200,json={"content":[{"type":"tool_use","id":"x","name":"submit_diagnosis","input":{"status":"supported","likely_service":top,"summary":"Unverified","claims":[{"text":"made up","evidence_ids":["fake"]}]}}]})
    p=AnthropicInvestigator("test-key","mock-model",transport=httpx.MockTransport(handler))
    result=investigate(case,predictor,lambda *_:None,"llm",p)
    assert result["provider"]["effective_mode"]=="offline-fallback"
    assert "fake" not in {e["id"] for e in result["evidence"]}
def test_provider_http_failure_falls_back(case,predictor):
    p=AnthropicInvestigator("test-key","mock-model",transport=httpx.MockTransport(lambda request:httpx.Response(429,json={"error":"rate limited"})))
    assert investigate(case,predictor,lambda *_:None,"llm",p)["provider"]["effective_mode"]=="offline-fallback"
def test_provider_deadline(case,predictor):
    p=AnthropicInvestigator("test-key","mock-model",budget_seconds=-1)
    with pytest.raises(TimeoutError):p.investigate(case,predictor.rank(case),ToolBox(case),lambda *_:None)
def test_query_limit(case):
    with pytest.raises(ValueError,match="long"):ToolBox(case).search_logs(case.services[0].name,"a"*201)
