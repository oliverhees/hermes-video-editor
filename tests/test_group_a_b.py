import pytest

from conftest import call, ffprobe, needs_ffmpeg, sha
from helpers import run_ok
from hermes_video_editor.tools.cut import atempo_chain, keep_segments

pytestmark = needs_ffmpeg


def test_detect_silence(media):
    r = call("lk_detect_silence", input=str(media["gap"]))
    assert r["ok"] and r["info"]["count"] == 1
    s = r["info"]["silences"][0]
    assert s["start_s"] == pytest.approx(1.0, abs=0.15) and s["end_s"] == pytest.approx(2.5, abs=0.15)
    assert r["output"] is None


def test_detect_silence_no_audio(media):
    r = call("lk_detect_silence", input=str(media["silent"]))
    assert r["ok"] is False and "no audio" in r["error"].lower()


def test_detect_scenes(media, tmp_path):
    import subprocess
    two = tmp_path / "two scenes.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=red:s=160x120:d=1:r=25",
                    "-f", "lavfi", "-i", "color=blue:s=160x120:d=1:r=25", "-filter_complex",
                    "[0][1]concat=n=2:v=1:a=0", "-pix_fmt", "yuv420p", str(two)], check=True)
    r = call("lk_detect_scenes", input=str(two), threshold=0.3)
    assert r["ok"] and r["info"]["count"] == 1
    assert r["info"]["scene_changes_s"][0] == pytest.approx(1.0, abs=0.1)


@pytest.mark.parametrize("fmt", ["png", "jpg"])
def test_extract_frame(media, out_dir, fmt):
    r, p = run_ok("lk_extract_frame", media["clip"], out_dir, time=1.5, format=fmt)
    assert r["output"].endswith("." + fmt)
    assert (p["video"]["width"], p["video"]["height"]) == (640, 360)


def test_extract_frame_beyond_end(media, out_dir):
    assert call("lk_extract_frame", input=str(media["clip"]), time=99, output_dir=str(out_dir))["ok"] is False


def test_split(media, out_dir):
    before = sha(media["clip"])
    r = call("lk_split", input=str(media["clip"]), times=[1, "00:02.5"], output_dir=str(out_dir))
    assert r["ok"], r
    outs = r["info"]["outputs"]
    assert len(outs) == 3 and outs[0].endswith("clip_part1.mp4")
    durs = [ffprobe(o)["duration"] for o in outs]
    assert durs == [pytest.approx(1, abs=0.15), pytest.approx(1.5, abs=0.15), pytest.approx(1.5, abs=0.15)]
    assert sha(media["clip"]) == before


@pytest.mark.parametrize("times", [[0], [4], [2, 2], [99], [], "x", ["bad"]])
def test_split_bad(media, out_dir, times):
    assert call("lk_split", input=str(media["clip"]), times=times, output_dir=str(out_dir))["ok"] is False


def test_join_copy(media, out_dir):
    r = call("lk_join", inputs=[str(media["clip"]), str(media["clip"])], output_dir=str(out_dir))
    assert r["ok"], r
    assert r["info"]["method"] == "stream_copy"
    assert ffprobe(r["output"])["duration"] == pytest.approx(8, abs=0.3)


def test_join_reencode_mixed(media, out_dir):
    r = call("lk_join", inputs=[str(media["clip"]), str(media["other"]), str(media["silent"])],
             output_dir=str(out_dir))
    assert r["ok"], r
    assert r["info"]["method"] == "reencode"
    p = ffprobe(r["output"])
    assert (p["video"]["width"], p["video"]["height"]) == (640, 360)
    assert p["audio"] is not None
    assert p["duration"] == pytest.approx(4 + 2 + 3, abs=0.4)


def test_join_errors(media, out_dir):
    assert call("lk_join", inputs=[str(media["clip"])], output_dir=str(out_dir))["ok"] is False
    r = call("lk_join", inputs=[str(media["clip"]), str(media["other"])], mode="copy", output_dir=str(out_dir))
    assert r["ok"] is False


def test_remove_silence(media, out_dir):
    r, p = run_ok("lk_remove_silence", media["gap"], out_dir, min_silence_s=0.5, padding_s=0.1)
    assert r["info"]["removed_s"] == pytest.approx(1.3, abs=0.2)
    assert p["duration"] == pytest.approx(4 - r["info"]["removed_s"], abs=0.25)


def test_remove_silence_nothing_to_remove(media, out_dir):
    r = call("lk_remove_silence", input=str(media["clip"]), output_dir=str(out_dir))
    assert r["ok"] and r["info"]["unchanged"] and r["output"] == str(media["clip"])


def test_remove_silence_needs_audio(media, out_dir):
    assert call("lk_remove_silence", input=str(media["silent"]), output_dir=str(out_dir))["ok"] is False


def test_remove_segments(media, out_dir):
    r, p = run_ok("lk_remove_segments", media["clip"], out_dir,
                  segments=[{"start": 1, "end": 2}, {"start": "00:03", "end": "00:03.5"}])
    assert p["duration"] == pytest.approx(4 - 1.5, abs=0.2)
    assert p["audio"] is not None


def test_remove_segments_silent_video(media, out_dir):
    r, p = run_ok("lk_remove_segments", media["silent"], out_dir, segments=[{"start": 0, "end": 1}])
    assert p["duration"] == pytest.approx(2, abs=0.2) and p["audio"] is None


@pytest.mark.parametrize("segs", [[], [{"start": 1}], [{"start": 2, "end": 1}], [{"start": 0, "end": 99}], "x"])
def test_remove_segments_bad(media, out_dir, segs):
    assert call("lk_remove_segments", input=str(media["clip"]), segments=segs, output_dir=str(out_dir))["ok"] is False


def test_keep_segments_pure():
    assert keep_segments(10, [(2, 4), (3, 5), (9, 12)]) == [(0.0, 2), (5, 9)]
    assert keep_segments(10, [(0, 10)]) == []


@pytest.mark.parametrize("f,n", [(1.5, 1), (2, 1), (4, 2), (0.25, 2), (0.5, 1), (3, 2)])
def test_atempo_chain(f, n):
    chain = atempo_chain(f)
    vals = [float(x.split("=")[1]) for x in chain.split(",")]
    assert len(vals) == n and all(0.5 <= v <= 2.0 for v in vals)
    prod = 1.0
    for v in vals:
        prod *= v
    assert prod == pytest.approx(f)


@pytest.mark.parametrize("factor,expected", [(2, 2.0), (0.5, 8.0), (4, 1.0)])
def test_change_speed(media, out_dir, factor, expected):
    r, p = run_ok("lk_change_speed", media["clip"], out_dir, factor=factor)
    assert p["duration"] == pytest.approx(expected, abs=0.3)
    assert p["audio"] is not None


def test_change_speed_silent_and_bad(media, out_dir):
    r, p = run_ok("lk_change_speed", media["silent"], out_dir, factor=2)
    assert p["audio"] is None
    for bad in (0.1, 5, "x", None):
        assert call("lk_change_speed", input=str(media["clip"]), factor=bad, output_dir=str(out_dir))["ok"] is False


def test_reverse(media, out_dir):
    r, p = run_ok("lk_reverse", media["clip"], out_dir)
    assert p["duration"] == pytest.approx(4, abs=0.2) and p["audio"] is not None


def test_loop_count_and_target(media, out_dir):
    r, p = run_ok("lk_loop", media["silent"], out_dir, count=3)
    assert p["duration"] == pytest.approx(9, abs=0.3)
    r, p = run_ok("lk_loop", media["clip"], out_dir, target_duration_s=10)
    assert p["duration"] == pytest.approx(10, abs=0.3)


def test_loop_bad(media, out_dir):
    for kw in ({}, {"count": 3, "target_duration_s": 5}, {"count": 1}):
        assert call("lk_loop", input=str(media["clip"]), output_dir=str(out_dir), **kw)["ok"] is False
