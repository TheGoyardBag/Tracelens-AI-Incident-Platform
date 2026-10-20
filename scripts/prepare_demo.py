"""Export a fixed, uncherry-picked set of held-out incidents without labels."""
from pathlib import Path
from tracelens.data import read_incidents, read_labels
root=Path(__file__).resolve().parents[1]
cases=read_incidents(root/"data/incidents.jsonl.gz");labels=read_labels(root/"data/labels.jsonl")
selected=[c for c in cases if labels[c.id].split=="test"][:12]+[c for c in cases if labels[c.id].split=="challenge"][:4]
(root/"data/demo-incidents.jsonl").write_text("\n".join(c.model_dump_json() for c in selected)+"\n")
(root/"examples/incident.json").write_text(selected[0].model_dump_json(indent=2)+"\n")
print(f"Exported {len(selected)} held-out incident observations. Ground truth was not exported.")
