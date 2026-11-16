import pytest

from app.engine.timeline import TimeMap, keep_segments, merge_intervals
from app.schemas import Cut


def cut(s, e, enabled=True):
    return Cut(id=f"{s}", start=s, end=e, enabled=enabled)


def test_merge_intervals():
    assert merge_intervals([(5, 6), (1, 2), (1.5, 3)]) == [(1, 3), (5, 6)]


def test_keep_segments_basic_and_disabled():
    cuts = [cut(1, 2), cut(4, 5), cut(6, 7, enabled=False)]
    assert keep_segments(cuts, 10) == [(0, 1), (2, 4), (5, 10)]


def test_keep_segments_overlapping_and_edges():
    cuts = [cut(0, 1), cut(0.5, 2), cut(9, 12)]
    assert keep_segments(cuts, 10) == [(2, 9)]


def test_keep_segments_snaps_to_frame_grid():
    segs = keep_segments([cut(1.01, 2.02)], 5, fps=30)
    for s, e in segs:
        assert abs(s * 30 - round(s * 30)) < 1e-9
        assert abs(e * 30 - round(e * 30)) < 1e-9 or e == 5


def test_timemap_mapping():
    tm = TimeMap([(0, 1), (2, 4), (5, 10)])
    assert tm.duration == 8
    assert tm.to_output(0.5) == 0.5
    assert tm.to_output(1.5) is None
    assert tm.to_output(3) == pytest.approx(2)
    assert tm.to_output(6) == pytest.approx(4)
    assert tm.to_source(2) == pytest.approx(3)


def test_map_interval_across_cut():
    tm = TimeMap([(0, 1), (2, 4)])
    assert tm.map_interval(0.5, 2.5) == pytest.approx((0.5, 1.5))
    assert tm.map_interval(1.2, 1.8) is None
