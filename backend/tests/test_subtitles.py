import pytest

from app.engine import subtitles
from app.engine.timeline import TimeMap
from app.schemas import SubtitleStyle, Word


def words(*specs):
    return [Word(start=s, end=e, text=t) for t, s, e in specs]


W = words(("Hola", 0.0, 0.4), ("a", 0.4, 0.5), ("todos.", 0.5, 1.0), ("Hoy", 3.0, 3.3),
          ("probamos", 3.3, 3.9), ("el", 3.9, 4.0), ("editor", 4.0, 4.5), ("nuevo", 4.5, 5.0))


def test_build_captions_breaks_on_punctuation_gap_and_size():
    caps = subtitles.build_captions(W, max_words=3, max_chars=40)
    assert [c.text for c in caps] == ["Hola a todos.", "Hoy probamos el", "editor nuevo"]
    assert caps[0].start == 0.0 and caps[0].end == 1.0


def test_retime_same_count_keeps_timing():
    cap = subtitles.build_captions(W[:3], max_words=5)[0]
    new = subtitles.retime_text(cap, "Hola a todas.")
    assert [w.text for w in new.words] == ["Hola", "a", "todas."]
    assert [w.start for w in new.words] == [0.0, 0.4, 0.5]
    assert new.edited


def test_retime_different_count_distributes():
    cap = subtitles.build_captions(W[:3], max_words=5)[0]
    new = subtitles.retime_text(cap, "Buenas tardes")
    assert len(new.words) == 2
    assert new.words[0].start == cap.start
    assert new.words[-1].end == pytest.approx(cap.end, abs=1e-3)


def test_output_cues_drop_cut_words_and_shift():
    caps = subtitles.build_captions(W, max_words=3, max_chars=40)
    tm = TimeMap([(0, 0.45), (2.0, 10)])  # elimina "todos." y el silencio
    cues = subtitles.output_cues(caps, tm)
    assert cues[0].text == "Hola a"
    assert cues[1].text == "Hoy probamos el"
    assert cues[1].start == pytest.approx(0.45 + 1.0)  # 3.0 en la fuente -> 1.45


def test_srt_format():
    cues = [subtitles.Cue(0.0, 1.5, "Hola"), subtitles.Cue(61.25, 3725.001, "Fin")]
    srt = subtitles.to_srt(cues)
    assert "00:00:00,000 --> 00:00:01,500" in srt
    assert "00:01:01,250 --> 01:02:05,001" in srt


def test_ass_contains_style_colors_and_highlight():
    style = SubtitleStyle(primary_color="#FF0000", highlight_color="#00FF00", highlight_words=True)
    caps = subtitles.build_captions(W[:3], max_words=5)
    cues = subtitles.output_cues(caps, TimeMap([(0, 10)]))
    ass = subtitles.to_ass(cues, style, 1080, 1920)
    assert "PlayResX: 1080" in ass and "PlayResY: 1920" in ass
    assert "&H000000FF" in ass            # rojo en BGR
    assert "{\\c&H0000FF00}" in ass       # resaltado verde
    assert ass.count("Dialogue:") == 3   # un evento por palabra


def test_ass_escapes_braces():
    cues = [subtitles.Cue(0, 1, "uso {llaves}")]
    ass = subtitles.to_ass(cues, SubtitleStyle(highlight_words=False), 1920, 1080)
    assert "uso (llaves)" in ass
