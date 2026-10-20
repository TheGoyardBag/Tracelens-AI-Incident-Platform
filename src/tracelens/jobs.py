"""Bounded in-process job queue; database records survive restart, workers do not.

Use one Uvicorn process. This is NOT a distributed task queue. Interrupted jobs
are explicitly marked interrupted instead of falsely presented as completed.
"""
from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore
from tracelens.agents.investigate import investigate
from tracelens.agents.provider import AnthropicInvestigator
from tracelens.store import ConflictError

class BusyError(RuntimeError):pass

class JobManager:
    def __init__(self,store,predictor,settings):
        self.store=store;self.predictor=predictor;self.settings=settings
        self.pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix="investigation")
        self.slots=BoundedSemaphore(8)

    def start(self,incident,mode,key):
        existing=self.store.get_run_by_key(key)
        if existing:
            if existing["incident_id"]!=incident.id or existing["mode"]!=mode:raise ConflictError("Idempotency key reused with a different request")
            return self.store.get_run(existing["id"])
        if not self.slots.acquire(blocking=False):raise BusyError("Investigation queue is full; retry later")
        try:
            run,new=self.store.create_run(incident.id,mode,key)
            if new:self.pool.submit(self._work,run["id"],incident,mode)
            else:self.slots.release()
            return run
        except Exception:
            self.slots.release();raise

    def _work(self,rid,incident,mode):
        try:
            self.store.update_run(rid,"running")
            provider=AnthropicInvestigator(self.settings.provider_key,self.settings.provider_model) if mode=="llm" else None
            result=investigate(incident,self.predictor,lambda k,v:self.store.emit(rid,k,v),mode,provider)
            self.store.update_run(rid,"complete",result=result)
            self.store.emit(rid,"complete",{"message":"Investigation ready","status":result["diagnosis"]["status"]})
        except Exception as exc:
            self.store.update_run(rid,"failed",error=f"Investigation failed ({type(exc).__name__}); inspect local server logs")
            self.store.emit(rid,"failed",{"error_type":type(exc).__name__})
            # Avoid dumping raw telemetry or provider keys into exception messages.
        finally:self.slots.release()

    def close(self):self.pool.shutdown(wait=True,cancel_futures=False)
