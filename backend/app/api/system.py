"""Estado del sistema, jobs y recursos (fuentes, perfiles)."""
from __future__ import annotations

import shutil
import subprocess
from functools import lru_cache

from fastapi import APIRouter, HTTPException

from .. import config, db
from ..engine import ffmpeg, render
from ..jobs import manager
from ..schemas import Job

router = APIRouter(prefix="/api")


@router.get("/system")
def system():
    try:
        import faster_whisper  # noqa: F401
        whisper = True
    except Exception:  # noqa: BLE001
        whisper = False
    return {
        "ffmpeg": ffmpeg.available(),
        "whisper": whisper,
        "whisper_models": config.WHISPER_MODELS,
        "default_whisper_model": config.DEFAULT_WHISPER_MODEL,
        "profiles": render.PROFILES,
        "workspace": str(config.WORKSPACE),
    }


@lru_cache(maxsize=1)
def _fonts() -> list[str]:
    if not shutil.which("fc-list"):
        return ["Arial", "Helvetica", "Inter", "DejaVu Sans"]
    out = subprocess.run(["fc-list", ":", "family"], capture_output=True, text=True).stdout
    fams = {line.split(",")[0].strip() for line in out.splitlines() if line.strip()}
    return sorted(f for f in fams if f and not f.startswith("."))


@router.get("/fonts")
def fonts():
    return _fonts()


@router.get("/jobs/{jid}", response_model=Job)
def get_job(jid: str):
    j = db.get_job(jid)
    if j is None:
        raise HTTPException(404, "Job no encontrado")
    return j


@router.get("/projects/{pid}/jobs", response_model=list[Job])
def project_jobs(pid: str):
    return db.list_jobs(pid)


@router.post("/jobs/{jid}/cancel")
def cancel_job(jid: str):
    if not manager.cancel(jid):
        raise HTTPException(409, "El job no está en ejecución")
    return {"ok": True}
