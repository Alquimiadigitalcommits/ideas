"""Transcripción con Faster-Whisper y timestamps por palabra."""
from __future__ import annotations

import threading
from typing import Callable, Optional

from ..schemas import Word

_models: dict[str, object] = {}
_lock = threading.Lock()


def _device() -> tuple[str, str]:
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda", "float16"
    except Exception:  # noqa: BLE001
        pass
    return "cpu", "int8"


def get_model(name: str):
    from faster_whisper import WhisperModel
    with _lock:
        if name not in _models:
            device, compute = _device()
            _models[name] = WhisperModel(name, device=device, compute_type=compute)
        return _models[name]


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
    segments, info = model.transcribe(
        audio, language=language or None, word_timestamps=True, vad_filter=True,
        beam_size=5, condition_on_previous_text=False,
    )
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
