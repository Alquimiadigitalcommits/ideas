"""Modo automático: de un video a un MP4 listo para la plataforma, en un solo proceso."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import config, db
from ..engine import facetrack, hardware, render, transcribe
from ..engine.reframe import ASPECTS
from ..jobs import JobContext, manager
from ..schemas import AutoEditSettings, ExportRequest, Job, ProjectDoc, SubtitleStyle
from .projects import (_SAFE, _get, _require_media, _stepper, _wrap_cancel,
                       do_autoedit, do_transcribe, prepare_assets)

router = APIRouter(prefix="/api")


class AutoRequest(BaseModel):
    platform: str = "tiktok"                     # clave de render.PROFILES
    remove_silences: bool = True
    pace: Literal["natural", "dinamico"] = "natural"
    subtitles: bool = True
    burn_subtitles: bool = True
    subtitle_style: Optional[SubtitleStyle] = None
    face_track: bool = True                      # solo se aplica si cambia la relación de aspecto
    enhance_audio: bool = True                   # quitar graves + reducción de ruido + volumen estándar
    language: Optional[str] = "es"
    whisper_model: Optional[str] = None          # None = según el equipo


PACE = {
    "natural": AutoEditSettings(),
    # ritmo de TikTok/Reels: pausas mínimas y menos aire entre frases
    "dinamico": AutoEditSettings(min_silence=0.35, padding=0.08, mid_sentence_padding=0.14, min_keep=0.3),
}


def plan_steps(req: AutoRequest, info) -> list[tuple[str, float]]:
    """Pasos con su peso relativo (estimado según cuánto tarda cada uno por minuto de video)."""
    target = render.PROFILES.get(req.platform, render.PROFILES["tiktok"])["aspect"]
    aw, ah = ASPECTS[target]
    reframe = abs(info.width / info.height - aw / ah) > 0.05
    steps = [("analizar", 0.04)]
    if info.has_audio and (req.subtitles or req.remove_silences):
        steps.append(("transcribir", 0.30))
    if info.has_audio and req.remove_silences:
        steps.append(("silencios", 0.04))
    if req.face_track and reframe:
        steps.append(("encuadre", 0.10))
    steps.append(("exportar", 0.52))
    total = sum(w for _, w in steps)
    return [(n, w / total) for n, w in steps]


LABEL = {"analizar": "Analizando el video", "transcribir": "Transcribiendo la voz", "silencios": "Quitando silencios",
         "encuadre": "Siguiendo el rostro", "exportar": "Exportando el video final"}


@router.post("/projects/{pid}/auto", response_model=Job)
def start_auto(pid: str, req: AutoRequest):
    p = _get(pid)
    info = _require_media(p)
    if req.platform not in render.PROFILES:
        raise HTTPException(400, f"Plataforma no válida: {req.platform}")
    if manager.active_for(pid, "auto"):
        raise HTTPException(409, "Ya se está creando un video para este proyecto")
    if info.has_audio and req.subtitles and transcribe.import_error():
        raise HTTPException(503, transcribe.import_error())
    hw = hardware.profile()
    model = req.whisper_model or hw["whisper_model"]
    steps = plan_steps(req, info)
    prof = render.PROFILES[req.platform]

    def run(ctx: JobContext):
        summary: dict = {"steps": [n for n, _ in steps], "hardware": hw["tier"], "model": model}
        t0 = time.time()
        acc = 0.0
        for i, (name, w) in enumerate(steps):
            prog = _stepper(ctx, acc, acc + w)
            prog(0.0, f"Paso {i + 1} de {len(steps)}: {LABEL[name]}")
            if name == "analizar":
                prepare_assets(pid, ctx, on_progress=lambda f: prog(f), force_proxy=False)
                # formato, estilo y audio según lo elegido (antes de transcribir: la agrupación usa el estilo)
                def setup(d: ProjectDoc):
                    d.format.aspect = prof["aspect"]
                    d.format.mode = "crop"
                    d.format.track_enabled = False
                    d.format.jump_zoom = 0.08 if req.pace == "dinamico" else 0.0
                    if req.subtitle_style:
                        d.subtitle_style = req.subtitle_style
                    d.audio.highpass = req.enhance_audio
                    d.audio.denoise = req.enhance_audio
                    d.audio.denoise_strength = 0.5
                    if not req.subtitles:
                        d.captions = []
                db.update_doc(pid, setup)
            elif name == "transcribir":
                r = do_transcribe(pid, info, model, req.language, ctx,
                                  lambda f, m=None: prog(f, f"Paso {i + 1} de {len(steps)}: {m or LABEL[name]}"))
                summary["words"] = r["words"]
            elif name == "silencios":
                r = do_autoedit(pid, info, PACE[req.pace], ctx, lambda f, m=None: prog(f))
                summary.update(cuts=r["cuts"], removed_seconds=r["removed_seconds"])
            elif name == "encuadre":
                cur = db.get_project(pid)
                assert cur
                proxy = config.project_dir(pid) / "proxy.mp4"
                src = str(proxy) if proxy.is_file() else info.source_path
                try:
                    tr = facetrack.track_faces(src, info.duration, on_progress=lambda f: prog(f),
                                               cancel_event=ctx.cancel_event)
                except Exception:  # noqa: BLE001  sin rostro detectable: se mantiene el recorte centrado
                    tr = {"track": [], "detection_rate": 0.0}
                ok = bool(tr["track"]) and tr["detection_rate"] >= 0.3
                summary["face"] = round(tr["detection_rate"], 2) if ok else None

                def apply_track(d: ProjectDoc):
                    d.format.track = tr["track"] if ok else []
                    d.format.track_enabled = ok
                db.update_doc(pid, apply_track)
            elif name == "exportar":
                cur = db.get_project(pid)
                assert cur
                stem = Path(info.file_name).stem
                base = _SAFE.sub("_", f"{stem}_{req.platform}_{time.strftime('%Y%m%d-%H%M%S')}").strip()
                ereq = ExportRequest(profile=req.platform, burn_subtitles=req.burn_subtitles and req.subtitles,
                                     write_srt=req.subtitles, normalize_audio=req.enhance_audio,
                                     preset=hw["export_preset"], crf=21)
                res = render.export(cur.doc, ereq, config.project_dir(pid) / "exports", base,
                                    on_progress=lambda f: prog(f), cancel_event=ctx.cancel_event)
                res["dir"] = str(config.project_dir(pid) / "exports")
                summary["export"] = res
            ctx.check()
            acc += w
        summary["seconds"] = round(time.time() - t0, 1)
        return summary

    return manager.submit(pid, "auto", _wrap_cancel(run), "Preparando la creación automática")
