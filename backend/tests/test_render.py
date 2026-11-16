import subprocess

import pytest

from app.engine import media, render
from app.engine.timeline import keep_segments
from app.schemas import Caption, Cut, ExportRequest, FormatSettings, ProjectDoc, Word
from tests.conftest import stream_durations


def _doc(path, **kw):
    return ProjectDoc(media=media.probe(str(path)), **kw)


def test_export_vertical_with_cuts_is_in_sync(tone_video, tmp_path):
    cuts = [Cut(id="a", start=2.0, end=4.0), Cut(id="b", start=6.0, end=6.5),
            Cut(id="c", start=7.0, end=7.5, enabled=False)]  # recuperado: no se corta
    caps = [Caption(id="1", start=0.2, end=1.8, text="antes del corte",
                    words=[Word(start=0.2, end=0.8, text="antes"), Word(start=0.8, end=1.2, text="del"),
                           Word(start=1.2, end=1.8, text="corte")]),
            Caption(id="2", start=4.5, end=5.5, text="después", words=[Word(start=4.5, end=5.5, text="después")])]
    doc = _doc(tone_video, cuts=cuts, captions=caps, format=FormatSettings(aspect="9:16", mode="crop"))
    req = ExportRequest(profile="tiktok", preset="ultrafast", crf=30)
    prog = []
    res = render.export(doc, req, tmp_path, "out", on_progress=prog.append)

    expected = 8 - 2 - 0.5
    assert res["duration"] == pytest.approx(expected, abs=0.05)
    d = stream_durations(tmp_path / "out.mp4")
    assert (int(d["video"]["width"]), int(d["video"]["height"])) == (1080, 1920)
    v, a = float(d["video"]["duration"]), float(d["audio"]["duration"])
    assert v == pytest.approx(expected, abs=0.05)
    assert abs(v - a) < 0.05, f"audio/video desincronizados: v={v} a={a}"
    assert prog and max(prog) > 0.8

    # la salida no debe contener los silencios eliminados: tono continuo salvo en el borde
    srt = (tmp_path / "out.srt").read_text()
    assert "00:00:02,500 --> 00:00:03,500" in srt  # "después": 4.5 s fuente - 2 s cortados
    assert (tmp_path / "out.ass").exists()


def test_export_audio_really_cut(tone_video, tmp_path):
    """Tras quitar los silencios, silencedetect no debe encontrar silencios en la salida."""
    doc = _doc(tone_video, cuts=[Cut(id="a", start=2.0, end=4.0), Cut(id="b", start=6.0, end=6.5)],
               format=FormatSettings(aspect="16:9"))
    render.export(doc, ExportRequest(profile="youtube", preset="ultrafast", crf=32, write_srt=False),
                  tmp_path, "cut")
    p = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(tmp_path / "cut.mp4"), "-af",
                        "silencedetect=n=-35dB:d=0.2", "-f", "null", "-"], capture_output=True, text=True)
    assert "silence_start" not in p.stderr


def test_export_blur_square_and_normalize(tone_video, tmp_path):
    doc = _doc(tone_video, format=FormatSettings(aspect="1:1", mode="blur"))
    res = render.export(doc, ExportRequest(profile="instagram_square", preset="ultrafast", crf=32,
                                           normalize_audio=True, fps=24), tmp_path, "sq")
    d = stream_durations(tmp_path / "sq.mp4")
    assert (int(d["video"]["width"]), int(d["video"]["height"])) == (1080, 1080)
    assert res["fps"] == 24


def test_export_without_audio_adds_silent_track(silent_video, tmp_path):
    doc = _doc(silent_video, format=FormatSettings(aspect="16:9", mode="fit"))
    render.export(doc, ExportRequest(profile="youtube", preset="ultrafast", crf=32, width=640, height=360),
                  tmp_path, "na")
    d = stream_durations(tmp_path / "na.mp4")
    assert "audio" in d and float(d["video"]["duration"]) == pytest.approx(3, abs=0.1)


def test_export_rejects_everything_cut(tone_video):
    doc = _doc(tone_video, cuts=[Cut(id="a", start=0, end=8)])
    with pytest.raises(ValueError):
        render.plan(doc, ExportRequest())


def test_many_segments(tone_video, tmp_path):
    """40 cortes pequeños: el grafo por archivo debe soportarlo y mantener la sincronía."""
    cuts = [Cut(id=str(i), start=i * 0.2 + 0.05, end=i * 0.2 + 0.1) for i in range(40)]
    doc = _doc(tone_video, cuts=cuts, format=FormatSettings(aspect="16:9"))
    req = ExportRequest(profile="youtube", preset="ultrafast", crf=34, width=640, height=360, write_srt=False)
    res = render.export(doc, req, tmp_path, "many")
    expected = sum(e - s for s, e in keep_segments(cuts, doc.media.duration, fps=30))
    d = stream_durations(tmp_path / "many.mp4")
    v, a = float(d["video"]["duration"]), float(d["audio"]["duration"])
    assert v == pytest.approx(expected, abs=0.07)
    assert abs(v - a) < 0.07
    assert res["segments"] == 41
