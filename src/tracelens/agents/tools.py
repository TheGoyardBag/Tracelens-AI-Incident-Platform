"""Read-only investigation tools and a per-run evidence registry.

Tools accept service names and trace IDs, never paths, SQL, URLs, or commands.
Telemetry is untrusted input. Redaction is best-effort, not a privacy guarantee.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from tracelens.schema import Incident

RUNBOOKS=[
    {"id":"runbook:cpu","title":"CPU saturation and queue pressure","text":"Inspect worker queue, CPU usage and traffic. Compare recent deployments. Reproduce under bounded load before changing concurrency."},
    {"id":"runbook:memory","title":"Memory pressure","text":"Inspect allocation growth, garbage collection pauses and heap limits. Compare a baseline time window. Capture a profile in an isolated environment."},
    {"id":"runbook:database","title":"Slow queries and lock contention","text":"Check statement timeouts, local query duration and lock waits. Inspect slow query traces. Reproduce with a read-only query plan in a test database."},
    {"id":"runbook:connection","title":"Dependency and connection failures","text":"Inspect downstream span errors, connection pool saturation, service discovery and endpoint changes. Test connectivity in a sandbox before suggesting a rollback."},
    {"id":"runbook:configuration","title":"Configuration regressions","text":"Compare recent application configuration deployments and validation errors. Correlation with a deployment is not proof. Review the diff before approving any rollback."},
]


def redact(text: str) -> str:
    text=re.sub(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b","[EMAIL]",text,flags=re.I)
    text=re.sub(r"\b(?:sk-|ghp_|github_pat_)[a-zA-Z0-9_-]{10,}","[TOKEN]",text)
    text=re.sub(r"(?i)bearer\s+[A-Za-z0-9._~+/-]+","Bearer [REDACTED]",text)
    text=re.sub(r"(?i)(password|secret|api[_-]?key|authorization|token)\s*[:=]\s*([^\s,;]+)",r"\1=[REDACTED]",text)
    text=re.sub(r"(?i)bearer\s+[A-Za-z0-9._~+/-]+","Bearer [REDACTED]",text)
    return text[:1200]


@dataclass
class EvidenceRegistry:
    items: dict[str, dict] = field(default_factory=dict)

    def add(self, evidence_id: str, kind: str, service: str|None, data: dict) -> dict:
        item={"id":evidence_id,"kind":kind,"service":service,"data":data}
        self.items[evidence_id]=item
        return item


class ToolBox:
    def __init__(self, incident: Incident, max_calls: int=10):
        self.incident=incident
        self.services={s.name:s for s in incident.services}
        self.registry=EvidenceRegistry()
        self.max_calls=max_calls
        self.calls=0

    def execute(self,name: str,args: dict) -> dict:
        if self.calls>=self.max_calls:raise ValueError("Investigation tool budget exhausted")
        functions={"get_service_metrics":self.get_service_metrics,"search_logs":self.search_logs,
                   "inspect_traces":self.inspect_traces,"get_recent_deployments":self.get_recent_deployments,
                   "retrieve_runbook":self.retrieve_runbook}
        if name not in functions:raise ValueError("Tool is not allowlisted")
        if not isinstance(args,dict):raise ValueError("Tool arguments must be an object")
        self.calls+=1
        return functions[name](**args)

    def _service(self,service):
        if service not in self.services:raise ValueError("Unknown service")
        return self.services[service]

    def get_service_metrics(self,service: str) -> dict:
        svc=self._service(service)
        n=len(next(iter(svc.metrics.values())))
        baseline=max(2,n//4)
        data={k:{"baseline":round(float(np.mean(v[:baseline])),4),
                 "recent":round(float(np.mean(v[-baseline:])),4),"peak":round(max(v),4)} for k,v in svc.metrics.items()}
        return {"evidence":[self.registry.add(f"metrics:{service}","metrics",service,data)]}

    def search_logs(self,service: str,query: str="") -> dict:
        self._service(service)
        if not isinstance(query,str) or len(query)>200:raise ValueError("Query too long")
        rows=sorted((l for l in self.incident.logs if l.service==service and query.lower() in l.message.lower()),key=lambda x:x.time)
        return {"evidence":[self.registry.add(f"log:{l.id}","log",service,{"time":l.time,"level":l.level,"message":redact(l.message)}) for l in rows[-12:]]}

    def inspect_traces(self,service: str) -> dict:
        self._service(service)
        rows=[s for s in self.incident.spans if s.service==service or s.target==service]
        rows=sorted(rows,key=lambda s:(s.status=="ERROR",s.time),reverse=True)[:12]
        return {"evidence":[self.registry.add(f"trace:{s.id}","trace",s.service,s.model_dump()) for s in rows]}

    def get_recent_deployments(self,service: str) -> dict:
        self._service(service)
        rows=[d for d in self.incident.deployments if d.service==service]
        return {"evidence":[self.registry.add(f"deploy:{d.id}","deployment",service,{**d.model_dump(),"summary":redact(d.summary)}) for d in rows]}

    def retrieve_runbook(self,query: str) -> dict:
        if not isinstance(query,str) or len(query)>1200:raise ValueError("Query too long")
        vector=TfidfVectorizer(stop_words="english")
        matrix=vector.fit_transform(r["title"]+" "+r["text"] for r in RUNBOOKS)
        similarities=(matrix@vector.transform([query]).T).toarray().ravel()
        order=np.argsort(-similarities)[:2]
        return {"evidence":[self.registry.add(RUNBOOKS[int(i)]["id"],"runbook",None,RUNBOOKS[int(i)]) for i in order if similarities[i]>0]}

    def schemas(self) -> list[dict]:
        service={"type":"string","enum":list(self.services)}
        definitions=[
            ("get_service_metrics","Compare baseline, recent, and peak metrics for a service",{"service":service},["service"]),
            ("search_logs","Read redacted incident logs for one service",{"service":service,"query":{"type":"string","maxLength":200}},["service"]),
            ("inspect_traces","Read spans involving a service or its dependencies",{"service":service},["service"]),
            ("get_recent_deployments","Inspect changes; temporal correlation is not proof",{"service":service},["service"]),
            ("retrieve_runbook","Retrieve reference guidance, not evidence of incident cause",{"query":{"type":"string","maxLength":1200}},["query"]),
        ]
        return [{"name":name,"description":description,"input_schema":{"type":"object","properties":props,"required":required,"additionalProperties":False}} for name,description,props,required in definitions]
