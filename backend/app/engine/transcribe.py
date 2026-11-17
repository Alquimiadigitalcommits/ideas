"""Transcripción con Faster-Whisper y timestamps por palabra."""
from __future__ import annotations

import os
import threading
from typing import Callable, Optional

from ..schemas import Word

_models: dict[str, object] = {}
_lock = threading.Lock()

VC_REDIST_URL = "https://aka.ms/vs/17/release/vc_redist.x64.exe"


class TranscriptionUnavailable(RuntimeError):
    """Error con un mensaje en lenguaje simple y la forma de solucionarlo."""


def explain(e: BaseException) -> str:
    msg = f"{type(e).__name__}: {e}"
    low = msg.lower()
    if "dll" in low or "msvcp" in low or "vcruntime" in low or "_ext" in low:
        return ("Faltan componentes de Windows para la transcripción (Microsoft Visual C++ Redistributable). "
                f"Vuelve a ejecutar el instalador o instálalo desde {VC_REDIST_URL} y reinicia el editor. "
                f"Detalle: {msg[:200]}")
    if any(k in low for k in ("connection", "resolve", "timed out", "max retries", "huggingface", "proxy", "ssl")):
        return ("No se pudo descargar el modelo de transcripción. Revisa tu conexión a internet "
                f"(solo se necesita la primera vez por modelo). Detalle: {msg[:200]}")
    if "memory" in low or "bad_alloc" in low:
        return "No hay memoria suficiente para este modelo. Usa el modelo 'tiny' o 'base' y cierra otros programas."
    return msg[:400]


def import_error() -> str | None:
    """None si la transcripción puede cargar; si no, el motivo explicado."""
    try:
        import ctranslate2  # noqa: F401
        import faster_whisper  # noqa: F401
        return None
    except BaseException as e:  # noqa: BLE001
        return explain(e)


def _device() -> tuple[str, str]:
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda", "float16"
    except Exception:  # noqa: BLE001
        pass
    return "cpu", "int8"


def get_model(name: str):
    try:
        from faster_whisper import WhisperModel
        with _lock:
            if name not in _models:
                device, compute = _device()
                _models[name] = WhisperModel(name, device=device, compute_type=compute,
                                             cpu_threads=max(1, (os.cpu_count() or 2)))
            return _models[name]
    except BaseException as e:  # noqa: BLE001
        raise TranscriptionUnavailable(explain(e)) from e


def _load_wav(path: str):
    """Lee el WAV mono 16 kHz generado por FFmpeg como float32 (evita depender de PyAV)."""
    import wave

    import numpy as np
    with wave.open(path, "rb") as w:
        if w.getframerate() != 16000 or w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise ValueError("Se esperaba WAV mono 16 kHz de 16 bits")
        data = w.readframes(w.getnframes())
    return np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0


def transcribe(wav_path: str, duration: float, model_name: str, language: Optional[str], *,
               on_progress: Optional[Callable[[float], None]] = None,
               cancel_event: Optional[threading.Event] = None) -> tuple[list[Word], str]:
    model = get_model(model_name)
    audio = _load_wav(wav_path)
    # beam_size 5 en equipos normales; en equipos modestos 2 (≈2× más rápido, casi igual de preciso)
    from .hardware import profile
    beam = 2 if profile()["tier"] == "modesto" else 5
    try:
        segments, info = model.transcribe(audio, language=language or None, word_timestamps=True,
                                          vad_filter=True, beam_size=beam, condition_on_previous_text=False)
    except BaseException:  # noqa: BLE001  el filtro de voz (onnxruntime) no cargó: se transcribe sin él
        segments, info = model.transcribe(audio, language=language or None, word_timestamps=True,
                                          vad_filter=False, beam_size=beam, condition_on_previous_text=False)
    words: list[Word] = []
    for seg in segments:  # generador perezoso: el progreso es real
        if cancel_event is not None and cancel_event.is_set():
            from .ffmpeg import OperationCanceled
            raise OperationCanceled()
        for w in seg.words or []:
            text = w.word.strip()
            if text:
                words.append(Word(start=round(w.start, 3), end=round(w.end, 3), text=text,
                                  prob=round(w.probability, 3)))
        if on_progress and duration:
            on_progress(min(0.999, seg.end / duration))
    return words, info.language
