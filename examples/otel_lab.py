#!/usr/bin/env python3
"""Generate ACTUAL OpenTelemetry spans from a small instrumented local workload.

This is a Python workload with logical service boundaries, not a distributed
production system. Latency/failures are intentionally injected in-process.
"""
from pathlib import Path
import argparse
import json
import time
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.sdk.resources import Resource
from opentelemetry.trace import Status, StatusCode

p=argparse.ArgumentParser(description=__doc__)
p.add_argument("--out",type=Path,default=Path("examples/lab-traces.json"))
p.add_argument("--requests",type=int,default=16)
a=p.parse_args()
if not 4<=a.requests<=100:p.error("Use 4..100 requests")
collected=[]
class Capture(SpanExporter):
    def export(self,spans):collected.extend(spans);return SpanExportResult.SUCCESS
    def shutdown(self):pass
    def force_flush(self,timeout_millis=30000):return True
tracers={};providers=[]
for name in ["gateway","checkout","payment","database"]:
    provider=TracerProvider(resource=Resource.create({"service.name":name}))
    provider.add_span_processor(SimpleSpanProcessor(Capture()))
    tracers[name]=provider.get_tracer("tracelens-lab");providers.append(provider)
for j in range(a.requests):
    fault=j>=a.requests//2
    with tracers["gateway"].start_as_current_span("POST /checkout") as g:
        with tracers["checkout"].start_as_current_span("checkout.handle") as c:
            with tracers["payment"].start_as_current_span("payment.authorize") as pay:
                with tracers["database"].start_as_current_span("SELECT account") as db:
                    time.sleep(.035 if fault else .002)
                    if fault:
                        db.record_exception(TimeoutError("statement timeout while waiting for a local lock"))
                        for span in [db,pay,c,g]:span.set_status(Status(StatusCode.ERROR,"dependency timed out"))
    time.sleep(.005)
resources={}
for span in collected:
    name=span.resource.attributes["service.name"]
    events=[]
    for event in span.events:
        events.append({"name":event.name,"timeUnixNano":str(event.timestamp),"attributes":[{"key":k,"value":{"stringValue":str(v)}} for k,v in (event.attributes or {}).items()]})
    resources.setdefault(name,[]).append({"traceId":f"{span.context.trace_id:032x}","spanId":f"{span.context.span_id:016x}",
        "parentSpanId":f"{span.parent.span_id:016x}" if span.parent else "","name":span.name,
        "startTimeUnixNano":str(span.start_time),"endTimeUnixNano":str(span.end_time),"status":{"code":span.status.status_code.value},"events":events})
payload={"resourceSpans":[{"resource":{"attributes":[{"key":"service.name","value":{"stringValue":name}}]},"scopeSpans":[{"scope":{"name":"tracelens-lab"},"spans":spans}]} for name,spans in resources.items()]}
a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(payload,indent=2)+"\n")
for provider in providers:provider.shutdown()
print(f"Captured {len(collected)} real SDK spans from a controlled, in-process fault experiment: {a.out}")
