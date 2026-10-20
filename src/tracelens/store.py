"""Portable SQLAlchemy persistence: SQLite locally, PostgreSQL by configuration.

This is a single-workspace prototype. It does not implement enterprise tenancy.
"""
from __future__ import annotations
from datetime import datetime, timezone
import uuid
from sqlalchemy import create_engine, MetaData, Table, Column, String, Integer, JSON, Text, ForeignKey, select, update, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool

metadata=MetaData()
incidents=Table("incidents",metadata,Column("id",String(96),primary_key=True),Column("title",String(160)),
                Column("source",String(30)),Column("created_at",String(50)),Column("payload",JSON,nullable=False))
runs=Table("runs",metadata,Column("id",String(36),primary_key=True),
           Column("incident_id",String(96),ForeignKey("incidents.id"),nullable=False),
           Column("idempotency_key",String(128),unique=True,nullable=False),Column("mode",String(20)),
           Column("status",String(30)),Column("created_at",String(50)),Column("updated_at",String(50)),
           Column("result",JSON),Column("error",String(500)))
events=Table("events",metadata,Column("id",Integer,primary_key=True,autoincrement=True),
             Column("run_id",String(36),ForeignKey("runs.id"),nullable=False,index=True),
             Column("kind",String(40)),Column("payload",JSON),Column("created_at",String(50)))
feedback=Table("feedback",metadata,Column("run_id",String(36),ForeignKey("runs.id"),primary_key=True),
               Column("payload",JSON),Column("created_at",String(50)))
approvals=Table("approvals",metadata,Column("id",String(36),primary_key=True),
                Column("run_id",String(36),ForeignKey("runs.id"),nullable=False,unique=True),
                Column("action",String(80)),Column("state",String(30)),Column("note",Text),Column("created_at",String(50)))
audit=Table("audit",metadata,Column("id",Integer,primary_key=True,autoincrement=True),
            Column("action",String(80)),Column("resource_id",String(96)),Column("detail",JSON),Column("created_at",String(50)))


def now():return datetime.now(timezone.utc).isoformat()

class ConflictError(ValueError):pass

class Store:
    def __init__(self,url: str):
        opts={"pool_pre_ping":True}
        if url.startswith("sqlite"):
            opts["connect_args"]={"check_same_thread":False,"timeout":10}
            if ":memory:" in url:opts["poolclass"]=StaticPool
        self.engine=create_engine(url,**opts)
        if url.startswith("sqlite"):
            @event.listens_for(self.engine,"connect")
            def pragmas(connection,_):
                cursor=connection.cursor();cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA journal_mode=WAL");cursor.execute("PRAGMA busy_timeout=10000");cursor.close()
        metadata.create_all(self.engine)

    def add_incident(self,case):
        try:
            with self.engine.begin() as c:
                c.execute(incidents.insert().values(id=case.id,title=case.title,source=case.source,created_at=now(),payload=case.model_dump()))
                c.execute(audit.insert().values(action="incident_imported",resource_id=case.id,detail={"source":case.source},created_at=now()))
        except IntegrityError as exc:raise ConflictError("An incident with this ID already exists") from exc

    def get_incident(self,incident_id):
        with self.engine.connect() as c:
            row=c.execute(select(incidents.c.payload).where(incidents.c.id==incident_id)).scalar_one_or_none()
        return row

    def list_incidents(self):
        with self.engine.connect() as c:
            rows=c.execute(select(incidents.c.id,incidents.c.title,incidents.c.source,incidents.c.created_at).order_by(incidents.c.id)).mappings().all()
        return [dict(r) for r in rows]

    def create_run(self,incident_id,mode,key):
        existing=self.get_run_by_key(key)
        if existing:
            if existing["incident_id"]!=incident_id or existing["mode"]!=mode:raise ConflictError("Idempotency key already belongs to a different request")
            return existing,False
        rid=str(uuid.uuid4());stamp=now()
        try:
            with self.engine.begin() as c:
                c.execute(runs.insert().values(id=rid,incident_id=incident_id,idempotency_key=key,mode=mode,status="queued",created_at=stamp,updated_at=stamp))
        except IntegrityError:
            existing=self.get_run_by_key(key)
            if existing is None:raise
            if existing["incident_id"]!=incident_id or existing["mode"]!=mode:raise ConflictError("Idempotency key conflict")
            return existing,False
        return self.get_run(rid),True

    def get_run_by_key(self,key):
        with self.engine.connect() as c:
            row=c.execute(select(runs).where(runs.c.idempotency_key==key)).mappings().first()
        return dict(row) if row else None

    def get_run(self,rid):
        with self.engine.connect() as c:
            row=c.execute(select(runs).where(runs.c.id==rid)).mappings().first()
        if not row:return None
        out=dict(row);out.pop("idempotency_key",None);return out

    def list_runs(self,incident_id=None):
        stmt=select(runs.c.id,runs.c.incident_id,runs.c.mode,runs.c.status,runs.c.created_at).order_by(runs.c.created_at.desc()).limit(50)
        if incident_id:stmt=stmt.where(runs.c.incident_id==incident_id)
        with self.engine.connect() as c:return [dict(r) for r in c.execute(stmt).mappings()]

    def update_run(self,rid,status,**values):
        with self.engine.begin() as c:
            c.execute(update(runs).where(runs.c.id==rid).values(status=status,updated_at=now(),**values))

    def emit(self,rid,kind,payload):
        with self.engine.begin() as c:
            c.execute(events.insert().values(run_id=rid,kind=kind,payload=payload,created_at=now()))

    def events_after(self,rid,after=0):
        with self.engine.connect() as c:
            rows=c.execute(select(events).where(events.c.run_id==rid,events.c.id>after).order_by(events.c.id).limit(200)).mappings()
            return [dict(r) for r in rows]

    def mark_interrupted(self):
        with self.engine.begin() as c:
            c.execute(update(runs).where(runs.c.status.in_(["queued","running"])).values(status="interrupted",error="Server restarted; start a new investigation",updated_at=now()))

    def add_feedback(self,rid,payload):
        with self.engine.begin() as c:
            existing=c.execute(select(feedback.c.run_id).where(feedback.c.run_id==rid)).first()
            if existing:c.execute(update(feedback).where(feedback.c.run_id==rid).values(payload=payload,created_at=now()))
            else:c.execute(feedback.insert().values(run_id=rid,payload=payload,created_at=now()))
            c.execute(audit.insert().values(action="feedback_recorded",resource_id=rid,detail=payload,created_at=now()))

    def approve(self,rid,note):
        with self.engine.begin() as c:
            row=c.execute(select(approvals).where(approvals.c.run_id==rid)).mappings().first()
            if row:return dict(row)
            record={"id":str(uuid.uuid4()),"run_id":rid,"action":"review_recommendation","state":"recorded_only","note":note,"created_at":now()}
            try:
                c.execute(approvals.insert().values(**record))
                c.execute(audit.insert().values(action="human_review_recorded",resource_id=rid,detail={"executes_changes":False},created_at=now()))
            except IntegrityError:raise ConflictError("A review was already recorded; refresh the run")
            return record

    def audit_log(self):
        with self.engine.connect() as c:return [dict(r) for r in c.execute(select(audit).order_by(audit.c.id.desc()).limit(100)).mappings()]
