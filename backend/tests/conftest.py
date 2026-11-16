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
