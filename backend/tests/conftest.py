import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

# Workspace aislado ANTES de importar la app
_WS = Path(tempfile.mkdtemp(prefix="sve-test-ws-"))
os.environ["SVE_WORKSPACE"] = str(_WS)

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def media_dir():
    d = Path(tempfile.mkdtemp(prefix="sve-test-media-"))
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture(scope="session")
def speech_video(media_dir) -> Path:
    """Video 1280x720 30 fps con voz y pausas conocidas (requiere espeak-ng)."""
    if not shutil.which("espeak-ng"):
        pytest.skip("espeak-ng no instalado")
    out = media_dir / "speech.mp4"
    subprocess.run([str(ROOT / "scripts" / "make_test_video.sh"), str(out)], check=True, capture_output=True)
    return out


@pytest.fixture(scope="session")
def tone_video(media_dir) -> Path:
    """Video 640x360 25 fps: tono 0-2 s, silencio 2-4 s, tono 4-6 s, silencio 6-6.5, tono 6.5-8."""
    out = media_dir / "tone.mov"
    expr = "if(between(t,2,4)+between(t,6,6.5),0,0.5*sin(2*PI*440*t))"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=25",
                    "-f", "lavfi", "-i", f"aevalsrc='{expr}':s=48000:c=stereo", "-t", "8",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", str(out)],
                   check=True)
    return out


@pytest.fixture(scope="session")
def silent_video(media_dir) -> Path:
    """MKV sin pista de audio."""
    out = media_dir / "noaudio.mkv"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=24",
                    "-t", "3", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(out)],
                   check=True)
    return out


def stream_durations(path: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration,width,height",
                          "-of", "json", str(path)], capture_output=True, text=True, check=True).stdout
    import json
    res = {}
    for s in json.loads(out)["streams"]:
        res[s["codec_type"]] = s
    return res


@pytest.fixture(scope="session")
def scene_video(media_dir) -> Path:
    """3 escenas: rojo 0-2 s, patrón 2-4.5 s, azul 4.5-6 s; con tono continuo."""
    out = media_dir / "scenes.mp4"
    subprocess.run([
        "ffmpeg", "-v", "error", "-y",
        "-f", "lavfi", "-i", "color=c=red:s=640x360:r=25:d=2",
        "-f", "lavfi", "-i", "testsrc=s=640x360:r=25:d=2.5",
        "-f", "lavfi", "-i", "color=c=blue:s=640x360:r=25:d=1.5",
        "-f", "lavfi", "-i", "sine=f=440:r=48000:d=6",
        "-filter_complex", "[0][1][2]concat=n=3:v=1:a=0,format=yuv420p[v]",
        "-map", "[v]", "-map", "3:a", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(out)], check=True)
    return out


@pytest.fixture(scope="session")
def face_video(media_dir) -> Path:
    """Rostro real (foto de scikit-image) que cruza un cuadro de 1280x720 de izquierda a derecha en 8 s."""
    skimage_data = pytest.importorskip("skimage.data")
    import cv2
    img = media_dir / "astronaut.png"
    cv2.imwrite(str(img), cv2.cvtColor(skimage_data.astronaut(), cv2.COLOR_RGB2BGR))
    out = media_dir / "face.mp4"
    # imagen 360x360 (rostro centrado en x≈0.44 de la imagen); x del overlay: 40 → 880
    subprocess.run([
        "ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=gray:s=1280x720:r=25:d=8",
        "-loop", "1", "-i", str(img), "-f", "lavfi", "-i", "sine=f=300:r=48000:d=8",
        "-filter_complex", "[1]scale=360:360[f];[0][f]overlay=x='40+105*t':y=180:shortest=1,format=yuv420p[v]",
        "-map", "[v]", "-map", "2:a", "-t", "8", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(out)],
        check=True)
    return out


@pytest.fixture(scope="session")
def music_file(media_dir) -> Path:
    out = media_dir / "music.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=3000:r=48000:d=5",
                    "-af", "volume=0.5", "-ac", "2", str(out)], check=True)
    return out


@pytest.fixture(scope="session")
def white_video(media_dir) -> Path:
    out = media_dir / "white.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=white:s=320x180:r=25:d=6",
                    "-f", "lavfi", "-i", "sine=f=440:r=48000:d=6", "-c:v", "libx264", "-preset", "ultrafast",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out)], check=True)
    return out


def frame_luma(path: Path, t: float) -> float:
    """Luminancia media (0-255) del fotograma en t."""
    out = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-frames:v", "1",
                          "-vf", f"trim=start={t - 0.001},signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-",
                          "-f", "null", "-"],
                         capture_output=True, text=True).stdout
    import re
    m = re.findall(r"YAVG=([\d.]+)", out)
    return float(m[0]) if m else -1   # el primer fotograma tras el recorte (el filtro procesa algunos más)


def band_rms_db(path: Path, start: float, dur: float, freq: int) -> float:
    """Nivel RMS (dB) en una banda estrecha alrededor de `freq` dentro de [start, start+dur]."""
    out = subprocess.run(["ffmpeg", "-v", "info", "-ss", f"{start}", "-t", f"{dur}", "-i", str(path),
                          "-af", f"bandpass=f={freq}:width_type=q:w=8,astats=metadata=0:reset=0",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    import re
    vals = re.findall(r"RMS level dB:\s*(-?[\d.]+|-inf)", out)
    v = vals[-1] if vals else "-inf"
    return -120.0 if v == "-inf" else float(v)
