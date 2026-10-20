"""Temporal/log/dependency fusion ranker. Artifacts use NPZ, never pickle."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import numpy as np
import torch
from torch import nn
from tracelens.schema import Incident, RankedService
from .features import extract, LOG_DIM, FEATURE_NAMES, GRAPH_INDICES

class FusionRanker(nn.Module):
    def __init__(self, hidden: int=24, ablation: str="full"):
        super().__init__()
        self.ablation=ablation
        self.temporal=nn.GRU(6,hidden,batch_first=True)
        self.log_encoder=nn.Sequential(nn.Linear(LOG_DIM,20),nn.GELU())
        self.stat_encoder=nn.Sequential(nn.Linear(len(FEATURE_NAMES),24),nn.GELU())
        self.head=nn.Sequential(nn.Linear(hidden+44,32),nn.GELU(),nn.Dropout(.12),nn.Linear(32,1))

    def forward(self,t,l,s):
        # Shapes: [batch, candidates, steps, features], [batch,candidates,features].
        b,c,steps,n=t.shape
        _,h=self.temporal(t.reshape(b*c,steps,n))
        if self.ablation=="no_logs":l=torch.zeros_like(l)
        if self.ablation=="no_graph":
            s=s.clone();s[...,GRAPH_INDICES]=0
        z=torch.cat((h[-1],self.log_encoder(l.reshape(b*c,-1)),self.stat_encoder(s.reshape(b*c,-1))),dim=-1)
        return self.head(z).reshape(b,c)


def save_model(model: FusionRanker, directory: Path, metadata: dict):
    directory.mkdir(parents=True,exist_ok=True)
    path=directory/"ranker.npz"
    np.savez_compressed(path,**{k:v.detach().cpu().numpy() for k,v in model.state_dict().items()})
    metadata={**metadata,"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"format":"numpy-state-dict-v1"}
    (directory/"model.json").write_text(json.dumps(metadata,indent=2)+"\n")


class Predictor:
    def __init__(self,directory: Path):
        self.metadata=json.loads((directory/"model.json").read_text())
        weights=directory/"ranker.npz"
        if hashlib.sha256(weights.read_bytes()).hexdigest()!=self.metadata["sha256"]:
            raise ValueError("Model checksum mismatch; retrain or restore the artifact")
        if self.metadata.get("feature_names")!=FEATURE_NAMES:
            raise ValueError("Feature schema mismatch; retrain this model")
        self.model=FusionRanker(hidden=self.metadata.get("hidden",24))
        with np.load(weights,allow_pickle=False) as arrays:
            self.model.load_state_dict({k:torch.from_numpy(arrays[k].copy()) for k in arrays.files})
        self.model.eval()
        self.temperature=max(.05,float(self.metadata.get("temperature",1)))
        self.threshold=float(self.metadata.get("acceptance_threshold",.70))

    def rank(self,incident: Incident) -> dict:
        f=extract(incident)
        with torch.inference_mode():
            args=[torch.from_numpy(a).unsqueeze(0) for a in (f.temporal,f.logs,f.stats)]
            logits=self.model(*args)[0]
            probs=torch.softmax(logits/self.temperature,dim=-1).numpy()
        rows=[RankedService(service=name,probability=float(probs[i]),score=float(logits[i])) for i,name in enumerate(f.names)]
        rows.sort(key=lambda x:x.probability,reverse=True)
        # Imported telemetry has no proven calibration; never silently reuse synthetic assurance.
        reasons=[]
        if incident.source!="synthetic":reasons.append("Calibration only evaluated on synthetic incidents")
        if rows[0].probability<self.threshold:reasons.append("Top candidate below validation-selected acceptance threshold")
        if max(s.metrics["error_rate"][-1] for s in incident.services)<.025 and max(f.stats[:,1])<.30:
            reasons.append("Insufficient incident signal in the supplied time window")
        if len(incident.logs)+len(incident.spans)<8:reasons.append("Sparse log/trace evidence")
        return {"candidates":[r.model_dump() for r in rows],"abstain":bool(reasons),"reasons":reasons,
                "model_version":self.metadata["model_version"],"acceptance_threshold":self.threshold,
                "score_note":"Candidate-relative probabilities; not proof of causality or production-calibrated confidence"}
