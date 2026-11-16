from app.engine.autoedit import compute_cuts
from app.schemas import AutoEditSettings, Word

S = AutoEditSettings(padding=0.1, mid_sentence_padding=0.3, min_keep=0.3)


def test_cuts_with_padding_and_edges():
    cuts = compute_cuts([(0.0, 1.0), (3.0, 5.0), (9.0, 10.0)], [], 10.0, S)
    assert [(c.start, c.end) for c in cuts] == [(0.0, 0.9), (3.1, 4.9), (9.1, 10.0)]


def test_word_mostly_inside_silence_blocks_cut():
    w = [Word(start=3.8, end=4.2, text="eh")]
    cuts = compute_cuts([(3.0, 5.0)], w, 10.0, S)
    assert all(not (c.start < 4.2 and c.end > 3.8) for c in cuts)


def test_word_bleeding_into_silence_does_not_block():
    w = [Word(start=2.0, end=3.3, text="hola.")]  # solo 0.3 de 1.3 s dentro del silencio
    cuts = compute_cuts([(3.0, 5.0)], w, 10.0, S)
    assert [(c.start, c.end) for c in cuts] == [(3.1, 4.9)]


def test_mid_sentence_keeps_more_air():
    w = [Word(start=2.0, end=2.9, text="entonces")]
    cuts = compute_cuts([(3.0, 5.0)], w, 10.0, S)
    assert [(c.start, c.end) for c in cuts] == [(3.3, 4.7)]


def test_short_keep_between_cuts_is_merged():
    cuts = compute_cuts([(1.0, 2.0), (2.25, 3.5)], [], 10.0, S)
    assert len(cuts) == 1 and cuts[0].start == 1.1 and cuts[0].end == 3.4
