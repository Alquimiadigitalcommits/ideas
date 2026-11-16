"""Análisis de audio auxiliar: estimación del piso de ruido para la reducción de ruido."""
from __future__ import annotations

import re
import subprocess
import threading

from .. import config
from ..schemas import MediaInfo
from .silence import detect_silences

_cache: dict[tuple[str, float], float] = {}
_lock = threading.Lock()


def noise_floor_db(info: MediaInfo, cancel_event=None) -> float:
    """RMS (dB) del tramo más silencioso y largo: la referencia que necesita afftdn (parámetro nf).

    Con el modo de seguimiento automático (tn=1) afftdn casi no actúa sobre ruido estacionario;
    con nf medido reduce ~30 dB el ruido sin tocar la voz (ver test_denoise_lowers_noise_floor).
    """
    key = (info.source_path, info.duration)
    with _lock:
        if key in _cache:
            return _cache[key]
    sil = detect_silences(info, -30, 0.4, cancel_event=cancel_event)
    level = -50.0
    if sil:
        s, e = max(sil, key=lambda x: x[1] - x[0])
        s, e = s + 0.1, min(e - 0.1, s + 3.1)
        if e - s > 0.2:
            out = subprocess.run([config.FFMPEG, "-hide_banner", "-nostdin", "-ss", f"{s:.3f}", "-t", f"{e - s:.3f}",
                                  "-i", info.source_path, "-map", "0:a:0", "-af", "astats=metadata=0",
                                  "-f", "null", "-"], capture_output=True, text=True).stderr
            vals = re.findall(r"RMS level dB:\s*(-?[\d.]+)", out)
            if vals:
                level = float(vals[-1])
    nf = max(-80.0, min(-20.0, level + 3.0))
    with _lock:
        _cache[key] = nf
    return nf
