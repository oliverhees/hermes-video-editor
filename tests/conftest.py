"""Loads the plugin as package 'hermes_video_editor' and builds synthetic media fixtures."""
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "hermes_video_editor", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
_pkg = importlib.util.module_from_spec(_spec)
sys.modules["hermes_video_editor"] = _pkg
_spec.loader.exec_module(_pkg)

from hermes_video_editor.schemas import TOOLS  # noqa: E402

HANDLERS = {t["name"]: t["handler"] for t in TOOLS}
HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
needs_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not installed")


def call(name, **args):
    """Call a tool handler and return the parsed JSON (also asserts it IS valid JSON)."""
    raw = HANDLERS[name](args)
    assert isinstance(raw, str)
    return json.loads(raw)


def ffprobe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True, check=True).stdout
    data = json.loads(out)
    v = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)
    return {"duration": float(data["format"].get("duration") or 0), "video": v, "audio": a}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _ff(*args):
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *map(str, args)], check=True)


@pytest.fixture(scope="session")
def media(tmp_path_factory):
    if not HAS_FFMPEG:
        pytest.skip("ffmpeg/ffprobe not installed")
    d = tmp_path_factory.mktemp("media")
    enc = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest"]
    clip = d / "clip.mp4"      # 4 s, 640x360, 25 fps, with audio
    _ff("-f", "lavfi", "-i", "testsrc=duration=4:size=640x360:rate=25",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=4", *enc, clip)
    silent = d / "silent.mp4"  # no audio stream
    _ff("-f", "lavfi", "-i", "testsrc=duration=3:size=320x240:rate=25",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", silent)
    odd = d / "odd.mp4"        # odd dimensions (needs yuv444p for libx264)
    _ff("-f", "lavfi", "-i", "testsrc=duration=2:size=321x241:rate=25",
        "-c:v", "libx264", "-pix_fmt", "yuv444p", odd)
    gap = d / "gap.mp4"        # 4 s, tone with digital silence from 1.0 s to 2.5 s
    _ff("-f", "lavfi", "-i", "testsrc=duration=4:size=320x240:rate=25",
        "-f", "lavfi", "-i", "sine=frequency=500:duration=4",
        "-af", "volume=enable='between(t,1,2.5)':volume=0", *enc, gap)
    other = d / "other.mp4"    # different size/fps/audio rate than clip.mp4 -> forces re-encode join
    _ff("-f", "lavfi", "-i", "testsrc2=duration=2:size=480x270:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=300:duration=2:sample_rate=44100", *enc, other)
    noisy = d / "noisy.mp4"    # 5 s 960x540 with grain -> a few MB, for compression tests
    _ff("-f", "lavfi", "-i", "testsrc2=duration=5:size=960x540:rate=25", "-f", "lavfi", "-i", "sine=duration=5",
        "-vf", "noise=alls=60:allf=t+u", "-c:v", "libx264", "-crf", "14", "-pix_fmt", "yuv420p", "-c:a", "aac", noisy)
    fast = d / "fast.mp4"      # 60 fps for fps-cap tests
    _ff("-f", "lavfi", "-i", "testsrc=duration=1:size=320x180:rate=60", "-c:v", "libx264", "-pix_fmt", "yuv420p", fast)
    rotated = d / "rotated.mp4"  # stored 640x360 with a 90 degree display rotation (phone footage)
    _ff("-display_rotation:v", "90", "-i", clip, "-c", "copy", rotated)
    tricky_dir = d / "mein Ordner ünï"
    tricky_dir.mkdir()
    tricky = tricky_dir / "clip äöü.mp4"
    shutil.copy(clip, tricky)
    return {"dir": d, "clip": clip, "silent": silent, "odd": odd, "tricky": tricky,
            "gap": gap, "other": other, "noisy": noisy, "fast": fast, "rotated": rotated}


@pytest.fixture
def out_dir(tmp_path):
    return tmp_path / "out"
