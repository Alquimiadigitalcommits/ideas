"""Etapas 2 a 5: divisiones, animaciones, transiciones, escenas, rostro, audio y música."""
import pytest

from app.engine import facetrack, media, render, scenes, subtitles
from app.engine.timeline import TimeMap, edit_segments
from app.schemas import (AudioSettings, Caption, Cut, ExportRequest, FormatSettings, MusicTrack, ProjectDoc,
                         SubtitleStyle, Transition, Word)
from tests.conftest import band_rms_db, frame_luma, stream_durations

FAST = dict(preset="ultrafast", crf=32, write_srt=False)


def doc_for(path, **kw):
    return ProjectDoc(media=media.probe(str(path)), **kw)


def check_sync(path, expected):
    d = stream_durations(path)
    v, a = float(d["video"]["duration"]), float(d["audio"]["duration"])
    assert v == pytest.approx(expected, abs=0.045), (v, expected)
    assert abs(v - a) < 0.025, (v, a)


# ------------------------------------------------------------------ etapa 2

def test_edit_segments_with_splits():
    cuts = [Cut(id="a", start=2, end=3), Cut(id="s", start=5, end=5, kind="split")]
    assert edit_segments(cuts, 10, fps=25) == [(0, 2), (3, 5), (5, 10)]
    # la división no cambia la duración ni el mapeo de tiempos
    assert TimeMap(edit_segments(cuts, 10)).duration == 9


@pytest.mark.parametrize("anim,needle", [("fade", "\\fad(150,"), ("slide", "\\move("), ("pop", "\\t(0,120"),
                                          ("typewriter", "\\alpha&HFF&")])
def test_subtitle_animations(anim, needle):
    words = [Word(start=0, end=0.4, text="Hola"), Word(start=0.4, end=0.9, text="mundo")]
    cues = subtitles.output_cues([Caption(id="1", start=0, end=0.9, text="Hola mundo", words=words)],
                                 TimeMap([(0, 5)]))
    ass = subtitles.to_ass(cues, SubtitleStyle(animation=anim), 1080, 1920)
    assert needle in ass


def test_animated_subtitles_render(tone_video, tmp_path):
    words = [Word(start=0.2, end=0.6, text="uno"), Word(start=0.6, end=1.0, text="dos")]
    doc = doc_for(tone_video, captions=[Caption(id="1", start=0.2, end=1.0, text="uno dos", words=words)],
                  subtitle_style=SubtitleStyle(animation="typewriter"), format=FormatSettings(aspect="16:9"))
    render.export(doc, ExportRequest(profile="youtube", width=640, height=360, **FAST), tmp_path, "anim")
    check_sync(tmp_path / "anim.mp4", 8)


# ------------------------------------------------------------------ etapa 4: transiciones

@pytest.mark.parametrize("ttype", ["fade", "dissolve", "zoom", "blur", "slide", "flash"])
def test_every_transition_keeps_duration_and_sync(tone_video, tmp_path, ttype):
    cuts = [Cut(id="a", start=2.0, end=4.0), Cut(id="b", start=6.0, end=6.5)]
    doc = doc_for(tone_video, cuts=cuts, transition_default=Transition(type=ttype, duration=0.6, intensity=0.8),
                  format=FormatSettings(aspect="16:9"))
    res = render.export(doc, ExportRequest(profile="youtube", width=320, height=180, **FAST), tmp_path, ttype)
    assert res["transitions"] == 2 and res["transitions_skipped"] == 0
    check_sync(tmp_path / f"{ttype}.mp4", 5.5)


@pytest.mark.parametrize("intensity,lo,hi", [(1.0, 0, 30), (0.5, 100, 150), (0.0, 225, 256)])
def test_fade_intensity_controls_darkness(white_video, tmp_path, intensity, lo, hi):
    doc = doc_for(white_video, cuts=[Cut(id="a", start=2, end=3,
                                         transition=Transition(type="fade", duration=1.0, intensity=intensity))],
                  format=FormatSettings(aspect="16:9"))
    render.export(doc, ExportRequest(profile="youtube", width=320, height=180, fps=25, **FAST), tmp_path, "f")
    assert lo <= frame_luma(tmp_path / "f.mp4", 2.0) <= hi   # centro de la unión (2 s de salida)
    assert frame_luma(tmp_path / "f.mp4", 1.0) > 225          # lejos de la unión: intacto


def test_flash_goes_white(tone_video, tmp_path):
    doc = doc_for(tone_video, cuts=[Cut(id="a", start=2, end=4)],
                  transition_default=Transition(type="flash", duration=0.4, intensity=1.0),
                  format=FormatSettings(aspect="16:9"))
    render.export(doc, ExportRequest(profile="youtube", width=320, height=180, fps=25, **FAST), tmp_path, "fl")
    assert frame_luma(tmp_path / "fl.mp4", 2.0) > 225


def test_split_hosts_effect_but_not_dissolve(white_video, tmp_path):
    cuts = [Cut(id="s1", start=2, end=2, kind="split", transition=Transition(type="fade", duration=0.8)),
            Cut(id="s2", start=4, end=4, kind="split", transition=Transition(type="dissolve", duration=0.8))]
    doc = doc_for(white_video, cuts=cuts, format=FormatSettings(aspect="16:9"))
    res = render.export(doc, ExportRequest(profile="youtube", width=320, height=180, fps=25, **FAST), tmp_path, "sp")
    assert res["transitions"] == 1 and res["transitions_skipped"] == 1
    assert frame_luma(tmp_path / "sp.mp4", 2.0) < 40
    check_sync(tmp_path / "sp.mp4", 6)


def test_jump_zoom_and_window_render(tone_video, tmp_path):
    cuts = [Cut(id="a", start=2.0, end=4.0, transition=Transition(type="dissolve", duration=0.6))]
    doc = doc_for(tone_video, cuts=cuts, format=FormatSettings(aspect="9:16", jump_zoom=0.15))
    req = ExportRequest(profile="tiktok", width=270, height=480, fps=25, **FAST)
    res = render.export(doc, req, tmp_path, "win", window=(1.0, 3.5))
    assert res["duration"] == pytest.approx(2.5, abs=0.05) and res["transitions"] == 1
    check_sync(tmp_path / "win.mp4", 2.5)


def test_many_transitions_long_expression(tone_video, tmp_path):
    cuts = [Cut(id=str(i), start=i * 0.25 + 0.1, end=i * 0.25 + 0.15) for i in range(30)]
    doc = doc_for(tone_video, cuts=cuts, transition_default=Transition(type="zoom", duration=0.2),
                  format=FormatSettings(aspect="16:9", jump_zoom=0.1))
    res = render.export(doc, ExportRequest(profile="youtube", width=320, height=180, **FAST), tmp_path, "many")
    assert res["segments"] == 31
    check_sync(tmp_path / "many.mp4", res["duration"])


# ------------------------------------------------------------------ etapa 3

def test_scene_detection(scene_video):
    found = scenes.detect_scenes(str(scene_video), 6.0)
    assert len(found) == 2
    assert found[0] == pytest.approx(2.0, abs=0.08) and found[1] == pytest.approx(4.5, abs=0.08)


def test_face_tracking_follows_subject(face_video):
    res = facetrack.track_faces(str(face_video), 8.0)
    tr = res["track"]
    assert res["detection_rate"] > 0.8 and len(tr) >= 2
    # centro esperado del rostro: (40+105 t + 0.44*360)/1280; la cámara va con algo de retraso
    expect = lambda t: (40 + 105 * t + 0.44 * 360) / 1280  # noqa: E731
    first, last = tr[0], tr[-1]
    assert first[1] == pytest.approx(expect(first[0]), abs=0.08)
    assert last[1] == pytest.approx(expect(last[0]), abs=0.1)
    assert last[1] - first[1] > 0.45
    assert len(tr) < 40   # trayectoria simplificada


def test_render_with_face_track(face_video, tmp_path):
    track = facetrack.track_faces(str(face_video), 8.0)["track"]
    doc = doc_for(face_video, format=FormatSettings(aspect="9:16", mode="crop", track_enabled=True, track=track),
                  cuts=[Cut(id="a", start=3, end=4)])
    render.export(doc, ExportRequest(profile="tiktok", width=270, height=480, fps=25, **FAST), tmp_path, "trk")
    script = (tmp_path / "trk.filtergraph.txt").read_text()
    assert "crop=" in script and "gte(t," in script
    check_sync(tmp_path / "trk.mp4", 7)


# ------------------------------------------------------------------ etapa 5: audio

def test_music_ducking_lowers_music_under_voice(tone_video, music_file, tmp_path):
    """Voz = tono 440 Hz (0-2 s, 4-6 s, 6.5-8 s); música = 3000 Hz. Se mide la banda de 3 kHz."""
    def run(ducking):
        mus = MusicTrack(path=str(music_file), file_name="m.wav", duration=5, volume_db=-6, loop=True,
                         fade_in=0, fade_out=0, ducking=ducking, ducking_amount=1.0)
        doc = doc_for(tone_video, audio=AudioSettings(music=mus), format=FormatSettings(aspect="16:9"))
        render.export(doc, ExportRequest(profile="youtube", width=320, height=180, **FAST), tmp_path, f"d{ducking}")
        p = tmp_path / f"d{ducking}.mp4"
        return band_rms_db(p, 0.6, 1.0, 3000), band_rms_db(p, 2.6, 1.0, 3000)
    on_voice, on_pause = run(True)
    assert on_pause - on_voice >= 6, (on_voice, on_pause)
    off_voice, off_pause = run(False)
    assert abs(off_pause - off_voice) < 2
    # en las pausas la música suena a su volumen configurado (-6 dB), con el loop activo
    assert on_pause == pytest.approx(band_rms_db(music_file, 0.5, 1.0, 3000) - 6, abs=2)


def test_music_only_on_silent_video(silent_video, music_file, tmp_path):
    mus = MusicTrack(path=str(music_file), file_name="m.wav", duration=5, loop=False, fade_in=0, fade_out=0)
    doc = doc_for(silent_video, audio=AudioSettings(music=mus), format=FormatSettings(aspect="16:9", mode="fit"))
    render.export(doc, ExportRequest(profile="youtube", width=320, height=180, **FAST), tmp_path, "mo")
    src_level = band_rms_db(music_file, 0.5, 1.5, 3000)
    # volumen por defecto de la música: -16 dB respecto del archivo original
    assert band_rms_db(tmp_path / "mo.mp4", 0.5, 1.5, 3000) == pytest.approx(src_level - 16, abs=1.5)
    check_sync(tmp_path / "mo.mp4", 3)


def test_denoise_lowers_noise_floor(speech_video, tmp_path, media_dir):
    import subprocess
    noisy = media_dir / "noisy.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(speech_video), "-f", "lavfi", "-i",
                    "anoisesrc=color=white:amplitude=0.02:r=48000", "-filter_complex",
                    "[0:a][1:a]amix=inputs=2:duration=first:normalize=0[a]", "-map", "0:v", "-map", "[a]",
                    "-c:v", "copy", "-c:a", "aac", str(noisy)], check=True)

    def floor(denoise):
        doc = doc_for(noisy, audio=AudioSettings(denoise=denoise, denoise_strength=1.0, highpass=denoise),
                      format=FormatSettings(aspect="16:9"))
        render.export(doc, ExportRequest(profile="youtube", width=320, height=180, **FAST), tmp_path, f"n{denoise}")
        return band_rms_db(tmp_path / f"n{denoise}.mp4", 9.0, 1.5, 4000)   # pausa larga 8.5–11 s
    assert floor(False) - floor(True) >= 6


def test_global_fades(white_video, tmp_path):
    doc = doc_for(white_video, audio=AudioSettings(fade_in=1.0, fade_out=1.0), format=FormatSettings(aspect="16:9"))
    render.export(doc, ExportRequest(profile="youtube", width=320, height=180, fps=25, **FAST), tmp_path, "gf")
    p = tmp_path / "gf.mp4"
    assert frame_luma(p, 0.0) < 40 and frame_luma(p, 3.0) > 225 and frame_luma(p, 5.96) < 60
    assert band_rms_db(p, 0.0, 0.15, 440) < band_rms_db(p, 2.5, 0.5, 440) - 10
