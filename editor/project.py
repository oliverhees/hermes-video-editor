"""Projects: validation, render graph (clips played back to back) and save/load."""
from __future__ import annotations

import json
import math
import os
import re
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
        entry = {"path": path, "in": a, "out": b, "info": info}
        if isinstance(c.get("tf"), dict):
            entry["tf"] = clean_tf(c["tf"])
        out.append(entry)
    return out


ASPECTS = {"16:9": (16, 9), "9:16": (9, 16), "1:1": (1, 1), "4:5": (4, 5)}
SHORTS = (360, 480, 720, 1080, 1440, 2160)
BG_MODES = ("blur", "black", "color")
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _jsround(x: float) -> int:
    """Math.round of JavaScript (halves go up), so the preview and the render agree to the pixel."""
    return int(math.floor(x + 0.5))


def _even(n: float) -> int:
    return max(2, _jsround(n / 2.0) * 2)


def sanitize_canvas(raw: Any) -> Dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    aspect = raw.get("aspect") if raw.get("aspect") in ASPECTS else "auto"
    short = raw.get("short") if raw.get("short") in SHORTS else 1080
    return {"aspect": aspect, "short": short}


def sanitize_bg(raw: Any) -> Dict[str, str]:
    raw = raw if isinstance(raw, dict) else {}
    mode = raw.get("mode") if raw.get("mode") in BG_MODES else "blur"
    color = raw.get("color") if isinstance(raw.get("color"), str) and COLOR_RE.match(raw.get("color")) else "#000000"
    return {"mode": mode, "color": color}


def clean_tf(tf: Any) -> Dict[str, float]:
    """Per-clip transform: s = scale relative to 'fit inside the canvas', x/y = centre offset as a fraction of the canvas."""
    tf = tf if isinstance(tf, dict) else {}

    def num(v: Any, default: float, lo: float, hi: float) -> float:
        try:
            f = float(v)
        except (TypeError, ValueError):
            return default
        return default if math.isnan(f) or math.isinf(f) else max(lo, min(hi, f))
    return {"s": num(tf.get("s"), 1.0, 0.05, 10.0), "x": num(tf.get("x"), 0.0, -3.0, 3.0), "y": num(tf.get("y"), 0.0, -3.0, 3.0)}


def canvas_size(aspect: str, short: int, first_w: int = 1280, first_h: int = 720) -> Tuple[int, int]:
    if aspect not in ASPECTS:
        return _even(first_w), _even(first_h)
    aw, ah = ASPECTS[aspect]
    sh = short if short in SHORTS else 1080
    return (_even(sh * aw / ah), _even(sh)) if aw >= ah else (_even(sh), _even(sh * ah / aw))


def fg_rect(iw: int, ih: int, W: int, H: int, tf: Any) -> Tuple[int, int, int, int]:
    """Where the picture sits on the canvas: (x, y, w, h). Identical to fgRect() in editor/web/timeline.js."""
    t = clean_tf(tf)
    f = min(W / float(iw), H / float(ih))
    w, h = _even(iw * f * t["s"]), _even(ih * f * t["s"])
    return (_jsround(W / 2.0 + t["x"] * W - w / 2.0), _jsround(H / 2.0 + t["y"] * H - h / 2.0), w, h)


def canvas_for(clips: List[Dict[str, Any]], canvas: Any = None) -> Tuple[int, int, float]:
    """Width, height, fps of the output. 'auto' takes the size of the first clip that has video."""
    cv = sanitize_canvas(canvas)
    fw, fh, fps = 1280, 720, 30.0
    for c in clips:
        v = c["info"].get("video")
        if v:
            fw, fh, fps = v["display_width"] or 1280, v["display_height"] or 720, round(v.get("fps") or 30.0, 2)
            break
    w, h = canvas_size(cv["aspect"], cv["short"], fw // 2 * 2, fh // 2 * 2)
    return max(2, w), max(2, h), fps


def _color_source(bg: Dict[str, str], W: int, H: int, fps: Any, d: float, label: str) -> str:
    colour = "0x" + bg["color"][1:] if bg["mode"] == "color" else "black"
    return "color=c=%s:s=%dx%d:r=%s:d=%.3f,format=yuv420p,setsar=1[%s]" % (colour, W, H, fps, d, label)


def video_chain(i: int, c: Dict[str, Any], W: int, H: int, fps: Any, d: float, bg: Dict[str, str]) -> List[str]:
    """Filter pieces that turn input i into a W x H picture of duration d with the clip's transform applied."""
    v = c["info"].get("video")
    if not v:                                                  # audio-only clip: just the background
        return [_color_source(bg, W, H, fps, d, "v%d" % i)]
    iw, ih = v["display_width"], v["display_height"]
    x, y, w, h = fg_rect(iw, ih, W, H, c.get("tf"))
    tail = "setsar=1,format=yuv420p,trim=duration=%.3f,setpts=PTS-STARTPTS" % d
    base = "[%d:v:0]setpts=PTS-STARTPTS,fps=%s" % (i, fps)
    if (x, y, w, h) == (0, 0, W, H):                           # the picture fills the canvas exactly
        return ["%s,scale=%d:%d,%s[v%d]" % (base, W, H, tail, i)]
    vx0, vy0, vx1, vy1 = max(0, -x), max(0, -y), min(w, W - x), min(h, H - y)
    if vx1 - vx0 < 2 or vy1 - vy0 < 2:                         # completely off canvas
        return [_color_source(bg, W, H, fps, d, "v%d" % i)]
    vw, vh = vx1 - vx0, vy1 - vy0
    crop = ""                                                  # only decode/scale what is visible (zoomed-in pictures stay cheap)
    if (vx0, vy0, vw, vh) != (0, 0, w, h):
        crop = "crop=%d:%d:%d:%d," % (max(2, _jsround(iw * vw / float(w))), max(2, _jsround(ih * vh / float(h))),
                                       _jsround(iw * vx0 / float(w)), _jsround(ih * vy0 / float(h)))
    ox, oy = max(x, 0), max(y, 0)
    covers = x <= 0 and y <= 0 and x + w >= W and y + h >= H
    if bg["mode"] == "blur" and not covers:
        bw, bh = max(8, W // 8), max(8, H // 8)
        r = max(1, min(4, bw // 4, bh // 4))
        return ["%s,split[b%d][f%d]" % (base, i, i),
                "[b%d]scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,boxblur=%d:2,scale=%d:%d:flags=bicubic,setsar=1[g%d]"
                % (i, bw, bh, bw, bh, r, W, H, i),
                "[f%d]%sscale=%d:%d[h%d]" % (i, crop, vw, vh, i),
                "[g%d][h%d]overlay=%d:%d:format=auto,%s[v%d]" % (i, i, ox, oy, tail, i)]
    return [_color_source(bg, W, H, fps, d, "g%d" % i),
            "%s,%sscale=%d:%d[h%d]" % (base, crop, vw, vh, i),
            "[g%d][h%d]overlay=%d:%d:format=auto:shortest=0,%s[v%d]" % (i, i, ox, oy, tail, i)]


def build_render_graph(clips: List[Dict[str, Any]], width: int, height: int, fps: float,
                       bg: Any = None) -> Tuple[List[str], str, bool]:
    """Pure: ffmpeg input args and a filter_complex that plays all clips back to back. Returns (inputs, graph, has_audio)."""
    bgs = sanitize_bg(bg)
    any_audio = any(c["info"]["has_audio"] for c in clips)
    inputs: List[str] = []
    parts: List[str] = []
    labels = ""
    for i, c in enumerate(clips):
        d = c["out"] - c["in"]
        inputs += ["-ss", "%.3f" % c["in"], "-t", "%.3f" % d, "-i", c["path"]]
        parts += video_chain(i, c, width, height, fps, d, bgs)
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


def render_project(clips: List[Dict[str, Any]], out_dir: Path, crf: int = 20, timeout: int = 3600,
                   canvas: Any = None, bg: Any = None) -> Path:
    """Render the sequence to <first clip name>_project.mp4 in out_dir. Inputs are never modified."""
    width, height, fps = canvas_for(clips, canvas)
    inputs, graph, has_audio = build_render_graph(clips, width, height, fps, bg)
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
            item = {"id": str(c.get("id"))[:40], "asset": str(c["asset"]), "in": float(c["in"]), "out": float(c["out"])}
            if isinstance(c.get("tf"), dict):
                item["tf"] = clean_tf(c["tf"])
            clean_clips.append(item)
        except (KeyError, TypeError, ValueError):
            raise ToolError("A clip has invalid times.")
    return {"version": 1, "name": str(obj.get("name") or "")[:120], "assets": clean_assets, "clips": clean_clips,
            "canvas": sanitize_canvas(obj.get("canvas")), "bg": sanitize_bg(obj.get("bg"))}


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
