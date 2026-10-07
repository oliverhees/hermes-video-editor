"""Projects: validation, render graph (clips played back to back) and save/load."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

from ..core.ffmpeg import (encode_args, filter_complex_args, probe, run_ffmpeg)
from ..core.paths import plan_output
from ..core.result import ToolError
from .security import inside, safe_dir, safe_media_file

PROJECT_SUFFIX = ".vproj.json"
MAX_CLIPS = 300
MAX_PROJECT_BYTES = 5 << 20


# --------------------------------------------------------------------------- clips for rendering
def sanitize_clips(raw: Any, roots: List[str]) -> List[Dict[str, Any]]:
    """Validate [{path, in, out}, ...] from the browser; clamp to the real file length; attach probe info."""
    if not isinstance(raw, list) or not raw:
        raise ToolError("The timeline is empty: add at least one clip.")
    if len(raw) > MAX_CLIPS:
        raise ToolError("Too many clips (limit %d)." % MAX_CLIPS)
    cache: Dict[str, Dict[str, Any]] = {}
    out = []
    for i, c in enumerate(raw):
        if not isinstance(c, dict):
            raise ToolError("Clip %d is invalid." % (i + 1))
        path = str(safe_media_file(c.get("path"), roots))
        if path not in cache:
            cache[path] = probe(Path(path))
        info = cache[path]
        try:
            a, b = float(c.get("in")), float(c.get("out"))
        except (TypeError, ValueError):
            raise ToolError("Clip %d needs numeric 'in' and 'out' times." % (i + 1))
        total = info["duration_s"] or b
        a, b = max(0.0, a), min(b, total)
        if b - a < 0.05:
            raise ToolError("Clip %d is shorter than 0.05 s after clamping to the file length." % (i + 1))
        out.append({"path": path, "in": a, "out": b, "info": info})
    return out


def canvas_for(clips: List[Dict[str, Any]]) -> Tuple[int, int, float]:
    """Width, height, fps of the output: taken from the first clip that has video."""
    for c in clips:
        v = c["info"].get("video")
        if v:
            w, h = (v["display_width"] or 1280) // 2 * 2, (v["display_height"] or 720) // 2 * 2
            return max(2, w), max(2, h), round(v.get("fps") or 30.0, 2)
    return 1280, 720, 30.0


def build_render_graph(clips: List[Dict[str, Any]], width: int, height: int, fps: float) -> Tuple[List[str], str, bool]:
    """Pure: ffmpeg input args and a filter_complex that plays all clips back to back. Returns (inputs, graph, has_audio)."""
    any_audio = any(c["info"]["has_audio"] for c in clips)
    inputs: List[str] = []
    parts: List[str] = []
    labels = ""
    for i, c in enumerate(clips):
        d = c["out"] - c["in"]
        inputs += ["-ss", "%.3f" % c["in"], "-t", "%.3f" % d, "-i", c["path"]]
        if c["info"]["has_video"]:
            parts.append("[%d:v:0]setpts=PTS-STARTPTS,scale=%d:%d:force_original_aspect_ratio=decrease,"
                         "pad=%d:%d:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=%s,format=yuv420p,trim=duration=%.3f,"
                         "setpts=PTS-STARTPTS[v%d]" % (i, width, height, width, height, fps, d, i))
        else:
            parts.append("color=c=black:s=%dx%d:r=%s:d=%.3f,format=yuv420p[v%d]" % (width, height, fps, d, i))
        labels += "[v%d]" % i
        if any_audio:
            if c["info"]["has_audio"]:
                parts.append("[%d:a:0]aresample=48000,aformat=channel_layouts=stereo,apad,atrim=duration=%.3f,"
                             "asetpts=PTS-STARTPTS[a%d]" % (i, d, i))
            else:
                parts.append("anullsrc=r=48000:cl=stereo:d=%.3f[a%d]" % (d, i))
            labels += "[a%d]" % i
    parts.append("%sconcat=n=%d:v=1:a=%d[vo]%s" % (labels, len(clips), int(any_audio), "[ao]" if any_audio else ""))
    return inputs, ";".join(parts), any_audio


def render_project(clips: List[Dict[str, Any]], out_dir: Path, crf: int = 20, timeout: int = 3600) -> Path:
    """Render the sequence to <first clip name>_project.mp4 in out_dir. Inputs are never modified."""
    width, height, fps = canvas_for(clips)
    inputs, graph, has_audio = build_render_graph(clips, width, height, fps)
    out = plan_output(Path(clips[0]["path"]), "project", ".mp4", None, str(out_dir), False)
    tmp = Path(tempfile.mkdtemp(prefix="ve_render_"))
    try:
        ff = ["-n"] + inputs + filter_complex_args(graph, tmp) + ["-map", "[vo]"]
        if has_audio:
            ff += ["-map", "[ao]"]
        ff += encode_args(".mp4", crf=crf, audio=has_audio)
        try:
            run_ffmpeg(ff + [str(out)], timeout)
        except ToolError:
            if out.exists():
                out.unlink()
            raise
    finally:
        shutil.rmtree(str(tmp), ignore_errors=True)
    if not out.exists() or out.stat().st_size == 0:
        raise ToolError("Rendering produced no output.")
    return out


# --------------------------------------------------------------------------- project files
def validate_project(obj: Any) -> Dict[str, Any]:
    """Keep only the fields we know; reject anything malformed."""
    if not isinstance(obj, dict) or obj.get("version") != 1:
        raise ToolError("Not a Video Editor project (version 1 expected).")
    assets, clips = obj.get("assets"), obj.get("clips")
    if not isinstance(assets, dict) or not isinstance(clips, list) or len(clips) > MAX_CLIPS or len(assets) > MAX_CLIPS:
        raise ToolError("Project is malformed.")
    clean_assets: Dict[str, Any] = {}
    for key, a in assets.items():
        if not isinstance(a, dict) or not isinstance(a.get("path"), str):
            raise ToolError("Asset '%s' is malformed." % key)
        clean_assets[str(key)[:40]] = {"path": a["path"], "name": str(a.get("name") or os.path.basename(a["path"]))[:200]}
    clean_clips = []
    for c in clips:
        if not isinstance(c, dict) or str(c.get("asset")) not in clean_assets:
            raise ToolError("A clip points to an asset that is not in the project.")
        try:
            clean_clips.append({"id": str(c.get("id"))[:40], "asset": str(c["asset"]), "in": float(c["in"]), "out": float(c["out"])})
        except (KeyError, TypeError, ValueError):
            raise ToolError("A clip has invalid times.")
    return {"version": 1, "name": str(obj.get("name") or "")[:120], "assets": clean_assets, "clips": clean_clips}


def project_path(raw: Any, roots: List[str], must_exist: bool) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise ToolError("Missing project path.")
    real = os.path.realpath(os.path.expanduser(raw))
    if not real.endswith(PROJECT_SUFFIX):
        real += PROJECT_SUFFIX if not real.endswith(".json") else ""
    if not real.endswith(PROJECT_SUFFIX):
        raise ToolError("Project files end with %s" % PROJECT_SUFFIX)
    if not inside(real, roots):
        raise ToolError("Project path is outside the folders the editor may access.")
    p = Path(real)
    if must_exist and not p.is_file():
        raise ToolError("Project file not found: %s" % raw)
    return p


def save_project(raw_path: Any, project: Any, roots: List[str]) -> str:
    p = project_path(raw_path, roots, False)
    data = validate_project(project)
    text = json.dumps(data, indent=1, ensure_ascii=False)
    if len(text.encode("utf-8")) > MAX_PROJECT_BYTES:
        raise ToolError("Project is too large.")
    safe_dir(str(p.parent), roots, create=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(str(tmp), str(p))
    return str(p)


def load_project(raw_path: Any, roots: List[str]) -> Dict[str, Any]:
    p = project_path(raw_path, roots, True)
    if p.stat().st_size > MAX_PROJECT_BYTES:
        raise ToolError("Project file is too large.")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        raise ToolError("Project file is not valid JSON.")
    out = validate_project(data)
    out["path"] = str(p)
    return out
