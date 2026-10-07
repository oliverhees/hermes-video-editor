"""Locate ffmpeg/ffprobe, run them safely, probe media, and drive single-output edits."""
from __future__ import annotations

import functools
import json
import re
import shutil
import subprocess
import time
import traceback
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .paths import plan_output, resolve_input
from .result import ToolError, fail, ok
from .validate import get_bool, get_timeout

INSTALL_HINT = ("Install FFmpeg: Linux `sudo apt install ffmpeg`, macOS `brew install ffmpeg`, "
                "Windows `winget install Gyan.FFmpeg`. Then restart Hermes.")
VIDEO_EXTS_COPYABLE = (".mp4", ".mov", ".mkv", ".m4v")


# --------------------------------------------------------------------------- binaries
def find_binary(name: str) -> str:
    found = shutil.which(name)
    if not found:
        raise ToolError("%s not found on PATH." % name, hint=INSTALL_HINT)
    return found


# --------------------------------------------------------------------------- errors
_ERROR_MAP = [
    (r"No such filter: '?(\w+)", "This FFmpeg build lacks the '%s' filter.",
     "Install a full FFmpeg build (e.g. Gyan 'full' on Windows, distro ffmpeg on Linux)."),
    (r"Unknown encoder '?([\w-]+)", "This FFmpeg build lacks the '%s' encoder.",
     "Install a full FFmpeg build with libx264/aac."),
    (r"Invalid data found when processing input", "Input is not a valid or complete media file.", None),
    (r"moov atom not found", "Input file is truncated or corrupt (moov atom missing).", None),
    (r"No space left on device", "Disk full.", "Free disk space or use output_dir on another drive."),
    (r"Permission denied", "Permission denied while reading/writing a file.",
     "Check file permissions and that the output is not open in another program."),
    (r"Output file .* does not contain any stream", "Nothing to write: selected streams do not exist.", None),
    (r"Stream specifier .* matches no streams|Stream map .* matches no streams",
     "A required stream (video or audio) is missing in the input.",
     "Run ve_media_probe to see which streams exist."),
    (r"Error (parsing|initializing) filter|Error reinitializing filters|Invalid argument",
     "FFmpeg rejected the filter/arguments.", "Check parameter values (ranges, even sizes, units)."),
]


def stderr_tail(text: str, lines: int = 12, chars: int = 1500) -> str:
    tail = "\n".join(text.strip().splitlines()[-lines:])
    return tail[-chars:]


def map_error(stderr: str) -> ToolError:
    for pattern, message, hint in _ERROR_MAP:
        m = re.search(pattern, stderr)
        if m:
            msg = message % m.group(1) if "%s" in message else message
            return ToolError(msg, hint=hint, stderr_tail=stderr_tail(stderr))
    return ToolError("FFmpeg failed.", hint="See ffmpeg_stderr_tail.", stderr_tail=stderr_tail(stderr))


# --------------------------------------------------------------------------- runner
class Proc:
    def __init__(self, returncode: int, stdout: str, stderr: str) -> None:
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


def run_binary(binary: str, args: List[str], timeout_s: float, check: bool = True) -> Proc:
    """subprocess.run with a list (never shell=True); kills the process on timeout."""
    cmd = [find_binary(binary)] + [str(a) for a in args]
    try:
        cp = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=timeout_s)
    except subprocess.TimeoutExpired as exc:
        err = (exc.stderr or b"").decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else ""
        raise ToolError("%s timed out after %ss and was killed." % (binary, timeout_s),
                        hint="Increase timeout_s or use a shorter clip / faster settings.",
                        stderr_tail=stderr_tail(err))
    except OSError as exc:
        raise ToolError("Could not start %s: %s" % (binary, exc), hint=INSTALL_HINT)
    proc = Proc(cp.returncode, cp.stdout.decode("utf-8", "replace"), cp.stderr.decode("utf-8", "replace"))
    if check and proc.returncode != 0:
        raise map_error(proc.stderr)
    return proc


def run_ffmpeg(args: List[str], timeout_s: float = 600, loglevel: str = "error",
               check: bool = True) -> Proc:
    base = ["-hide_banner", "-nostdin", "-nostats", "-loglevel", loglevel]
    return run_binary("ffmpeg", base + [str(a) for a in args], timeout_s, check)


# --------------------------------------------------------------------------- probe
def _fps(stream: Dict[str, Any]) -> Optional[float]:
    for key in ("avg_frame_rate", "r_frame_rate"):
        raw = stream.get(key) or "0/0"
        try:
            val = Fraction(raw)
        except (ValueError, ZeroDivisionError):
            continue
        if val > 0:
            return round(float(val), 3)
    return None


def _rotation(stream: Dict[str, Any]) -> int:
    rot = stream.get("tags", {}).get("rotate")
    for side in stream.get("side_data_list", []) or []:
        if "rotation" in side:
            rot = side["rotation"]
    try:
        return int(float(rot)) % 360 if rot is not None else 0
    except (TypeError, ValueError):
        return 0


def _num(value: Any, cast: Callable[[Any], Any] = float) -> Any:
    try:
        return cast(value)
    except (TypeError, ValueError):
        return None


def summarize_probe(raw: Dict[str, Any], path: Path) -> Dict[str, Any]:
    fmt = raw.get("format", {})
    video = None
    audio = []
    subs = 0
    for s in raw.get("streams", []):
        kind = s.get("codec_type")
        if kind == "video" and not s.get("disposition", {}).get("attached_pic") and video is None:
            w, h, rot = s.get("width"), s.get("height"), _rotation(s)
            dw, dh = (h, w) if rot in (90, 270) else (w, h)
            video = {"index": s.get("index"), "codec": s.get("codec_name"), "width": w, "height": h,
                     "display_width": dw, "display_height": dh, "fps": _fps(s), "rotation": rot,
                     "pix_fmt": s.get("pix_fmt"), "bit_rate": _num(s.get("bit_rate"), int),
                     "duration_s": _num(s.get("duration"))}
        elif kind == "audio":
            audio.append({"index": s.get("index"), "codec": s.get("codec_name"),
                          "channels": s.get("channels"), "sample_rate": _num(s.get("sample_rate"), int),
                          "bit_rate": _num(s.get("bit_rate"), int),
                          "language": s.get("tags", {}).get("language"),
                          "duration_s": _num(s.get("duration"))})
        elif kind == "subtitle":
            subs += 1
    duration = _num(fmt.get("duration"))
    if duration is None:
        cands = [x for x in [video and video["duration_s"]] + [a["duration_s"] for a in audio] if x]
        duration = max(cands) if cands else None
    return {"path": str(path), "format": fmt.get("format_name"), "duration_s": duration,
            "size_bytes": _num(fmt.get("size"), int), "bit_rate": _num(fmt.get("bit_rate"), int),
            "has_video": video is not None, "has_audio": bool(audio), "video": video,
            "audio": audio, "subtitle_streams": subs}


def probe(path: Path, timeout_s: float = 60) -> Dict[str, Any]:
    proc = run_binary("ffprobe", ["-v", "error", "-print_format", "json", "-show_format",
                                  "-show_streams", str(path)], timeout_s, check=False)
    if proc.returncode != 0:
        raise ToolError("Not a readable media file: %s" % path,
                        hint="Check that the file is a valid video/audio file.",
                        stderr_tail=stderr_tail(proc.stderr))
    try:
        raw = json.loads(proc.stdout or "{}")
    except ValueError:
        raise ToolError("ffprobe returned unreadable output for %s" % path)
    info = summarize_probe(raw, path)
    if not info["has_video"] and not info["has_audio"]:
        raise ToolError("No audio or video stream found in %s" % path,
                        hint="This does not look like a media file.")
    return info


# --------------------------------------------------------------------------- encoding helpers
def output_ext(src: Path, force_mp4: bool = False) -> str:
    """Container extension safe for libx264+aac: keep mp4/mov/mkv/m4v, else .mp4."""
    ext = src.suffix.lower()
    return ext if (ext in VIDEO_EXTS_COPYABLE and not force_mp4) else ".mp4"


def encode_args(ext: str, crf: int = 20, preset: str = "veryfast", audio: bool = True) -> List[str]:
    args = ["-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p"]
    if audio:
        args += ["-c:a", "aac", "-b:a", "192k"]
    if ext in (".mp4", ".mov", ".m4v"):
        args += ["-movflags", "+faststart"]
    return args


def even_filter(info: Dict[str, Any]) -> Optional[str]:
    """Scale filter that rounds odd dimensions down to even (yuv420p/libx264 need it)."""
    v = info.get("video") or {}
    if (v.get("display_width") or 0) % 2 or (v.get("display_height") or 0) % 2:
        return "scale=trunc(iw/2)*2:trunc(ih/2)*2"
    return None


# --------------------------------------------------------------------------- job
class Job:
    """One validated input -> one output. Handles naming, running, cleanup, result."""

    def __init__(self, args: Dict[str, Any], op: str, ext: Optional[str] = None,
                 need_video: bool = False, need_audio: bool = False, key: str = "input") -> None:
        self.args = args
        self.started = time.time()
        self.timeout = get_timeout(args)
        self.overwrite = get_bool(args, "overwrite", False)
        self.src = resolve_input(args.get(key), key)
        self.info = probe(self.src)
        if need_video and not self.info["has_video"]:
            raise ToolError("Input has no video stream.", hint="Use an audio tool, or pick a video file.")
        if need_audio and not self.info["has_audio"]:
            raise ToolError("Input has no audio stream.",
                            hint="This clip is silent; skip audio tools or add audio first (ve_replace_audio).")
        self.out = plan_output(self.src, op, ext or self.src.suffix, args.get("output"),
                               args.get("output_dir"), self.overwrite)

    def run(self, ff_args: List[str], loglevel: str = "error") -> None:
        """Run ffmpeg writing to self.out. ff_args must not contain the output path."""
        flag = "-y" if self.overwrite else "-n"
        try:
            run_ffmpeg([flag] + ff_args + [str(self.out)], self.timeout, loglevel)
        except ToolError:
            self._cleanup()
            raise
        if not self.out.exists() or self.out.stat().st_size == 0:
            self._cleanup()
            raise ToolError("FFmpeg finished but produced no output.", hint="Check parameters.")

    def _cleanup(self) -> None:
        try:
            if self.out.exists():
                self.out.unlink()
        except OSError:
            pass

    def done(self, **extra: Any) -> Dict[str, Any]:
        """Probe the output and build the ok() payload."""
        try:
            out_info = probe(self.out)
        except ToolError:
            out_info = {}
        info = {"input": str(self.src), "elapsed_s": round(time.time() - self.started, 2),
                "width": (out_info.get("video") or {}).get("width"),
                "height": (out_info.get("video") or {}).get("height"),
                "fps": (out_info.get("video") or {}).get("fps"),
                "has_audio": out_info.get("has_audio"), "size_bytes": out_info.get("size_bytes")}
        info.update(extra)
        return {"output": str(self.out), "duration_s": out_info.get("duration_s"), "info": info}


# --------------------------------------------------------------------------- handler wrapper
def tool_handler(fn: Callable[[Dict[str, Any]], Any]) -> Callable[..., str]:
    """Wrap fn(args)->dict|str into handler(args, **kwargs)->JSON string. Never raises."""
    @functools.wraps(fn)
    def handler(args: Any = None, **kwargs: Any) -> str:
        try:
            if args is None:
                args = {}
            if not isinstance(args, dict):
                raise ToolError("Tool arguments must be an object/dict.")
            result = fn(args)
            return result if isinstance(result, str) else ok(**result)
        except ToolError as exc:
            return fail(exc.message, exc.hint, exc.stderr_tail, **exc.extra)
        except Exception as exc:  # noqa: BLE001 - the agent must never see a raised exception
            return fail("Unexpected error: %s: %s" % (type(exc).__name__, exc),
                        hint="This is a bug in the plugin; please report it.",
                        ffmpeg_stderr_tail=stderr_tail(traceback.format_exc(), lines=6))
    return handler
