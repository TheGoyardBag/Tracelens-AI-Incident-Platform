#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from tracelens.integrations.otlp import convert_otlp
p=argparse.ArgumentParser(description="Convert an OTLP trace JSON file into a normalized incident (not a collector)")
p.add_argument("source",type=Path);p.add_argument("--id",required=True);p.add_argument("--out",type=Path,required=True)
a=p.parse_args()
if a.source.stat().st_size>10_000_000:p.error("Input file exceeds 10 MB")
case=convert_otlp(json.loads(a.source.read_text()),a.id)
a.out.write_text(case.model_dump_json(indent=2)+"\n")
print(f"Wrote {a.out}. Imported predictions are explicitly uncalibrated; inspect evidence manually.")
