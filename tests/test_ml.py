import json
import shutil
import numpy as np
import pytest
import torch
from tracelens.data import build_dataset,read_incidents,read_labels
from tracelens.ml.train import validate_splits,metrics,fit_one
from tracelens.ml.model import Predictor,FusionRanker,save_model
from tracelens.ml.features import extract,FEATURE_NAMES


def test_grouped_splits_and_challenge(root):
    cases=read_incidents(root/"data/incidents.jsonl.gz");labels=read_labels(root/"data/labels.jsonl")
    validate_splits(cases,labels)
def test_group_leak_rejected(root):
    cases=read_incidents(root/"data/incidents.jsonl.gz");labels=read_labels(root/"data/labels.jsonl")
    first=next(l for l in labels.values() if l.split=="train")
    sibling=next(l for l in labels.values() if l.experiment_id==first.experiment_id and l.incident_id!=first.incident_id)
    labels[sibling.incident_id]=sibling.model_copy(update={"split":"test"})
    with pytest.raises(ValueError,match="leaked"):validate_splits(cases,labels)
def test_generator_reproducibility(tmp_path):
    a=tmp_path/"a";b=tmp_path/"b"
    build_dataset(a,seed=9,repeats=4);build_dataset(b,seed=9,repeats=4)
    assert (a/"incidents.jsonl.gz").read_bytes()==(b/"incidents.jsonl.gz").read_bytes()
    assert (a/"labels.jsonl").read_bytes()==(b/"labels.jsonl").read_bytes()
def test_forward_and_gradients(case):
    f=extract(case);model=FusionRanker()
    inputs=[torch.from_numpy(a).unsqueeze(0) for a in (f.temporal,f.logs,f.stats)]
    out=model(*inputs);assert out.shape==(1,6)
    out.sum().backward()
    for layer in [model.temporal,model.log_encoder,model.stat_encoder]:assert any(p.grad is not None and p.grad.abs().sum()>0 for p in layer.parameters())
def test_different_candidate_count():
    model=FusionRanker().eval()
    assert model(torch.zeros(2,4,24,6),torch.zeros(2,4,64),torch.zeros(2,4,len(FEATURE_NAMES))).shape==(2,4)
def test_predictor_probabilities(predictor,case):
    result=predictor.rank(case)
    assert len(result["candidates"])==6
    assert abs(sum(r["probability"] for r in result["candidates"])-1)<1e-5
    assert result["candidates"][0]["probability"]>=result["candidates"][-1]["probability"]
def test_candidate_order_does_not_change_prediction(predictor,case):
    a=predictor.rank(case);b=predictor.rank(case.model_copy(update={"services":list(reversed(case.services))}))
    assert a["candidates"][0]["service"]==b["candidates"][0]["service"]
def test_imported_is_uncalibrated(predictor,case):
    result=predictor.rank(case.model_copy(update={"source":"imported"}))
    assert result["abstain"]
    assert any("synthetic" in r for r in result["reasons"])
def test_low_signal_abstains(predictor,case):
    raw=case.model_dump()
    for svc in raw["services"]:
        svc["metrics"]["error_rate"]=[0.]*24;svc["metrics"]["latency_ms"]=[20.]*24
    from tracelens.schema import Incident
    result=predictor.rank(Incident.model_validate(raw))
    assert any("Insufficient incident signal" in r for r in result["reasons"])
def test_checksum_rejects_corruption(tmp_path,root):
    shutil.copytree(root/"artifacts",tmp_path/"model")
    with (tmp_path/"model/ranker.npz").open("ab") as f:f.write(b"corrupt")
    with pytest.raises(ValueError,match="checksum"):Predictor(tmp_path/"model")
def test_feature_schema_rejected(tmp_path,root):
    shutil.copytree(root/"artifacts",tmp_path/"model")
    path=tmp_path/"model/model.json";m=json.loads(path.read_text());m["feature_names"]=["wrong"];path.write_text(json.dumps(m))
    with pytest.raises(ValueError,match="schema"):Predictor(tmp_path/"model")
def test_training_smoke(case):
    f=extract(case);x=[np.stack([getattr(f,k)]*6) for k in ["temporal","logs","stats"]]
    y=np.array([0]*6)
    model,scores,history=fit_one(x,y,np.array([0,1,2,3]),np.array([4,5]),17,2,"full")
    assert scores.shape==(6,6) and len(history)==2 and np.isfinite(scores).all()
def test_metrics_known_answer():
    result=metrics(np.array([[4,0],[0,4]]),np.array([0,0]),threshold=.5,groups=["a","b"])
    assert result["top1"]==.5 and result["mrr"]==.75 and result["coverage"]==1.
    assert len(result["top1_group_bootstrap_95ci"])==2
