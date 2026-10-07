import json

import pytest

from hermes_video_editor.core.paths import ff_escape_path, plan_output, unique_path
from hermes_video_editor.core.result import ToolError, fail, ok
from hermes_video_editor.core.timeparse import format_time, parse_time


@pytest.mark.parametrize("raw,expected", [
    ("5", 5.0), (5, 5.0), ("12.5", 12.5), ("01:30", 90.0), ("1:05", 65.0),
    ("00:01:30.250", 90.25), ("1:00:00", 3600.0), (0, 0.0),
])
def test_parse_time_ok(raw, expected):
    assert parse_time(raw) == pytest.approx(expected)


@pytest.mark.parametrize("raw", ["", "abc", "1:2:3:4", "-5", -1, "1:75", "00:61:00", "1,5", None, True,
                                 float("nan"), float("inf"), "1:30.5:00"])
def test_parse_time_bad(raw):
    with pytest.raises(ToolError):
        parse_time(raw)


def test_format_time():
    assert format_time(90.25) == "00:01:30.250"


def test_result_shapes():
    good = json.loads(ok("a.mp4", 1.5, {"x": 1}))
    assert good == {"ok": True, "output": "a.mp4", "duration_s": 1.5, "info": {"x": 1}}
    bad = json.loads(fail("boom", "try this", "tail"))
    assert bad["ok"] is False and bad["error"] == "boom"
    assert bad["hint"] == "try this" and bad["ffmpeg_stderr_tail"] == "tail"


def test_escape_windows_path():
    assert ff_escape_path(r"C:\Users\me\a b.srt") == r"C\\:/Users/me/a b.srt"


def test_escape_specials():
    assert ff_escape_path("/tmp/it's.srt") == r"/tmp/it\\\'s.srt"
    assert ff_escape_path("/tmp/a,b[1];c=d.srt") == r"/tmp/a\,b\[1\]\;c\=d.srt"
    assert ff_escape_path("/plain/ünï/x.srt") == "/plain/ünï/x.srt"


def test_unique_and_plan_output(tmp_path):
    src = tmp_path / "in.mp4"
    src.write_bytes(b"x")
    first = plan_output(src, "trim", ".mp4")
    assert first.name == "in_trim.mp4"
    first.write_bytes(b"y")
    assert plan_output(src, "trim", ".mp4").name == "in_trim_1.mp4"
    (tmp_path / "in_trim_1.mp4").write_bytes(b"y")
    assert plan_output(src, "trim", ".mp4").name == "in_trim_2.mp4"
    assert plan_output(src, "trim", ".mp4", overwrite=True) == first
    assert unique_path(tmp_path / "free.mp4").name == "free.mp4"


def test_output_never_equals_input(tmp_path):
    src = tmp_path / "in.mp4"
    src.write_bytes(b"x")
    with pytest.raises(ToolError):
        plan_output(src, "trim", ".mp4", output=str(src), overwrite=True)


@pytest.mark.parametrize("name", ["a b.srt", "it's.srt", "a:b.srt", "a,b[1];c=d.srt", "ünï äö.srt"])
def test_escape_works_in_real_ffmpeg(tmp_path, name):
    """Real ffmpeg must accept the escaped path inside a subtitles filter."""
    import shutil, subprocess, sys
    if sys.platform.startswith("win") and ":" in name:
        pytest.skip("':' is not allowed in Windows file names")
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    filters = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
    if " subtitles " not in filters:
        pytest.skip("ffmpeg build lacks the subtitles filter (libass)")
    srt = tmp_path / name
    srt.write_text("1\n00:00:00,000 --> 00:00:00,800\nHi\n", encoding="utf-8")
    r = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=160x120:d=1",
                        "-vf", "subtitles=" + ff_escape_path(srt), "-f", "null", "-"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
