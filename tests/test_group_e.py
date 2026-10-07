import subprocess

import pytest

from conftest import call, ffprobe, needs_ffmpeg, sha
from helpers import run_ok

pytestmark = needs_ffmpeg


@pytest.fixture(scope="module")
def music(media):
    m = media["dir"] / "music.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=220:duration=2",
                    "-c:a", "libmp3lame", str(m)], check=True)
    return m


@pytest.mark.parametrize("fmt,codec", [("mp3", "mp3"), ("wav", "pcm_s16le"), ("m4a", "aac"), ("flac", "flac")])
def test_extract_audio(media, out_dir, fmt, codec):
    r, p = run_ok("lk_extract_audio", media["clip"], out_dir, format=fmt)
    assert r["output"].endswith("." + fmt) and p["video"] is None and p["audio"]["codec_name"] == codec
    assert p["duration"] == pytest.approx(4, abs=0.3)


def test_extract_audio_errors(media, out_dir):
    assert call("lk_extract_audio", input=str(media["silent"]), output_dir=str(out_dir))["ok"] is False
    assert call("lk_extract_audio", input=str(media["clip"]), audio_track=3, output_dir=str(out_dir))["ok"] is False
    assert call("lk_extract_audio", input=str(media["clip"]), format="ogg", output_dir=str(out_dir))["ok"] is False


@pytest.mark.parametrize("mode,exp", [("trim", 4.0), ("shortest", 2.0), ("loop", 4.0)])
def test_replace_audio(media, music, out_dir, mode, exp):
    r, p = run_ok("lk_replace_audio", media["clip"], out_dir, audio=str(music), mode=mode)
    assert p["duration"] == pytest.approx(exp, abs=0.3)
    assert p["video"]["codec_name"] == "h264" and p["audio"] is not None


def test_replace_audio_silent_video_and_bad(media, music, out_dir):
    r, p = run_ok("lk_replace_audio", media["silent"], out_dir, audio=str(music), mode="loop")
    assert p["audio"] is not None and p["duration"] == pytest.approx(3, abs=0.3)
    assert call("lk_replace_audio", input=str(media["clip"]), audio=str(media["silent"]), output_dir=str(out_dir))["ok"] is False
    assert call("lk_replace_audio", input=str(media["clip"]), output_dir=str(out_dir))["ok"] is False


@pytest.mark.parametrize("ducking", [True, False])
def test_mix_music(media, music, out_dir, ducking):
    r, p = run_ok("lk_mix_music", media["clip"], out_dir, music=str(music), ducking=ducking, music_volume_db=-12)
    assert p["duration"] == pytest.approx(4, abs=0.3) and p["audio"] is not None
    assert p["video"]["codec_name"] == "h264"


def test_mix_music_silent_clip(media, music, out_dir):
    r, p = run_ok("lk_mix_music", media["silent"], out_dir, music=str(music))
    assert p["audio"] is not None and p["duration"] == pytest.approx(3, abs=0.3)
    assert r["info"]["ducking"] is False


def test_normalize_loudness(media, out_dir):
    r, p = run_ok("lk_normalize_loudness", media["clip"], out_dir, target_lufs=-20)
    assert r["info"]["measured_after_lufs"] == pytest.approx(-20, abs=1.5)
    assert p["duration"] == pytest.approx(4, abs=0.3)


def test_normalize_loudness_errors(media, out_dir):
    assert call("lk_normalize_loudness", input=str(media["silent"]), output_dir=str(out_dir))["ok"] is False
    assert call("lk_normalize_loudness", input=str(media["clip"]), target_lufs=5, output_dir=str(out_dir))["ok"] is False


@pytest.mark.parametrize("ms", [250, -250])
def test_sync_audio_offset(media, out_dir, ms):
    r, p = run_ok("lk_sync_audio_offset", media["clip"], out_dir, offset_ms=ms)
    assert p["duration"] == pytest.approx(4, abs=0.3) and p["audio"] is not None


def test_sync_audio_offset_bad(media, out_dir):
    for kw in ({}, {"offset_ms": 0}, {"offset_ms": 99999}):
        assert call("lk_sync_audio_offset", input=str(media["clip"]), output_dir=str(out_dir), **kw)["ok"] is False
    assert call("lk_sync_audio_offset", input=str(media["silent"]), offset_ms=100, output_dir=str(out_dir))["ok"] is False


def _lufs(path):
    from hermes_video_editor.tools.audio import measure_loudness
    return measure_loudness(path, 60)["input_i"]


def test_adjust_volume(media, out_dir):
    base = _lufs(media["clip"])
    r, p = run_ok("lk_adjust_volume", media["clip"], out_dir, db=-6)
    assert _lufs(r["output"]) == pytest.approx(base - 6, abs=1.0)
    r, p = run_ok("lk_adjust_volume", media["clip"], out_dir, factor=0.5)
    assert _lufs(r["output"]) == pytest.approx(base - 6, abs=1.0)


def test_adjust_volume_bad(media, out_dir):
    for kw in ({}, {"db": 3, "factor": 2}, {"db": 99}, {"factor": -1}):
        assert call("lk_adjust_volume", input=str(media["clip"]), output_dir=str(out_dir), **kw)["ok"] is False


def test_fade_audio(media, out_dir):
    r, p = run_ok("lk_fade_audio", media["clip"], out_dir, fade_in_s=1, fade_out_s=1)
    assert p["duration"] == pytest.approx(4, abs=0.3)
    def mean_vol(ss, t):
        err = subprocess.run(["ffmpeg", "-hide_banner", "-ss", str(ss), "-t", str(t), "-i", str(r["output"]),
                              "-vn", "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True).stderr
        return float(err.split("mean_volume:")[1].split("dB")[0])
    assert mean_vol(0, 0.3) < mean_vol(1.5, 0.5) - 6      # faded in
    assert mean_vol(3.7, 0.3) < mean_vol(1.5, 0.5) - 6    # faded out
    for kw in ({}, {"fade_in_s": 3, "fade_out_s": 3}):
        assert call("lk_fade_audio", input=str(media["clip"]), output_dir=str(out_dir), **kw)["ok"] is False


@pytest.mark.parametrize("preset", ["light", "medium", "strong", "voice"])
def test_denoise_audio(media, out_dir, preset):
    r, p = run_ok("lk_denoise_audio", media["clip"], out_dir, preset=preset)
    assert p["duration"] == pytest.approx(4, abs=0.3) and p["video"]["codec_name"] == "h264"


def test_audio_tools_on_audio_only_file(media, out_dir):
    wav = call("lk_extract_audio", input=str(media["clip"]), format="wav", output_dir=str(out_dir))["output"]
    r = call("lk_adjust_volume", input=wav, db=3, output_dir=str(out_dir))
    assert r["ok"] and r["output"].endswith(".wav")
    r = call("lk_denoise_audio", input=wav, output_dir=str(out_dir))
    assert r["ok"] and ffprobe(r["output"])["video"] is None
