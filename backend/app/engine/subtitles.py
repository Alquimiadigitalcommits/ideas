"""Frases de subtítulos: agrupación, edición, mapeo a la salida, SRT y ASS."""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Sequence

from ..schemas import Caption, SubtitleStyle, Word
from .timeline import TimeMap

PUNCT_BREAK = (".", "?", "!", "…", ",", ";", ":")


def build_captions(words: Sequence[Word], max_words: int = 4, max_chars: int = 28,
                   max_gap: float = 0.7, max_duration: float = 4.0) -> list[Caption]:
    caps: list[Caption] = []
    cur: list[Word] = []

    def flush():
        if cur:
            caps.append(Caption(id=uuid.uuid4().hex[:8], start=cur[0].start, end=cur[-1].end,
                                text=" ".join(w.text for w in cur), words=list(cur)))
            cur.clear()

    for w in words:
        if cur:
            text_len = len(" ".join(x.text for x in cur)) + 1 + len(w.text)
            if (len(cur) >= max_words or text_len > max_chars or w.start - cur[-1].end > max_gap
                    or w.end - cur[0].start > max_duration or cur[-1].text.endswith(PUNCT_BREAK)):
                flush()
        cur.append(w)
    flush()
    return caps


def regroup(captions: Sequence[Caption], max_words: int, max_chars: int) -> list[Caption]:
    """Reagrupa todas las palabras (p. ej. al cambiar 'palabras por bloque')."""
    words = [w for c in captions for w in c.words]
    return build_captions(words, max_words=max_words, max_chars=max_chars)


def retime_text(caption: Caption, new_text: str) -> Caption:
    """Aplica un texto editado repartiendo el tiempo de la frase entre las palabras nuevas
    en proporción a su longitud. Si el número de palabras no cambia, conserva los tiempos."""
    tokens = new_text.split()
    c = caption.model_copy(deep=True)
    c.text = " ".join(tokens)
    c.edited = True
    if not tokens:
        c.words = []
        return c
    if len(tokens) == len(caption.words):
        c.words = [Word(start=w.start, end=w.end, text=t, prob=w.prob) for w, t in zip(caption.words, tokens)]
        return c
    total = sum(len(t) for t in tokens)
    span = caption.end - caption.start
    t = caption.start
    words = []
    for tok in tokens:
        d = span * len(tok) / total
        words.append(Word(start=round(t, 3), end=round(t + d, 3), text=tok))
        t += d
    c.words = words
    return c


@dataclass
class Cue:
    start: float
    end: float
    text: str
    words: list[tuple[float, float, str]] = field(default_factory=list)


def output_cues(captions: Sequence[Caption], tm: TimeMap) -> list[Cue]:
    """Traduce las frases al eje de salida. Las palabras cortadas desaparecen."""
    cues: list[Cue] = []
    for cap in sorted(captions, key=lambda c: c.start):
        if cap.words and " ".join(w.text for w in cap.words) != " ".join(cap.text.split()):
            cap = retime_text(cap, cap.text)  # texto editado sin recalcular palabras
        words = []
        for w in cap.words:
            iv = tm.map_interval(w.start, w.end)
            if iv:
                words.append((iv[0], iv[1], w.text))
        if cap.words:
            if not words:
                continue
            start, end = words[0][0], words[-1][1]
            text = " ".join(w[2] for w in words)
        else:
            iv = tm.map_interval(cap.start, cap.end)
            if not iv:
                continue
            start, end, text = iv[0], iv[1], cap.text
        if not text.strip():
            continue
        cues.append(Cue(start, max(end, start + 0.2), text, words))
    # sin superposición y con una duración mínima legible
    for i in range(len(cues) - 1):
        if cues[i].end > cues[i + 1].start:
            cues[i].end = max(cues[i].start + 0.05, cues[i + 1].start)
    return cues


def _srt_time(t: float) -> str:
    ms = int(round(max(0.0, t) * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def to_srt(cues: Sequence[Cue], uppercase: bool = False) -> str:
    lines = []
    for i, c in enumerate(cues, 1):
        text = c.text.upper() if uppercase else c.text
        lines += [str(i), f"{_srt_time(c.start)} --> {_srt_time(c.end)}", text, ""]
    return "\n".join(lines)


# ------------------------------------------------------------------ ASS

def _ass_time(t: float) -> str:
    cs = int(round(max(0.0, t) * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _ass_color(hex_color: str, alpha: int = 0) -> str:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", "\\N")


def style_scale(width: int, height: int) -> float:
    """El tamaño de fuente del estilo está definido para un lado corto de 1080 px."""
    return min(width, height) / 1080.0


def to_ass(cues: Sequence[Cue], style: SubtitleStyle, width: int, height: int) -> str:
    k = style_scale(width, height)
    size = max(8, round(style.font_size * k))
    outline = round(style.outline_width * k, 2)
    shadow = round(style.shadow * k, 2)
    margin = round(width * 0.08)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Main,{style.font_family},{size},{_ass_color(style.primary_color)},{_ass_color(style.highlight_color)},{_ass_color(style.outline_color)},{_ass_color(style.shadow_color, 0x60)},{-1 if style.bold else 0},0,0,0,100,100,0,0,1,{outline},{shadow},5,{margin},{margin},0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    x, y = width // 2, round(height * style.position_y)
    pos = f"{{\\pos({x},{y})}}"
    hl = _ass_color(style.highlight_color)
    events = []

    def fmt(t: str) -> str:
        return _escape(t.upper() if style.uppercase else t)

    for c in cues:
        if style.highlight_words and c.words:
            # un evento por palabra: la palabra activa en color de resaltado
            bounds = [c.start] + [w[0] for w in c.words[1:]] + [c.end]
            if c.words[0][0] > c.start + 0.01:
                events.append((c.start, c.words[0][0], pos + fmt(c.text)))
            for i, w in enumerate(c.words):
                s = max(c.start, w[0]) if i else max(c.start, min(w[0], bounds[1]))
                e = bounds[i + 1] if i + 1 < len(bounds) else c.end
                if e - s < 0.01:
                    continue
                parts = []
                for j, ww in enumerate(c.words):
                    t = fmt(ww[2])
                    parts.append(f"{{\\c{hl}}}{t}{{\\r}}" if j == i else t)
                events.append((s, e, pos + " ".join(parts)))
        else:
            events.append((c.start, c.end, pos + fmt(c.text)))

    body = "\n".join(f"Dialogue: 0,{_ass_time(s)},{_ass_time(e)},Main,,0,0,0,,{t}" for s, e, t in events)
    return header + body + "\n"


def strip_tags(ass_text: str) -> str:
    return re.sub(r"\{[^}]*\}", "", ass_text)
