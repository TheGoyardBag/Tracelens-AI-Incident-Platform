"""Bounded, evidence-first investigations. Offline mode is a deterministic policy,
not an LLM. Optional hosted mode uses an actual tool-calling provider.
"""
from __future__ import annotations
from collections.abc import Callable
import time
from tracelens.schema import Incident, Diagnosis, Claim
from .tools import ToolBox

Emit=Callable[[str,dict],None]


def validate_diagnosis(diagnosis: Diagnosis,box: ToolBox) -> Diagnosis:
    names=set(box.services)
    if diagnosis.likely_service is not None and diagnosis.likely_service not in names:
        raise ValueError("Diagnosis names a service outside this incident")
    for claim in diagnosis.claims:
        if any(key not in box.registry.items for key in claim.evidence_ids):
            raise ValueError("Diagnosis cites evidence that was not retrieved")
    if diagnosis.status=="supported":
        if not diagnosis.likely_service or not diagnosis.claims:raise ValueError("Supported diagnosis needs claims and a service")
        keys={key for c in diagnosis.claims for key in c.evidence_ids}
        matching=[box.registry.items[k] for k in keys if box.registry.items[k]["kind"]!="runbook" and (
            box.registry.items[k]["service"]==diagnosis.likely_service or
            box.registry.items[k]["data"].get("target")==diagnosis.likely_service)]
        if not matching:raise ValueError("Supported diagnosis needs telemetry about its proposed service")
    # This verifies reference integrity, not natural-language entailment.
    return diagnosis


def collect_offline(ranking: dict,box: ToolBox,emit: Emit):
    for candidate in ranking["candidates"][:2]:
        for name in ("get_service_metrics","search_logs","inspect_traces"):
            before=time.monotonic();args={"service":candidate["service"]}
            result=box.execute(name,args)
            emit("tool",{"tool":name,"arguments":args,"evidence_count":len(result["evidence"]),
                         "evidence_ids":[e["id"] for e in result["evidence"]],"duration_ms":round((time.monotonic()-before)*1000,2)})
    name="get_recent_deployments";args={"service":ranking["candidates"][0]["service"]}
    result=box.execute(name,args);emit("tool",{"tool":name,"arguments":args,"evidence_count":len(result["evidence"])})
    messages=" ".join(x["data"].get("message","") for x in box.registry.items.values() if x["service"]==args["service"])
    result=box.execute("retrieve_runbook",{"query":messages[:1200]})
    emit("tool",{"tool":"retrieve_runbook","arguments":{"query":"Retrieved incident log excerpts"},"evidence_count":len(result["evidence"])})


def draft_offline(ranking: dict,box: ToolBox) -> Diagnosis:
    top=ranking["candidates"][0]["service"]
    m=box.registry.items[f"metrics:{top}"]["data"]
    claims=[Claim(text=f"{top} error rate changed from {m['error_rate']['baseline']:.1%} to {m['error_rate']['recent']:.1%}; mean latency changed from {m['latency_ms']['baseline']:.0f} to {m['latency_ms']['recent']:.0f} ms.",evidence_ids=[f"metrics:{top}"])]
    errors=[e for e in box.registry.items.values() if e["kind"]=="log" and e["service"]==top and e["data"]["level"]=="ERROR"]
    if errors:
        e=errors[-1];claims.append(Claim(text=f"A retrieved error log from {top} says: {e['data']['message']}",evidence_ids=[e["id"]]))
    spans=[e for e in box.registry.items.values() if e["kind"]=="trace" and e["data"]["status"]=="ERROR" and (e["service"]==top or e["data"].get("target")==top)]
    if spans:
        claims.append(Claim(text=f"{len(spans)} retrieved failed spans involve {top} as a caller or target. This shows association, not proof of the initiating fault.",evidence_ids=[e["id"] for e in spans[:8]]))
    runbooks=[e for e in box.registry.items.values() if e["kind"]=="runbook"]
    limitations=list(ranking["reasons"])+["Reference checks establish citation existence, not causal correctness.","Offline policy gathers evidence deterministically; no language model was called."]
    enough=bool(errors or spans)
    if not enough:limitations.append("No supporting error log or failed trace retrieved for the top candidate")
    return Diagnosis(status="inconclusive" if ranking["abstain"] or not enough else "supported",likely_service=top,
        summary=f"{top} is the model's highest-ranked hypothesis. Inspect the cited telemetry and compare the alternative candidates before acting.",
        claims=claims,next_steps=([r["data"]["text"] for r in runbooks[:2]] or ["Inspect the complete trace path and compare service health with the baseline window."])+["Validate any change in an isolated sandbox; this application never executes remediation."],
        limitations=limitations[:8])


def investigate(incident: Incident,predictor,emit: Emit,mode: str="offline",llm_client=None) -> dict:
    started=time.monotonic();box=ToolBox(incident)
    emit("status",{"message":"Ranking candidate services from telemetry","mode":mode})
    ranking=predictor.rank(incident)
    emit("ranking",ranking)
    provider={"requested_mode":mode,"effective_mode":mode,"input_tokens":0,"output_tokens":0,"calls":0}
    if mode=="llm":
        if llm_client is None:raise ValueError("LLM mode requires an explicitly configured provider")
        try:
            diagnosis,usage=llm_client.investigate(incident,ranking,box,emit)
            provider.update(usage)
            diagnosis=validate_diagnosis(diagnosis,box)
            if ranking["abstain"] and diagnosis.status=="supported":
                diagnosis=diagnosis.model_copy(update={"status":"inconclusive","limitations":(diagnosis.limitations+ranking["reasons"])[:8]})
        except Exception as exc:
            # Never silently pass off a deterministic result as a hosted model answer.
            emit("warning",{"message":"Hosted investigation unavailable or failed validation; switched to offline evidence policy","error_type":type(exc).__name__})
            provider.update(getattr(llm_client,"last_usage",{}))
            provider["effective_mode"]="offline-fallback"
            box=ToolBox(incident);collect_offline(ranking,box,emit);diagnosis=draft_offline(ranking,box)
            diagnosis.limitations.append("Hosted model request failed or returned an invalid diagnosis; no hosted answer is shown.")
    else:
        collect_offline(ranking,box,emit);diagnosis=draft_offline(ranking,box)
    validate_diagnosis(diagnosis,box)
    emit("validation",{"citation_integrity":"passed","claim_count":len(diagnosis.claims),"semantic_entailment":"not automatically verified"})
    return {"ranking":ranking,"diagnosis":diagnosis.model_dump(),"evidence":list(box.registry.items.values()),
            "provider":provider,"tool_calls":box.calls,"duration_ms":round((time.monotonic()-started)*1000,2),
            "remediation":{"mode":"approval-record-only","executes_infrastructure_changes":False}}
