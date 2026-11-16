import pytest

from app.engine import media, subtitles, transcribe


@pytest.fixture(scope="module")
def tiny_available():
    try:
        transcribe.get_model("tiny")
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"Modelo Whisper no disponible: {e}")


def test_transcribe_spanish(speech_video, tmp_path, tiny_available):
    info = media.probe(str(speech_video))
    wav = media.extract_audio_wav(info, tmp_path)
    prog = []
    words, lang = transcribe.transcribe(str(wav), info.duration, "tiny", "es", on_progress=prog.append)
    text = " ".join(w.text.lower() for w in words)
    assert lang == "es"
    assert "canal" in text and "gracias" in text
    assert all(0 <= w.start <= w.end <= info.duration + 0.1 for w in words)
    assert prog
    caps = subtitles.build_captions(words, max_words=4)
    assert len(caps) >= 5


def test_transcribe_cancel(speech_video, tmp_path, tiny_available):
    import threading

    from app.engine.ffmpeg import OperationCanceled
    info = media.probe(str(speech_video))
    wav = media.extract_audio_wav(info, tmp_path)
    ev = threading.Event()
    ev.set()
    with pytest.raises(OperationCanceled):
        transcribe.transcribe(str(wav), info.duration, "tiny", "es", cancel_event=ev)
