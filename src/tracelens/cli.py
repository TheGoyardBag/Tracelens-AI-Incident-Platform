from __future__ import annotations
import argparse
import json
from pathlib import Path

def main(argv=None):
    p=argparse.ArgumentParser(prog="tracelens",description="Local-first incident investigation prototype")
    sub=p.add_subparsers(dest="command",required=True)
    api=sub.add_parser("serve");api.add_argument("--port",type=int,default=8000);api.add_argument("--host",default="127.0.0.1")
    rank=sub.add_parser("rank");rank.add_argument("incident",type=Path);rank.add_argument("--model-dir",type=Path,default=Path("artifacts"))
    args=p.parse_args(argv)
    if args.command=="serve":
        import uvicorn
        uvicorn.run("tracelens.api:create_app",factory=True,host=args.host,port=args.port,workers=1)
    elif args.command=="rank":
        from tracelens.schema import Incident
        from tracelens.ml.model import Predictor
        from tracelens.agents.investigate import investigate
        case=Incident.model_validate_json(args.incident.read_text())
        result=investigate(case,Predictor(args.model_dir),lambda k,v:None)
        print(json.dumps(result,indent=2))
if __name__=="__main__":main()
