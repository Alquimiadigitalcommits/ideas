"""Exportación final con FFmpeg: cortes exactos + reencuadre + subtítulos + audio."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..schemas import ExportRequest, ProjectDoc
from . import ffmpeg, reframe, subtitles
from .timeline import TimeMap, keep_segments

PROFILES = {
    "tiktok": {"label": "TikTok", "aspect": "9:16", "short": 1080, "fps": 30, "audio_kbps": 192},
    "reels": {"label": "Instagram Reels", "aspect": "9:16", "short": 1080, "fps": 30, "audio_kbps": 192},
    "shorts": {"label": "YouTube Shorts", "aspect": "9:16", "short": 1080, "fps": 30, "audio_kbps": 192},
    "youtube": {"label": "YouTube", "aspect": "16:9", "short": 1080, "fps": 30, "audio_kbps": 256},
    "instagram_square": {"label": "Instagram cuadrado", "aspect": "1:1", "short": 1080, "fps": 30, "audio_kbps": 192},
}


@dataclass
class RenderPlan:
    segments: list[tuple[float, float]]
    width: int
    height: int
    fps: float
    duration: float


def plan(doc: ProjectDoc, req: ExportRequest) -> RenderPlan:
    assert doc.media is not None
    prof = PROFILES.get(req.profile, PROFILES["tiktok"])
    fps = req.fps or prof["fps"]
    if req.width and req.height:
        w, h = req.width - req.width % 2, req.height - req.height % 2
    else:
        w, h = reframe.output_size(doc.format.aspect, prof["short"])
    segs = keep_segments(doc.cuts, doc.media.duration, fps=fps)
    if not segs:
        raise ValueError("Los cortes eliminan todo el video: no queda nada que exportar.")
    return RenderPlan(segs, w, h, fps, sum(e - s for s, e in segs))


def _ff_escape_path(p: Path) -> str:
    # escape para usar una ruta dentro de un filtro (subtitles=...)
    s = str(p).replace("\\", "/")
    return s.replace(":", "\\:").replace("'", "\\'").replace(",", "\\,").replace("[", "\\[").replace("]", "\\]")


def build_filter_script(doc: ProjectDoc, req: ExportRequest, rp: RenderPlan, ass_path: Optional[Path]) -> str:
    m = doc.media
    assert m is not None
    n = len(rp.segments)
    parts: list[str] = []

    if n == 1:
        parts.append(f"[0:v]fps={rp.fps:g}[vs0]")
    else:
        parts.append(f"[0:v]fps={rp.fps:g},split={n}" + "".join(f"[vs{i}]" for i in range(n)))
    for i, (s, e) in enumerate(rp.segments):
        parts.append(f"[vs{i}]trim=start={s:.6f}:end={e:.6f},setpts=PTS-STARTPTS[v{i}]")

    if m.has_audio:
        head = "[0:a]aresample=48000:async=1,aformat=sample_fmts=fltp:channel_layouts=stereo"
        parts.append(head + ("[as0]" if n == 1 else f",asplit={n}" + "".join(f"[as{i}]" for i in range(n))))
        for i, (s, e) in enumerate(rp.segments):
            parts.append(f"[as{i}]atrim=start={s:.6f}:end={e:.6f},asetpts=PTS-STARTPTS[a{i}]")
        parts.append("".join(f"[v{i}][a{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[vc][ac]")
    else:
        parts.append("".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[vc]")

    parts.append(reframe.build_filter("vc", "vr", m.width, m.height, doc.format, rp.width, rp.height))
    last = "vr"
    if ass_path is not None:
        parts.append(f"[{last}]subtitles=filename='{_ff_escape_path(ass_path)}'[vsub]")
        last = "vsub"
    parts.append(f"[{last}]format=yuv420p[vout]")

    if m.has_audio:
        if req.normalize_audio:
            parts.append("[ac]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[aout]")
        else:
            parts.append("[ac]anull[aout]")
    return ";\n".join(parts)


def export(doc: ProjectDoc, req: ExportRequest, out_dir: Path, base_name: str, *,
           on_progress=None, cancel_event=None) -> dict:
    assert doc.media is not None
    out_dir.mkdir(parents=True, exist_ok=True)
    rp = plan(doc, req)
    tm = TimeMap(rp.segments)
    cues = subtitles.output_cues(doc.captions, tm)

    result: dict = {"width": rp.width, "height": rp.height, "fps": rp.fps,
                    "duration": round(rp.duration, 3), "segments": len(rp.segments), "files": []}

    ass_path = None
    if req.burn_subtitles and cues:
        ass_path = out_dir / f"{base_name}.ass"
        ass_path.write_text(subtitles.to_ass(cues, doc.subtitle_style, rp.width, rp.height), encoding="utf-8")
    if req.write_srt and cues:
        srt = out_dir / f"{base_name}.srt"
        srt.write_text(subtitles.to_srt(cues, doc.subtitle_style.uppercase), encoding="utf-8")
        result["files"].append(srt.name)

    script = out_dir / f"{base_name}.filtergraph.txt"
    script.write_text(build_filter_script(doc, req, rp, ass_path), encoding="utf-8")

    mp4 = out_dir / f"{base_name}.mp4"
    tmp = out_dir / f"{base_name}.part.mp4"
    prof = PROFILES.get(req.profile, PROFILES["tiktok"])
    args = ["-i", doc.media.source_path]
    if not doc.media.has_audio:
        args += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
    args += ["-filter_complex_script", str(script), "-map", "[vout]"]
    args += ["-map", "[aout]"] if doc.media.has_audio else ["-map", "1:a", "-shortest"]
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
