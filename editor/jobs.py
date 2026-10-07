"""Background jobs for the editor: preview preparation (proxy, waveform, thumbnails) and the export pipeline."""
from __future__ import annotations

import array
import hashlib
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..core.ffmpeg import has_encoder, probe, run_ffmpeg
from ..core.result import ToolError
from ..platform_rules import PLATFORM_RULES

CACHE_ROOT = Path(tempfile.gettempdir()) / "hermes-video-editor-cache"
BROWSER_VIDEO = {"h264", "vp8", "vp9"}
BROWSER_AUDIO = {"aac", "mp3", "opus", "vorbis"}
BROWSER_EXTS = {".mp4", ".m4v", ".mov", ".webm"}


class Job:
    def __init__(self, kind: str) -> None:
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind
        self.state = "running"
        self.progress = 0.0
        self.step = ""
        self.result: Dict[str, Any] = {}
        self.error: Optional[Dict[str, str]] = None
        self.created = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "kind": self.kind, "state": self.state, "progress": round(self.progress, 3),
                "step": self.step, "result": self.result, "error": self.error}


class JobRegistry:
    def __init__(self, keep: int = 40) -> None:
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.Lock()
        self._keep = keep

    def start(self, kind: str, target: Callable[[Job], None]) -> Job:
        job = Job(kind)
        with self._lock:
            self._jobs[job.id] = job
            for old in sorted(self._jobs.values(), key=lambda j: j.created)[:-self._keep]:
                self._jobs.pop(old.id, None)

        def runner() -> None:
            try:
                target(job)
                job.state = "done"
                job.progress = 1.0
            except ToolError as exc:
                job.state, job.error = "error", {"error": exc.message, "hint": exc.hint or ""}
            except Exception as exc:  # noqa: BLE001 - never kill the server thread
                job.state, job.error = "error", {"error": "%s: %s" % (type(exc).__name__, exc), "hint": ""}

        threading.Thread(target=runner, daemon=True).start()
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)


# --------------------------------------------------------------------------- preview preparation
def cache_id(path: Path) -> str:
    st = path.stat()
    return hashlib.sha1(("%s|%d|%d" % (path, st.st_mtime_ns, st.st_size)).encode("utf-8")).hexdigest()[:16]


def cache_dir(cid: str) -> Path:
    d = CACHE_ROOT / cid
    d.mkdir(parents=True, exist_ok=True)
    return d


def playback_plan(path: Path, info: Dict[str, Any], client_h264: bool) -> str:
    """'original' when the browser can play the file as it is, else 'h264' / 'vp8' proxy (or 'none' for audio-only)."""
    if not info["has_video"]:
        return "original"
    v = info["video"]
    a_ok = (not info["has_audio"]) or info["audio"][0].get("codec") in BROWSER_AUDIO
    direct = (path.suffix.lower() in BROWSER_EXTS and v.get("codec") in BROWSER_VIDEO and a_ok
              and (v.get("pix_fmt") or "yuv420p") in ("yuv420p", "yuvj420p") and not v.get("rotation"))
    if direct and (client_h264 or v.get("codec") != "h264"):
        return "original"
    return "h264" if client_h264 else "vp8"


def make_proxy(src: Path, info: Dict[str, Any], dest: Path, kind: str, timeout: int = 1800) -> None:
    height = min(720, (info["video"] or {}).get("display_height") or 720) // 2 * 2
    vf = "scale=-2:%d" % height
    ff = ["-y", "-i", str(src), "-map", "0:v:0", "-map", "0:a:0?", "-vf", vf]
    if kind == "h264":
        ff += ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "27", "-pix_fmt", "yuv420p", "-g", "24",
               "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart"]
    else:
        if not has_encoder("libvpx"):
            raise ToolError("Preview needs H.264 or VP8 support; this browser has no H.264 and FFmpeg has no libvpx.",
                            hint="Editing still works; the preview is unavailable.")
        ff += ["-c:v", "libvpx", "-b:v", "1500k", "-quality", "realtime", "-cpu-used", "8", "-g", "24",
               "-pix_fmt", "yuv420p", "-c:a", "libvorbis", "-b:a", "96k"]
    tmp = dest.with_name("tmp_" + dest.name)
    run_ffmpeg(ff + [str(tmp)], timeout)
    os.replace(str(tmp), str(dest))


def make_waveform(src: Path, duration: float, dest: Path, timeout: int = 600) -> List[float]:
    if dest.is_file():
        return json.loads(dest.read_text())
    count = int(max(200, min(6000, duration * 12)))
    with tempfile.TemporaryDirectory(prefix="ve_wave_") as tmp:
        pcm = Path(tmp) / "a.pcm"
        run_ffmpeg(["-y", "-i", str(src), "-vn", "-map", "0:a:0", "-ac", "1", "-ar", "8000", "-f", "s16le",
                    str(pcm)], timeout)
        samples = array.array("h")
        with open(str(pcm), "rb") as fh:
            samples.frombytes(fh.read())
    if not len(samples):
        return []
    if sys.byteorder == "big":
        samples.byteswap()
    per = max(1, len(samples) // count)
    peaks = []
    for i in range(0, len(samples), per):
        chunk = samples[i:i + per]
        peaks.append(max(max(chunk), -min(chunk)) / 32768.0)
    top = max(peaks) or 1.0
    out = [round(p / top, 3) for p in peaks]
    dest.write_text(json.dumps(out))
    return out


def make_thumbs(src: Path, duration: float, dest: Path, timeout: int = 600) -> int:
    n = int(max(8, min(80, round(duration / 2.0))))
    if not dest.is_file():
        vf = "fps=%.6f,scale=160:90:force_original_aspect_ratio=increase,crop=160:90,tile=%dx1" % (n / duration, n)
        run_ffmpeg(["-y", "-ss", "%.3f" % (duration / (2.0 * n)), "-i", str(src), "-map", "0:v:0", "-an", "-vf", vf,
                    "-frames:v", "1", "-q:v", "5", str(dest)], timeout)
    return n


def prepare(job: Job, src: Path, client_h264: bool) -> None:
    info = probe(src)
    cid = cache_id(src)
    d = cache_dir(cid)
    dur = info["duration_s"] or 0.0
    job.result = {"cache_id": cid, "duration_s": dur, "has_video": info["has_video"], "has_audio": info["has_audio"],
                  "info": info, "playback": None, "waveform": None, "thumbs": None}
    plan = playback_plan(src, info, client_h264)
    if plan == "original":
        job.result["playback"] = {"kind": "original"}
    job.step = "waveform"
    if info["has_audio"] and dur:
        job.result["waveform"] = make_waveform(src, dur, d / "waveform.json")
    job.progress = 0.25
    job.step = "thumbnails"
    if info["has_video"] and dur:
        try:
            n = make_thumbs(src, dur, d / "thumbs.jpg")
            job.result["thumbs"] = {"name": "thumbs.jpg", "count": n}
        except ToolError:
            job.result["thumbs"] = None
    job.progress = 0.5
    if plan != "original":
        job.step = "preview"
        name = "proxy.mp4" if plan == "h264" else "proxy.webm"
        if not (d / name).is_file():
            make_proxy(src, info, d / name, plan)
        job.result["playback"] = {"kind": "proxy", "name": name}


# --------------------------------------------------------------------------- export pipeline
ASPECT_REFRAME = {"crop_9x16": ("ve_crop_to_aspect", {"aspect": "9:16"}),
                  "blur_9x16": ("ve_pad_blur_background", {"width": 1080, "height": 1920}),
                  "crop_1x1": ("ve_crop_to_aspect", {"aspect": "1:1"}),
                  "crop_4x5": ("ve_crop_to_aspect", {"aspect": "4:5"}),
                  "crop_16x9": ("ve_crop_to_aspect", {"aspect": "16:9"})}
SPEEDS = (0.5, 0.75, 1.0, 1.25, 1.5, 2.0)


def build_steps(req: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Pure: turn an export request into an ordered list of tool calls."""
    steps: List[Dict[str, Any]] = []
    cuts = req.get("cuts") or []
    if cuts:
        steps.append({"label": "Removing cuts", "tool": "ve_remove_segments",
                      "args": {"segments": [{"start": float(a), "end": float(b)} for a, b in cuts]}})
    speed = float(req.get("speed") or 1.0)
    if speed != 1.0:
        steps.append({"label": "Changing speed", "tool": "ve_change_speed", "args": {"factor": speed}})
    reframe = req.get("reframe") or "none"
    if reframe != "none":
        tool, base = ASPECT_REFRAME[reframe]
        args = dict(base)
        if tool == "ve_crop_to_aspect" and req.get("anchor") in ("center", "left", "right", "top", "bottom"):
            args["anchor"] = req["anchor"]
        steps.append({"label": "Reframing", "tool": tool, "args": args})
    if req.get("loudness") is not None:
        steps.append({"label": "Normalising loudness", "tool": "ve_normalize_loudness",
                      "args": {"target_lufs": float(req["loudness"]), "verify": False}})
    if req.get("preset"):
        steps.append({"label": "Exporting for %s" % req["preset"], "tool": "ve_export_preset",
                      "args": {"preset": req["preset"]}})
    return steps


def validate_export(req: Dict[str, Any]) -> None:
    from ..tools.export import EXPORT_PRESETS
    for pair in req.get("cuts") or []:
        if not (isinstance(pair, (list, tuple)) and len(pair) == 2 and all(isinstance(x, (int, float)) for x in pair)
                and 0 <= pair[0] < pair[1]):
            raise ToolError("Each cut must be [start, end] in seconds with end > start.")
    if float(req.get("speed") or 1.0) not in SPEEDS:
        raise ToolError("speed must be one of %s" % list(SPEEDS))
    if (req.get("reframe") or "none") not in ["none"] + list(ASPECT_REFRAME):
        raise ToolError("Unknown reframe option.")
    if req.get("preset") and req["preset"] not in EXPORT_PRESETS:
        raise ToolError("Unknown preset.")
    if req.get("loudness") is not None and not (-40 <= float(req["loudness"]) <= -5):
        raise ToolError("loudness must be between -40 and -5 LUFS.")


def run_export(job: Job, src: Path, req: Dict[str, Any], final_dir: Path) -> None:
    from ..schemas import TOOLS
    handlers = {t["name"]: t["handler"] for t in TOOLS}
    steps = build_steps(req)
    if not steps:
        raise ToolError("Nothing to export: add a cut, change speed/format, or pick a preset.")
    tmp = Path(tempfile.mkdtemp(prefix="ve_export_"))
    current, result = src, None
    try:
        for i, step in enumerate(steps):
            job.step = step["label"]
            job.progress = i / float(len(steps))
            last = i == len(steps) - 1
            args = dict(step["args"], input=str(current), output_dir=str(final_dir if last else tmp),
                        timeout_s=3600)
            raw = json.loads(handlers[step["tool"]](args))
            if not raw.get("ok"):
                raise ToolError(raw.get("error", "Step failed"), raw.get("hint"), raw.get("ffmpeg_stderr_tail"))
            result, current = raw, Path(raw["output"])
    finally:
        shutil.rmtree(str(tmp), ignore_errors=True)
    out = result["output"]
    summary: Dict[str, Any] = {"output": out, "duration_s": result.get("duration_s"),
                               "size_bytes": os.path.getsize(out), "steps": [s["label"] for s in steps],
                               "platform_check": None}
    if req.get("preset") in PLATFORM_RULES:
        check = json.loads(handlers["ve_platform_check"]({"input": out, "platform": req["preset"]}))
        if check.get("ok"):
            summary["platform_check"] = check["info"]
    job.result = summary
