#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from tracelens.data import build_dataset
p=argparse.ArgumentParser(description="Generate labeled SYNTHETIC demonstration incidents")
p.add_argument("--output",type=Path,default=Path("data"));p.add_argument("--seed",type=int,default=42)
p.add_argument("--repeats",type=int,default=12)
a=p.parse_args()
if a.repeats<4:p.error("Use at least four repeats")
print(json.dumps(build_dataset(a.output,a.seed,a.repeats),indent=2))
