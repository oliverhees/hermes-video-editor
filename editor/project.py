"""Projects: validation, render graph (clips played back to back) and save/load."""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Tuple

from ..core.ffmpeg import (encode_args, filter_complex_args, probe, require_filter, run_ffmpeg)
from ..core.fonts import resolve_font
from ..core.paths import ff_escape_path, plan_output, unique_path
from ..core.result import ToolError
from .security import inside, safe_dir, safe_image_file, safe_media_file

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
        extra = clean_clip_fields(c)
        if extra.get("freeze"):                                # a still frame: only the picture at 'in' is used
            a = min(max(0.0, a), max(0.0, total - 0.1))
            b = a + 0.1
        else:
            a, b = max(0.0, a), min(b, total)
        if b - a < 0.05:
            raise ToolError("Clip %d is shorter than 0.05 s after clamping to the file length." % (i + 1))
        entry = {"path": path, "in": a, "out": b, "info": info}
        entry.update(extra)
        out.append(entry)
    return out


ASPECTS = {"16:9": (16, 9), "9:16": (9, 16), "1:1": (1, 1), "4:5": (4, 5)}
SHORTS = (360, 480, 720, 1080, 1440, 2160)
BG_MODES = ("blur", "black", "color", "gradient", "image")
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


def sanitize_bg(raw: Any, roots: Any = None) -> Dict[str, str]:
    """Background behind pictures that do not fill the canvas: blur, black, one colour, a two-colour gradient or a picture.
    Old modes keep the old two keys; gradient adds color2, image adds the (checked) picture path."""
    raw = raw if isinstance(raw, dict) else {}
    mode = raw.get("mode") if raw.get("mode") in BG_MODES else "blur"
    out = {"mode": mode, "color": _hex(raw.get("color"), "#000000")}
    if mode == "gradient":
        out["color2"] = _hex(raw.get("color2"), "#1b1464")
    elif mode == "image":
        path = raw.get("image")
        if roots is not None:
            path = str(safe_image_file(path, roots))
        elif not isinstance(path, str) or not path.strip():
            out["mode"] = "black"
            return out
        out["image"] = path
    return out


MAX_BGS = 100


def sanitize_bgsegs(raw: Any, roots: Any = None) -> List[Dict[str, Any]]:
    """Background strips: a background (same modes as the project background) for a free time range of the timeline."""
    if raw is None:
        return []
    if not isinstance(raw, list) or len(raw) > MAX_BGS:
        raise ToolError("'bgs' must be a list with at most %d entries." % MAX_BGS)
    out = []
    for b in raw:
        if not isinstance(b, dict):
            continue
        item = sanitize_bg(b, roots)
        item.update({"id": str(b.get("id") or "b")[:40], "start": _num(b.get("start"), 0.0, 0.0, 86400.0),
                     "dur": _num(b.get("dur"), 3.0, 0.1, 3600.0), "track": _track(b.get("track"))})
        out.append(item)
    return out


SRT_TIME = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)")


def parse_srt(text: str) -> List[Dict[str, Any]]:
    """Cues of an .srt file as [{start, end, text}] in seconds (text on one line, empty cues dropped)."""
    cues = []
    for block in re.split(r"\r?\n\s*\r?\n", text.strip()):
        lines = [ln for ln in block.splitlines() if ln.strip()]
        for k, ln in enumerate(lines):
            m = SRT_TIME.search(ln)
            if m:
                g = [int(x) for x in m.groups()]
                t0, t1 = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000.0, g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000.0
                body = CONTROL_RE.sub("", " ".join(" ".join(lines[k + 1:]).split()))
                if body and t1 > t0:
                    cues.append({"start": t0, "end": t1, "text": body[:500]})
                break
    return cues


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


TRANSITIONS = ("fade", "fadeblack", "fadewhite", "dissolve", "wipeleft", "wiperight", "slideleft", "slideright", "circleopen", "circleclose", "pixelize")


def clean_adj(adj: Any) -> Dict[str, Any]:
    """Per-clip look and sound: brightness -1..1, contrast/saturation 0..3 (1 = unchanged), volume in dB, mute, fades in seconds."""
    adj = adj if isinstance(adj, dict) else {}
    return {"br": _num(adj.get("br"), 0.0, -1.0, 1.0), "ct": _num(adj.get("ct"), 1.0, 0.0, 3.0), "sa": _num(adj.get("sa"), 1.0, 0.0, 3.0),
            "vol": _num(adj.get("vol"), 0.0, -60.0, 24.0), "mute": bool(adj.get("mute")),
            "fi": _num(adj.get("fi"), 0.0, 0.0, 30.0), "fo": _num(adj.get("fo"), 0.0, 0.0, 30.0)}


def adj_is_default(a: Dict[str, Any]) -> bool:
    return a == clean_adj({})


def clean_clip_fields(c: Dict[str, Any]) -> Dict[str, Any]:
    """The optional per-clip fields (transform, adjustments, speed, still frame, transition into this clip). Defaults are left out.
    Limits are identical to cleanClipExtras() in editor/web/timeline.js."""
    out: Dict[str, Any] = {}
    if isinstance(c.get("tf"), dict):
        out["tf"] = clean_tf(c["tf"])
    if isinstance(c.get("adj"), dict):
        adj = clean_adj(c["adj"])
        if not adj_is_default(adj):
            out["adj"] = adj
    sp = _num(c.get("sp"), 1.0, 0.25, 4.0)
    if abs(sp - 1.0) > 1e-6:
        out["sp"] = sp
    fr = _num(c.get("freeze"), 0.0, 0.0, 30.0)
    if fr >= 0.1:
        out["freeze"] = fr
    tr = c.get("tr")
    if isinstance(tr, dict) and tr.get("type") in TRANSITIONS:
        out["tr"] = {"type": tr["type"], "dur": _num(tr.get("dur"), 0.5, 0.1, 5.0)}
    return out


def clip_dur(c: Dict[str, Any]) -> float:
    """How long a clip plays on the timeline (still frames: their hold time; otherwise source length divided by speed)."""
    if c.get("freeze"):
        return float(c["freeze"])
    return (c["out"] - c["in"]) / float(c.get("sp") or 1.0)


def clip_layout(clips: List[Dict[str, Any]]) -> Tuple[List[float], List[float], List[float], float]:
    """Start, duration and incoming transition length of every clip, and the total. A transition makes a clip start earlier
    (overlapping the previous one) and is capped at half of each neighbour so two transitions never meet. Mirrors layout() in timeline.js."""
    starts: List[float] = []
    durs = [clip_dur(c) for c in clips]
    trs: List[float] = []
    end = 0.0
    for i, c in enumerate(clips):
        td = 0.0
        if i > 0 and isinstance(c.get("tr"), dict):
            td = round(min(c["tr"]["dur"], durs[i - 1] / 2.0, durs[i] / 2.0), 3)
            if td < 0.05:
                td = 0.0
        trs.append(td)
        start = end - td
        starts.append(start)
        end = start + durs[i]
    return starts, durs, trs, end


def _num(v: Any, default: float, lo: float, hi: float) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return default if math.isnan(f) or math.isinf(f) else max(lo, min(hi, f))


def _hex(v: Any, default: str) -> str:
    return v if isinstance(v, str) and COLOR_RE.match(v) else default


CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
MAX_TEXTS, MAX_AUDIOS = 200, 50
MAX_SHAPES, MAX_SCENES, MAX_TRACKS = 200, 100, 12
TRACK_KINDS = ("scene", "shape", "text", "overlay", "bg", "audio")
SHAPE_KINDS = ("rect", "rounded", "ellipse")


def _track(v: Any) -> int:
    return int(_num(v, 0, 0, MAX_TRACKS - 1))


def sanitize_tracks(raw: Any) -> Dict[str, int]:
    """How many lanes of each kind the timeline shows (at least one)."""
    raw = raw if isinstance(raw, dict) else {}
    return {k: int(_num(raw.get(k), 1, 1, MAX_TRACKS)) for k in TRACK_KINDS}


def clean_shape(sh: Any) -> Dict[str, Any]:
    """A coloured shape (backing for text, frame, bar). x/y = centre, w/h = size, all as fractions of the canvas."""
    sh = sh if isinstance(sh, dict) else {}
    return {"id": str(sh.get("id") or "s")[:40], "kind": sh.get("kind") if sh.get("kind") in SHAPE_KINDS else "rect",
            "start": _num(sh.get("start"), 0.0, 0.0, 86400.0), "dur": _num(sh.get("dur"), 3.0, 0.1, 3600.0),
            "x": _num(sh.get("x"), 0.5, -0.5, 1.5), "y": _num(sh.get("y"), 0.5, -0.5, 1.5),
            "w": _num(sh.get("w"), 0.5, 0.02, 3.0), "h": _num(sh.get("h"), 0.2, 0.02, 3.0),
            "color": _hex(sh.get("color"), "#000000"), "op": _num(sh.get("op"), 0.6, 0.0, 1.0),
            "radius": _num(sh.get("radius"), 0.25, 0.0, 0.5), "track": _track(sh.get("track")),
            "fi": _num(sh.get("fi"), 0.0, 0.0, 10.0), "fo": _num(sh.get("fo"), 0.0, 0.0, 10.0)}


def sanitize_shapes(raw: Any) -> List[Dict[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list) or len(raw) > MAX_SHAPES:
        raise ToolError("'shapes' must be a list with at most %d entries." % MAX_SHAPES)
    return [clean_shape(x) for x in raw]


def sanitize_scenes(raw: Any) -> List[Dict[str, Any]]:
    """Scenes bundle items so they move together. They only exist in the editor and the project file; the render ignores them."""
    if raw is None:
        return []
    if not isinstance(raw, list) or len(raw) > MAX_SCENES:
        raise ToolError("'scenes' must be a list with at most %d entries." % MAX_SCENES)
    out = []
    for sc in raw:
        if not isinstance(sc, dict):
            continue
        items = [str(i)[:40] for i in (sc.get("items") if isinstance(sc.get("items"), list) else [])][:400]
        out.append({"id": str(sc.get("id") or "sc")[:40], "name": CONTROL_RE.sub("", str(sc.get("name") or "Scene"))[:60],
                    "start": _num(sc.get("start"), 0.0, 0.0, 86400.0), "dur": _num(sc.get("dur"), 3.0, 0.1, 3600.0),
                    "color": _hex(sc.get("color"), "#8b6cf0"), "items": items, "track": _track(sc.get("track"))})
    return out


def clean_text(t: Any) -> Dict[str, Any]:
    """One text on the picture. Limits are identical to cleanText() in editor/web/timeline.js."""
    t = t if isinstance(t, dict) else {}
    return {"id": str(t.get("id") or "t")[:40], "text": CONTROL_RE.sub("", str(t.get("text") if t.get("text") is not None else ""))[:500],
            "start": _num(t.get("start"), 0.0, 0.0, 86400.0), "dur": _num(t.get("dur"), 3.0, 0.1, 3600.0),
            "x": _num(t.get("x"), 0.5, -0.5, 1.5), "y": _num(t.get("y"), 0.82, -0.5, 1.5), "size": _num(t.get("size"), 0.07, 0.01, 0.5),
            "color": _hex(t.get("color"), "#ffffff"), "box": bool(t.get("box")), "boxColor": _hex(t.get("boxColor"), "#000000"),
            "boxOpacity": _num(t.get("boxOpacity"), 0.55, 0.0, 1.0), "outline": t.get("outline") is not False,
            "track": _track(t.get("track")), "fi": _num(t.get("fi"), 0.0, 0.0, 10.0), "fo": _num(t.get("fo"), 0.0, 0.0, 10.0)}


def sanitize_texts(raw: Any) -> List[Dict[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list) or len(raw) > MAX_TEXTS:
        raise ToolError("'texts' must be a list with at most %d entries." % MAX_TEXTS)
    return [c for c in (clean_text(t) for t in raw) if c["text"].strip()]


def clean_audio_fields(a: Dict[str, Any]) -> Dict[str, Any]:
    return {"start": _num(a.get("start"), 0.0, 0.0, 86400.0), "vol": _num(a.get("vol"), -10.0, -60.0, 24.0),
            "fi": _num(a.get("fi"), 0.0, 0.0, 60.0), "fo": _num(a.get("fo"), 0.0, 0.0, 60.0), "duck": bool(a.get("duck")),
            "track": _track(a.get("track"))}


def sanitize_audios(raw: Any, roots: List[str]) -> List[Dict[str, Any]]:
    """Audio items for rendering: [{path, in, out, start, vol, fi, fo, duck}] -> same plus probe info."""
    if raw is None:
        return []
    if not isinstance(raw, list) or len(raw) > MAX_AUDIOS:
        raise ToolError("'audios' must be a list with at most %d entries." % MAX_AUDIOS)
    out, cache = [], {}
    for i, a in enumerate(raw):
        if not isinstance(a, dict):
            raise ToolError("Audio item %d is invalid." % (i + 1))
        path = str(safe_media_file(a.get("path"), roots))
        if path not in cache:
            cache[path] = probe(Path(path))
        info = cache[path]
        if not info["has_audio"]:
            raise ToolError("Audio item %d (%s) has no sound." % (i + 1, os.path.basename(path)))
        total = info["duration_s"] or 0
        lo, hi = _num(a.get("in"), 0.0, 0.0, 86400.0), _num(a.get("out"), total, 0.0, 86400.0)
        hi = min(hi, total) if total else hi
        if hi - lo < 0.05:
            raise ToolError("Audio item %d is shorter than 0.05 s." % (i + 1))
        item = {"path": path, "in": lo, "out": hi, "info": info}
        item.update(clean_audio_fields(a))
        out.append(item)
    return out


MAX_OVERLAYS = 30


def clean_overlay_fields(o: Dict[str, Any]) -> Dict[str, Any]:
    """Placement of a picture-in-picture item. Limits are identical to cleanOverlay() in editor/web/timeline.js."""
    return {"start": _num(o.get("start"), 0.0, 0.0, 86400.0), "tf": clean_tf(o.get("tf") if isinstance(o.get("tf"), dict) else {"s": 0.4, "x": 0.27, "y": -0.27}),
            "op": _num(o.get("op"), 1.0, 0.0, 1.0), "sound": bool(o.get("sound")), "vol": _num(o.get("vol"), 0.0, -60.0, 24.0),
            "track": _track(o.get("track")), "fi": _num(o.get("fi"), 0.0, 0.0, 10.0), "fo": _num(o.get("fo"), 0.0, 0.0, 10.0)}


def sanitize_overlays(raw: Any, roots: List[str]) -> List[Dict[str, Any]]:
    """Overlay items (a second video track on top of the main one): [{path, in, out, start, tf, op, sound, vol}]."""
    if raw is None:
        return []
    if not isinstance(raw, list) or len(raw) > MAX_OVERLAYS:
        raise ToolError("'overlays' must be a list with at most %d entries." % MAX_OVERLAYS)
    out, cache = [], {}
    for i, o in enumerate(raw):
        if not isinstance(o, dict):
            raise ToolError("Overlay %d is invalid." % (i + 1))
        path = str(safe_media_file(o.get("path"), roots))
        if path not in cache:
            cache[path] = probe(Path(path))
        info = cache[path]
        if not info.get("video"):
            raise ToolError("Overlay %d (%s) has no picture." % (i + 1, os.path.basename(path)))
        total = info["duration_s"] or 0
        lo, hi = _num(o.get("in"), 0.0, 0.0, 86400.0), _num(o.get("out"), total, 0.0, 86400.0)
        hi = min(hi, total) if total else hi
        if hi - lo < 0.05:
            raise ToolError("Overlay %d is shorter than 0.05 s." % (i + 1))
        item = {"path": path, "in": lo, "out": hi, "info": info}
        item.update(clean_overlay_fields(o))
        out.append(item)
    return out


def shape_filters(shapes: List[Dict[str, Any]], W: int, H: int, fps: Any, src: str, dst: str) -> List[str]:
    """Draw every shape in its own time window: a one-frame rgba picture with a shaped alpha, looped for the window."""
    parts: List[str] = []
    cur = src
    for k, sh in enumerate(shapes):
        w, h = _even(sh["w"] * W), _even(sh["h"] * H)
        x, y = _jsround(sh["x"] * W - w / 2.0), _jsround(sh["y"] * H - h / 2.0)
        op = round(sh["op"], 3)
        if sh["kind"] == "rect":
            alpha = "%s" % round(255 * op, 2)
        elif sh["kind"] == "ellipse":
            alpha = "%s*clip((1-hypot((X+0.5-W/2)/(W/2),(Y+0.5-H/2)/(H/2)))*min(W,H)/2+0.5,0,1)" % round(255 * op, 2)
        else:
            rad = max(1.0, sh["radius"] * min(w, h))
            alpha = ("%s*clip(%s-hypot(max(abs(X+0.5-W/2)-(W/2-%s),0),max(abs(Y+0.5-H/2)-(H/2-%s),0))+0.5,0,1)"
                     % (round(255 * op, 2), round(rad, 2), round(rad, 2), round(rad, 2)))
        rgb = sh["color"][1:]
        parts.append("color=c=0x%s:s=%dx%d:r=%s:d=%.4f,format=rgba,geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='%s',"
                     "loop=loop=-1:size=1:start=0,trim=duration=%.3f%s,setpts=PTS-STARTPTS+%.3f/TB[sh%d]"
                     % (rgb, w, h, fps, 1.0 / float(fps if isinstance(fps, (int, float)) else 25), alpha, sh["dur"],
                        "".join("," + f for f in alpha_fade_filters(sh.get("fi", 0.0), sh.get("fo", 0.0), sh["dur"])), sh["start"], k))
        nxt = dst if k == len(shapes) - 1 else "shx%d" % k
        parts.append("[%s][sh%d]overlay=%d:%d:format=auto:eof_action=pass:%s[%s]" % (cur, k, x, y, _enable(sh["start"], sh["start"] + sh["dur"]), nxt))
        cur = nxt
    return parts


def _enable(a: float, b: float) -> str:
    from ..tools.overlay import enable_expr
    return enable_expr(a, b)


def overlay_filters(overlays: List[Dict[str, Any]], first_input: int, W: int, H: int, fps: Any, src: str, dst: str) -> List[str]:
    """Lay every overlay over the picture [src] during its own time window; the result is [dst]."""
    from ..tools.overlay import enable_expr
    parts: List[str] = []
    cur = src
    for k, o in enumerate(overlays):         # callers pass them bottom to top
        v = o["info"]["video"]
        x, y, w, h = fg_rect(v["display_width"], v["display_height"], W, H, o["tf"])
        d = o["out"] - o["in"]
        chain = ["[%d:v:0]setpts=PTS-STARTPTS" % (first_input + k), "fps=%s" % fps, "scale=%d:%d" % (w, h), "setsar=1", "format=yuva420p"]
        if o["op"] < 0.999:
            chain.append("colorchannelmixer=aa=%s" % round(o["op"], 3))
        chain += ["trim=duration=%.3f" % d] + alpha_fade_filters(o.get("fi", 0.0), o.get("fo", 0.0), d) + ["setpts=PTS-STARTPTS+%.3f/TB" % o["start"]]
        parts.append(",".join(chain) + "[o%d]" % k)
        nxt = dst if k == len(overlays) - 1 else "ov%d" % k
        parts.append("[%s][o%d]overlay=%d:%d:format=auto:eof_action=pass:%s[%s]" % (cur, k, x, y, enable_expr(o["start"], o["start"] + d), nxt))
        cur = nxt
    return parts


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
    """The background as a source of duration d (solid colour, gradient or picture)."""
    if bg["mode"] == "gradient":
        require_filter("gradients", "a gradient background")
        return ("gradients=s=%dx%d:r=%s:d=%.3f:c0=0x%s:c1=0x%s:x0=0:y0=0:x1=0:y1=%d:nb_colors=2:speed=0.00001,format=yuv420p,setsar=1[%s]"
                % (W, H, fps, d, bg["color"][1:], bg["color2"][1:], H, label))
    if bg["mode"] == "image" and bg.get("image"):
        return ("movie=filename=%s,scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,format=yuv420p,setsar=1,"
                "loop=loop=-1:size=1,fps=%s,trim=duration=%.3f,setpts=PTS-STARTPTS[%s]"
                % (ff_escape_path(Path(bg["image"])), W, H, W, H, fps, d, label))
    colour = "0x" + bg["color"][1:] if bg["mode"] == "color" else "black"
    return "color=c=%s:s=%dx%d:r=%s:d=%.3f,format=yuv420p,setsar=1[%s]" % (colour, W, H, fps, d, label)


def _blur_branch(src: str, dst: str, W: int, H: int) -> str:
    bw, bh = max(8, W // 8), max(8, H // 8)
    r = max(1, min(4, bw // 4, bh // 4))
    return ("[%s]scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,boxblur=%d:2,scale=%d:%d:flags=bicubic,setsar=1[%s]"
            % (src, bw, bh, bw, bh, r, W, H, dst))


def _bg_pieces(i: int, d: float, W: int, H: int, fps: Any, layers: List[Dict[str, Any]], final: str) -> Tuple[List[str], str]:
    """Build the background of clip i from its layers (project background first, then strips in their time windows) into [final].
    Blur layers read from the clip's own picture (labels b<i>_<k>, made by the caller's split)."""
    pieces: List[str] = []
    last_k = len(layers) - 1
    for k, L in enumerate(layers):
        name = final if last_k == 0 else "g%d_%d" % (i, k)
        if L["blur"]:
            pieces.append(_blur_branch("b%d_%d" % (i, k), name, W, H))
        else:
            pieces.append(_color_source(L["bg"], W, H, fps, d, name))
    cur = "g%d_0" % i
    for k in range(1, len(layers)):
        a, b = layers[k]["win"]
        nxt = final if k == last_k else "g%d_c%d" % (i, k)
        pieces.append("[%s][g%d_%d]overlay=0:0:format=auto:%s[%s]" % (cur, i, k, _enable(a, b), nxt))
        cur = nxt
    return pieces, final


def video_chain(i: int, c: Dict[str, Any], W: int, H: int, fps: Any, d: float, bg: Dict[str, str],
                strips: Any = None) -> List[str]:
    """Filter pieces that turn input i into a W x H picture of duration d with the clip's transform, adjustments, speed and
    still-frame settings applied. `strips` = background strips that overlap the clip, each with a clip-local window (a, b)."""
    strips = strips or []
    v = c["info"].get("video")
    adj = c.get("adj") or {}

    def layers_for(can_blur: bool) -> List[Dict[str, Any]]:
        ls = [{"bg": bg, "win": None, "blur": can_blur and bg["mode"] == "blur"}]
        ls += [{"bg": s, "win": s["win"], "blur": can_blur and s["mode"] == "blur"} for s in strips]
        return ls

    if not v:                                                  # audio-only clip: just the background
        return _bg_pieces(i, d, W, H, fps, layers_for(False), "v%d" % i)[0]
    iw, ih = v["display_width"], v["display_height"]
    x, y, w, h = fg_rect(iw, ih, W, H, c.get("tf"))
    tail = "setsar=1,format=yuv420p,trim=duration=%.3f,setpts=PTS-STARTPTS" % d
    if c.get("freeze"):
        base = "[%d:v:0]setpts=PTS-STARTPTS,trim=end_frame=1,loop=loop=-1:size=1,fps=%s" % (i, fps)
    elif c.get("sp"):
        base = "[%d:v:0]setpts=(PTS-STARTPTS)/%s,fps=%s" % (i, round(c["sp"], 4), fps)
    else:
        base = "[%d:v:0]setpts=PTS-STARTPTS,fps=%s" % (i, fps)
    look = []                                                  # brightness / contrast / saturation of the clip itself
    if adj and (adj["br"] != 0 or adj["ct"] != 1 or adj["sa"] != 1):
        look.append("eq=brightness=%s:contrast=%s:saturation=%s" % (round(adj["br"], 3), round(adj["ct"], 3), round(adj["sa"], 3)))
    fi, fo = (min(adj.get("fi", 0.0), d), min(adj.get("fo", 0.0), d)) if adj else (0.0, 0.0)
    if (x, y, w, h) == (0, 0, W, H):                           # the picture fills the canvas exactly
        fades = []
        if fi > 0:
            fades.append("fade=t=in:st=0:d=%.3f" % fi)
        if fo > 0:
            fades.append("fade=t=out:st=%.3f:d=%.3f" % (max(0.0, d - fo), fo))
        return ["%s" % ",".join([base + ",scale=%d:%d" % (W, H)] + look + fades + [tail]) + "[v%d]" % i]
    vx0, vy0, vx1, vy1 = max(0, -x), max(0, -y), min(w, W - x), min(h, H - y)
    if vx1 - vx0 < 2 or vy1 - vy0 < 2:                         # completely off canvas
        return _bg_pieces(i, d, W, H, fps, layers_for(False), "v%d" % i)[0]
    vw, vh = vx1 - vx0, vy1 - vy0
    crop = ""                                                  # only decode/scale what is visible (zoomed-in pictures stay cheap)
    if (vx0, vy0, vw, vh) != (0, 0, w, h):
        crop = "crop=%d:%d:%d:%d," % (max(2, _jsround(iw * vw / float(w))), max(2, _jsround(ih * vh / float(h))),
                                       _jsround(iw * vx0 / float(w)), _jsround(ih * vy0 / float(h)))
    ox, oy = max(x, 0), max(y, 0)
    covers = x <= 0 and y <= 0 and x + w >= W and y + h >= H
    layers = layers_for(not covers)
    if covers:
        layers = layers[:1]                                    # the picture hides everything behind it
    fg = ",".join(look + (["format=yuva420p"] if (fi > 0 or fo > 0) else []) + alpha_fade_filters(fi, fo, d))
    fg = ("," + fg) if fg else ""
    nblur = sum(1 for L in layers if L["blur"])
    pieces: List[str] = []
    if nblur:
        outs = "".join("[b%d_%d]" % (i, k) for k, L in enumerate(layers) if L["blur"])
        pieces.append("%s,split=%d[f%d]%s" % (base, nblur + 1, i, outs))
        fg_src = "[f%d]%sscale=%d:%d%s[h%d]" % (i, crop, vw, vh, fg, i)
    else:
        fg_src = "%s,%sscale=%d:%d%s[h%d]" % (base, crop, vw, vh, fg, i)
    bpieces, last = _bg_pieces(i, d, W, H, fps, layers, "g%d" % i)
    pieces += bpieces
    pieces.append(fg_src)
    pieces.append("[%s][h%d]overlay=%d:%d:format=auto%s,%s[v%d]" % (last, i, ox, oy, "" if nblur else ":shortest=0", tail, i))
    return pieces


def fade_alpha_expr(start: float, dur: float, fi: float, fo: float) -> str:
    """drawtext alpha (0..1) for a fade in/out inside [start, start+dur]; '' when there is no fade."""
    terms = []
    if fi > 0:
        terms.append("(t-%.3f)/%.3f" % (start, fi))
    if fo > 0:
        terms.append("(%.3f-t)/%.3f" % (start + dur, fo))
    if not terms:
        return ""
    return "clip(%s,0,1)" % (terms[0] if len(terms) == 1 else "min(%s,%s)" % tuple(terms))


def alpha_fade_filters(fi: float, fo: float, d: float) -> List[str]:
    """fade filters that ramp the alpha channel in and/or out over a clip of duration d."""
    out = []
    fi, fo = min(fi, d), min(fo, d)
    if fi > 0:
        out.append("fade=t=in:st=0:d=%.3f:alpha=1" % fi)
    if fo > 0:
        out.append("fade=t=out:st=%.3f:d=%.3f:alpha=1" % (max(0.0, d - fo), fo))
    return out


def text_filters(texts: List[Dict[str, Any]], W: int, H: int, workdir: Path) -> str:
    """drawtext chain for all texts (each in its own time window). Text goes through files: no escaping problems."""
    from ..tools.overlay import enable_expr
    if not texts:
        return ""
    require_filter("drawtext", "text on the timeline")
    font = resolve_font()
    chain = []
    for i, t in enumerate(texts):
        f = Path(workdir) / ("text%d.txt" % i)
        f.write_text(t["text"], encoding="utf-8")
        size = max(8, _jsround(t["size"] * H))
        opts = ["textfile=%s" % ff_escape_path(f), "expansion=none", "fontsize=%d" % size, "fontcolor=%s" % t["color"],
                "x=%d-text_w/2" % _jsround(t["x"] * W), "y=%d-text_h/2" % _jsround(t["y"] * H)]
        if font:
            opts.append("fontfile=%s" % ff_escape_path(font))
        if t["outline"]:
            opts += ["borderw=%d" % max(1, _jsround(size * 0.06)), "bordercolor=black"]
        if t["box"]:
            opts += ["box=1", "boxcolor=%s@%s" % (t["boxColor"], round(t["boxOpacity"], 3)), "boxborderw=%d" % max(6, size // 4)]
        al = fade_alpha_expr(t["start"], t["dur"], t.get("fi", 0.0), t.get("fo", 0.0))
        if al:
            opts.append("alpha='%s'" % al)
        opts.append(enable_expr(t["start"], t["start"] + t["dur"]))
        chain.append("drawtext=" + ":".join(opts))
    return ",".join(chain)


def audio_mix_parts(has_main: bool, audios: List[Dict[str, Any]], first_input: int) -> List[str]:
    """Mix the audio items (volume, fades, start time) with the timeline's own sound [ac]; result label is [ao]."""
    parts: List[str] = []
    ducked = [j for j, a in enumerate(audios) if a["duck"]] if has_main else []
    labels = []
    for j, a in enumerate(audios):
        d = a["out"] - a["in"]
        chain = ["[%d:a:0]aresample=48000" % (first_input + j), "aformat=channel_layouts=stereo", "volume=%sdB" % round(a["vol"], 2)]
        if a["fi"] > 0:
            chain.append("afade=t=in:st=0:d=%s" % round(min(a["fi"], d), 3))
        if a["fo"] > 0:
            fo = min(a["fo"], d)
            chain.append("afade=t=out:st=%.3f:d=%s" % (d - fo, round(fo, 3)))
        ms = _jsround(a["start"] * 1000)
        if ms > 0:
            chain.append("adelay=%d|%d" % (ms, ms))
        parts.append(",".join(chain) + "[m%d]" % j)
    if ducked:
        outs = "".join("[s%d]" % k for k in range(len(ducked)))
        parts.append("[ac]asplit=%d[mn]%s" % (len(ducked) + 1, outs))
        main = "[mn]"
    else:
        main = "[ac]"
    k = 0
    for j in range(len(audios)):
        if j in ducked:
            parts.append("[m%d][s%d]sidechaincompress=threshold=0.04:ratio=6:attack=20:release=400[d%d]" % (j, k, j))
            labels.append("[d%d]" % j)
            k += 1
        else:
            labels.append("[m%d]" % j)
    ins = ([main] if has_main else []) + labels
    parts.append("%samix=inputs=%d:duration=%s:normalize=0[amx]" % ("".join(ins), len(ins), "first" if has_main else "longest"))
    parts.append("[amx]alimiter=limit=0.97[ao]")
    return parts


def atempo_chain(sp: float) -> str:
    """atempo only accepts 0.5..2 per stage in older ffmpeg builds: chain stages for the full 0.25..4 range."""
    stages = []
    while sp > 2.0 + 1e-9:
        stages.append("atempo=2.0")
        sp /= 2.0
    while sp < 0.5 - 1e-9:
        stages.append("atempo=0.5")
        sp /= 0.5
    stages.append("atempo=%s" % round(sp, 4))
    return ",".join(stages)


def clip_audio_chain(i: int, c: Dict[str, Any], d: float) -> str:
    """The sound of clip i as [a<i>] of duration d: speed, volume, mute and fades applied; silence for stills and clips without sound."""
    adj = c.get("adj") or {}
    if c.get("freeze") or not c["info"]["has_audio"]:
        return "anullsrc=r=48000:cl=stereo:d=%.3f[a%d]" % (d, i)
    chain = ["[%d:a:0]aresample=48000" % i, "aformat=channel_layouts=stereo"]
    if c.get("sp"):
        chain.append(atempo_chain(c["sp"]))
    if adj.get("mute"):
        chain.append("volume=0")
    elif adj.get("vol"):
        chain.append("volume=%sdB" % round(adj["vol"], 2))
    chain += ["apad", "atrim=duration=%.3f" % d, "asetpts=PTS-STARTPTS"]
    if adj.get("fi", 0) > 0:
        chain.append("afade=t=in:st=0:d=%.3f" % min(adj["fi"], d))
    if adj.get("fo", 0) > 0:
        fo = min(adj["fo"], d)
        chain.append("afade=t=out:st=%.3f:d=%.3f" % (max(0.0, d - fo), fo))
    return ",".join(chain) + "[a%d]" % i


def strips_for_clip(bgsegs: List[Dict[str, Any]], start: float, d: float) -> List[Dict[str, Any]]:
    """Background strips that overlap the clip [start, start+d], with their window in clip time. Higher track = more in front."""
    out = []
    for sg in sorted(bgsegs, key=lambda b: b.get("track", 0)):
        a, b = max(0.0, sg["start"] - start), min(d, sg["start"] + sg["dur"] - start)
        if b - a > 0.02:
            out.append(dict(sg, win=(a, b)))
    return out


def join_with_transitions(clips: List[Dict[str, Any]], trs: List[float], durs: List[float], any_audio: bool,
                          vlabel: str, alabel: str, fps: Any) -> List[str]:
    """Join the clips one after the other: xfade/acrossfade where a clip has a transition, a plain concat where it has none."""
    parts: List[str] = []
    accv, acca = "v0", "a0"
    acc_len = durs[0]
    last = len(clips) - 1
    for i in range(1, len(clips)):
        outv = vlabel if i == last else "jv%d" % i
        outa = alabel if i == last else "ja%d" % i
        if trs[i] > 0:
            parts.append("[%s][v%d]xfade=transition=%s:duration=%s:offset=%.3f[%s]" % (accv, i, clips[i]["tr"]["type"], trs[i], acc_len - trs[i], outv))
            if any_audio:
                parts.append("[%s][a%d]acrossfade=d=%s[%s]" % (acca, i, trs[i], outa))
            acc_len += durs[i] - trs[i]
        else:
            ins = "[%s]%s[v%d]%s" % (accv, "[%s]" % acca if any_audio else "", i, "[a%d]" % i if any_audio else "")
            raw = outv if i == last else "jc%d" % i                 # concat hands out a microsecond clock; xfade wants the frame clock
            parts.append("%sconcat=n=2:v=1:a=%d[%s]%s" % (ins, int(any_audio), raw, "[%s]" % outa if any_audio else ""))
            if raw != outv:
                parts.append("[%s]fps=%s[%s]" % (raw, fps, outv))
            acc_len += durs[i]
        accv, acca = outv, outa
    return parts


def build_render_graph(clips: List[Dict[str, Any]], width: int, height: int, fps: float, bg: Any = None,
                       texts: Any = None, audios: Any = None, workdir: Any = None, overlays: Any = None,
                       shapes: Any = None, bgs: Any = None) -> Tuple[List[str], str, bool]:
    """Pure (apart from text files in workdir): ffmpeg input args and a filter_complex that plays all clips (joined by hard cuts
    or transitions), then stacks shapes, the overlay track and the texts on top (in that order; inside a kind the higher track
    is on top) and mixes the audio items. Background strips sit behind the clips. Returns (inputs, graph, has_audio)."""
    bgs_default = sanitize_bg(bg)
    bgsegs = list(bgs or [])
    by_track = lambda items: sorted(items, key=lambda i: i.get("track", 0))      # noqa: E731 - stable: later items stay above
    texts, overlays, shapes = by_track(texts or []), by_track(overlays or []), by_track(shapes or [])
    audios = list(audios or []) + [dict(path=o["path"], info=o["info"], duck=False, fi=0.0, fo=0.0, vol=o["vol"], start=o["start"],
                                        **{"in": o["in"], "out": o["out"]}) for o in overlays if o["sound"] and o["info"]["has_audio"]]
    if texts and workdir is None:
        raise ToolError("Internal error: texts need a work folder.")
    any_audio = any(c["info"]["has_audio"] for c in clips)
    starts, durs, trs, total = clip_layout(clips)
    use_xfade = any(t > 0 for t in trs)
    inputs: List[str] = []
    parts: List[str] = []
    labels = ""
    for i, c in enumerate(clips):
        d = durs[i]
        src_len = 0.2 if c.get("freeze") else c["out"] - c["in"]
        inputs += ["-ss", "%.3f" % c["in"], "-t", "%.3f" % src_len, "-i", c["path"]]
        parts += video_chain(i, c, width, height, fps, d, bgs_default, strips_for_clip(bgsegs, starts[i], d))
        labels += "[v%d]" % i
        if any_audio:
            parts.append(clip_audio_chain(i, c, d))
            labels += "[a%d]" % i
    vlabel = "vc" if (texts or overlays or shapes) else "vo"
    alabel = "ac" if audios else "ao"
    if not use_xfade:
        parts.append("%sconcat=n=%d:v=1:a=%d[%s]%s" % (labels, len(clips), int(any_audio), vlabel, "[%s]" % alabel if any_audio else ""))
    else:
        parts += join_with_transitions(clips, trs, durs, any_audio, vlabel, alabel, fps)
    cur = vlabel
    if shapes:
        dst = "vs" if (overlays or texts) else "vo"
        parts += shape_filters(shapes, width, height, fps, cur, dst)
        cur = dst
    if overlays:
        for o in overlays:
            inputs += ["-ss", "%.3f" % o["in"], "-t", "%.3f" % (o["out"] - o["in"]), "-i", o["path"]]
        dst = "vt" if texts else "vo"
        parts += overlay_filters(overlays, len(clips), width, height, fps, cur, dst)
        cur = dst
    if texts:
        parts.append("[%s]%s[vo]" % (cur, text_filters(texts, width, height, Path(workdir))))
    if audios:
        first = len(clips) + len(overlays)
        for a in audios:
            inputs += ["-ss", "%.3f" % a["in"], "-t", "%.3f" % (a["out"] - a["in"]), "-i", a["path"]]
        parts += audio_mix_parts(any_audio, audios, first)
        any_audio = True
    return inputs, ";".join(parts), any_audio


def render_project(clips: List[Dict[str, Any]], out_dir: Path, crf: int = 20, timeout: int = 3600,
                   canvas: Any = None, bg: Any = None, texts: Any = None, audios: Any = None, overlays: Any = None,
                   shapes: Any = None, bgs: Any = None) -> Path:
    """Render the sequence (+ texts, + audio items) to <first clip name>_project.mp4 in out_dir. Inputs are never modified."""
    width, height, fps = canvas_for(clips, canvas)
    out = plan_output(Path(clips[0]["path"]), "project", ".mp4", None, str(out_dir), False)
    part = out.with_name(".%s.%s.part.mp4" % (out.stem, uuid.uuid4().hex[:8]))     # only this run owns it
    tmp = Path(tempfile.mkdtemp(prefix="ve_render_"))
    try:
        inputs, graph, has_audio = build_render_graph(clips, width, height, fps, bg, texts, audios, tmp, overlays, shapes, bgs)
        ff = ["-y"] + inputs + filter_complex_args(graph, tmp) + ["-map", "[vo]"]
        if has_audio:
            ff += ["-map", "[ao]"]
        if audios or overlays or shapes:                             # music / overlays may be longer than the picture
            ff += ["-t", "%.3f" % clip_layout(clips)[3]]
        ff += encode_args(".mp4", crf=crf, audio=has_audio)
        try:
            run_ffmpeg(ff + [str(part)], timeout)
        except ToolError:
            if part.exists():
                part.unlink()
            raise
    finally:
        shutil.rmtree(str(tmp), ignore_errors=True)
    if not part.exists() or part.stat().st_size == 0:
        raise ToolError("Rendering produced no output.")
    if out.exists():                                     # a file with that name appeared meanwhile: keep it, use the next free name
        out = unique_path(out)
    os.replace(str(part), str(out))
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
            item.update(clean_clip_fields(c))
            clean_clips.append(item)
        except (KeyError, TypeError, ValueError):
            raise ToolError("A clip has invalid times.")
    clean_audios = []
    for a in (obj.get("audios") or [])[:MAX_AUDIOS]:
        if not isinstance(a, dict) or str(a.get("asset")) not in clean_assets:
            raise ToolError("An audio item points to an asset that is not in the project.")
        try:
            item = {"id": str(a.get("id"))[:40], "asset": str(a["asset"]), "in": float(a["in"]), "out": float(a["out"])}
        except (KeyError, TypeError, ValueError):
            raise ToolError("An audio item has invalid times.")
        item.update(clean_audio_fields(a))
        clean_audios.append(item)
    clean_overlays = []
    for o in (obj.get("overlays") or [])[:MAX_OVERLAYS]:
        if not isinstance(o, dict) or str(o.get("asset")) not in clean_assets:
            raise ToolError("An overlay points to an asset that is not in the project.")
        try:
            item = {"id": str(o.get("id"))[:40], "asset": str(o["asset"]), "in": float(o["in"]), "out": float(o["out"])}
        except (KeyError, TypeError, ValueError):
            raise ToolError("An overlay has invalid times.")
        item.update(clean_overlay_fields(o))
        clean_overlays.append(item)
    return {"version": 1, "name": str(obj.get("name") or "")[:120], "assets": clean_assets, "clips": clean_clips, "overlays": clean_overlays,
            "shapes": sanitize_shapes(obj.get("shapes")), "scenes": sanitize_scenes(obj.get("scenes")), "tracks": sanitize_tracks(obj.get("tracks")),
            "canvas": sanitize_canvas(obj.get("canvas")), "bg": sanitize_bg(obj.get("bg")), "bgs": sanitize_bgsegs(obj.get("bgs")),
            "texts": sanitize_texts(obj.get("texts") or []), "audios": clean_audios}


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
    tmp = p.with_name(".%s.%s.part" % (p.name, uuid.uuid4().hex[:8]))        # only this save owns it
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(str(tmp), str(p))
    except OSError as exc:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise ToolError("Could not save the project: %s" % exc)
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
