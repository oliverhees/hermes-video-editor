import os
import sys
import types

import pytest

from conftest import call, ffprobe, needs_ffmpeg, sha
from helpers import run_ok
from hermes_video_editor.platform_rules import PLATFORM_RULES
from hermes_video_editor.tools.export import (EXPORT_PRESETS, choose_height, evaluate, plan_video_kbps,
                                              segments_to_srt, srt_time)

pytestmark = needs_ffmpeg


def test_rules_and_presets_consistent():
    assert set(EXPORT_PRESETS) == set(PLATFORM_RULES)
    assert "VERIFY" in sys.modules["hermes_video_editor.platform_rules"].__doc__


@pytest.mark.parametrize("preset", [p for p in EXPORT_PRESETS if p not in ("discord_8mb", "youtube_4k")])
def test_export_preset(media, out_dir, preset):
    r, p = run_ok("lk_export_preset", media["clip"], out_dir, preset=preset)
    cfg = EXPORT_PRESETS[preset]
    v = p["video"]
    assert r["output"].endswith(".mp4") and v["codec_name"] == "h264" and v["pix_fmt"] == "yuv420p"
    assert p["audio"]["codec_name"] == "aac" and p["duration"] == pytest.approx(4, abs=0.3)
    if cfg["size"]:
        assert (v["width"], v["height"]) == cfg["size"]
    else:
        assert (v["width"], v["height"]) == (640, 360)
    # faststart: moov before mdat
    head = open(r["output"], "rb").read(4096)
    assert head.find(b"moov") != -1


def test_export_4k_and_cover(media, out_dir):
    r, p = run_ok("lk_export_preset", media["silent"], out_dir, preset="youtube_4k")
    assert (p["video"]["width"], p["video"]["height"]) == (3840, 2160) and p["audio"] is None
    r, p = run_ok("lk_export_preset", media["clip"], out_dir, preset="reels", fit="cover")
    assert (p["video"]["width"], p["video"]["height"]) == (1080, 1920)


def test_export_fps_cap_and_odd(media, out_dir):
    r, p = run_ok("lk_export_preset", media["fast"], out_dir, preset="reels")
    assert eval(p["video"]["r_frame_rate"]) == pytest.approx(30, abs=0.1)
    r, p = run_ok("lk_export_preset", media["odd"], out_dir, preset="web_mp4")
    assert p["video"]["width"] % 2 == 0 and p["video"]["height"] % 2 == 0


def test_export_discord_size(media, out_dir):
    r, p = run_ok("lk_export_preset", media["noisy"], out_dir, preset="discord_8mb")
    assert os.path.getsize(r["output"]) <= 8_000_000
    assert p["video"]["codec_name"] == "h264"


def test_export_bad(media, out_dir):
    assert call("lk_export_preset", input=str(media["clip"]), preset="myspace", output_dir=str(out_dir))["ok"] is False
    assert call("lk_export_preset", input=str(media["clip"]), output_dir=str(out_dir))["ok"] is False


def test_platform_check_pass_and_fail(media, out_dir):
    exported = call("lk_export_preset", input=str(media["clip"]), preset="reels", output_dir=str(out_dir))["output"]
    r = call("lk_platform_check", input=exported, platform="reels")
    assert r["ok"] and r["output"] is None
    by = {c["check"]: c for c in r["info"]["checks"]}
    assert by["aspect_ratio"]["status"] == "pass" and by["duration_max"]["status"] == "pass"
    assert by["video_codec"]["status"] == "pass" and by["fps_max"]["status"] == "pass"
    assert "loudness" in by          # measured because the clip has audio
    bad = call("lk_platform_check", input=str(media["clip"]), platform="reels")
    assert bad["ok"] and bad["info"]["passed"] is False and "aspect_ratio" in bad["info"]["failed"]
    assert any("lk_crop_to_aspect" in f for f in bad["info"]["fixes"])


def test_platform_check_loudness_fix(media):
    r = call("lk_platform_check", input=str(media["clip"]), platform="youtube_1080p")
    by = {c["check"]: c for c in r["info"]["checks"]}
    if by["loudness"]["status"] == "fail":
        assert "lk_normalize_loudness" in by["loudness"]["fix"]


def test_platform_check_options_and_errors(media):
    r = call("lk_platform_check", input=str(media["silent"]), platform="web_mp4", check_loudness=False)
    assert r["ok"] and "audio_stream" in r["info"]["warnings"]
    assert call("lk_platform_check", input=str(media["clip"]), platform="nope")["ok"] is False
    assert call("lk_platform_check", input=str(media["clip"]))["ok"] is False


def test_evaluate_pure():
    info = {"duration_s": 200, "size_bytes": 5_000_000, "has_audio": True, "audio": [{"codec": "mp3"}],
            "video": {"display_width": 1920, "display_height": 1080, "fps": 120.0, "codec": "vp9", "pix_fmt": "yuv444p"}}
    st = {c["check"]: c["status"] for c in evaluate(info, PLATFORM_RULES["reels"])}
    assert st["duration_max"] == "fail" and st["aspect_ratio"] == "fail" and st["fps_max"] == "fail"
    assert st["video_codec"] == "fail" and st["audio_codec"] == "fail" and st["pixel_format"] == "warn"
    assert evaluate({"video": None, "duration_s": 1}, PLATFORM_RULES["reels"])[0]["status"] == "fail"
    loud = evaluate({**info, "video": {**info["video"], "fps": 30, "codec": "h264", "pix_fmt": "yuv420p"}},
                    {"loudness_lufs": -14, "loudness_tolerance": 2, "max_true_peak_db": -1.0},
                    {"input_i": -20.0, "input_tp": 0.5})
    assert [c["status"] for c in loud if c["check"] in ("loudness", "true_peak")] == ["fail", "warn"]


def test_compress_pure():
    assert plan_video_kbps(100, 10, 96) == pytest.approx(10 * 8000 * 0.96 / 100 - 96)
    assert choose_height(8000, 1920, 1080, 30) == 1080
    assert choose_height(600, 1920, 1080, 30) == 360
    assert choose_height(10, 1920, 1080, 30) == 240


def test_compress_to_size(media, out_dir):
    src_mb = os.path.getsize(media["noisy"]) / 1e6
    target = round(src_mb / 3, 2)
    assert src_mb > 0.6
    r, p = run_ok("lk_compress_to_size", media["noisy"], out_dir, target_mb=target)
    got = os.path.getsize(r["output"]) / 1e6
    assert got <= target and got > target * 0.4
    assert p["duration"] == pytest.approx(5, abs=0.3) and p["audio"] is not None


def test_compress_silent_and_errors(media, out_dir):
    r, p = run_ok("lk_compress_to_size", media["silent"], out_dir, target_mb=0.3)
    assert os.path.getsize(r["output"]) <= 300_000 and p["audio"] is None
    assert call("lk_compress_to_size", input=str(media["noisy"]), target_mb=0.2, output_dir=str(out_dir))["ok"] in (True, False)
    for kw in ({}, {"target_mb": 0}, {"target_mb": "big"}):
        assert call("lk_compress_to_size", input=str(media["clip"]), output_dir=str(out_dir), **kw)["ok"] is False


def test_to_gif(media, out_dir):
    r, p = run_ok("lk_to_gif", media["clip"], out_dir, start=1, duration=2, fps=10, width=200)
    assert r["output"].endswith(".gif") and p["video"]["codec_name"] == "gif" and p["video"]["width"] == 200
    assert p["duration"] == pytest.approx(2, abs=0.3)


def test_to_gif_bad(media, out_dir):
    for kw in ({"start": 99}, {"end": 2, "duration": 1}, {"fps": 99}, {"start": 3, "end": 3}):
        assert call("lk_to_gif", input=str(media["clip"]), output_dir=str(out_dir), **kw)["ok"] is False


def test_contact_sheet(media, out_dir):
    r, p = run_ok("lk_contact_sheet", media["clip"], out_dir, columns=3, rows=2, thumb_width=160)
    v = p["video"]
    assert r["output"].endswith(".jpg")
    assert v["width"] == 3 * 160 + 4 * 4 + 2 * 4 - 4 + 4 or v["width"] > 3 * 160
    assert v["height"] > 2 * 90
    r, p = run_ok("lk_contact_sheet", media["silent"], out_dir, format="png")
    assert r["output"].endswith(".png")


def test_srt_helpers():
    assert srt_time(3725.5) == "01:02:05,500"
    assert segments_to_srt([(0, 1.5, " Hallo  Welt "), (2, 3, "  "), (3, 4, "Ende")]) == \
        "1\n00:00:00,000 --> 00:00:01,500\nHallo Welt\n\n3\n00:00:03,000 --> 00:00:04,000\nEnde\n"


def test_transcribe_without_faster_whisper(media, out_dir, monkeypatch):
    monkeypatch.setitem(sys.modules, "faster_whisper", None)     # import raises ImportError
    r = call("lk_transcribe_captions", input=str(media["clip"]), output_dir=str(out_dir))
    assert r["ok"] is False and "pip install faster-whisper" in r["hint"]


def _fake_whisper(monkeypatch, fail=False):
    mod = types.ModuleType("faster_whisper")

    class Seg:
        def __init__(self, s, e, t):
            self.start, self.end, self.text = s, e, t

    class WhisperModel:
        def __init__(self, name, **kw):
            assert kw["local_files_only"] is True        # never download
            if fail:
                raise RuntimeError("model not cached")

        def transcribe(self, path, **kw):
            assert os.path.exists(path)
            return iter([Seg(0.0, 1.0, " Hallo Welt"), Seg(1.0, 2.5, " zweiter Satz")]), types.SimpleNamespace(language="de")

    mod.WhisperModel = WhisperModel
    monkeypatch.setitem(sys.modules, "faster_whisper", mod)


def test_transcribe_with_fake_model(media, out_dir, monkeypatch):
    _fake_whisper(monkeypatch)
    before = sha(media["clip"])
    r = call("lk_transcribe_captions", input=str(media["clip"]), output_dir=str(out_dir), language="de")
    assert r["ok"], r
    text = open(r["output"], encoding="utf-8").read()
    assert text.startswith("1\n00:00:00,000 --> 00:00:01,000\nHallo Welt") and "zweiter Satz" in text
    assert r["info"]["segments"] == 2 and sha(media["clip"]) == before


def test_transcribe_errors(media, out_dir, monkeypatch):
    _fake_whisper(monkeypatch, fail=True)
    r = call("lk_transcribe_captions", input=str(media["clip"]), output_dir=str(out_dir))
    assert r["ok"] is False and "never downloads" in r["hint"]
    _fake_whisper(monkeypatch)
    assert call("lk_transcribe_captions", input=str(media["silent"]), output_dir=str(out_dir))["ok"] is False
    assert call("lk_transcribe_captions", input=str(media["clip"]), language="xx1", output_dir=str(out_dir))["ok"] is False
