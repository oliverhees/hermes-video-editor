"""A. Inspect tools."""
from __future__ import annotations

import importlib.util
import platform
import shutil
import sys
from typing import Any, Dict, List

from ..core.ffmpeg import INSTALL_HINT, probe, run_binary, run_ffmpeg, tool_handler
from ..core.paths import resolve_input
from ..core.result import fail
from ..core.spec import ToolSpec
from ..core.validate import get_timeout

WANT_ENCODERS = ("libx264", "aac", "libx265")
WANT_FILTERS = ("drawtext", "subtitles", "loudnorm", "sidechaincompress", "hqdn3d", "deshake",
                "palettegen", "afftdn", "atempo", "silencedetect", "boxblur")


def _listing_names(text: str) -> set:
    names = set()
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and len(parts[0]) >= 2 and not line.startswith(("Encoders", "Filters", "-")):
            names.add(parts[1])
    return names


@tool_handler
def media_doctor(args: Dict[str, Any]) -> Any:
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    info: Dict[str, Any] = {
        "ffmpeg": ffmpeg, "ffprobe": ffprobe, "python": sys.version.split()[0],
        "platform": platform.platform(),
        "faster_whisper_installed": importlib.util.find_spec("faster_whisper") is not None,
    }
    if not ffmpeg or not ffprobe:
        return fail("ffmpeg and/or ffprobe not found on PATH.", INSTALL_HINT, info=info)
    timeout = get_timeout(args) if "timeout_s" in args else 60
    version = run_ffmpeg(["-version"], timeout, loglevel="error").stdout.splitlines()
    info["ffmpeg_version"] = version[0] if version else "unknown"
    enc = _listing_names(run_ffmpeg(["-encoders"], timeout).stdout)
    fil = _listing_names(run_ffmpeg(["-filters"], timeout).stdout)
    info["encoders"] = {n: n in enc for n in WANT_ENCODERS}
    info["filters"] = {n: n in fil for n in WANT_FILTERS}
    missing: List[str] = [n for n, v in list(info["encoders"].items()) + list(info["filters"].items()) if not v]
    info["missing"] = missing
    if not info["encoders"]["libx264"] or not info["encoders"]["aac"]:
        return fail("FFmpeg lacks libx264 or aac; most tools need them.",
                    "Install a full FFmpeg build.", info=info)
    return {"output": None, "duration_s": None, "info": info}


@tool_handler
def media_probe(args: Dict[str, Any]) -> Any:
    path = resolve_input(args.get("input"))
    info = probe(path, get_timeout(args))
    return {"output": None, "duration_s": info["duration_s"], "info": info}


SPECS = [
    ToolSpec(
        name="ve_media_doctor",
        description=("Check that FFmpeg/ffprobe are installed and which encoders/filters exist "
                     "(libx264, aac, libx265, drawtext, subtitles, loudnorm...). Run this once if "
                     "any other ve_* tool reports a missing binary or filter. Takes no media file."),
        handler=media_doctor, common=("timeout_s",)),
    ToolSpec(
        name="ve_media_probe",
        description=("Read-only inspection of a media file: duration (seconds), resolution, fps, "
                     "codecs, bitrate, rotation, audio streams, has_audio/has_video. ALWAYS call this "
                     "before editing a clip. Does not create any file."),
        handler=media_probe, common=("input", "timeout_s")),
]
