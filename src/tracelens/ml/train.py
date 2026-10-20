"""Reproducible, grouped training with a separate validation and challenge set."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import random
import time
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import torch
from torch.nn import functional as F
from sklearn.ensemble import HistGradientBoostingRegressor
from tracelens.data import read_incidents, read_labels
from .features import extract, heuristic_scores, FEATURE_NAMES
from .model import FusionRanker, save_model


def validate_splits(incidents,labels):
    if set(labels)!={i.id for i in incidents}:
        raise ValueError("Incident/label IDs must match exactly")
    group_split={}
    pairs={s:set() for s in ("train","validation","test","challenge")}
    for case in incidents:
        label=labels[case.id]
        if label.root_service not in {s.name for s in case.services}:
            raise ValueError("Ground-truth service missing from incident")
        previous=group_split.setdefault(label.experiment_id,label.split)
        if previous!=label.split:raise ValueError("Experiment leaked across splits")
        pairs[label.split].add((label.root_service,label.fault_family))
    if pairs["challenge"] & (pairs["train"]|pairs["validation"]):
        raise ValueError("Challenge service/fault combinations leaked into model selection")
    if any(not pairs[s] for s in pairs):raise ValueError("All four splits are required")


def softmax(a,temperature=1.):
    a=np.asarray(a,dtype=np.float64)/temperature
    a=a-a.max(axis=-1,keepdims=True)
    p=np.exp(a)
    return p/p.sum(axis=-1,keepdims=True)


def metrics(logits,y,temperature=1.,threshold=None,groups=None):
    p=softmax(logits,temperature)
    order=np.argsort(-p,axis=1)
    y=np.asarray(y)
    hit=order[:,0]==y
    confidence=p.max(axis=1)
    rank=(order==y[:,None]).argmax(axis=1)+1
    out={"incidents":len(y),"top1":float(hit.mean()),"top3":float((rank<=3).mean()),
         "mrr":float((1/rank).mean()),"nll":float(-np.log(p[np.arange(len(y)),y].clip(1e-12)).mean())}
    ece=0.
    for low in np.linspace(0,.9,10):
        m=(confidence>=low)&(confidence<(low+.1) if low<.9 else confidence<=1)
        if m.any():ece+=float(m.mean()*abs(hit[m].mean()-confidence[m].mean()))
    out["ece_10_bins"]=ece
    if threshold is not None:
        accepted=confidence>=threshold
        out.update(coverage=float(accepted.mean()),selective_accuracy=float(hit[accepted].mean()) if accepted.any() else None)
    if groups is not None:
        # Bootstrap experiment groups, not correlated observations independently.
        unique=sorted(set(groups));g=np.asarray(groups);rng=np.random.default_rng(2026)
        means=np.array([hit[g==k].mean() for k in unique])
        estimates=np.array([means[rng.integers(0,len(means),len(means))].mean() for _ in range(500)])
        out["top1_group_bootstrap_95ci"]=[float(x) for x in np.quantile(estimates,[.025,.975])]
    return out


def fit_one(x,y,train_idx,val_idx,seed,epochs,ablation):
    random.seed(seed);np.random.seed(seed);torch.manual_seed(seed)
    model=FusionRanker(ablation=ablation)
    optimizer=torch.optim.AdamW(model.parameters(),lr=.0025,weight_decay=.01)
    tensors=[torch.from_numpy(z) for z in x]; targets=torch.from_numpy(y).long()
    generator=torch.Generator().manual_seed(seed)
    best=float("inf");best_state=None;stale=0;history=[]
    for epoch in range(epochs):
        model.train();loss_sum=0.;seen=0
        perm=torch.randperm(len(train_idx),generator=generator).numpy()
        for start in range(0,len(perm),32):
            ix=train_idx[perm[start:start+32]]
            optimizer.zero_grad(set_to_none=True)
            pred=model(*(t[ix] for t in tensors))
            loss=F.cross_entropy(pred,targets[ix])
            loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),1.0);optimizer.step()
            loss_sum+=loss.item()*len(ix);seen+=len(ix)
        model.eval()
        with torch.inference_mode():val=F.cross_entropy(model(*(t[val_idx] for t in tensors)),targets[val_idx]).item()
        history.append({"epoch":epoch+1,"train_loss":loss_sum/seen,"validation_loss":val})
        if val<best-1e-4:
            best=val;best_state={k:v.detach().clone() for k,v in model.state_dict().items()};stale=0
        else:stale+=1
        if stale>=8:break
    model.load_state_dict(best_state);model.eval()
    with torch.inference_mode():scores=model(*tensors).numpy()
    return model,scores,history


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data",type=Path,default=Path("data"))
    parser.add_argument("--artifacts",type=Path,default=Path("artifacts"))
    parser.add_argument("--reports",type=Path,default=Path("reports"))
    parser.add_argument("--epochs",type=int,default=60)
    parser.add_argument("--seed",type=int,default=42)
    parser.add_argument("--mlflow-dir",type=Path,default=None)
    args=parser.parse_args(argv)
    if args.epochs<1:parser.error("--epochs must be positive")
    start=time.monotonic();torch.set_num_threads(2)
    torch.use_deterministic_algorithms(True)
    incidents=read_incidents(args.data/"incidents.jsonl.gz");labels=read_labels(args.data/"labels.jsonl")
    validate_splits(incidents,labels)
    if len({len(i.services) for i in incidents})!=1:
        raise ValueError("Training batches currently require a fixed candidate count; inference supports variable counts")
    feats=[extract(i) for i in incidents]
    x=[np.stack([getattr(f,k) for f in feats]) for k in ("temporal","logs","stats")]
    y=np.array([f.names.index(labels[i.id].root_service) for f,i in zip(feats,incidents)])
    splits={s:np.array([j for j,i in enumerate(incidents) if labels[i.id].split==s]) for s in ("train","validation","test","challenge")}
    tr,va=splits["train"],splits["validation"]
    runs={};scores_by={};models={}
    for ablation in ("full","no_logs","no_graph"):
        print(f"Training {ablation} on {len(tr)} incidents...",flush=True)
        model,scores,history=fit_one(x,y,tr,va,args.seed,args.epochs,ablation)
        scores_by[ablation]=scores;models[ablation]=model;runs[ablation]=history
    # Fit candidate-level regression only on training incident candidates.
    target=(np.arange(x[2].shape[1])[None,:]==y[:,None]).astype(float)
    baseline=HistGradientBoostingRegressor(max_iter=140,max_leaf_nodes=12,l2_regularization=2.,random_state=args.seed)
    baseline.fit(x[2][tr].reshape(-1,len(FEATURE_NAMES)),target[tr].ravel())
    scores_by["gradient_boosting"]=baseline.predict(x[2].reshape(-1,len(FEATURE_NAMES))).reshape(len(incidents),-1)
    scores_by["error_latency_heuristic"]=np.stack([heuristic_scores(f) for f in feats])
    temperatures={}
    for name,scores in scores_by.items():
        temperatures[name]=float(min(np.geomspace(.1,5,65),key=lambda t:metrics(scores[va],y[va],t)["nll"]))
    val_p=softmax(scores_by["full"][va],temperatures["full"])
    acceptable=[]
    for threshold in np.linspace(.35,.99,65):
        m=val_p.max(axis=1)>=threshold
        if m.sum()>=max(10,len(va)*.1) and (val_p[m].argmax(axis=1)==y[va][m]).mean()>=.85:
            acceptable.append(float(threshold))
    threshold=min(acceptable) if acceptable else 1.0
    result={"source":"synthetic","seed":args.seed,"generated_at":datetime.now(timezone.utc).isoformat(),
            "warning":"Only generated incidents. These measurements do not establish real-world diagnosis accuracy.",
            "split_counts":{k:len(v) for k,v in splits.items()},"results":{},"temperatures":temperatures,
            "acceptance_threshold":threshold,"threshold_policy":"Lowest validation threshold with >=85% accuracy and >=10 observations (or 10% coverage)",
            "confidence_interval":"500 grouped bootstrap replicates over experiment IDs; not repeated training seeds"}
    for name,scores in scores_by.items():
        result["results"][name]={}
        for split,ix in splits.items():
            result["results"][name][split]=metrics(scores[ix],y[ix],temperatures[name],threshold if name=="full" else None,
                [labels[incidents[j].id].experiment_id for j in ix])
    result["training_seconds"]=round(time.monotonic()-start,3)
    datahash=hashlib.sha256((args.data/"incidents.jsonl.gz").read_bytes()).hexdigest()
    metadata={"model_version":f"fusion-gru-v1-seed{args.seed}","hidden":24,"feature_names":FEATURE_NAMES,
              "temperature":temperatures["full"],"acceptance_threshold":threshold,"training_source":"synthetic",
              "seed":args.seed,"dataset_sha256":datahash,"sample_steps":24,"log_features":64,
              "parameter_count":sum(p.numel() for p in models["full"].parameters()),
              "note":"Compact trained neural ranker, not a pretrained foundation model; correlated candidate probabilities"}
    save_model(models["full"],args.artifacts,metadata)
    args.reports.mkdir(parents=True,exist_ok=True)
    (args.reports/"evaluation.json").write_text(json.dumps(result,indent=2)+"\n")
    (args.reports/"training-history.json").write_text(json.dumps(runs,indent=2)+"\n")
    details=[]
    for j,i in enumerate(incidents):
        if labels[i.id].split not in ("test","challenge"):continue
        p=softmax(scores_by["full"][j:j+1],temperatures["full"])[0]
        details.append({"incident_id":i.id,"split":labels[i.id].split,"expected":labels[i.id].root_service,
            "predicted":feats[j].names[int(p.argmax())],"candidate_probability":float(p.max()),"accepted":bool(p.max()>=threshold)})
    (args.reports/"heldout-predictions.json").write_text(json.dumps(details,indent=2)+"\n")
    lines=["# Synthetic-data evaluation","","**These are measured results on generated data, not production incidents or RCAEval.**","",
           "Models and temperature scaling are fitted using training/validation only. Test and challenge sets are untouched during selection.","",
           "| Model | Test top-1 | Test top-3 | Challenge top-1 | Test MRR |","|---|---:|---:|---:|---:|"]
    for name,r in result["results"].items():
        lines.append(f"| {name} | {r['test']['top1']:.1%} | {r['test']['top3']:.1%} | {r['challenge']['top1']:.1%} | {r['test']['mrr']:.3f} |")
    lines += ["",f"Split sizes: `{result['split_counts']}`.",f"Training time in this environment: {result['training_seconds']} seconds.",
        "","The neural model is not required to beat gradient boosting. Report the result, not a preferred narrative.",
        "The no-log and no-graph models are separately retrained ablations, not an attribution method.",
        "The challenge set holds out service/fault combinations; it does not establish performance on unseen fault mechanisms.",
        "Both observations of each fault experiment remain in the same split. Bootstrap intervals are over groups, not observations.",
        "Check `evaluation.json` for selective accuracy, coverage, NLL, ECE, and confidence intervals."]
    (args.reports/"EVALUATION.md").write_text("\n".join(lines)+"\n")
    if args.mlflow_dir:
        import mlflow
        mlflow.set_tracking_uri(args.mlflow_dir.resolve().as_uri())
        mlflow.set_experiment("tracelens-synthetic-ranking")
        with mlflow.start_run():
            mlflow.log_params({"seed":args.seed,"source":"synthetic","dataset_sha256":datahash})
            for name,r in result["results"].items():
                mlflow.log_metrics({f"{name}.test.{k}":v for k,v in r["test"].items() if isinstance(v,(int,float))})
            mlflow.log_artifacts(str(args.reports));mlflow.log_artifacts(str(args.artifacts),artifact_path="ranker")
    print("\n".join(lines));return result

if __name__=="__main__":main()
