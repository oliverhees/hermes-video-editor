"""A. Inspect tools."""
from __future__ import annotations

import importlib.util
import platform
import shutil
import sys
from typing import Any, Dict, List

import re

from ..core.ffmpeg import INSTALL_HINT, Job, probe, run_ffmpeg, tool_handler
from ..core.paths import resolve_input
from ..core.result import ToolError, fail
from ..core.spec import ToolSpec
from ..core.timeparse import format_time
from ..core.validate import get_choice, get_num, get_time, get_timeout
from ._common import tprop

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


def detect_silence_ranges(src: Any, noise_db: float, min_d: float, timeout: float,
                          duration: Any) -> List[List[float]]:
    """Run silencedetect; returns [[start, end], ...] in seconds (open end -> clip duration)."""
    proc = run_ffmpeg(["-i", str(src), "-vn", "-map", "0:a:0", "-af",
                       "silencedetect=noise=%sdB:d=%s" % (noise_db, min_d), "-f", "null", "-"],
                      timeout, loglevel="info")
    ranges: List[List[float]] = []
    start = None
    for line in proc.stderr.splitlines():
        m = re.search(r"silence_start:\s*(-?[\d.]+)", line)
        if m:
            start = max(0.0, float(m.group(1)))
            continue
        m = re.search(r"silence_end:\s*(-?[\d.]+)", line)
        if m and start is not None:
            ranges.append([start, float(m.group(1))])
            start = None
    if start is not None and duration:
        ranges.append([start, float(duration)])
    return ranges


@tool_handler
def detect_silence(args: Dict[str, Any]) -> Any:
    noise = get_num(args, "noise_db", -35, lo=-90, hi=0)
    min_d = get_num(args, "min_duration_s", 0.5, lo=0.05, hi=3600)
    path = resolve_input(args.get("input"))
    info = probe(path)
    if not info["has_audio"]:
        raise ToolError("Input has no audio stream, so there is nothing to analyse.",
                        hint="Silent clips have no silence ranges; skip this tool.")
    ranges = detect_silence_ranges(path, noise, min_d, get_timeout(args), info["duration_s"])
    total = sum(e - s for s, e in ranges)
    return {"output": None, "duration_s": info["duration_s"],
            "info": {"silences": [{"start_s": round(s, 3), "end_s": round(e, 3),
                                   "duration_s": round(e - s, 3)} for s, e in ranges],
                     "count": len(ranges), "total_silence_s": round(total, 3),
                     "noise_db": noise, "min_duration_s": min_d}}


@tool_handler
def detect_scenes(args: Dict[str, Any]) -> Any:
    threshold = get_num(args, "threshold", 0.3, lo=0.01, hi=1.0)
    path = resolve_input(args.get("input"))
    info = probe(path)
    if not info["has_video"]:
        raise ToolError("Input has no video stream.")
    proc = run_ffmpeg(["-i", str(path), "-an", "-vf",
                       "select=gt(scene\\,%s),showinfo" % threshold, "-f", "null", "-"],
                      get_timeout(args), loglevel="info")
    times = [round(float(m.group(1)), 3) for m in re.finditer(r"pts_time:\s*([\d.]+)", proc.stderr)]
    return {"output": None, "duration_s": info["duration_s"],
            "info": {"scene_changes_s": times, "count": len(times), "threshold": threshold,
                     "timestamps": [format_time(t) for t in times]}}


@tool_handler
def extract_frame(args: Dict[str, Any]) -> Any:
    t = get_time(args, "time", 0.0)
    fmt = get_choice(args, "format", ("png", "jpg"), "png")
    job = Job(args, "frame_%ds" % int(t), ext="." + fmt, need_video=True)
    total = job.info["duration_s"]
    if total is not None and t >= total:
        raise ToolError("'time' (%.2fs) is beyond the clip length (%.2fs)." % (t, total))
    ff = ["-ss", "%.3f" % t, "-i", str(job.src), "-map", "0:v:0", "-frames:v", "1"]
    if fmt == "jpg":
        ff += ["-q:v", "2"]
    job.run(ff)
    return job.done(op="extract_frame", time=format_time(t))


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
    ToolSpec(
        name="ve_detect_silence",
        description=("Find silent stretches in the audio track and return their start/end times in seconds. "
                     "Read-only (no file created). Use ve_remove_silence to actually cut them out."),
        handler=detect_silence, common=("input", "timeout_s"),
        properties={
            "noise_db": {"type": "number", "default": -35, "minimum": -90, "maximum": 0,
                         "description": "Level below which audio counts as silence, in dB. -35 default; -50 = stricter."},
            "min_duration_s": {"type": "number", "default": 0.5,
                               "description": "Minimum silence length in seconds. Default 0.5."}}),
    ToolSpec(
        name="ve_detect_scenes",
        description=("Find scene-change (cut) timestamps in a video. Read-only. Returns seconds and "
                     "HH:MM:SS.mmm. Useful before ve_split or for choosing thumbnails."),
        handler=detect_scenes, common=("input", "timeout_s"),
        properties={"threshold": {"type": "number", "default": 0.3, "minimum": 0.01, "maximum": 1,
                                  "description": "Scene-change sensitivity 0.01-1. Lower = more cuts found. Default 0.3."}}),
    ToolSpec(
        name="ve_extract_frame",
        description=("Save one still image (png or jpg) from a video at a given time. Use ve_contact_sheet "
                     "for many frames at once."),
        handler=extract_frame,
        properties={"time": tprop("Time of the frame. Default 0."),
                    "format": {"type": "string", "enum": ["png", "jpg"], "default": "png",
                               "description": "Image format. png = lossless, jpg = smaller."}}),
]
