"""B. Cut & time tools."""
from __future__ import annotations

from typing import Any, Dict

from ..core.ffmpeg import Job, encode_args, even_filter, output_ext, tool_handler
from ..core.result import ToolError
from ..core.spec import ToolSpec
from ..core.timeparse import format_time
from ..core.validate import get_choice, get_num, get_time


def build_trim_args(src: str, start: float, duration: Any, mode: str, ext: str, crf: int,
                    has_audio: bool, vf: Any = None) -> list:
    """Pure function: ffmpeg arguments (without output path) for ve_trim."""
    args = ["-ss", "%.3f" % start, "-i", src]
    if duration is not None:
        args += ["-t", "%.3f" % duration]
    args += ["-map", "0:v:0", "-map", "0:a?"]
    if mode == "fast":
        args += ["-c", "copy", "-avoid_negative_ts", "make_zero"]
        if ext in (".mp4", ".mov", ".m4v"):
            args += ["-movflags", "+faststart"]
    else:
        if vf:
            args += ["-vf", vf]
        args += encode_args(ext, crf=crf, audio=has_audio)
    return args


@tool_handler
def trim(args: Dict[str, Any]) -> Any:
    start = get_time(args, "start", 0.0)
    end = get_time(args, "end")
    duration = get_time(args, "duration")
    mode = get_choice(args, "mode", ("accurate", "fast"), "accurate")
    crf = int(get_num(args, "crf", 20, lo=0, hi=51, integer=True))
    if end is not None and duration is not None:
        raise ToolError("Give either 'end' or 'duration', not both.")
    if end is not None and end <= start:
        raise ToolError("'end' (%s) must be greater than 'start' (%s)." % (end, start))
    if duration is not None and duration <= 0:
        raise ToolError("'duration' must be > 0.")
    job = Job(args, "trim", ext=None, need_video=True)
    ext = job.src.suffix.lower() if mode == "fast" else output_ext(job.src)
    job.out = job.out.with_suffix(ext) if not args.get("output") else job.out
    total = job.info["duration_s"]
    if total is not None and start >= total:
        raise ToolError("'start' (%.2fs) is at or beyond the clip length (%.2fs)." % (start, total),
                        hint="Run ve_media_probe for the duration.")
    if end is not None:
        duration = end - start
    if duration is not None and total is not None:
        duration = min(duration, total - start)
    job.run(build_trim_args(str(job.src), start, duration, mode, ext, crf, job.info["has_audio"],
                                even_filter(job.info)))
    return job.done(op="trim", mode=mode, start=format_time(start), requested_duration_s=duration)


SPECS = [
    ToolSpec(
        name="ve_trim",
        description=("Keep one section of a video: from 'start' to 'end' (or start + 'duration'), all "
                     "in seconds or MM:SS / HH:MM:SS. mode 'accurate' (default) re-encodes with frame-exact "
                     "cuts; mode 'fast' stream-copies (instant, lossless, but cuts snap to keyframes). "
                     "Use ve_split to cut into several parts and ve_remove_segments to delete middle sections."),
        handler=trim,
        properties={
            "start": {"type": ["number", "string"], "default": 0,
                      "description": "Start time. Seconds (12.5) or MM:SS or HH:MM:SS(.ms). Default 0."},
            "end": {"type": ["number", "string"],
                    "description": "End time (same formats). Exclusive with 'duration'. Default: end of clip."},
            "duration": {"type": ["number", "string"],
                         "description": "Length to keep after 'start' (same formats). Exclusive with 'end'."},
            "mode": {"type": "string", "enum": ["accurate", "fast"], "default": "accurate",
                     "description": "accurate = re-encode, frame-exact; fast = stream copy, keyframe-snapped."},
            "crf": {"type": "integer", "minimum": 0, "maximum": 51, "default": 20,
                    "description": "H.264 quality for accurate mode (lower = better/larger). Default 20."},
        }),
]
