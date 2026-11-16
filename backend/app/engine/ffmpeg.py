"""Ejecución de FFmpeg/FFprobe con progreso, cancelación y errores legibles."""
from __future__ import annotations

import json
import shutil
import subprocess
import threading
from collections import deque
from typing import Callable, Optional, Sequence

from .. import config


class FFmpegError(RuntimeError):
    pass


class OperationCanceled(Exception):
    pass


def available() -> dict:
    ff = shutil.which(config.FFMPEG)
    fp = shutil.which(config.FFPROBE)
    version = None
    if ff:
        out = subprocess.run([ff, "-hide_banner", "-version"], capture_output=True, text=True)
        version = out.stdout.splitlines()[0] if out.stdout else None
    return {"ffmpeg": ff, "ffprobe": fp, "version": version, "ok": bool(ff and fp)}


def probe_json(path: str) -> dict:
    cmd = [config.FFPROBE, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise FFmpegError(f"No se pudo leer el archivo: {p.stderr.strip()[:400] or 'formato no reconocido'}")
    return json.loads(p.stdout)


def run(
    args: Sequence[str],
    *,
    duration: Optional[float] = None,
    on_progress: Optional[Callable[[float], None]] = None,
    cancel_event: Optional[threading.Event] = None,
    capture_stderr: bool = False,
) -> str:
    """Ejecuta ffmpeg. `duration` (s esperados de salida) permite calcular el progreso.

    Devuelve stderr si capture_stderr=True (útil para filtros de análisis como silencedetect).
    """
    cmd = [config.FFMPEG, "-hide_banner", "-nostdin", "-y", "-progress", "pipe:1", "-nostats", *args]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            errors="replace", bufsize=1)
    stderr_tail: deque[str] = deque(maxlen=60)
    stderr_full: list[str] = []

    def read_stderr() -> None:
        assert proc.stderr is not None
        for line in proc.stderr:
            stderr_tail.append(line)
            if capture_stderr:
                stderr_full.append(line)

    t = threading.Thread(target=read_stderr, daemon=True)
    t.start()

    canceled = False
    assert proc.stdout is not None
    for line in proc.stdout:
        if cancel_event is not None and cancel_event.is_set():
            canceled = True
            proc.terminate()
            break
        if on_progress and duration and line.startswith("out_time_us="):
            try:
                us = int(line.split("=", 1)[1])
                on_progress(min(1.0, max(0.0, us / 1e6 / duration)))
            except ValueError:
                pass
    try:
        proc.wait(timeout=10 if canceled else None)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    t.join(timeout=5)

    if canceled or (cancel_event is not None and cancel_event.is_set()):
        raise OperationCanceled()
    if proc.returncode != 0:
        tail = "".join(stderr_tail).strip()
        raise FFmpegError(f"FFmpeg terminó con código {proc.returncode}:\n{tail[-1500:]}")
    return "".join(stderr_full)
