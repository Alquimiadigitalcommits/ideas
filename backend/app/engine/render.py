"""Exportación final con FFmpeg.

Cadena de video:  cortes exactos (trim) → bloques (concat) → transiciones con solapamiento (xfade)
                  → reencuadre (estático o siguiendo el rostro) → efectos en el tiempo (fundidos,
                  flash, zoom, desenfoque, zoom alternado) → subtítulos (libass).
Cadena de audio:  limpieza (paso alto, reducción de ruido) → cortes (atrim, micro-fundidos anti-clic)
                  → cruces (acrossfade) → ganancia de voz → música con envolvente y ducking
                  → normalización → fundidos globales → duración exacta del video.

Las transiciones con solapamiento toman material del interior del corte (“handles”), así que la
duración total y la posición de cada unión no cambian: audio y subtítulos siguen sincronizados.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..schemas import ExportRequest, ProjectDoc, Transition
from . import audio as audio_analysis, ffmpeg, reframe, subtitles
from .timeline import TimeMap, edit_segments

PROFILES = {
    "tiktok": {"label": "TikTok", "aspect": "9:16", "short": 1080, "fps": 30, "audio_kbps": 192},
    "reels": {"label": "Instagram Reels", "aspect": "9:16", "short": 1080, "fps": 30, "audio_kbps": 192},
    "shorts": {"label": "YouTube Shorts", "aspect": "9:16", "short": 1080, "fps": 30, "audio_kbps": 192},
    "youtube": {"label": "YouTube", "aspect": "16:9", "short": 1080, "fps": 30, "audio_kbps": 256},
    "instagram_square": {"label": "Instagram cuadrado", "aspect": "1:1", "short": 1080, "fps": 30, "audio_kbps": 192},
}

OVERLAP_ONLY = {"dissolve", "slide"}          # sin material en el corte no se pueden hacer
XFADE_NAME = {"slide": {"left": "slideleft", "right": "slideright", "up": "slideup", "down": "slidedown"}}
DECLICK = 0.006


@dataclass
class Join:
    i: int                  # unión entre el segmento i y el i+1
    c: float                # tiempo de salida de la unión (relativo al render)
    gap: float              # material eliminado en la fuente (0 = división)
    trans: Optional[Transition]
    h: float = 0.0          # mitad del cruce con solapamiento
    half: float = 0.0       # mitad de la ventana del efecto
    skipped: bool = False


@dataclass
class RenderPlan:
    segments: list[tuple[float, float]]
    seg_index: list[int]           # índice del segmento en el plan completo (para zoom alternado)
    joins: list[Join]
    width: int
    height: int
    fps: float
    duration: float                # duración de este render
    total_duration: float          # duración de la exportación completa
    out_offset: float = 0.0        # inicio de la ventana en la salida completa
    src_offset: float = 0.0        # -ss aplicado a la fuente

    @property
    def lengths(self) -> list[float]:
        return [e - s for s, e in self.segments]


def _floor_frames(x: float, fps: float) -> float:
    return math.floor(max(0.0, x) * fps + 1e-6) / fps


def _owner(doc: ProjectDoc, e: float, s_next: float, fps: float):
    tol = 1.0 / fps
    if s_next - e > tol / 2:
        cands = [c for c in doc.cuts if c.enabled and c.kind != "split" and c.start < s_next and c.end > e]
    else:
        cands = [c for c in doc.cuts if c.enabled and c.kind == "split" and abs(c.start - e) <= tol]
    return min(cands, key=lambda c: c.start) if cands else None


def _build_joins(doc: ProjectDoc, segs: list[tuple[float, float]], fps: float) -> list[Join]:
    lengths = [e - s for s, e in segs]
    joins = []
    acc = 0.0
    for i in range(len(segs) - 1):
        acc += lengths[i]
        gap = max(0.0, segs[i + 1][0] - segs[i][1])
        owner = _owner(doc, segs[i][1], segs[i + 1][0], fps)
        t = owner.transition if owner is not None and owner.transition is not None else doc.transition_default
        trans = t if t.type != "none" and t.duration > 0 else None
        j = Join(i=i, c=acc, gap=gap, trans=trans)
        if trans:
            lim = min(lengths[i], lengths[i + 1]) / 2
            j.half = _floor_frames(min(trans.duration / 2, lim), fps)
            if gap > 0:
                j.h = _floor_frames(min(trans.duration / 2, gap / 2, lim), fps)
            if j.h < 1 / fps:
                j.h = 0.0
                if trans.type in OVERLAP_ONLY:
                    j.skipped = True
            if j.half < 1 / fps:
                j.skipped = True
        joins.append(j)
    return joins


def plan(doc: ProjectDoc, req: ExportRequest, window: Optional[tuple[float, float]] = None) -> RenderPlan:
    assert doc.media is not None
    prof = PROFILES.get(req.profile, PROFILES["tiktok"])
    fps = req.fps or prof["fps"]
    if req.width and req.height:
        w, h = req.width - req.width % 2, req.height - req.height % 2
    else:
        w, h = reframe.output_size(doc.format.aspect, prof["short"])
    full = edit_segments(doc.cuts, doc.media.duration, fps=fps)
    if not full:
        raise ValueError("Los cortes eliminan todo el video: no queda nada que exportar.")
    total = sum(e - s for s, e in full)
    segs, idx, out_offset = full, list(range(len(full))), 0.0
    if window is not None:
        w0, w1 = max(0.0, window[0]), min(total, window[1])
        if w1 - w0 < 1 / fps:
            raise ValueError("La ventana de previsualización está fuera del video.")
        segs, idx, acc = [], [], 0.0
        for k, (s, e) in enumerate(full):
            o0, o1 = acc, acc + (e - s)
            acc = o1
            a, b = max(o0, w0), min(o1, w1)
            if b - a >= 1 / fps:
                segs.append((s + (a - o0), s + (b - o0)))
                idx.append(k)
        out_offset = w0 if not segs else w0
    joins = _build_joins(doc, segs, fps)
    src_offset = max(0.0, segs[0][0] - 1.0) if window is not None else 0.0
    return RenderPlan(segs, idx, joins, w, h, fps, sum(e - s for s, e in segs), total, out_offset, src_offset)


def _ff_escape_path(p: Path) -> str:
    s = str(p).replace("\\", "/")
    return s.replace(":", "\\:").replace("'", "\\'").replace(",", "\\,").replace("[", "\\[").replace("]", "\\]")


def _bump(c: float, half: float) -> str:
    return f"max(0,1-abs(t-{c:.4f})/{half:.4f})"


# ------------------------------------------------------------------ reencuadre con seguimiento

def _track_expr(doc: ProjectDoc, rp: RenderPlan, cw: int) -> Optional[str]:
    m = doc.media
    tr = sorted(doc.format.track)
    if not (doc.format.track_enabled and tr and m and m.width > cw):
        return None
    span = m.width - cw

    def x_at(t: float) -> float:
        if t <= tr[0][0]:
            cx = tr[0][1]
        elif t >= tr[-1][0]:
            cx = tr[-1][1]
        else:
            k = next(i for i in range(1, len(tr)) if tr[i][0] >= t)
            (t0, c0, _), (t1, c1, _) = tr[k - 1], tr[k]
            cx = c0 + (c1 - c0) * (t - t0) / max(1e-6, t1 - t0)
        return min(span, max(0.0, cx * m.width - cw / 2))

    terms = []
    acc = 0.0
    for s, e in rp.segments:
        pts = [s] + [k[0] for k in tr if s < k[0] < e] + [e]
        for a, b in zip(pts, pts[1:]):
            oa, ob = acc + a - s, acc + b - s
            if ob - oa < 1e-4:
                continue
            xa, xb = x_at(a), x_at(b)
            if abs(xb - xa) < 0.5:
                terms.append(f"gte(t,{oa:.4f})*lt(t,{ob:.4f})*{xa:.1f}")
            else:
                terms.append(f"gte(t,{oa:.4f})*lt(t,{ob:.4f})*({xa:.1f}+{xb - xa:.2f}*(t-{oa:.4f})/{ob - oa:.4f})")
        acc += e - s
    terms.append(f"gte(t,{acc:.4f})*{x_at(rp.segments[-1][1]):.1f}")
    return "+".join(terms)


def _reframe(doc: ProjectDoc, rp: RenderPlan, inp: str, out: str) -> str:
    m = doc.media
    assert m is not None
    fmt = doc.format
    if fmt.mode == "crop":
        cw, ch, x, y = reframe.crop_box(m.width, m.height, fmt.aspect, fmt.offset_x, fmt.offset_y, fmt.zoom)
        xe = _track_expr(doc, rp, cw)
        xs = f"'{xe}'" if xe else str(x)
        return f"[{inp}]crop={cw}:{ch}:{xs}:{y},scale={rp.width}:{rp.height}:flags=lanczos,setsar=1[{out}]"
    return reframe.build_filter(inp, out, m.width, m.height, fmt, rp.width, rp.height)


# ------------------------------------------------------------------ efectos en el tiempo

def _effects(doc: ProjectDoc, rp: RenderPlan, inp: str, out_dir: Path, base: str) -> tuple[list[str], str]:
    parts: list[str] = []
    cur = inp
    black, white, zoom, blur = [], [], [], []
    for j in rp.joins:
        if not j.trans or j.skipped:
            continue
        k = max(0.0, min(1.0, j.trans.intensity))
        if j.trans.type == "fade":
            black.append(f"{k:.3f}*{_bump(j.c, j.half)}")
        elif j.trans.type == "flash":
            white.append(f"{k:.3f}*{_bump(j.c, j.half)}")
        elif j.trans.type == "zoom":
            zoom.append(f"{0.4 * k:.3f}*{_bump(j.c, j.half)}")
        elif j.trans.type == "blur":
            blur.append(j)
    a = doc.audio
    O, D = rp.out_offset, rp.total_duration
    if a.fade_in > 0 and O < a.fade_in:
        black.append(f"max(0,1-(t+{O:.4f})/{a.fade_in:.4f})")
    if a.fade_out > 0 and O + rp.duration > D - a.fade_out:
        black.append(f"max(0,1-({D:.4f}-t-{O:.4f})/{a.fade_out:.4f})")
    jz = doc.format.jump_zoom
    if jz > 0:
        acc = 0.0
        for (s, e), k in zip(rp.segments, rp.seg_index):
            if k % 2 == 1:
                zoom.append(f"{jz:.3f}*gte(t,{acc:.4f})*lt(t,{acc + e - s:.4f})")
            acc += e - s

    if zoom:
        z = "(1+" + "+".join(zoom) + ")"
        parts.append(f"[{cur}]scale=w='trunc({rp.width}*{z}/2)*2':h='trunc({rp.height}*{z}/2)*2':eval=frame,"
                     f"crop={rp.width}:{rp.height},setsar=1[fx_z]")
        cur = "fx_z"
    if blur:
        cmd = out_dir / f"{base}.blur.cmd"
        lines, windows = [], []
        smax = 22 * rp.height / 1080
        for j in blur:
            k = max(0.0, min(1.0, j.trans.intensity))  # type: ignore[union-attr]
            a0, a1 = j.c - j.half, j.c + j.half
            windows.append(f"between(t,{a0:.4f},{a1:.4f})")
            n = max(2, round(2 * j.half * rp.fps))
            for f in range(n + 1):
                t = a0 + (a1 - a0) * f / n
                sig = smax * k * max(0.0, 1 - abs(t - j.c) / j.half)
                lines.append(f"{t:.4f} gblur@fx sigma {sig:.2f};")
            lines.append(f"{a1 + 1 / rp.fps:.4f} gblur@fx sigma 0;")
        cmd.write_text("\n".join(lines), encoding="utf-8")
        parts.append(f"[{cur}]sendcmd=f='{_ff_escape_path(cmd)}',gblur@fx=sigma=0:enable='{'+'.join(windows)}'[fx_b]")
        cur = "fx_b"
    if black or white:
        kb = "(" + "+".join(black) + ")" if black else "0"
        kw = "(" + "+".join(white) + ")" if white else "0"
        tot = f"min(1,{kb}+{kw})"
        # eq: Y' = (Y-128)*contrast + 128 + 256*brightness. Con contrast = 1-k se lleva Y hacia el negro
        # de video (16) o el blanco (235) en proporción k: brightness = (16-128)/256*k ó (235-128)/256*k.
        parts.append(f"[{cur}]eq=eval=frame:contrast='1-{tot}':brightness='0.418*min(1,{kw})-0.4375*min(1,{kb})'"
                     f":saturation='1-{tot}'[fx_e]")
        cur = "fx_e"
    return parts, cur


# ------------------------------------------------------------------ grafo

def build_filter_script(doc: ProjectDoc, req: ExportRequest, rp: RenderPlan, ass_path: Optional[Path],
                        out_dir: Path, base: str, music_input: Optional[int], noise_floor: float = -50.0) -> str:
    m = doc.media
    assert m is not None
    n = len(rp.segments)
    off = rp.src_offset
    parts: list[str] = []
    joins = rp.joins
    ov = [j.h if j.trans and not j.skipped else 0.0 for j in joins]   # solapamiento por unión

    # bloques: se separan en las uniones con solapamiento
    blocks: list[list[int]] = [[0]]
    for i in range(n - 1):
        if ov[i] > 0:
            blocks.append([i + 1])
        else:
            blocks[-1].append(i + 1)

    def rng(i: int, first: bool, last: bool) -> tuple[float, float]:
        s, e = rp.segments[i]
        if first and i > 0:
            s -= ov[i - 1]
        if last and i < n - 1:
            e += ov[i]
        return s - off, e - off

    has_a = m.has_audio
    parts.append(f"[0:v]fps={rp.fps:g},format=yuv420p,setsar=1" + (f",split={n}" if n > 1 else "")
                 + "".join(f"[vs{i}]" for i in range(n)))
    if has_a:
        clean = "aresample=48000:async=1,aformat=sample_fmts=fltp:channel_layouts=stereo"
        if doc.audio.highpass:
            clean += ",highpass=f=80"
        if doc.audio.denoise:
            nr = 6 + 24 * max(0.0, min(1.0, doc.audio.denoise_strength))
            clean += f",afftdn=nr={nr:.1f}:nf={noise_floor:.1f}"
        parts.append(f"[0:a]{clean}" + (f",asplit={n}" if n > 1 else "") + "".join(f"[as{i}]" for i in range(n)))

    for b, blk in enumerate(blocks):
        for pos, i in enumerate(blk):
            s, e = rng(i, pos == 0, pos == len(blk) - 1)
            parts.append(f"[vs{i}]trim=start={s:.6f}:end={e:.6f},setpts=PTS-STARTPTS[v{i}]")
            if has_a:
                fades = ""
                if pos > 0 and joins[i - 1].gap > 0:
                    fades += f",afade=t=in:st=0:d={DECLICK}"
                if pos < len(blk) - 1 and joins[i].gap > 0:
                    fades += f",afade=t=out:st={e - s - DECLICK:.6f}:d={DECLICK}"
                parts.append(f"[as{i}]atrim=start={s:.6f}:end={e:.6f},asetpts=PTS-STARTPTS{fades}[a{i}]")
        if len(blk) == 1:
            parts.append(f"[v{blk[0]}]settb=AVTB[bv{b}]")
            if has_a:
                parts.append(f"[a{blk[0]}]anull[ba{b}]")
        else:
            if has_a:
                parts.append("".join(f"[v{i}][a{i}]" for i in blk) + f"concat=n={len(blk)}:v=1:a=1[bc{b}][ba{b}]")
            else:
                parts.append("".join(f"[v{i}]" for i in blk) + f"concat=n={len(blk)}:v=1:a=0[bc{b}]")
            parts.append(f"[bc{b}]settb=AVTB[bv{b}]")   # xfade exige la misma base de tiempo en ambas entradas

    vcur, acur = "bv0", "ba0"
    for b in range(1, len(blocks)):
        j = joins[blocks[b][0] - 1]
        t = j.trans
        assert t is not None
        name = XFADE_NAME.get(t.type, {}).get(t.direction, "fade")
        parts.append(f"[{vcur}][bv{b}]xfade=transition={name}:duration={2 * j.h:.6f}:offset={j.c - j.h:.6f}[xv{b}]")
        vcur = f"xv{b}"
        if has_a:
            parts.append(f"[{acur}][ba{b}]acrossfade=d={2 * j.h:.6f}:c1=tri:c2=tri[xa{b}]")
            acur = f"xa{b}"

    parts.append(_reframe(doc, rp, vcur, "vr"))
    fx, last = _effects(doc, rp, "vr", out_dir, base)
    parts += fx
    if ass_path is not None:
        parts.append(f"[{last}]subtitles=filename='{_ff_escape_path(ass_path)}'[vsub]")
        last = "vsub"
    parts.append(f"[{last}]format=yuv420p[vout]")

    # ---------------- audio
    a = doc.audio
    D, O, Dt = rp.duration, rp.out_offset, rp.total_duration
    voice = None
    if has_a:
        voice = acur
        if a.voice_gain_db:
            parts.append(f"[{voice}]volume={a.voice_gain_db:.2f}dB[vg]")
            voice = "vg"
    mix = voice
    mus = a.music
    if music_input is not None and mus is not None:
        env = [f"pow(10,{mus.volume_db:.2f}/20)"]
        if mus.fade_in > 0:
            env.append(f"min(1,(t+{O:.4f})/{mus.fade_in:.4f})")
        if mus.fade_out > 0:
            env.append(f"min(1,max(0,({Dt:.4f}-t-{O:.4f})/{mus.fade_out:.4f}))")
        parts.append(f"[{music_input}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                     f"atrim=start={mus.start_offset + O if not mus.loop else 0:.6f},asetpts=PTS-STARTPTS,"
                     f"atrim=duration={D:.6f},volume='{'*'.join(env)}':eval=frame[mu]")
        if voice is not None and mus.ducking:
            ratio = 2 + 18 * max(0.0, min(1.0, mus.ducking_amount))
            parts.append(f"[{voice}]asplit=2[vm][vsc]")
            parts.append(f"[mu][vsc]sidechaincompress=threshold=0.02:ratio={ratio:.1f}:attack=15:release=350:makeup=1[mud]")
            parts.append("[vm][mud]amix=inputs=2:duration=first:normalize=0:dropout_transition=0[mx]")
            mix = "mx"
        elif voice is not None:
            parts.append(f"[{voice}][mu]amix=inputs=2:duration=first:normalize=0:dropout_transition=0[mx]")
            mix = "mx"
        else:
            mix = "mu"
    if mix is not None:
        chain = []
        if req.normalize_audio:
            chain.append("loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000")
        # marcas de tiempo continuas y duración exacta del video (ver test de regresión)
        chain.append("asetpts=N/SR/TB")
        env = []
        if a.fade_in > 0 and O < a.fade_in:
            env.append(f"min(1,(t+{O:.4f})/{a.fade_in:.4f})")
        if a.fade_out > 0 and O + D > Dt - a.fade_out:
            env.append(f"min(1,max(0,({Dt:.4f}-t-{O:.4f})/{a.fade_out:.4f}))")
        if env:
            chain.append(f"volume='{'*'.join(env)}':eval=frame")
        chain.append(f"apad=whole_dur={D:.6f},atrim=end={D:.6f}")
        parts.append(f"[{mix}]" + ",".join(chain) + "[aout]")
    return ";\n".join(parts)


def export(doc: ProjectDoc, req: ExportRequest, out_dir: Path, base_name: str, *,
           window: Optional[tuple[float, float]] = None, on_progress=None, cancel_event=None) -> dict:
    assert doc.media is not None
    out_dir.mkdir(parents=True, exist_ok=True)
    rp = plan(doc, req, window)
    # Subtítulos en el eje de este render (si es una ventana, relativo a su inicio)
    tm = TimeMap(rp.segments)
    cues = subtitles.output_cues(doc.captions, tm)

    applied = [j for j in rp.joins if j.trans and not j.skipped]
    result: dict = {"width": rp.width, "height": rp.height, "fps": rp.fps,
                    "duration": round(rp.duration, 3), "segments": len(rp.segments), "files": [],
                    "transitions": len(applied), "transitions_skipped": sum(1 for j in rp.joins if j.skipped)}

    ass_path = None
    if req.burn_subtitles and cues:
        ass_path = out_dir / f"{base_name}.ass"
        ass_path.write_text(subtitles.to_ass(cues, doc.subtitle_style, rp.width, rp.height), encoding="utf-8")
    if req.write_srt and cues:
        srt = out_dir / f"{base_name}.srt"
        srt.write_text(subtitles.to_srt(cues, doc.subtitle_style.uppercase), encoding="utf-8")
        result["files"].append(srt.name)

    mus = doc.audio.music
    music_ok = mus is not None and os.path.isfile(mus.path)
    music_input = 1 if music_ok else None
    script = out_dir / f"{base_name}.filtergraph.txt"
    nf = -50.0
    if doc.audio.denoise and doc.media.has_audio:
        nf = audio_analysis.noise_floor_db(doc.media, cancel_event=cancel_event)
        result["noise_floor_db"] = round(nf, 1)
    script.write_text(build_filter_script(doc, req, rp, ass_path, out_dir, base_name, music_input, nf),
                      encoding="utf-8")

    mp4 = out_dir / f"{base_name}.mp4"
    tmp = out_dir / f"{base_name}.part.mp4"
    prof = PROFILES.get(req.profile, PROFILES["tiktok"])
    args: list[str] = []
    if rp.src_offset > 0:
        args += ["-ss", f"{rp.src_offset:.6f}"]
    args += ["-i", doc.media.source_path]
    if music_ok:
        assert mus is not None
        if mus.loop:
            args += ["-stream_loop", "-1"]
            if mus.start_offset + rp.out_offset > 0:
                args += ["-ss", f"{(mus.start_offset + rp.out_offset) % max(mus.duration, 0.01):.6f}"]
        args += ["-i", mus.path]
    has_audio_out = doc.media.has_audio or music_ok
    if not has_audio_out:
        args += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
    args += ["-filter_complex_script", str(script), "-map", "[vout]"]
    args += ["-map", "[aout]"] if has_audio_out else ["-map", "1:a", "-shortest"]
    args += ["-c:v", "libx264", "-preset", req.preset, "-crf", str(req.crf), "-profile:v", "high",
             "-pix_fmt", "yuv420p", "-r", f"{rp.fps:g}",
             "-c:a", "aac", "-b:a", f"{prof['audio_kbps']}k", "-ar", "48000", "-ac", "2",
             "-movflags", "+faststart", "-f", "mp4", str(tmp)]
    try:
        ffmpeg.run(args, duration=rp.duration, on_progress=on_progress, cancel_event=cancel_event)
    except BaseException:
        if tmp.exists():
            tmp.unlink()
        raise
    os.replace(tmp, mp4)
    result["files"].insert(0, mp4.name)
    result["video"] = mp4.name
    result["cues"] = len(cues)
    return result
