from __future__ import annotations
import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import Path
import secrets
from typing import Literal
import torch
from fastapi import FastAPI, Depends, HTTPException, Request, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import Field
from .schema import Incident, StrictModel
from .config import Settings
from .data import read_incidents
from .ml.model import Predictor
from .store import Store, ConflictError
from .jobs import JobManager, BusyError

class RunRequest(StrictModel):
    incident_id: str=Field(min_length=1,max_length=96)
    mode: Literal["offline","llm"]="offline"
    idempotency_key: str=Field(min_length=12,max_length=128)

class FeedbackRequest(StrictModel):
    correct: bool
    expected_service: str|None=Field(default=None,max_length=96)
    note: str=Field(default="",max_length=1200)

class ReviewRequest(StrictModel):
    confirmed: Literal[True]
    note: str=Field(min_length=1,max_length=1200)


class BodyLimit:
    def __init__(self,app,limit=2_000_000):self.app=app;self.limit=limit
    async def __call__(self,scope,receive,send):
        if scope["type"]!="http" or scope.get("method") not in ("POST","PUT","PATCH"):
            return await self.app(scope,receive,send)
        parts=[];total=0
        while True:
            message=await receive()
            if message["type"]=="http.disconnect":return
            body=message.get("body",b"");total+=len(body)
            if total>self.limit:
                return await JSONResponse({"detail":"Request exceeds 2 MB limit"},status_code=413)(scope,receive,send)
            parts.append(body)
            if not message.get("more_body",False):break
        sent=False
        async def replay():
            nonlocal sent
            if not sent:
                sent=True;return {"type":"http.request","body":b"".join(parts),"more_body":False}
            return await receive()
        return await self.app(scope,replay,send)


def create_app(settings: Settings|None=None) -> FastAPI:
    settings=settings or Settings.from_env()
    torch.set_num_threads(2)
    store=Store(settings.database_url)
    predictor=Predictor(settings.model_dir)
    jobs=JobManager(store,predictor,settings)
    @asynccontextmanager
    async def lifespan(app):
        store.mark_interrupted()
        if not store.list_incidents() and settings.demo_file.exists():
            for case in read_incidents(settings.demo_file):store.add_incident(case)
        yield
        jobs.close();store.engine.dispose()
    app=FastAPI(title="TraceLens",version="0.1.0",description="Evidence-backed incident investigations. Demo data is synthetic; remediation is never executed.",lifespan=lifespan)
    app.state.store=store;app.state.predictor=predictor
    app.add_middleware(BodyLimit)
    app.add_middleware(CORSMiddleware,allow_origins=list(settings.cors_origins),allow_methods=["GET","POST"],allow_headers=["Authorization","Content-Type"],allow_credentials=False)
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=list(settings.allowed_hosts))
    bearer=HTTPBearer(auto_error=False)
    def authorize(credentials: HTTPAuthorizationCredentials|None=Depends(bearer)):
        if not credentials or not secrets.compare_digest(credentials.credentials.encode("utf-8"),settings.token.encode("utf-8")):
            raise HTTPException(401,"Valid bearer token required",headers={"WWW-Authenticate":"Bearer"})
    secure=[Depends(authorize)]
    static=Path(__file__).parent/"static"
    app.mount("/static",StaticFiles(directory=static),name="static")
    @app.middleware("http")
    async def security_headers(request,call_next):
        response=await call_next(request)
        response.headers["X-Content-Type-Options"]="nosniff"
        response.headers["Referrer-Policy"]="no-referrer"
        response.headers["X-Frame-Options"]="DENY"
        if request.url.path.startswith("/api"):response.headers["Cache-Control"]="no-store"
        if request.url.path=="/":response.headers["Content-Security-Policy"]="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
        return response
    @app.get("/",include_in_schema=False)
    def home():return FileResponse(static/"index.html")
    @app.get("/health")
    def health():return {"status":"ok","model":predictor.metadata["model_version"],"llm_ready":settings.llm_ready,"mode":"single-workspace-prototype"}
    @app.get("/api/incidents",dependencies=secure)
    def list_incidents():return {"incidents":store.list_incidents()}
    @app.post("/api/incidents",status_code=201,dependencies=secure)
    def import_incident(incident: Incident):
        # New uploads are never accepted as synthetic evaluation members by assertion alone.
        case=incident.model_copy(update={"source":"imported"})
        try:store.add_incident(case)
        except ConflictError as exc:raise HTTPException(409,str(exc))
        return {"id":case.id,"source":case.source}
    def case_or_404(iid):
        data=store.get_incident(iid)
        if data is None:raise HTTPException(404,"Incident not found")
        return Incident.model_validate(data)
    @app.get("/api/incidents/{incident_id}",dependencies=secure)
    def get_incident(incident_id:str):return case_or_404(incident_id)
    @app.post("/api/runs",status_code=202,dependencies=secure)
    def start_run(body: RunRequest):
        case=case_or_404(body.incident_id)
        if body.mode=="llm" and not settings.llm_ready:
            raise HTTPException(422,"Hosted mode requires an API key, model ID, and explicit telemetry-export consent")
        try:return jobs.start(case,body.mode,body.idempotency_key)
        except ConflictError as exc:raise HTTPException(409,str(exc))
        except BusyError as exc:raise HTTPException(429,str(exc),headers={"Retry-After":"5"})
    @app.get("/api/runs",dependencies=secure)
    def list_runs(incident_id:str|None=None):return {"runs":store.list_runs(incident_id)}
    def run_or_404(rid):
        row=store.get_run(rid)
        if row is None:raise HTTPException(404,"Investigation not found")
        return row
    @app.get("/api/runs/{run_id}",dependencies=secure)
    def get_run(run_id:str):return run_or_404(run_id)
    @app.get("/api/runs/{run_id}/events",dependencies=secure)
    async def event_stream(run_id:str,request:Request,after:int=Query(default=0,ge=0)):
        run_or_404(run_id)
        async def generate():
            cursor=after
            for tick in range(600):
                if await request.is_disconnected():return
                rows=store.events_after(run_id,cursor)
                for row in rows:
                    cursor=row["id"]
                    yield f"id: {cursor}\nevent: step\ndata: {json.dumps(row)}\n\n"
                run=store.get_run(run_id)
                if run["status"] in ("complete","failed","interrupted"):
                    # Flush any event committed between the query and final state read.
                    for row in store.events_after(run_id,cursor):
                        cursor=row["id"];yield f"id: {cursor}\nevent: step\ndata: {json.dumps(row)}\n\n"
                    yield f"event: done\ndata: {json.dumps({'status':run['status']})}\n\n";return
                if tick%50==0:yield ": keepalive\n\n"
                await asyncio.sleep(.1)
            yield "event: reconnect\ndata: {}\n\n"
        return StreamingResponse(generate(),media_type="text/event-stream",headers={"X-Accel-Buffering":"no","Cache-Control":"no-store"})
    @app.post("/api/runs/{run_id}/feedback",dependencies=secure)
    def record_feedback(run_id:str,body:FeedbackRequest):
        row=run_or_404(run_id)
        if row["status"]!="complete":raise HTTPException(409,"Wait for a completed investigation")
        case=case_or_404(row["incident_id"])
        if body.expected_service and body.expected_service not in {s.name for s in case.services}:raise HTTPException(422,"Unknown expected service")
        store.add_feedback(run_id,body.model_dump());return {"saved":True,"used_for_training":False}
    @app.post("/api/runs/{run_id}/review",dependencies=secure)
    def record_review(run_id:str,body:ReviewRequest):
        row=run_or_404(run_id)
        if row["status"]!="complete":raise HTTPException(409,"Wait for a completed investigation")
        try:record=store.approve(run_id,body.note)
        except ConflictError as exc:raise HTTPException(409,str(exc))
        return {"review":record,"executes_changes":False,"message":"Human review recorded. No infrastructure changes were executed."}
    @app.get("/api/audit",dependencies=secure)
    def audit_log():return {"events":store.audit_log()}
    @app.get("/api/evaluation",dependencies=secure)
    def evaluation():
        path=settings.root/"reports/evaluation.json"
        if not path.exists():raise HTTPException(404,"Train the model to create evaluation reports")
        return json.loads(path.read_text())
    return app
