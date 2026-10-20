"""Create an investigation and inspect it with the configured local token."""
import argparse
import json
import time
import uuid
from pathlib import Path
import httpx
from tracelens.config import Settings

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--incident',type=Path,help='Optional normalized JSON file to import')
args=parser.parse_args();settings=Settings.from_env()
with httpx.Client(base_url='http://127.0.0.1:8000',headers={'Authorization':f'Bearer {settings.token}'},timeout=15) as client:
    if args.incident:
        response=client.post('/api/incidents',json=json.loads(args.incident.read_text()));response.raise_for_status()
        incident_id=response.json()['id']
    else:
        response=client.get('/api/incidents');response.raise_for_status()
        cases=response.json()['incidents']
        if not cases:raise SystemExit('No incidents; import one first')
        incident_id=cases[0]['id']
    response=client.post('/api/runs',json={'incident_id':incident_id,'mode':'offline','idempotency_key':str(uuid.uuid4())});response.raise_for_status()
    run_id=response.json()['id']
    for _ in range(120):
        response=client.get(f'/api/runs/{run_id}');response.raise_for_status();run=response.json()
        if run['status'] in ('complete','failed','interrupted'):
            print(json.dumps(run,indent=2));break
        time.sleep(.5)
    else:raise SystemExit('Timed out waiting; the persisted run can be inspected later')
