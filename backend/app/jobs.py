"""Cola de trabajos en segundo plano con progreso y cancelación."""
from __future__ import annotations

import logging
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

from . import config, db
from .schemas import Job

log = logging.getLogger("sve.jobs")


class Canceled(Exception):
    """Se lanza dentro de un job cuando el usuario lo cancela."""


class JobContext:
    def __init__(self, job_id: str):
        self.job_id = job_id
        self.cancel_event = threading.Event()
        self._last_progress = -1.0

    @property
    def canceled(self) -> bool:
        return self.cancel_event.is_set()

    def check(self) -> None:
        if self.cancel_event.is_set():
            raise Canceled()

    def progress(self, value: float, message: Optional[str] = None) -> None:
        value = max(0.0, min(1.0, value))
        # Evita escribir en SQLite por cada décima de punto
        if message is None and abs(value - self._last_progress) < 0.005:
            return
        self._last_progress = value
        fields: dict = {"progress": value}
        if message is not None:
            fields["message"] = message
        db.update_job(self.job_id, **fields)


JobFn = Callable[[JobContext], Optional[dict]]


class JobManager:
    def __init__(self, workers: int = config.MAX_PARALLEL_JOBS):
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="sve-job")
        self._contexts: dict[str, JobContext] = {}
        self._lock = threading.Lock()

    def submit(self, project_id: Optional[str], kind: str, fn: JobFn, message: str = "En cola") -> Job:
        job = db.insert_job(project_id, kind, message)
        ctx = JobContext(job.id)
        with self._lock:
            self._contexts[job.id] = ctx
        self._pool.submit(self._run, ctx, fn)
        return job

    def _run(self, ctx: JobContext, fn: JobFn) -> None:
        jid = ctx.job_id
        try:
            if ctx.canceled:
                raise Canceled()
            db.update_job(jid, status="running", message="Procesando")
            result = fn(ctx)
            ctx.check()
            db.update_job(jid, status="done", progress=1.0, message="Completado", result=result or {})
        except Canceled:
            db.update_job(jid, status="canceled", message="Cancelado por el usuario")
        except Exception as e:  # noqa: BLE001
            log.error("Job %s falló: %s", jid, traceback.format_exc())
            db.update_job(jid, status="failed", message="Error", error=str(e) or e.__class__.__name__)
        finally:
            with self._lock:
                self._contexts.pop(jid, None)

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            ctx = self._contexts.get(job_id)
        if ctx is None:
            return False
        ctx.cancel_event.set()
        return True

    def active_for(self, project_id: str, kind: str) -> Optional[str]:
        with self._lock:
            ids = list(self._contexts)
        for jid in ids:
            j = db.get_job(jid)
            if j and j.project_id == project_id and j.kind == kind and j.status in ("queued", "running"):
                return jid
        return None


manager = JobManager()
