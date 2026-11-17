"""Autoverificación: `python -m app.selfcheck`. La ejecuta el instalador al terminar.

Prueba de verdad cada pieza que necesitan los subtítulos y la edición automática, y explica en lenguaje
simple qué falta. Código de salida 0 = todo bien.
"""
from __future__ import annotations

import math
import struct
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

from . import config

OK, FAIL, WARN = "[OK]", "[FALLA]", "[AVISO]"


def line(tag: str, msg: str) -> None:
    print(f"{tag:8s} {msg}", flush=True)


def check_ffmpeg() -> bool:
    try:
        out = subprocess.run([config.FFMPEG, "-hide_banner", "-filters"], capture_output=True, text=True).stdout
        enc = subprocess.run([config.FFMPEG, "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
    except FileNotFoundError:
        line(FAIL, "No se encontró FFmpeg. Vuelve a ejecutar el instalador.")
        return False
    ok = True
    for name, txt, needle in (("subtítulos (libass)", out, " subtitles "), ("video H.264 (libx264)", enc, "libx264")):
        if needle in txt:
            line(OK, f"FFmpeg tiene {name}")
        else:
            line(FAIL, f"Este FFmpeg no tiene {name}. Instala la versión completa (winget install Gyan.FFmpeg).")
            ok = False
    return ok


def check_burn(tmp: Path) -> bool:
    """Graba un subtítulo con una fuente incluida y comprueba que aparezcan píxeles de texto."""
    from .engine import render, subtitles
    from .engine.timeline import TimeMap
    from .schemas import Caption, SubtitleStyle
    cues = subtitles.output_cues([Caption(id="1", start=0, end=1, text="PRUEBA", words=[])], TimeMap([(0, 1)]))
    ass = tmp / "prueba.ass"
    ass.write_text(subtitles.to_ass(cues, SubtitleStyle(font_family="Outfit", position_y=0.5,
                                                         highlight_words=False), 320, 180), encoding="utf-8")
    png = tmp / "prueba.png"
    vf = f"subtitles=filename='{render._ff_escape_path(ass)}':fontsdir='{render._ff_escape_path(config.FONTS_DIR)}'"
    r = subprocess.run([config.FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "color=black:s=320x180:d=1",
                        "-vf", f"{vf},signalstats,metadata=print:key=lavfi.signalstats.YMAX:file=-",
                        "-frames:v", "1", "-f", "null", "-"], capture_output=True, text=True)
    ymax = [float(x.split("=")[1]) for x in r.stdout.split() if x.startswith("lavfi.signalstats.YMAX=")]
    if r.returncode == 0 and ymax and ymax[0] > 200:
        line(OK, "Los subtítulos se graban en el video (fuentes incluidas)")
        return True
    line(FAIL, f"No se pudieron grabar subtítulos en el video: {r.stderr.strip()[-300:] or 'sin texto visible'}")
    return False


def check_whisper(tmp: Path, model: str) -> bool:
    from .engine import transcribe
    err = transcribe.import_error()
    if err:
        line(FAIL, err)
        return False
    line(OK, "La transcripción carga correctamente")
    t = time.time()
    try:
        transcribe.get_model(model)
    except Exception as e:  # noqa: BLE001
        line(FAIL, str(e))
        return False
    line(OK, f"Modelo de transcripción '{model}' listo ({time.time() - t:.0f} s)")
    wav = tmp / "tono.wav"
    with wave.open(str(wav), "wb") as w:   # 2 s: tono + silencio (prueba todo el flujo, incluido el filtro de voz)
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"".join(struct.pack("<h", int(3000 * math.sin(2 * math.pi * 220 * i / 16000)) if i < 16000 else 0)
                               for i in range(32000)))
    try:
        t = time.time()
        transcribe.transcribe(str(wav), 2.0, model, "es")
        line(OK, f"Transcripción de prueba completada ({time.time() - t:.1f} s)")
        return True
    except Exception as e:  # noqa: BLE001
        line(FAIL, transcribe.explain(e))
        return False


def main() -> int:
    from .engine import hardware
    hw = hardware.profile()
    print("\nSmart Video Editor - verificación\n")
    line(OK, f"Equipo: {hw['threads']} hilos, {hw['ram_gb']} GB de RAM, AVX2: {'sí' if hw['avx2'] else 'no'} "
             f"-> perfil {hw['tier']} (transcripción '{hw['whisper_model']}', exportación '{hw['export_preset']}')")
    if hw["ram_gb"] < 6:
        line(WARN, "Menos de 6 GB de RAM: cierra otros programas al exportar.")
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        ok = check_ffmpeg()
        ok = check_burn(tmp) and ok
        ok = check_whisper(tmp, hw["whisper_model"]) and ok
    print("\n" + ("Todo listo." if ok else "Hay problemas: revisa las líneas [FALLA] de arriba.") + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
