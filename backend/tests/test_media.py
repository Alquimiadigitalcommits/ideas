import json

import pytest

from app.engine import media, silence
from tests.conftest import stream_durations


def test_probe(tone_video):
    info = media.probe(str(tone_video))
    assert (info.width, info.height) == (640, 360)
    assert info.fps == 25
    assert info.duration == pytest.approx(8, abs=0.1)
    assert info.has_audio and info.video_codec == "h264"


def test_probe_rejects_bad_extension(tmp_path):
    f = tmp_path / "x.avi"
    f.write_bytes(b"0")
    with pytest.raises(ValueError):
        media.probe(str(f))


def test_probe_rejects_corrupt_file(tmp_path):
    f = tmp_path / "x.mp4"
    f.write_bytes(b"esto no es un video")
    with pytest.raises(Exception):
        media.probe(str(f))


def test_probe_no_audio(silent_video):
    info = media.probe(str(silent_video))
    assert not info.has_audio and info.fps == 24


def test_proxy_waveform_thumbs(tone_video, tmp_path):
    info = media.probe(str(tone_video))
    progress = []
    proxy = media.make_proxy(info, tmp_path, on_progress=progress.append)
    d = stream_durations(proxy)
    assert float(d["video"]["duration"]) == pytest.approx(8, abs=0.1)
    assert int(d["video"]["height"]) == 360  # nunca agranda
    assert progress and progress[-1] > 0.9

    wf = json.loads(media.make_waveform(info, tmp_path).read_text())
    assert len(wf["peaks"]) == pytest.approx(8 * wf["pps"], abs=2)
    # el silencio 2-4 s debe verse plano
    assert max(wf["peaks"][110:190]) < 0.01 and max(wf["peaks"][10:90]) > 0.5

    media.make_thumbnails(info, tmp_path, count=8)
    meta = json.loads((tmp_path / "thumbs.json").read_text())
    assert meta["count"] == 8 and (tmp_path / "thumbs.jpg").stat().st_size > 1000


def test_silencedetect_tone(tone_video):
    info = media.probe(str(tone_video))
    sil = silence.detect_silences(info, -35, 0.4)
    assert len(sil) == 2
    assert sil[0] == pytest.approx((2.0, 4.0), abs=0.05)
    assert sil[1] == pytest.approx((6.0, 6.5), abs=0.05)


def test_silencedetect_speech(speech_video):
    info = media.probe(str(speech_video))
    sil = silence.detect_silences(info, -35, 0.6)
    long_pauses = [s for s in sil if s[1] - s[0] > 1.4]
    # inicio (1.0 s), 3 pausas largas conocidas (1.8, 2.2, 1.5 s) y final (1.2 s)
    assert len(long_pauses) >= 3
