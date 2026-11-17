"""Estado del sistema, jobs y recursos (fuentes, perfiles)."""
from __future__ import annotations

import os
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from .. import config, db
from ..engine import ffmpeg, hardware, render, transcribe
from ..jobs import manager
from ..schemas import Job

router = APIRouter(prefix="/api")


@router.get("/system")
def system():
    whisper_error = transcribe.import_error()
    return {
        "ffmpeg": ffmpeg.available(),
        "whisper": whisper_error is None,
        "whisper_error": whisper_error,
        "hardware": hardware.profile(),
        "whisper_models": config.WHISPER_MODELS,
        "default_whisper_model": config.DEFAULT_WHISPER_MODEL,
        "profiles": render.PROFILES,
        "workspace": str(config.WORKSPACE),
    }


WINDOWS_FONTS = ["Arial", "Arial Black", "Impact", "Segoe UI", "Verdana", "Tahoma", "Trebuchet MS", "Georgia",
                 "Comic Sans MS", "Calibri"]


def bundled_fonts() -> list[dict]:
    """Fuentes incluidas con la app: familia, peso CSS y archivo."""
    out = []
    for f in sorted(config.FONTS_DIR.glob("*.[ot]tf")):
        stem = f.stem
        fam, _, style = stem.partition("-")
        family = {"BigShoulders": "Big Shoulders", "BricolageGrotesque": "Bricolage Grotesque",
                  "JetBrainsMono": "JetBrains Mono", "PixelifySans": "Pixelify Sans"}.get(fam, fam)
        weight = {"Regular": 400, "Medium": 500, "Bold": 700, "ExtraBold": 800, "Black": 900}.get(style, 400)
        out.append({"family": family, "weight": weight, "file": f.name, "css_scale": _css_scale(f)})
    return out


@lru_cache(maxsize=64)
def _css_scale(path: Path) -> float:
    """libass dimensiona la fuente para que usWinAscent+usWinDescent = tamaño ASS (medido: error ≤ 3 px);
    CSS usa el em. css = ass * unitsPerEm / (winAscent + winDescent)."""
    try:
        from fontTools.ttLib import TTFont
        t = TTFont(str(path), lazy=True)
        o, up = t["OS/2"], t["head"].unitsPerEm
        total = o.usWinAscent + o.usWinDescent
        return round(up / total, 4) if total > 0 else 0.82
    except Exception:  # noqa: BLE001
        return 0.82


@lru_cache(maxsize=1)
def _fonts() -> list[str]:
    bundled = sorted({b["family"] for b in bundled_fonts()})
    system: list[str] = []
    if os.name == "nt":
        windir = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        system = [f for f in WINDOWS_FONTS if windir.is_dir()]
    elif shutil.which("fc-list"):
        out = subprocess.run(["fc-list", ":", "family"], capture_output=True, text=True).stdout
        fams = {line.split(",")[0].strip() for line in out.splitlines() if line.strip()}
        system = sorted(f for f in fams if f and not f.startswith("."))
    return bundled + [f for f in system if f not in bundled]


@router.get("/fonts")
def fonts():
    return _fonts()


@router.get("/fonts/bundled")
def fonts_bundled():
    return bundled_fonts()


@router.get("/fonts/file/{name}")
def font_file(name: str):
    path = config.FONTS_DIR / name
    if "/" in name or "\\" in name or not path.is_file():
        raise HTTPException(404, "Fuente no encontrada")
    return FileResponse(path, headers={"Cache-Control": "max-age=86400"})


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
