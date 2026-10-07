import subprocess

import pytest

from conftest import call, needs_ffmpeg
from helpers import run_ok

pytestmark = needs_ffmpeg


def size(p):
    return p["video"]["width"], p["video"]["height"]


def frame(path, t=0.5, vf=None):
    """Raw RGB bytes of one frame (optionally cropped by vf)."""
    cmd = ["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(path), "-frames:v", "1"]
    if vf:
        cmd += ["-vf", vf]
    return subprocess.run(cmd + ["-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout


def diff(a, b):
    """Number of bytes that differ clearly (> 48 levels); ignores re-encode noise."""
    return sum(1 for x, y in zip(a, b) if abs(x - y) > 48)


def has_filter(name):
    out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
    return (" %s " % name) in out


SRT = "1\n00:00:00,000 --> 00:00:02,000\nHallo Welt äöü\n\n2\n00:00:02,000 --> 00:00:04,000\nZweite Zeile\n"
VTT = "WEBVTT\n\n00:00.000 --> 00:02.000\nHello VTT\n"
ASS = """[Script Info]
ScriptType: v4.00+
PlayResX: 640
PlayResY: 360

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,40,&H0000FFFF,&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,2,0,2,10,10,20,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,ASS caption
"""


@pytest.fixture(scope="module")
def assets(tmp_path_factory):
    d = tmp_path_factory.mktemp("assets")
    (d / "caps ä.srt").write_text(SRT, encoding="utf-8")
    (d / "caps.vtt").write_text(VTT, encoding="utf-8")
    (d / "caps.ass").write_text(ASS, encoding="utf-8")
    (d / "bad.txt").write_text("x")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=red:s=100x60:d=1",
                    "-frames:v", "1", str(d / "logo.png")], check=True)
    return d


@pytest.mark.skipif(not has_filter("drawtext"), reason="ffmpeg built without drawtext/freetype")
def test_add_text(media, out_dir):
    r, p = run_ok("ve_add_text", media["clip"], out_dir, text="Hello ünï\nWorld", position="center", box=True,
                  color="#FFD400", start=0, end=2)
    assert size(p) == (640, 360) and p["audio"] is not None
    src = frame(media["clip"], 1.0)
    assert diff(src, frame(r["output"], 1.0)) > 500           # text visible inside the window
    assert diff(frame(media["clip"], 3.0), frame(r["output"], 3.0)) < diff(src, frame(r["output"], 1.0)) / 10


@pytest.mark.skipif(not has_filter("drawtext"), reason="ffmpeg built without drawtext/freetype")
@pytest.mark.parametrize("pos", ["top_left", "top", "top_right", "left", "right", "bottom_left", "bottom_right"])
def test_add_text_positions_and_percent(media, out_dir, pos):
    r, p = run_ok("ve_add_text", media["silent"], out_dir, text="100% {x} 'quote' : , ; [b]", position=pos)
    assert p["audio"] is None


def test_add_text_bad(media, out_dir):
    for kw in ({}, {"text": " "}, {"text": "x", "position": "nowhere"}, {"text": "x", "color": "red;rm"},
               {"text": "x", "start": 3, "end": 1}, {"text": "x", "font_file": "/no/such.ttf"}):
        assert call("ve_add_text", input=str(media["clip"]), output_dir=str(out_dir), **kw)["ok"] is False


@pytest.mark.skipif(not has_filter("subtitles"), reason="ffmpeg built without libass")
@pytest.mark.parametrize("name", ["caps ä.srt", "caps.vtt", "caps.ass"])
def test_burn_captions(media, assets, out_dir, name):
    r, p = run_ok("ve_burn_captions", media["clip"], out_dir, captions=str(assets / name))
    assert size(p) == (640, 360) and p["audio"] is not None
    assert diff(frame(media["clip"], 1.0), frame(r["output"], 1.0)) > 300


@pytest.mark.skipif(not has_filter("subtitles"), reason="ffmpeg built without libass")
def test_burn_captions_style_and_reels_safe(media, assets, out_dir):
    r, p = run_ok("ve_burn_captions", media["clip"], out_dir, captions=str(assets / "caps ä.srt"),
                  font_size=40, outline_px=3, bottom_margin_px=10, color="#FFD400", reels_safe=True)
    assert r["info"]["bottom_margin_px"] >= int(360 * 0.18)
    # reels-safe: bottom 10% strip stays clean, text is higher up
    bottom = "crop=iw:ih*0.08:0:ih*0.92"
    assert diff(frame(media["clip"], 1.0, bottom), frame(r["output"], 1.0, bottom)) < 50


@pytest.mark.skipif(not has_filter("subtitles"), reason="ffmpeg built without libass")
def test_burn_captions_bad(media, assets, out_dir):
    for kw in ({}, {"captions": str(assets / "bad.txt")}, {"captions": str(assets / "missing.srt")},
               {"captions": str(assets / "caps.vtt"), "color": "notacolor1"}):
        assert call("ve_burn_captions", input=str(media["clip"]), output_dir=str(out_dir), **kw)["ok"] is False


def test_image_overlay(media, assets, out_dir):
    r, p = run_ok("ve_add_image_overlay", media["clip"], out_dir, image=str(assets / "logo.png"),
                  corner="top_left", scale_percent=20, opacity=0.8, margin_px=10, start=1, end=3)
    assert size(p) == (640, 360) and p["audio"] is not None
    corner = "crop=100:50:10:10"
    assert diff(frame(media["clip"], 2.0, corner), frame(r["output"], 2.0, corner)) > 1000
    assert diff(frame(media["clip"], 0.2, corner), frame(r["output"], 0.2, corner)) < 100  # before start
    assert diff(frame(media["clip"], 3.6, corner), frame(r["output"], 3.6, corner)) < 100  # after end


def test_image_overlay_bad(media, out_dir):
    assert call("ve_add_image_overlay", input=str(media["clip"]), output_dir=str(out_dir))["ok"] is False
    assert call("ve_add_image_overlay", input=str(media["clip"]), image=str(media["clip"].parent / "nope.png"),
                output_dir=str(out_dir))["ok"] is False


@pytest.mark.parametrize("audio,has_audio", [("main", True), ("pip", True), ("mix", True), ("none", False)])
def test_pip(media, out_dir, audio, has_audio):
    r, p = run_ok("ve_picture_in_picture", media["clip"], out_dir, pip_input=str(media["other"]),
                  corner="bottom_left", audio=audio)
    assert size(p) == (640, 360) and (p["audio"] is not None) == has_audio
    assert p["duration"] == pytest.approx(4, abs=0.3)


def test_pip_loop_silent_main_and_timing(media, out_dir):
    r, p = run_ok("ve_picture_in_picture", media["clip"], out_dir, pip_input=str(media["silent"]), loop_pip=True,
                  start=1, end=3)
    assert p["duration"] == pytest.approx(4, abs=0.3)
    r, p = run_ok("ve_picture_in_picture", media["silent"], out_dir, pip_input=str(media["other"]), audio="pip")
    assert p["audio"] is not None and r["info"]["audio_used"] == "pip"
    r, p = run_ok("ve_picture_in_picture", media["silent"], out_dir, pip_input=str(media["silent"]), audio="mix")
    assert p["audio"] is None


@pytest.mark.parametrize("layout,exp", [("horizontal", (640 + 640, 360)), ("vertical", (640, 360 + 360))])
def test_stack(media, out_dir, layout, exp):
    clone = media["clip"]
    r, p = run_ok("ve_stack_videos", media["clip"], out_dir, input2=str(clone), layout=layout)
    assert size(p) == exp and p["audio"] is not None


def test_stack_different_sizes_and_audio(media, out_dir):
    r, p = run_ok("ve_stack_videos", media["clip"], out_dir, input2=str(media["other"]), layout="horizontal", audio="mix")
    assert p["video"]["height"] == 360 and p["video"]["width"] % 2 == 0 and p["audio"] is not None
    assert p["duration"] == pytest.approx(2, abs=0.3)
    r, p = run_ok("ve_stack_videos", media["silent"], out_dir, input2=str(media["clip"]), layout="vertical", audio="second")
    assert p["audio"] is not None and size(p)[0] == 320
    r, p = run_ok("ve_stack_videos", media["clip"], out_dir, input2=str(media["silent"]), audio="second")
    assert p["audio"] is None


@pytest.mark.parametrize("mode", ["blur", "pixelate"])
def test_blur_region(media, out_dir, mode):
    r, p = run_ok("ve_blur_region", media["clip"], out_dir, x=100, y=50, width=200, height=120, mode=mode, strength=16)
    assert size(p) == (640, 360) and p["audio"] is not None
    box = "crop=200:120:100:50"
    assert diff(frame(media["clip"], 1.0, box), frame(r["output"], 1.0, box)) > 5000
    outside = "crop=100:100:500:200"
    assert diff(frame(media["clip"], 1.0, outside), frame(r["output"], 1.0, outside)) < 100


def test_blur_region_bad(media, out_dir):
    for kw in ({}, {"x": 600, "y": 0, "width": 100, "height": 100}, {"x": 0, "y": 0, "width": 2, "height": 2},
               {"x": 0, "y": 0, "width": 50, "height": 50, "mode": "zzz"}):
        assert call("ve_blur_region", input=str(media["clip"]), output_dir=str(out_dir), **kw)["ok"] is False


def test_blur_region_odd_and_timed(media, out_dir):
    r, p = run_ok("ve_blur_region", media["odd"], out_dir, x=10, y=10, width=100, height=80, start=0.5, end=1)
    assert size(p) == (320, 240)
