"""Tools added in 0.3: lk_loudness_report, lk_mute_video, lk_crossfade_join."""
import subprocess

import pytest

from conftest import call, ffprobe, needs_ffmpeg, sha

pytestmark = needs_ffmpeg


def test_loudness_report_measures_without_writing(media, tmp_path):
    before = sha(media["clip"])
    r = call("lk_loudness_report", input=str(media["clip"]))
    assert r["ok"] and r["output"] is None
    i = r["info"]
    assert -40 < i["integrated_lufs"] < -10 and i["verdict"] in ("ok", "too quiet", "too loud or peaking") and i["advice"]
    assert sha(media["clip"]) == before
    quiet = tmp_path / "quiet.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=3", "-af", "volume=-30dB", str(quiet)], check=True)
    assert call("lk_loudness_report", input=str(quiet))["info"]["verdict"] == "too quiet"
    nosound = call("lk_loudness_report", input=str(media["silent"]))
    assert nosound["ok"] is False and "no audio" in nosound["error"].lower()


def test_mute_video_drops_audio_keeps_picture(media, tmp_path):
    r = call("lk_mute_video", input=str(media["clip"]), output_dir=str(tmp_path))
    assert r["ok"]
    v = ffprobe(r["output"])
    assert v["audio"] is None and v["video"]["width"] == 640
    assert v["duration"] == pytest.approx(4, abs=0.2)
    again = call("lk_mute_video", input=str(media["silent"]), output_dir=str(tmp_path))
    assert again["ok"] and again["info"].get("unchanged") is True and again["output"] == str(media["silent"])
    assert call("lk_mute_video", input="/no/such.mp4")["ok"] is False


def test_crossfade_join_overlaps_clips(media, tmp_path):
    r = call("lk_crossfade_join", inputs=[str(media["clip"]), str(media["other"])], duration_s=1.0, transition="dissolve", output_dir=str(tmp_path))
    assert r["ok"], r
    v = ffprobe(r["output"])
    assert v["duration"] == pytest.approx(4 + 2 - 1, abs=0.35)           # one transition overlaps
    assert (v["video"]["width"], v["video"]["height"]) == (640, 360) and v["audio"] is not None
    assert r["info"]["expected_duration_s"] == pytest.approx(5, abs=0.01)
    # the middle of the transition really blends: neither plain clip frame
    mix = subprocess.run(["ffmpeg", "-v", "error", "-ss", "3.5", "-i", r["output"], "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, check=True).stdout
    assert len(mix) == 640 * 360 * 3
    # three clips (one without sound) and the guard rails
    three = call("lk_crossfade_join", inputs=[str(media["clip"]), str(media["silent"]), str(media["other"])], duration_s=0.5, output_dir=str(tmp_path / "t"))
    assert three["ok"], three
    assert ffprobe(three["output"])["duration"] == pytest.approx(4 + 3 + 2 - 1.0, abs=0.4)
    short = call("lk_crossfade_join", inputs=[str(media["clip"]), str(media["other"])], duration_s=2.5)
    assert short["ok"] is False and "too short" in short["error"]
    assert call("lk_crossfade_join", inputs=[str(media["clip"])])["ok"] is False
    assert call("lk_crossfade_join", inputs=[str(media["clip"]), str(media["other"])], transition="nope")["ok"] is False
