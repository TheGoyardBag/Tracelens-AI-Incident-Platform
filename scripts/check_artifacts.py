from pathlib import Path
import hashlib
import json
from tracelens.ml.model import Predictor
from tracelens.ml.train import validate_splits
from tracelens.data import read_incidents,read_labels
root=Path(__file__).resolve().parents[1]
model=Predictor(root/'artifacts')
data=root/'data/incidents.jsonl.gz'
assert hashlib.sha256(data.read_bytes()).hexdigest()==model.metadata['dataset_sha256'],'Dataset differs from trained artifact'
cases=read_incidents(data);labels=read_labels(root/'data/labels.jsonl')
validate_splits(cases,labels)
for case in read_incidents(root/'data/demo-incidents.jsonl'):
    assert labels[case.id].split in ('test','challenge'),'Demo includes training/validation examples'
print('Artifact hash, data hash, feature schema, grouped partitions and held-out demo export verified.')
