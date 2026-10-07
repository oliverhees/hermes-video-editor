import pytest

from conftest import call, needs_ffmpeg
from helpers import run_ok
from hermes_video_editor.tools.picture import crop_geometry, resize_filter

pytestmark = needs_ffmpeg


def size(p):
    return p["video"]["width"], p["video"]["height"]


def test_crop(media, out_dir):
    r, p = run_ok("lk_crop", media["clip"], out_dir, x=10, y=20, width=300, height=200)
    assert size(p) == (300, 200) and p["audio"] is not None
    assert call("lk_crop", input=str(media["clip"]), width=700, height=100, output_dir=str(out_dir))["ok"] is False
    assert call("lk_crop", input=str(media["clip"]), output_dir=str(out_dir))["ok"] is False


@pytest.mark.parametrize("aspect,anchor,exp", [("9:16", "center", (202, 360)), ("1:1", "left", (360, 360)),
                                               ("4:5", "right", (286, 358)), ("16:9", "top", (640, 360))])
def test_crop_to_aspect(media, out_dir, aspect, anchor, exp):
    r, p = run_ok("lk_crop_to_aspect", media["clip"], out_dir, aspect=aspect, anchor=anchor)
    w, h = size(p)
    assert abs(w - exp[0]) <= 2 and abs(h - exp[1]) <= 2 and w % 2 == 0 and h % 2 == 0


def test_crop_geometry_pure():
    assert crop_geometry(1920, 1080, "9:16", "center") == (606, 1080, 657, 0)
    assert crop_geometry(1920, 1080, "9:16", "left")[2] == 0
    assert crop_geometry(1920, 1080, "9:16", "right")[2] == 1920 - 606
    assert crop_geometry(1080, 1920, "1:1", "top")[3] == 0
    assert crop_geometry(1080, 1920, "1:1", "bottom")[3] == 840
    assert crop_geometry(1080, 1920, "1:1", "left")[2] == 0  # irrelevant anchor: nothing to cut horizontally


def test_crop_to_aspect_output_width_and_odd(media, out_dir):
    r, p = run_ok("lk_crop_to_aspect", media["odd"], out_dir, aspect="1:1", output_width=100)
    assert size(p) == (100, 100)
    assert call("lk_crop_to_aspect", input=str(media["clip"]), aspect="2:3", output_dir=str(out_dir))["ok"] is False


def test_resize(media, out_dir):
    assert size(run_ok("lk_resize", media["clip"], out_dir, preset="480p")[1]) == (854, 480)
    assert size(run_ok("lk_resize", media["clip"], out_dir, width=320)[1]) == (320, 180)
    assert size(run_ok("lk_resize", media["clip"], out_dir, height=100)[1]) == (178, 100)
    assert size(run_ok("lk_resize", media["clip"], out_dir, width=300, height=300)[1]) == (300, 168)
    assert size(run_ok("lk_resize", media["clip"], out_dir, width=300, height=300, keep_aspect=False)[1]) == (300, 300)
    assert size(run_ok("lk_resize", media["clip"], out_dir, preset="1080x1920")[1]) == (1080, 608)
    assert size(run_ok("lk_resize", media["odd"], out_dir, width=161)[1])[0] % 2 == 0


def test_resize_pure_and_bad(media, out_dir):
    assert resize_filter(1080, 1920, None, None, "720p", True) == "scale=720:-2"
    assert resize_filter(1920, 1080, None, None, "720p", True) == "scale=-2:720"
    assert call("lk_resize", input=str(media["clip"]), output_dir=str(out_dir))["ok"] is False
    assert call("lk_resize", input=str(media["clip"]), preset="8k", output_dir=str(out_dir))["ok"] is False


def test_rotate_flip(media, out_dir):
    assert size(run_ok("lk_rotate_flip", media["clip"], out_dir, rotate=90)[1]) == (360, 640)
    assert size(run_ok("lk_rotate_flip", media["clip"], out_dir, rotate=270)[1]) == (360, 640)
    assert size(run_ok("lk_rotate_flip", media["clip"], out_dir, rotate=180, hflip=True)[1]) == (640, 360)
    assert size(run_ok("lk_rotate_flip", media["clip"], out_dir, vflip=True)[1]) == (640, 360)
    for kw in ({}, {"rotate": 45}):
        assert call("lk_rotate_flip", input=str(media["clip"]), output_dir=str(out_dir), **kw)["ok"] is False


def test_pad_blur_background(media, out_dir):
    r, p = run_ok("lk_pad_blur_background", media["clip"], out_dir, width=270, height=480, blur_strength=10)
    assert size(p) == (270, 480) and p["audio"] is not None
    r, p = run_ok("lk_pad_blur_background", media["silent"], out_dir, width=270, height=480)
    assert size(p) == (270, 480) and p["audio"] is None


def test_color_adjust(media, out_dir):
    r, p = run_ok("lk_color_adjust", media["clip"], out_dir, brightness=0.1, contrast=1.2, saturation=0, gamma=1.1)
    assert size(p) == (640, 360)
    assert call("lk_color_adjust", input=str(media["clip"]), output_dir=str(out_dir))["ok"] is False
    assert call("lk_color_adjust", input=str(media["clip"]), contrast=9, output_dir=str(out_dir))["ok"] is False


@pytest.mark.parametrize("s", ["light", "medium", "strong"])
def test_denoise_video(media, out_dir, s):
    assert size(run_ok("lk_denoise_video", media["silent"], out_dir, strength=s)[1]) == (320, 240)


def test_fade_video(media, out_dir):
    r, p = run_ok("lk_fade_video", media["clip"], out_dir, fade_in_s=1, fade_out_s=1)
    assert p["duration"] == pytest.approx(4, abs=0.2) and r["info"]["audio_faded"]
    r, p = run_ok("lk_fade_video", media["silent"], out_dir, fade_out_s=1)
    assert p["audio"] is None
    for kw in ({}, {"fade_in_s": 3, "fade_out_s": 3}):
        assert call("lk_fade_video", input=str(media["clip"]), output_dir=str(out_dir), **kw)["ok"] is False


@pytest.mark.parametrize("s", ["low", "high"])
def test_stabilize(media, out_dir, s):
    r, p = run_ok("lk_stabilize", media["clip"], out_dir, strength=s)
    assert size(p) == (640, 360)
