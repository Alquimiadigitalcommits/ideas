"""Análisis de medios y generación de recursos de previsualización."""
from __future__ import annotations

import json
import os
import struct
import subprocess
import threading
from pathlib import Path
from typing import Callable, Optional

from .. import config
from ..schemas import MediaInfo
from . import ffmpeg


def _parse_fps(rate: str | None) -> float:
    if not rate or rate in ("0/0", "0"):
        return 0.0
    if "/" in rate:
        n, d = rate.split("/")
        return float(n) / float(d) if float(d) else 0.0
    return float(rate)


def probe(path: str) -> MediaInfo:
    if not os.path.isfile(path):
        raise FileNotFoundError(f"No existe el archivo: {path}")
    ext = Path(path).suffix.lower()
    if ext not in config.ALLOWED_EXTENSIONS:
        raise ValueError(f"Formato no soportado ({ext}). Usa MP4, MOV o MKV.")
    data = ffmpeg.probe_json(path)
    streams = data.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"
              and not s.get("disposition", {}).get("attached_pic")), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if v is None:
        raise ValueError("El archivo no contiene una pista de video.")
    fmt = data.get("format", {})
    duration = float(fmt.get("duration") or v.get("duration") or 0)
    if duration <= 0:
        raise ValueError("No se pudo determinar la duración del video.")
    fps = _parse_fps(v.get("avg_frame_rate")) or _parse_fps(v.get("r_frame_rate")) or 30.0

    rotation = 0
    for sd in v.get("side_data_list", []) or []:
        if "rotation" in sd:
            rotation = int(sd["rotation"])
    if not rotation and v.get("tags", {}).get("rotate"):
        rotation = int(v["tags"]["rotate"])
    w, h = int(v["width"]), int(v["height"])
    if abs(rotation) % 180 == 90:  # ffmpeg autorota: dimensiones visibles
        w, h = h, w

    return MediaInfo(
        source_path=os.path.abspath(path), file_name=os.path.basename(path), duration=duration,
        width=w, height=h, fps=round(fps, 3), video_codec=v.get("codec_name"),
        audio_codec=a.get("codec_name") if a else None, has_audio=a is not None,
        size_bytes=int(fmt.get("size") or os.path.getsize(path)), rotation=rotation,
    )


def proxy_path(pdir: Path) -> Path:
    return pdir / "proxy.mp4"


def make_proxy(info: MediaInfo, pdir: Path, *, on_progress=None, cancel_event=None) -> Path:
    """Proxy H.264 a FPS constante, ≤720p, keyframe cada ~1 s, faststart."""
    out = proxy_path(pdir)
    tmp = pdir / "proxy.tmp.mp4"
    fps = info.fps if 1 <= info.fps <= 60 else 30
    h = min(config.PROXY_MAX_HEIGHT, info.height)
    h -= h % 2
    vf = f"scale=-2:{h}:flags=bicubic,fps={fps:g},format=yuv420p"
    args = ["-i", info.source_path, "-map", "0:v:0", "-vf", vf,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
            "-g", str(max(1, round(fps))), "-keyint_min", str(max(1, round(fps))), "-sc_threshold", "0"]
    if info.has_audio:
        args += ["-map", "0:a:0", "-c:a", "aac", "-b:a", "128k", "-ac", "2"]
    args += ["-movflags", "+faststart", "-f", "mp4", str(tmp)]
    ffmpeg.run(args, duration=info.duration, on_progress=on_progress, cancel_event=cancel_event)
    os.replace(tmp, out)
    return out


def make_waveform(info: MediaInfo, pdir: Path, *, peaks_per_second: int = 50, cancel_event=None) -> Path:
    """Picos de amplitud (0..1) para dibujar la forma de onda. Se guarda como JSON."""
    out = pdir / "waveform.json"
    if not info.has_audio:
        out.write_text(json.dumps({"pps": peaks_per_second, "peaks": []}))
        return out
    sr = 8000
    block = sr // peaks_per_second
    cmd = [config.FFMPEG, "-hide_banner", "-nostdin", "-v", "error", "-i", info.source_path,
           "-map", "0:a:0", "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    peaks: list[float] = []
    assert proc.stdout is not None
    buf_size = block * 2
    try:
        while True:
            if cancel_event is not None and cancel_event.is_set():
                proc.kill()
                raise ffmpeg.OperationCanceled()
            chunk = proc.stdout.read(buf_size)
            if not chunk:
                break
            n = len(chunk) // 2
            if n == 0:
                break
            samples = struct.unpack(f"<{n}h", chunk[: n * 2])
            peaks.append(round(max(abs(min(samples)), abs(max(samples))) / 32768, 3))
    finally:
        proc.wait()
    m = max(peaks) if peaks else 1
    if m > 0:
        peaks = [round(p / m, 3) for p in peaks]
    out.write_text(json.dumps({"pps": peaks_per_second, "peaks": peaks}))
    return out


def make_thumbnails(info: MediaInfo, pdir: Path, *, count: int = 60, cancel_event=None) -> Path:
    """Tira horizontal de miniaturas (sprite) para la pista de video."""
    out = pdir / "thumbs.jpg"
    count = max(1, min(count, int(info.duration) or 1))
    interval = info.duration / count
    th = 90
    vf = f"fps=1/{interval:.4f},scale=-2:{th},tile={count}x1"
    ffmpeg.run(["-i", info.source_path, "-map", "0:v:0", "-vf", vf, "-frames:v", "1",
                "-q:v", "5", str(out)], cancel_event=cancel_event)
    meta = pdir / "thumbs.json"
    tw = round(th * info.width / info.height)
    tw += tw % 2
    meta.write_text(json.dumps({"count": count, "interval": interval, "tile_width": tw, "tile_height": th}))
    return out


def extract_audio_wav(info: MediaInfo, pdir: Path, *, cancel_event=None) -> Path:
    """WAV mono 16 kHz para Whisper (más rápido que decodificar el contenedor cada vez)."""
    out = pdir / "audio16k.wav"
    if out.exists():
        return out
    tmp = pdir / "audio16k.tmp.wav"
    ffmpeg.run(["-i", info.source_path, "-map", "0:a:0", "-ac", "1", "-ar", "16000",
                "-c:a", "pcm_s16le", "-f", "wav", str(tmp)], duration=info.duration, cancel_event=cancel_event)
    os.replace(tmp, out)
    return out
