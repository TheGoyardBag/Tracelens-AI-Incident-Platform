"""Optional dependency demonstration; install .[graph] first."""
from pathlib import Path
import json
from tracelens.data import read_incidents
from tracelens.ml.model import Predictor
from tracelens.agents.graph import build_graph
root=Path(__file__).resolve().parents[1]
case=read_incidents(root/'data/demo-incidents.jsonl')[0]
graph=build_graph(case,Predictor(root/'artifacts'),lambda kind,payload:print(kind,payload))
result=graph.invoke({})
print(json.dumps(result,indent=2))
