"""Cross-cutting edge cases: rotated phone footage, unicode paths through several tools, never-raise contract."""
import json

import pytest

from conftest import HANDLERS, call, needs_ffmpeg, sha
from helpers import run_ok

pytestmark = needs_ffmpeg


def size(p):
    return p["video"]["width"], p["video"]["height"]


def test_probe_reports_display_size_for_rotated(media):
    v = call("lk_media_probe", input=str(media["rotated"]))["info"]["video"]
    assert (v["width"], v["height"], v["rotation"]) == (640, 360, 90)
    assert (v["display_width"], v["display_height"]) == (360, 640)


def test_rotated_footage_uses_displayed_geometry(media, out_dir):
    assert size(run_ok("lk_crop_to_aspect", media["rotated"], out_dir, aspect="1:1")[1]) == (360, 360)
    assert size(run_ok("lk_trim", media["rotated"], out_dir, duration=1)[1]) == (360, 640)
    assert size(run_ok("lk_export_preset", media["rotated"], out_dir, preset="reels")[1]) == (1080, 1920)
    assert size(run_ok("lk_resize", media["rotated"], out_dir, preset="480p")[1]) == (480, 854)
    r = call("lk_crop", input=str(media["rotated"]), x=0, y=0, width=300, height=600, output_dir=str(out_dir))
    assert r["ok"], r


@pytest.mark.parametrize("name,kw", [
    ("lk_resize", {"preset": "480p"}), ("lk_change_speed", {"factor": 2}), ("lk_normalize_loudness", {}),
    ("lk_extract_frame", {"time": 1}), ("lk_to_gif", {"duration": 1}), ("lk_export_preset", {"preset": "web_mp4"}),
    ("lk_denoise_audio", {}), ("lk_rotate_flip", {"rotate": 90}),
])
def test_unicode_spaces_path_through_tools(media, name, kw):
    before = sha(media["tricky"])
    r = call(name, input=str(media["tricky"]), **kw)
    assert r["ok"], r
    assert "mein Ordner ünï" in r["output"]
    assert sha(media["tricky"]) == before


def test_every_tool_survives_garbage_args():
    garbage = [None, {}, {"input": ""}, {"input": "/definitely/not/here.mp4"}, {"input": 123}, {"timeout_s": "abc"},
               {"input": ["a"]}, {"inputs": "x"}, "text", 42]
    for name, handler in HANDLERS.items():
        for g in garbage:
            data = json.loads(handler(g))
            assert isinstance(data, dict) and "ok" in data, (name, g)
            if name != "lk_media_doctor":
                assert data["ok"] is False, (name, g)
            if not data["ok"]:
                assert data["error"], (name, g)
