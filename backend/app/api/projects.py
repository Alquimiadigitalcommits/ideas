"""Endpoints de proyectos, importación, acciones de procesamiento y archivos."""
from __future__ import annotations

import json
import os
import re
import shutil
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel

from .. import config, db
from ..engine import autoedit, facetrack, ffmpeg, media, render, scenes, silence, subtitles, transcribe
from ..engine.timeline import TimeMap, keep_segments
from ..jobs import Canceled, JobContext, manager
from ..schemas import AutoEditSettings, ExportRequest, Job, MusicTrack, Project, ProjectDoc, TranscribeRequest

router = APIRouter(prefix="/api")


def _with_status(p: Project) -> Project:
    p.media_available = bool(p.doc.media and os.path.isfile(p.doc.media.source_path)) if p.doc.media else None
    return p


def _get(pid: str) -> Project:
    p = db.get_project(pid)
    if p is None:
        raise HTTPException(404, "Proyecto no encontrado")
    return _with_status(p)


def _require_media(p: Project):
    if p.doc.media is None:
        raise HTTPException(400, "El proyecto aún no tiene un video importado")
    if not os.path.isfile(p.doc.media.source_path):
        raise HTTPException(400, f"No se encuentra el video original: {p.doc.media.source_path}")
    return p.doc.media


def _wrap_cancel(fn):
    """Traduce la cancelación de FFmpeg/Whisper a la del gestor de jobs."""
    def inner(ctx: JobContext):
        try:
            return fn(ctx)
        except ffmpeg.OperationCanceled:
            raise Canceled()
    return inner


def _ensure_single(pid: str, kind: str):
    if manager.active_for(pid, kind):
        raise HTTPException(409, "Ya hay una operación de este tipo en curso para el proyecto")


# ------------------------------------------------------------------ CRUD

class CreateProject(BaseModel):
    name: str = "Proyecto sin título"


class SaveProject(BaseModel):
    rev: int
    doc: ProjectDoc
    name: Optional[str] = None


@router.get("/projects", response_model=list[Project])
def list_projects():
    return [_with_status(p) for p in db.list_projects()]


@router.post("/projects", response_model=Project)
def create_project(body: CreateProject):
    return db.create_project(body.name.strip() or "Proyecto sin título")


@router.get("/projects/{pid}", response_model=Project)
def get_project(pid: str):
    return _get(pid)


@router.put("/projects/{pid}", response_model=Project)
def save_project(pid: str, body: SaveProject):
    _get(pid)
    try:
        return _with_status(db.save_project(pid, body.doc, expected_rev=body.rev, name=body.name))
    except db.RevisionConflict as c:
        return JSONResponse(status_code=409, content={
            "detail": "El proyecto cambió en el servidor", "project": json.loads(c.current.model_dump_json())})


@router.delete("/projects/{pid}")
def delete_project(pid: str):
    _get(pid)
    db.delete_project(pid)
    # Solo se borra la carpeta de trabajo del proyecto; un original importado por ruta nunca se toca.
    shutil.rmtree(config.PROJECTS_DIR / pid, ignore_errors=True)
    return {"ok": True}


# ------------------------------------------------------------------ importación

def _prepare_job(pid: str):
    def run(ctx: JobContext):
        p = db.get_project(pid)
        assert p and p.doc.media
        info = p.doc.media
        pdir = config.project_dir(pid)
        ctx.progress(0.01, "Generando miniaturas")
        media.make_thumbnails(info, pdir, cancel_event=ctx.cancel_event)
        ctx.progress(0.08, "Analizando forma de onda")
        media.make_waveform(info, pdir, cancel_event=ctx.cancel_event)
        ctx.progress(0.15, "Creando proxy de previsualización")
        media.make_proxy(info, pdir, cancel_event=ctx.cancel_event,
                         on_progress=lambda f: ctx.progress(0.15 + 0.85 * f))
        db.update_doc(pid, lambda d: setattr(d, "proxy_ready", True))
        return {"proxy": True}
    return _wrap_cancel(run)


def _set_media(pid: str, path: str) -> Job:
    info = media.probe(path)

    def mutate(d: ProjectDoc):
        d.media = info
        d.proxy_ready = False
        d.cuts = []
        d.captions = []
        d.language = None
        # formato inicial sugerido según el video
        d.format.aspect = "16:9" if info.width >= info.height else "9:16"

    db.update_doc(pid, mutate)
    pdir = config.project_dir(pid)
    for f in ("proxy.mp4", "waveform.json", "thumbs.jpg", "thumbs.json", "audio16k.wav"):
        (pdir / f).unlink(missing_ok=True)
    return manager.submit(pid, "prepare", _prepare_job(pid), "Preparando video")


_SAFE = re.compile(r"[^\w.\- ]+", re.UNICODE)


@router.post("/projects/{pid}/import", response_model=Job)
async def import_upload(pid: str, file: UploadFile = File(...)):
    _get(pid)
    name = _SAFE.sub("_", os.path.basename(file.filename or "video.mp4")).strip() or "video.mp4"
    if Path(name).suffix.lower() not in config.ALLOWED_EXTENSIONS:
        raise HTTPException(400, "Formato no soportado. Usa MP4, MOV o MKV.")
    dest_dir = config.project_dir(pid) / "source"
    dest_dir.mkdir(exist_ok=True)
    dest = dest_dir / name
    with open(dest, "wb") as out:
        while chunk := await file.read(8 * 1024 * 1024):
            out.write(chunk)
    try:
        return _set_media(pid, str(dest))
    except (ValueError, FileNotFoundError, ffmpeg.FFmpegError) as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, str(e))


class ImportPath(BaseModel):
    path: str


@router.post("/projects/{pid}/import-path", response_model=Job)
def import_path(pid: str, body: ImportPath):
    """Importa un archivo local sin copiarlo (se abre solo en lectura)."""
    _get(pid)
    try:
        return _set_media(pid, os.path.expanduser(body.path))
    except (ValueError, FileNotFoundError, ffmpeg.FFmpegError) as e:
        raise HTTPException(400, str(e))


# ------------------------------------------------------------------ acciones

@router.post("/projects/{pid}/transcribe", response_model=Job)
def start_transcribe(pid: str, body: TranscribeRequest):
    p = _get(pid)
    info = _require_media(p)
    if not info.has_audio:
        raise HTTPException(400, "El video no tiene audio para transcribir")
    if body.model not in config.WHISPER_MODELS:
        raise HTTPException(400, f"Modelo no válido. Opciones: {', '.join(config.WHISPER_MODELS)}")
    _ensure_single(pid, "transcribe")

    def run(ctx: JobContext):
        pdir = config.project_dir(pid)
        ctx.progress(0.01, "Extrayendo audio")
        wav = media.extract_audio_wav(info, pdir, cancel_event=ctx.cancel_event)
        ctx.progress(0.06, f"Cargando modelo Whisper '{body.model}' (la primera vez se descarga)")
        transcribe.get_model(body.model)
        ctx.check()
        ctx.progress(0.1, "Transcribiendo")
        words, lang = transcribe.transcribe(str(wav), info.duration, body.model, body.language,
                                            on_progress=lambda f: ctx.progress(0.1 + 0.9 * f),
                                            cancel_event=ctx.cancel_event)

        def mutate(d: ProjectDoc):
            d.captions = subtitles.build_captions(words, d.subtitle_style.max_words, d.subtitle_style.max_chars)
            d.language = lang

        db.update_doc(pid, mutate)
        return {"words": len(words), "language": lang}

    return manager.submit(pid, "transcribe", _wrap_cancel(run), "Transcripción en cola")


@router.post("/projects/{pid}/autoedit", response_model=Job)
def start_autoedit(pid: str, body: AutoEditSettings):
    p = _get(pid)
    info = _require_media(p)
    _ensure_single(pid, "autoedit")

    def run(ctx: JobContext):
        ctx.progress(0.0, "Detectando silencios")
        sil = silence.detect_silences(info, body.noise_db, body.min_silence,
                                      on_progress=lambda f: ctx.progress(0.9 * f),
                                      cancel_event=ctx.cancel_event)
        cur = db.get_project(pid)
        assert cur
        words = [w for c in cur.doc.captions for w in c.words]
        cuts = autoedit.compute_cuts(sil, words, info.duration, body)

        def mutate(d: ProjectDoc):
            d.cuts = [c for c in d.cuts if c.kind == "manual"] + cuts
            d.cuts.sort(key=lambda c: c.start)
            d.autoedit = body

        updated = db.update_doc(pid, mutate)
        segs = keep_segments(updated.doc.cuts, info.duration)
        out = sum(e - s for s, e in segs)
        return {"silences": len(sil), "cuts": len(cuts), "used_words": bool(words),
                "removed_seconds": round(info.duration - out, 2), "output_duration": round(out, 2)}

    return manager.submit(pid, "autoedit", _wrap_cancel(run), "Auto-edición en cola")


@router.post("/projects/{pid}/export", response_model=Job)
def start_export(pid: str, body: ExportRequest):
    p = _get(pid)
    _require_media(p)
    try:
        render.plan(p.doc, body)  # valida antes de encolar
    except ValueError as e:
        raise HTTPException(400, str(e))

    def run(ctx: JobContext):
        cur = db.get_project(pid)
        assert cur
        stamp = time.strftime("%Y%m%d-%H%M%S")
        stem = Path(cur.doc.media.file_name).stem if cur.doc.media else "video"
        base = _SAFE.sub("_", body.file_name or f"{stem}_{body.profile}_{stamp}").strip()
        out_dir = config.project_dir(pid) / "exports"
        ctx.progress(0.0, "Exportando")
        res = render.export(cur.doc, body, out_dir, base, on_progress=ctx.progress, cancel_event=ctx.cancel_event)
        res["dir"] = str(out_dir)
        return res

    return manager.submit(pid, "export", _wrap_cancel(run), "Exportación en cola")


# ------------------------------------------------------------------ archivos

def _project_file(pid: str, name: str) -> Path:
    path = config.project_dir(pid) / name
    if not path.is_file():
        raise HTTPException(404, "Archivo no disponible todavía")
    return path


@router.get("/projects/{pid}/media/preview")
def preview_video(pid: str):
    p = _get(pid)
    proxy = config.project_dir(pid) / "proxy.mp4"
    if p.doc.proxy_ready and proxy.is_file():
        return FileResponse(proxy, media_type="video/mp4")
    m = p.doc.media
    if m and m.video_codec == "h264" and m.source_path.lower().endswith((".mp4", ".mov")) \
            and os.path.isfile(m.source_path):
        return FileResponse(m.source_path, media_type="video/mp4")
    raise HTTPException(404, "La previsualización aún se está generando")


@router.get("/projects/{pid}/media/waveform")
def waveform(pid: str):
    return FileResponse(_project_file(pid, "waveform.json"), media_type="application/json")


@router.get("/projects/{pid}/media/thumbs.jpg")
def thumbs(pid: str):
    return FileResponse(_project_file(pid, "thumbs.jpg"), media_type="image/jpeg")


@router.get("/projects/{pid}/media/thumbs.json")
def thumbs_meta(pid: str):
    return FileResponse(_project_file(pid, "thumbs.json"), media_type="application/json")


@router.get("/projects/{pid}/subtitles.srt")
def srt(pid: str):
    p = _get(pid)
    m = _require_media(p)
    tm = TimeMap(keep_segments(p.doc.cuts, m.duration))
    text = subtitles.to_srt(subtitles.output_cues(p.doc.captions, tm), p.doc.subtitle_style.uppercase)
    name = Path(m.file_name).stem + ".srt"
    return PlainTextResponse(text, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/projects/{pid}/project-file")
def project_file(pid: str):
    p = _get(pid)
    return Response(p.model_dump_json(indent=2), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{_SAFE.sub("_", p.name)}.svep.json"'})


@router.get("/projects/{pid}/exports")
def list_exports(pid: str):
    d = config.project_dir(pid) / "exports"
    if not d.is_dir():
        return []
    files = sorted((f for f in d.iterdir() if f.suffix in (".mp4", ".srt") and ".part." not in f.name),
                   key=lambda f: f.stat().st_mtime, reverse=True)
    return [{"name": f.name, "size": f.stat().st_size, "mtime": f.stat().st_mtime, "path": str(f)} for f in files]


@router.get("/projects/{pid}/exports/{name}")
def download_export(pid: str, name: str):
    if "/" in name or "\\" in name or name.startswith("."):
        raise HTTPException(400, "Nombre inválido")
    path = config.project_dir(pid) / "exports" / name
    if not path.is_file():
        raise HTTPException(404, "No existe")
    return FileResponse(path, filename=name)


# ------------------------------------------------------------------ análisis visual (etapa 3)

def _analysis_source(pid: str, p: Project) -> str:
    """El proxy (≤720p) es más rápido de analizar y tiene la misma línea de tiempo que el original."""
    proxy = config.project_dir(pid) / "proxy.mp4"
    return str(proxy) if p.doc.proxy_ready and proxy.is_file() else p.doc.media.source_path  # type: ignore[union-attr]


class ScenesRequest(BaseModel):
    threshold: float = 27.0
    min_scene_len: float = 0.6


@router.post("/projects/{pid}/scenes", response_model=Job)
def start_scenes(pid: str, body: ScenesRequest):
    p = _get(pid)
    info = _require_media(p)
    _ensure_single(pid, "scenes")
    src = _analysis_source(pid, p)

    def run(ctx: JobContext):
        ctx.progress(0.0, "Detectando cambios de escena")
        found = scenes.detect_scenes(src, info.duration, body.threshold, body.min_scene_len,
                                     on_progress=ctx.progress, cancel_event=ctx.cancel_event)
        db.update_doc(pid, lambda d: setattr(d, "scenes", found))
        return {"scenes": len(found)}

    return manager.submit(pid, "scenes", _wrap_cancel(run), "Detección de escenas en cola")


@router.post("/projects/{pid}/facetrack", response_model=Job)
def start_facetrack(pid: str):
    p = _get(pid)
    info = _require_media(p)
    _ensure_single(pid, "facetrack")
    src = _analysis_source(pid, p)

    def run(ctx: JobContext):
        ctx.progress(0.0, "Buscando rostros")
        res = facetrack.track_faces(src, info.duration, on_progress=ctx.progress, cancel_event=ctx.cancel_event)
        if not res["track"]:
            raise RuntimeError("No se detectaron rostros frontales en el video")

        def mutate(d: ProjectDoc):
            d.format.track = res["track"]
            d.format.track_enabled = True
            d.format.mode = "crop"

        db.update_doc(pid, mutate)
        return {"keyframes": len(res["track"]), "detection_rate": res["detection_rate"]}

    return manager.submit(pid, "facetrack", _wrap_cancel(run), "Seguimiento de rostro en cola")


# ------------------------------------------------------------------ música (etapa 5)

MUSIC_EXT = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".opus"}


@router.post("/projects/{pid}/music", response_model=Project)
async def upload_music(pid: str, file: UploadFile = File(...)):
    _get(pid)
    name = _SAFE.sub("_", os.path.basename(file.filename or "musica.mp3")).strip() or "musica.mp3"
    if Path(name).suffix.lower() not in MUSIC_EXT:
        raise HTTPException(400, "Formato de audio no soportado. Usa MP3, WAV, M4A, AAC, OGG, FLAC u OPUS.")
    d = config.project_dir(pid) / "music"
    d.mkdir(exist_ok=True)
    dest = d / name
    with open(dest, "wb") as out:
        while chunk := await file.read(4 * 1024 * 1024):
            out.write(chunk)
    try:
        data = ffmpeg.probe_json(str(dest))
        if not any(st.get("codec_type") == "audio" for st in data.get("streams", [])):
            raise ValueError("El archivo no contiene audio")
        dur = float(data.get("format", {}).get("duration") or 0)
        if dur <= 0:
            raise ValueError("No se pudo leer la duración del audio")
    except (ValueError, ffmpeg.FFmpegError) as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, str(e))

    def mutate(doc: ProjectDoc):
        prev = doc.audio.music
        keep = prev.model_dump(exclude={"path", "file_name", "duration"}) if prev else {}
        doc.audio.music = MusicTrack(path=str(dest), file_name=name, duration=dur, **keep)

    return _with_status(db.update_doc(pid, mutate))


@router.delete("/projects/{pid}/music", response_model=Project)
def delete_music(pid: str):
    p = _get(pid)
    if p.doc.audio.music:
        mpath = Path(p.doc.audio.music.path)
        if config.PROJECTS_DIR in mpath.parents:   # solo se borra la copia del proyecto
            mpath.unlink(missing_ok=True)
    return _with_status(db.update_doc(pid, lambda d: setattr(d.audio, "music", None)))


@router.get("/projects/{pid}/media/music")
def music_file(pid: str):
    p = _get(pid)
    m = p.doc.audio.music
    if not m or not os.path.isfile(m.path):
        raise HTTPException(404, "Sin música")
    return FileResponse(m.path)


# ------------------------------------------------------------------ proyectos portables (etapa 2)

@router.post("/projects/import", response_model=Project)
async def import_project(file: UploadFile = File(...)):
    raw = await file.read()
    try:
        data = json.loads(raw)
        doc = ProjectDoc.model_validate(data["doc"] if isinstance(data, dict) and "doc" in data else data)
        name = (data.get("name") if isinstance(data, dict) else None) or Path(file.filename or "Proyecto").stem
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"No es un proyecto válido: {str(e)[:300]}")
    doc.proxy_ready = False
    p = db.create_project(f"{name} (importado)".replace(".svep", ""))
    p = db.save_project(p.id, doc)
    if doc.media and os.path.isfile(doc.media.source_path):
        manager.submit(p.id, "prepare", _prepare_job(p.id), "Preparando video")
    return _with_status(p)


class RelinkRequest(BaseModel):
    path: str
    force: bool = False


@router.post("/projects/{pid}/relink", response_model=Job)
def relink(pid: str, body: RelinkRequest):
    """Apunta el proyecto a otra ubicación del mismo video conservando todas las ediciones."""
    p = _get(pid)
    if p.doc.media is None:
        raise HTTPException(400, "El proyecto no tiene video; usa importar")
    try:
        info = media.probe(os.path.expanduser(body.path))
    except (ValueError, FileNotFoundError, ffmpeg.FFmpegError) as e:
        raise HTTPException(400, str(e))
    old = p.doc.media.duration
    if abs(info.duration - old) > 1.0 and not body.force:
        raise HTTPException(409, f"La duración no coincide ({info.duration:.1f} s vs {old:.1f} s del proyecto). "
                                 "Puede no ser el mismo video.")

    def mutate(d: ProjectDoc):
        d.media = info
        d.proxy_ready = False

    db.update_doc(pid, mutate)
    pdir = config.project_dir(pid)
    for f in ("proxy.mp4", "waveform.json", "thumbs.jpg", "thumbs.json", "audio16k.wav"):
        (pdir / f).unlink(missing_ok=True)
    return manager.submit(pid, "prepare", _prepare_job(pid), "Preparando video")


# ------------------------------------------------------------------ previsualización exacta (etapa 4)

class PreviewRequest(BaseModel):
    center: float                 # tiempo de salida
    span: float = 3.0             # duración total del tramo
    short_side: int = 540


@router.post("/projects/{pid}/preview-clip", response_model=Job)
def start_preview(pid: str, body: PreviewRequest):
    p = _get(pid)
    _require_media(p)
    span = max(0.5, min(20.0, body.span))
    window = (body.center - span / 2, body.center + span / 2)
    aspect = p.doc.format.aspect
    from ..engine.reframe import output_size
    w, h = output_size(aspect, body.short_side)
    req = ExportRequest(profile="tiktok", width=w, height=h, preset="ultrafast", crf=26, write_srt=False)
    try:
        render.plan(p.doc, req, window)
    except ValueError as e:
        raise HTTPException(400, str(e))

    def run(ctx: JobContext):
        cur = db.get_project(pid)
        assert cur
        out_dir = config.project_dir(pid) / "previews"
        for old in out_dir.glob("preview_*"):
            old.unlink(missing_ok=True)
        base = f"preview_{int(time.time() * 1000)}"
        res = render.export(cur.doc, req, out_dir, base, window=window,
                            on_progress=ctx.progress, cancel_event=ctx.cancel_event)
        res["start"] = round(max(0.0, window[0]), 3)
        return res

    return manager.submit(pid, "preview", _wrap_cancel(run), "Renderizando previsualización")


@router.get("/projects/{pid}/previews/{name}")
def preview_file(pid: str, name: str):
    if "/" in name or "\\" in name or name.startswith("."):
        raise HTTPException(400, "Nombre inválido")
    path = config.project_dir(pid) / "previews" / name
    if not path.is_file():
        raise HTTPException(404, "No existe")
    return FileResponse(path, media_type="video/mp4")
