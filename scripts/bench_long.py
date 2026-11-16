"""Mide cada etapa del motor con un video largo. Uso: python scripts/bench_long.py video.mp4 carpeta_salida"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.engine import autoedit, media, render, scenes, silence, subtitles, transcribe  # noqa: E402
from app.schemas import AutoEditSettings, ExportRequest, FormatSettings, ProjectDoc, Transition  # noqa: E402

src, out = sys.argv[1], Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
times = {}


def step(name, fn):
    t = time.time()
    r = fn()
    times[name] = round(time.time() - t, 1)
    print(f"{name}: {times[name]} s", flush=True)
    return r


info = step("probe", lambda: media.probe(src))
print(f"duración {info.duration:.0f} s, {info.width}x{info.height}, {info.size_bytes / 1e6:.0f} MB")
step("miniaturas", lambda: media.make_thumbnails(info, out))
step("forma de onda", lambda: media.make_waveform(info, out))
step("proxy 720p", lambda: media.make_proxy(info, out))
wav = step("extraer audio 16k", lambda: media.extract_audio_wav(info, out))
words, lang = step("whisper base", lambda: transcribe.transcribe(str(wav), info.duration, "base", "es"))
sil = step("silencios", lambda: silence.detect_silences(info, -35, 0.6))
cuts = step("reglas de corte", lambda: autoedit.compute_cuts(sil, words, info.duration, AutoEditSettings()))
step("escenas (proxy)", lambda: scenes.detect_scenes(str(out / "proxy.mp4"), info.duration))
caps = subtitles.build_captions(words, 4, 28)
doc = ProjectDoc(media=info, cuts=cuts, captions=caps, format=FormatSettings(aspect="9:16"),
                 transition_default=Transition(type="fade", duration=0.3, intensity=0.6))
res = step("export 1080x1920 veryfast", lambda: render.export(
    doc, ExportRequest(profile="tiktok", preset="veryfast", crf=23, normalize_audio=True), out, "long"))
print(json.dumps({"words": len(words), "cuts": len(cuts), "export": {k: res[k] for k in
      ("duration", "segments", "transitions", "cues")}, "times": times}, ensure_ascii=False))
