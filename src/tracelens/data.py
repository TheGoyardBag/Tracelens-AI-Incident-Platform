"""Deterministic synthetic incidents with separated labels and grouped splits.

Two observations of the same fault experiment always stay in one split. Held-out
service/fault combinations form a separate challenge set. This is NOT real-world
training data or an estimate of production diagnosis accuracy.
"""
from __future__ import annotations
import gzip
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone
import numpy as np
from .schema import Incident, Label, METRICS

SERVICES = ["gateway", "checkout", "payment", "catalog", "database", "cache"]
FAULTS = ["cpu_saturation", "memory_pressure", "query_latency", "connection_failure", "config_regression"]
LOCAL_MESSAGES = {
    "cpu_saturation": "worker queue is growing; execution exceeded its time budget",
    "memory_pressure": "allocation pressure increased; garbage collection pause exceeded limit",
    "query_latency": "local query execution exceeded statement timeout; lock wait observed",
    "connection_failure": "connection pool exhausted; connection acquisition timed out",
    "config_regression": "local request validation failed after runtime configuration reload",
}


def read_incidents(path: Path) -> list[Incident]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as f:
        return [Incident.model_validate_json(line) for line in f if line.strip()]


def read_labels(path: Path) -> dict[str, Label]:
    with path.open(encoding="utf-8") as f:
        labels = [Label.model_validate_json(line) for line in f if line.strip()]
    if len({l.incident_id for l in labels}) != len(labels):
        raise ValueError("Duplicate label ID")
    return {l.incident_id: l for l in labels}


def generate_case(seed: int, root_index: int, fault: str, incident_id: str, variant: int = 0) -> Incident:
    rng = np.random.default_rng(seed)
    names = SERVICES.copy()
    root = names[root_index]
    onset = int(rng.integers(8, 13))
    n = 24
    severity = float(rng.uniform(.25, 1.1))
    low_visibility = bool(rng.random() < .16)
    concurrent_fault = bool(rng.random() < .35)
    confounding_family = str(rng.choice(FAULTS))
    propagation = [s for s in names if s != root and rng.random() < .58]
    distractor = str(rng.choice([s for s in names if s != root]))
    incident_logs, spans, deployments, services = [], [], [], []
    # Synthetic recent deployments are sometimes unrelated to the actual fault.
    for j, s in enumerate(names):
        if rng.random() < .25 or (s == root and fault == "config_regression"):
            deployments.append(dict(id=f"deploy-{j}", service=s, time=max(0,onset-2),
                                    version=f"v1.{int(rng.integers(1,60))}.{variant}",
                                    summary="Application configuration and dependency update"))
    for j, s in enumerate(names):
        error = np.clip(rng.normal(.008, .004, n), 0, 1)
        latency = rng.uniform(20, 110) * np.exp(rng.normal(0, .10, n))
        cpu = np.clip(rng.normal(rng.uniform(12,40), 3, n), 0, 100)
        memory = rng.uniform(120, 600) * np.exp(rng.normal(0,.025,n))
        rate = np.clip(rng.normal(rng.uniform(45, 190), 8, n), 1, None)
        queue = np.clip(rng.normal(2, .8, n), 0, None)
        intensity = severity * rng.uniform(.7, 1.3)
        local_onset = onset + (int(rng.integers(0,3)) if s in propagation else 0)
        affected = s == root or s in propagation
        if affected:
            error[local_onset:] += intensity * rng.uniform(.12,.55)
            latency[local_onset:] *= 1 + intensity * rng.uniform(1.1,4)
            queue[local_onset:] += intensity * rng.uniform(3,12)
            rate[local_onset:] *= rng.uniform(.6,1.05)
        if s == root:
            if fault == "cpu_saturation": cpu[onset:] += intensity * rng.uniform(30,60)
            elif fault == "memory_pressure": memory[onset:] *= np.linspace(1.2, 2.4, n-onset)
            elif fault == "query_latency": latency[onset:] *= rng.uniform(1.5,3.2)
            elif fault == "connection_failure": queue[onset:] += rng.uniform(5,14)
            else: error[onset:] += rng.uniform(.03,.18)
        if s == distractor:
            # Confounders: unrelated load spikes and occasional misleading warnings.
            cpu[onset+1:] += rng.uniform(15,40)
            latency[onset+2:] *= rng.uniform(1.2,2.5)
        if s == distractor and concurrent_fault:
            error[onset+1:] += rng.uniform(.10,.35)
            queue[onset+1:] += rng.uniform(3,10)
            if confounding_family == "memory_pressure": memory[onset+1:] *= np.linspace(1.1,2.0,n-onset-1)
            if confounding_family == "cpu_saturation": cpu[onset+1:] += rng.uniform(20,40)
        if s == root and low_visibility:
            # Sampling gaps hide some local signals, while callers still see failures.
            for arr in (cpu,memory,queue): arr[onset:] = arr[:6].mean()
        if rng.random() < .12:
            # Partial signal loss without revealing which service is the cause.
            cpu[:] = cpu[:6].mean()
            memory[:] = memory[:6].mean()
        metrics = dict(zip(METRICS, [np.clip(error,0,1), latency, np.clip(cpu,0,100), memory,rate,queue]))
        services.append(dict(name=s, metrics={k: np.round(v,5).tolist() for k,v in metrics.items()}))
        for k in range(6):
            t = int(rng.integers(0,n))
            msg, level = "request completed; worker heartbeat received", "INFO"
            if t >= local_onset and affected and rng.random() < (.20 if low_visibility else .72):
                msg = LOCAL_MESSAGES[fault] if s == root else f"request to dependency {root} failed; upstream timeout"
                level = "ERROR"
            elif s == distractor and t >= onset and rng.random()<.65:
                msg,level = LOCAL_MESSAGES[confounding_family],("ERROR" if concurrent_fault else "WARN")
            incident_logs.append(dict(id=f"log-{j}-{k}", service=s, time=t,level=level,message=msg))
        for k in range(6):
            t = int(rng.integers(0,n))
            target = None
            if k % 2 == 0:
                target = root if s in propagation and rng.random() < (.15 if low_visibility else .65) else str(rng.choice([x for x in names if x != s]))
            failed = bool(t >= local_onset and (affected or (concurrent_fault and s == distractor)) and rng.random() < .70)
            spans.append(dict(id=f"span-{j}-{k}", service=s,target=target,time=t,
                              duration_ms=round(float(latency[t]*rng.uniform(.7,1.3)),4),
                              status="ERROR" if failed else "OK",operation="dependency.request" if target else "handler.execute",
                              trace_id=f"trace-{j}-{k}"))
    # Service order must not encode the label.
    rng.shuffle(services)
    return Incident.model_validate(dict(id=incident_id,title="Elevated errors and request latency",
        source="synthetic",started_at=(datetime(2025,1,1,tzinfo=timezone.utc)+timedelta(minutes=seed%100000)).isoformat(),
        services=services,logs=incident_logs,spans=spans,deployments=deployments))


def build_dataset(out: Path, seed: int = 42, repeats: int = 12) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    records, labels = [], []
    # Six combinations have no representation in training or validation.
    challenge = {(r, (r*2)%len(FAULTS)) for r in range(len(SERVICES))}
    assignments = []
    for root in range(len(SERVICES)):
        for fi, fault in enumerate(FAULTS):
            for repeat in range(repeats):
                assignments.append((root,fi,fault,repeat))
    regular = [i for i,(r,fi,_,_) in enumerate(assignments) if (r,fi) not in challenge]
    rng.shuffle(regular)
    a,b = int(.65*len(regular)),int(.82*len(regular))
    split_for = {i: "train" if j<a else "validation" if j<b else "test" for j,i in enumerate(regular)}
    for i,(root,fi,fault,repeat) in enumerate(assignments):
        split=split_for.get(i,"challenge")
        for variant in range(2):
            iid=f"inc-{i:04d}-{variant}"
            case=generate_case(seed*100000+i*7+variant,root,fault,iid,variant)
            records.append(case)
            labels.append(Label(incident_id=iid,experiment_id=f"experiment-{i:04d}",root_service=SERVICES[root],fault_family=fault,split=split))
    # mtime=0 removes timestamps from gzip headers for reproducible bytes.
    with (out/"incidents.jsonl.gz").open("wb") as raw:
        with gzip.GzipFile(fileobj=raw,mode="wb",mtime=0) as f:
            for case in records:f.write((case.model_dump_json()+"\n").encode())
    (out/"labels.jsonl").write_text("\n".join(l.model_dump_json() for l in labels)+"\n")
    counts={s:sum(l.split==s for l in labels) for s in ("train","validation","test","challenge")}
    manifest={"source":"synthetic", "seed":seed,"repeats":repeats,"incidents":len(records),"split_counts":counts,
        "grouping":"Both variants of an experiment share a split", "challenge":"Held-out service/fault pairs",
        "warning":"Synthetic demonstration data. Not production evidence. No customer telemetry."}
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    return manifest
