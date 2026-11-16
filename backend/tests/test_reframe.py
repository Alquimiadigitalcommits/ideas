from app.engine.reframe import build_filter, crop_box, output_size
from app.schemas import FormatSettings


def test_output_sizes():
    assert output_size("9:16") == (1080, 1920)
    assert output_size("16:9") == (1920, 1080)
    assert output_size("1:1") == (1080, 1080)
    assert output_size("16:9", 720) == (1280, 720)


def test_crop_box_landscape_to_vertical():
    cw, ch, x, y = crop_box(1920, 1080, "9:16", 0.5, 0.5)
    assert ch == 1080 and cw == 606 and x == (1920 - 606) // 2 and y == 0
    assert crop_box(1920, 1080, "9:16", 0.0, 0.5)[2] == 0
    assert crop_box(1920, 1080, "9:16", 1.0, 0.5)[2] == 1920 - 606


def test_crop_box_vertical_to_landscape():
    cw, ch, x, y = crop_box(1080, 1920, "16:9", 0.5, 0.5)
    assert cw == 1080 and ch == 606 and x == 0


def test_filters_build():
    for mode in ("crop", "fit", "blur"):
        f = build_filter("in", "out", 1920, 1080, FormatSettings(aspect="9:16", mode=mode), 1080, 1920)
        assert f.startswith("[in]") and f.endswith("[out]")
