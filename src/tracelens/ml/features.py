"""Feature extraction reads ONLY the public incident, never the label store."""
from __future__ import annotations
from dataclasses import dataclass
import re
import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer
from tracelens.schema import Incident, METRICS

STEPS=24
LOG_DIM=64
FEATURE_NAMES=[
    "error_delta","latency_ratio","cpu_delta","memory_ratio","request_ratio","queue_delta",
    "error_peak","latency_peak_ratio","cpu_peak","memory_slope","early_error_delta","late_error_delta",
    "local_span_error_rate","incoming_error_rate","outgoing_error_rate","dependent_failure_count",
    "error_log_fraction","warning_log_fraction","deployment_near_onset","telemetry_density",
]
GRAPH_INDICES=[12,13,14,15]
VECTOR=HashingVectorizer(n_features=LOG_DIM,alternate_sign=False,norm="l2",ngram_range=(1,2),lowercase=True)

@dataclass
class Features:
    temporal: np.ndarray
    logs: np.ndarray
    stats: np.ndarray
    names: list[str]


def extract(incident: Incident) -> Features:
    temporal, logs, stats, names=[],[],[],[]
    for svc in incident.services:
        names.append(svc.name)
        a=np.stack([np.asarray(svc.metrics[k],dtype=np.float32) for k in METRICS],axis=-1)
        if a.shape[0]!=STEPS:
            old=np.linspace(0,1,len(a)); new=np.linspace(0,1,STEPS)
            a=np.stack([np.interp(new,old,a[:,j]) for j in range(len(METRICS))],axis=-1)
        base=np.mean(a[:6],axis=0)
        offsets=np.array([.02,20,10,64,10,2],dtype=np.float32)
        normalized=np.log((a+offsets)/(base+offsets)).clip(-6,6)
        temporal.append(normalized)
        own=[l for l in incident.logs if l.service==svc.name]
        # Strip service names, identifiers and digits to discourage memorizing entities.
        text=" ".join(l.message for l in own)
        for name in sorted((s.name for s in incident.services),key=len,reverse=True):
            text=re.sub(r"\b"+re.escape(name)+r"\b","service",text,flags=re.I)
        text=re.sub(r"\b[0-9]+\b","number",text)
        logs.append(VECTOR.transform([text]).toarray()[0])
        local=[s for s in incident.spans if s.service==svc.name and not s.target]
        incoming=[s for s in incident.spans if s.target==svc.name]
        outgoing=[s for s in incident.spans if s.service==svc.name and s.target]
        frac=lambda rows:sum(s.status=="ERROR" for s in rows)/max(1,len(rows))
        err=lambda rows:sum(l.level=="ERROR" for l in rows)/max(1,len(rows))
        x=[
            float(a[12:,0].mean()-base[0]),float(normalized[12:,1].mean()),
            float((a[12:,2].mean()-base[2])/100),float(normalized[12:,3].mean()),
            float(normalized[12:,4].mean()),float(normalized[12:,5].mean()),
            float(a[:,0].max()),float(normalized[:,1].max()),float(a[:,2].max()/100),
            float((normalized[-4:,3].mean()-normalized[6:10,3].mean())),
            float(a[8:14,0].mean()-base[0]),float(a[-6:,0].mean()-base[0]),
            frac(local),frac(incoming),frac(outgoing),
            len({s.service for s in incoming if s.status=="ERROR"})/max(1,len(incident.services)-1),
            err(own),sum(l.level=="WARN" for l in own)/max(1,len(own)),
            float(any(d.service==svc.name for d in incident.deployments)),
            min(1,(len(own)+len(local)+len(incoming)+len(outgoing))/16),
        ]
        stats.append(x)
    return Features(np.array(temporal,dtype=np.float32),np.array(logs,dtype=np.float32),
                    np.array(stats,dtype=np.float32),names)


def heuristic_scores(f: Features) -> np.ndarray:
    """Untrained error/latency baseline: intentionally simple and reproducible."""
    return f.stats[:,0]*2+f.stats[:,1]*.4+f.stats[:,2]*.2
