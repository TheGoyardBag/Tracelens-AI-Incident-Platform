"""File adapter for an OTLP/JSON ExportTraceServiceRequest subset.

Not a general OTLP collector: this supports trace resourceSpans/scopeSpans only.
Missing CPU/memory/queue metrics are represented as zeros (unknown), so imported
incidents are explicitly outside the synthetic model's calibration domain.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timezone
import math
import re
import numpy as np
from tracelens.schema import Incident, clean_identifier
from tracelens.agents.tools import redact


def attributes(rows):
    output={}
    for row in rows:
        value=row.get("value",{})
        for kind in ("stringValue","intValue","doubleValue","boolValue"):
            if kind in value:output[row.get("key","")]=value[kind];break
    return output


def convert_otlp(payload:dict,incident_id:str,source:str="imported") -> Incident:
    if not isinstance(payload,dict) or not isinstance(payload.get("resourceSpans"),list):
        raise ValueError("Expected OTLP/JSON resourceSpans")
    records=[];raw_names={}
    for resource in payload["resourceSpans"]:
        raw=str(attributes(resource.get("resource",{}).get("attributes",[])).get("service.name",""))
        if not raw:raise ValueError("Every resource needs service.name")
        service=clean_identifier(raw)
        if service in raw_names and raw_names[service]!=raw:raise ValueError("Service names collide after normalization")
        raw_names[service]=raw
        for scope in resource.get("scopeSpans",[]):
            for span in scope.get("spans",[]):
                if len(records)>=900:raise ValueError("Limit adapter imports to 900 spans per incident")
                trace_id=str(span.get("traceId",""));span_id=str(span.get("spanId",""))
                if not re.fullmatch(r"[0-9a-fA-F]{32}",trace_id) or not re.fullmatch(r"[0-9a-fA-F]{16}",span_id):
                    raise ValueError("OTLP trace/span IDs must be 32/16 hex characters")
                start=int(span["startTimeUnixNano"]);end=int(span["endTimeUnixNano"])
                if start<0 or end<start:raise ValueError("Invalid span timestamps")
                records.append({"service":service,"trace":trace_id,"id":span_id,"parent":span.get("parentSpanId",""),
                                "start":start,"end":end,"raw":span})
    if not records:raise ValueError("No spans in payload")
    if not 2<=len(raw_names)<=32:raise ValueError("An incident requires 2..32 services")
    first=min(r["start"] for r in records);last=max(r["end"] for r in records)
    width=max(1000.,(last-first)/24)
    step_seconds=width/1e9
    mapping={(r["trace"],r["id"]):r for r in records}
    if len(mapping)!=len(records):raise ValueError("Duplicate spans")
    buckets=defaultdict(list);spans=[];logs=[]
    for r in records:
        t=min(23,max(0,int((r["start"]-first)/width)))
        ms=(r["end"]-r["start"])/1e6
        code=r["raw"].get("status",{}).get("code",0)
        status="ERROR" if code in (2,"STATUS_CODE_ERROR") else "OK"
        base=dict(service=r["service"],time=t,duration_ms=ms,status=status,
                  operation=str(r["raw"].get("name","span"))[:240],trace_id=r["trace"])
        key=r["trace"]+"-"+r["id"]
        spans.append(dict(id="span-"+key,**base))
        buckets[(r["service"],t)].append((ms,status=="ERROR"))
        parent=mapping.get((r["trace"],r["parent"]))
        if parent and parent["service"]!=r["service"]:
            spans.append(dict(id="edge-"+key,**{**base,"service":parent["service"],"target":r["service"]}))
        for j,event in enumerate(r["raw"].get("events",[])[:4]):
            values=attributes(event.get("attributes",[]))
            message=values.get("exception.message",event.get("name","span event"))
            logs.append(dict(id=f"event-{key}-{j}",service=r["service"],time=t,
                             level="ERROR" if event.get("name")=="exception" else "INFO",message=redact(str(message))))
    services=[]
    for name in raw_names:
        measurements={k:[] for k in ("error_rate","latency_ms","request_rate")}
        for i in range(24):
            rows=buckets[(name,i)]
            measurements["error_rate"].append(sum(x[1] for x in rows)/len(rows) if rows else 0.)
            measurements["latency_ms"].append(float(np.mean([x[0] for x in rows])) if rows else 0.)
            measurements["request_rate"].append(len(rows)/step_seconds)
        measurements.update(cpu_pct=[0.]*24,memory_mb=[0.]*24,queue_depth=[0.]*24)
        services.append(dict(name=name,metrics=measurements))
    return Incident.model_validate(dict(id=incident_id,title="OTLP trace snapshot (CPU, memory and queue metrics unavailable)",source=source,
        started_at=datetime.fromtimestamp(first/1e9,tz=timezone.utc).isoformat(),sample_seconds=step_seconds,
        services=services,logs=logs,spans=spans,deployments=[]))
