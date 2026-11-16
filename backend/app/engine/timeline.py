"""Segmentos conservados y mapeo tiempo-fuente → tiempo-salida.

Es la única fuente de verdad para la sincronía: video, audio y subtítulos se
traducen con estas funciones. El frontend tiene una copia equivalente en
frontend/src/lib/timemap.ts.
"""
from __future__ import annotations

from bisect import bisect_right
from typing import Iterable, Optional, Sequence

Interval = tuple[float, float]


def merge_intervals(intervals: Iterable[Interval], gap: float = 0.0) -> list[Interval]:
    out: list[list[float]] = []
    for s, e in sorted((min(a, b), max(a, b)) for a, b in intervals):
        if out and s <= out[-1][1] + gap:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return [(s, e) for s, e in out]


def active_cut_intervals(cuts: Sequence, duration: float) -> list[Interval]:
    iv = []
    for c in cuts:
        if not getattr(c, "enabled", True):
            continue
        s, e = max(0.0, c.start), min(duration, c.end)
        if e - s > 1e-6:
            iv.append((s, e))
    return merge_intervals(iv)


def _snap(t: float, fps: Optional[float]) -> float:
    if not fps:
        return t
    return round(t * fps) / fps


def keep_segments(cuts: Sequence, duration: float, fps: Optional[float] = None) -> list[Interval]:
    """Complemento de los cortes activos dentro de [0, duration].

    Con `fps`, los bordes se ajustan a la grilla de frames para que audio y
    video de cada segmento tengan exactamente la misma duración.
    """
    segs: list[Interval] = []
    cursor = 0.0
    for s, e in active_cut_intervals(cuts, duration):
        if s > cursor:
            segs.append((cursor, s))
        cursor = max(cursor, e)
    if cursor < duration:
        segs.append((cursor, duration))
    if fps:
        snapped = []
        for s, e in segs:
            ss, ee = _snap(s, fps), _snap(e, fps)
            ee = min(ee, duration) if e >= duration - 1e-6 else ee
            if ee - ss >= 1.0 / fps - 1e-9:
                snapped.append((ss, ee))
        segs = snapped
    return segs


def output_duration(segments: Sequence[Interval]) -> float:
    return sum(e - s for s, e in segments)


class TimeMap:
    """Traduce tiempos de la fuente al eje de salida (tras aplicar cortes)."""

    def __init__(self, segments: Sequence[Interval]):
        self.segments = list(segments)
        self._starts = [s for s, _ in self.segments]
        self._offsets = []
        acc = 0.0
        for s, e in self.segments:
            self._offsets.append(acc)
            acc += e - s
        self.duration = acc

    def to_output(self, t: float) -> Optional[float]:
        """None si `t` cae dentro de un corte."""
        i = bisect_right(self._starts, t) - 1
        if i < 0:
            return None
        s, e = self.segments[i]
        if t > e + 1e-9:
            return None
        return self._offsets[i] + (t - s)

    def map_interval(self, start: float, end: float) -> Optional[Interval]:
        """Intervalo de salida que cubre lo que sobrevive de [start, end]."""
        pieces = []
        for (s, e), off in zip(self.segments, self._offsets):
            a, b = max(s, start), min(e, end)
            if b - a > 1e-6:
                pieces.append((off + a - s, off + b - s))
        if not pieces:
            return None
        return pieces[0][0], pieces[-1][1]

    def to_source(self, t_out: float) -> float:
        for (s, e), off in zip(self.segments, self._offsets):
            if t_out <= off + (e - s) + 1e-9:
                return s + max(0.0, t_out - off)
        return self.segments[-1][1] if self.segments else 0.0


def edit_segments(cuts: Sequence, duration: float, fps: Optional[float] = None) -> list[Interval]:
    """Segmentos conservados, además divididos en las divisiones (cortes de longitud cero).

    Una división no quita material: solo crea una unión donde aplicar una transición.
    """
    segs = keep_segments(cuts, duration, fps)
    points = sorted({_snap(c.start, fps) for c in cuts
                     if getattr(c, "kind", "") == "split" and getattr(c, "enabled", True)})
    if not points:
        return segs
    min_len = (1.0 / fps) if fps else 0.05
    out: list[Interval] = []
    for s, e in segs:
        cur = s
        for p in points:
            if cur + min_len <= p <= e - min_len:
                out.append((cur, p))
                cur = p
        out.append((cur, e))
    return out
