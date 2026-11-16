"""Reglas de corte inteligente.

Entrada: silencios medidos por FFmpeg (señal real) + palabras de Whisper (opcional).
Las palabras solo PROTEGEN: un corte nunca se superpone a una palabra transcrita,
y si la frase continúa después de la pausa se deja más aire para no romper el ritmo.
"""
from __future__ import annotations

import uuid
from typing import Sequence

from ..schemas import AutoEditSettings, Cut, Word
from .timeline import merge_intervals

SENTENCE_END = (".", "?", "!", "…", "。", "？", "！")


def _subtract(interval: tuple[float, float], blockers: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
    s, e = interval
    out = []
    cur = s
    for bs, be in blockers:
        if be <= cur or bs >= e:
            continue
        if bs > cur:
            out.append((cur, bs))
        cur = max(cur, be)
    if cur < e:
        out.append((cur, e))
    return out


def compute_cuts(silences: Sequence[tuple[float, float]], words: Sequence[Word], duration: float,
                 settings: AutoEditSettings) -> list[Cut]:
    words = sorted(words, key=lambda w: w.start)

    gaps: list[tuple[float, float]] = []
    for ss, se in silences:
        blockers = []
        if settings.protect_words:
            # Los tiempos de Whisper se "derraman" hacia los silencios (±0.4 s). Una palabra solo
            # bloquea el corte si al menos la mitad de ella cae dentro del silencio medido:
            # en ese caso probablemente es voz baja que el umbral confundió con silencio.
            for w in words:
                dur = max(1e-3, w.end - w.start)
                overlap = min(w.end, se) - max(w.start, ss)
                if overlap > 0 and overlap / dur >= 0.5:
                    blockers.append((w.start, w.end))
        gaps.extend(_subtract((ss, se), merge_intervals(blockers)) if blockers else [(ss, se)])

    raw: list[tuple[float, float, str]] = []
    for gs, ge in gaps:
        prev = next((w for w in reversed(words) if w.start < gs), None)
        mid_sentence = prev is not None and not prev.text.strip().endswith(SENTENCE_END)
        pad = settings.mid_sentence_padding if mid_sentence else settings.padding
        pad_before = 0.0 if gs <= 0.01 else pad
        pad_after = 0.0 if ge >= duration - 0.01 else pad
        cs, ce = gs + pad_before, ge - pad_after
        if ce - cs < 0.12:
            continue
        reason = f"Pausa de {ge - gs:.1f} s" + (" (dentro de frase)" if mid_sentence else "")
        raw.append((cs, ce, gs, ge, reason))

    raw.sort()
    # Si entre dos pausas solo hay un sonido muy corto (clic, respiración) y ninguna palabra,
    # se eliminan ambas pausas y ese sonido en un solo corte.
    merged: list[list] = []
    for cs, ce, gs, ge, reason in raw:
        if merged:
            ps, pe, pgs, pge, preason = merged[-1]
            content = gs - pge
            has_word = any(w.start < gs and w.end > pge and min(w.end, gs) - max(w.start, pge) > 0.05
                           for w in words)
            if content < settings.min_keep and not has_word:
                merged[-1] = [ps, max(pe, ce), pgs, ge, preason]
                continue
        merged.append([cs, ce, gs, ge, reason])

    return [Cut(id=uuid.uuid4().hex[:8], start=round(s, 3), end=round(e, 3), kind="silence",
                enabled=True, reason=r) for s, e, _gs, _ge, r in merged]
