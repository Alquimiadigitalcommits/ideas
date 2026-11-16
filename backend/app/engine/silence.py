"""Detección de silencios con el filtro silencedetect de FFmpeg."""
from __future__ import annotations

import re

from ..schemas import MediaInfo
from . import ffmpeg

_START = re.compile(r"silence_start:\s*(-?[\d.]+)")
_END = re.compile(r"silence_end:\s*(-?[\d.]+)")


def detect_silences(info: MediaInfo, noise_db: float, min_silence: float, *,
                    on_progress=None, cancel_event=None) -> list[tuple[float, float]]:
    if not info.has_audio:
        return []
    stderr = ffmpeg.run(
        ["-i", info.source_path, "-map", "0:a:0", "-vn",
         "-af", f"silencedetect=noise={noise_db}dB:d={min_silence}", "-f", "null", "-"],
        duration=info.duration, on_progress=on_progress, cancel_event=cancel_event, capture_stderr=True,
    )
    return parse_silencedetect(stderr, info.duration)


def parse_silencedetect(stderr: str, duration: float) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    start = None
    for line in stderr.splitlines():
        m = _START.search(line)
        if m:
            start = max(0.0, float(m.group(1)))
            continue
        m = _END.search(line)
        if m and start is not None:
            out.append((start, min(duration, float(m.group(1)))))
            start = None
    if start is not None:  # el archivo termina en silencio
        out.append((start, duration))
    return out
