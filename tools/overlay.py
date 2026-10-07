"""D. Overlay & text tools."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.ffmpeg import Job, new_tempdir, require_filter, tool_handler
from ..core.fonts import resolve_font
from ..core.paths import ff_escape_path, resolve_input
from ..core.result import ToolError
from ..core.spec import ToolSpec
from ..core.validate import get_bool, get_choice, get_num, get_time
from ._common import (CRF_PROP, EVEN, crf_of, display_size, finish_vf, run_graph, second_input, tprop)

COLOR_RE = re.compile(r"^(#[0-9a-fA-F]{6,8}|0x[0-9a-fA-F]{6,8}|[A-Za-z]{3,20})(@[01](\.\d+)?)?$")
CORNERS = ("top_left", "top_right", "bottom_left", "bottom_right", "center")
POSITIONS = ("top_left", "top", "top_right", "left", "center", "right", "bottom_left", "bottom", "bottom_right")


def get_color(args: Dict[str, Any], key: str, default: str) -> str:
    value = str(args.get(key) or default)
    if not COLOR_RE.match(value):
        raise ToolError("Parameter '%s' is not a valid colour: %r" % (key, value),
                        hint="Use a name (white, yellow) or hex (#FFD400).")
    return value


def enable_expr(start: Optional[float], end: Optional[float]) -> str:
    """Filter 'enable' option with graph-level escaped commas, or '' for always on."""
    if start is not None and end is not None:
        return "enable=between(t\\,%.3f\\,%.3f)" % (start, end)
    if start is not None:
        return "enable=gte(t\\,%.3f)" % start
    if end is not None:
        return "enable=lte(t\\,%.3f)" % end
    return ""


def check_window(start: Optional[float], end: Optional[float]) -> None:
    if start is not None and end is not None and end <= start:
        raise ToolError("'end' must be greater than 'start'.")


def corner_xy(corner: str, margin: int) -> str:
    """overlay=x:y expression for a corner (W/H = main, w/h = overlay)."""
    return {"top_left": "%d:%d" % (margin, margin),
            "top_right": "W-w-%d:%d" % (margin, margin),
            "bottom_left": "%d:H-h-%d" % (margin, margin),
            "bottom_right": "W-w-%d:H-h-%d" % (margin, margin),
            "center": "(W-w)/2:(H-h)/2"}[corner]


# ------------------------------------------------------------------ add_text
def text_xy(position: str, margin: int) -> str:
    xs = {"left": str(margin), "center": "(w-text_w)/2", "right": "w-text_w-%d" % margin}
    ys = {"top": str(margin), "middle": "(h-text_h)/2", "bottom": "h-text_h-%d" % margin}
    col = "left" if position.endswith("left") else "right" if position.endswith("right") else "center"
    row = "top" if position.startswith("top") else "bottom" if position.startswith("bottom") else "middle"
    if position == "left":
        col, row = "left", "middle"
    if position == "right":
        col, row = "right", "middle"
    return "x=%s:y=%s" % (xs[col], ys[row])


@tool_handler
def add_text(args: Dict[str, Any]) -> Any:
    text = args.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ToolError("Missing required parameter 'text'.")
    position = get_choice(args, "position", POSITIONS, "bottom")
    size = get_num(args, "font_size", None, lo=6, hi=800, integer=True)
    color = get_color(args, "color", "white")
    outline = int(get_num(args, "outline_px", 2, lo=0, hi=20, integer=True))
    box = get_bool(args, "box", False)
    box_color = get_color(args, "box_color", "black")
    box_opacity = get_num(args, "box_opacity", 0.5, lo=0, hi=1)
    start, end = get_time(args, "start"), get_time(args, "end")
    check_window(start, end)
    require_filter("drawtext", "ve_add_text")
    job = Job(args, "text", ext="av", need_video=True)
    dw, dh = display_size(job.info)
    size = int(size or max(16, round(min(dw, dh) * 0.06)))
    margin = int(get_num(args, "margin_px", round(min(dw, dh) * 0.05), lo=0, hi=2000, integer=True))
    font = resolve_font(args.get("font_file"))
    if args.get("font_file") and not Path(str(args["font_file"])).is_file():
        raise ToolError("font_file not found: %s" % args["font_file"])
    with new_tempdir() as tmp:
        tfile = Path(tmp) / "text.txt"
        tfile.write_text(text, encoding="utf-8")
        opts = ["textfile=%s" % ff_escape_path(tfile), "expansion=none", "fontsize=%d" % size,
                "fontcolor=%s" % color, text_xy(position, margin)]
        if font:
            opts.append("fontfile=%s" % ff_escape_path(font))
        if outline:
            opts += ["borderw=%d" % outline, "bordercolor=black"]
        if box:
            opts += ["box=1", "boxcolor=%s@%s" % (box_color.split("@")[0], box_opacity),
                     "boxborderw=%d" % max(8, size // 4)]
        en = enable_expr(start, end)
        if en:
            opts.append(en)
        out = finish_vf(job, args, "drawtext=" + ":".join(opts), op="add_text", position=position,
                        font=font or "ffmpeg default", font_size=size)
    return out


# ------------------------------------------------------------------ burn_captions
def ass_color(value: str) -> str:
    """'#RRGGBB' / name -> ASS '&H00BBGGRR'."""
    names = {"white": "FFFFFF", "black": "000000", "yellow": "FFD400", "red": "FF0000", "green": "00FF00",
             "blue": "0000FF", "cyan": "00FFFF", "magenta": "FF00FF", "orange": "FF8800"}
    v = value.lstrip("#").replace("0x", "")
    v = names.get(value.lower(), v)
    if not re.match(r"^[0-9a-fA-F]{6}$", v):
        raise ToolError("Caption colour must be a hex value like #FFD400 or a basic colour name.")
    return "&H00%s%s%s" % (v[4:6], v[2:4], v[0:2])


def caption_style(w: int, h: int, font_px: int, outline_px: int, margin_px: int, color: str,
                  bold: bool, font_name: Optional[str]) -> str:
    """ASS style string. libass scales styles from a 288-px-high script, so convert pixels."""
    k = 288.0 / h
    parts = ["FontSize=%d" % max(1, round(font_px * k)), "Outline=%s" % max(0, round(outline_px * k, 1)),
             "MarginV=%d" % max(0, round(margin_px * k)), "MarginL=%d" % round(384 * 0.06),
             "MarginR=%d" % round(384 * 0.06), "Alignment=2", "Bold=%d" % int(bold),
             "PrimaryColour=%s" % ass_color(color), "OutlineColour=&H00000000", "BorderStyle=1"]
    if font_name:
        parts.append("FontName=%s" % re.sub(r"[^A-Za-z0-9 _-]", "", font_name))
    return ",".join(parts)


@tool_handler
def burn_captions(args: Dict[str, Any]) -> Any:
    cap = resolve_input(args.get("captions"), "captions")
    if cap.suffix.lower() not in (".srt", ".ass", ".ssa", ".vtt"):
        raise ToolError("Captions must be .srt, .ass, .ssa or .vtt (got %s)." % cap.suffix)
    font_px = get_num(args, "font_size", None, lo=6, hi=400, integer=True)
    outline = get_num(args, "outline_px", None, lo=0, hi=30)
    margin = get_num(args, "bottom_margin_px", None, lo=0, hi=2000, integer=True)
    reels_safe = get_bool(args, "reels_safe", False)
    color = str(args.get("color") or "white")
    bold = get_bool(args, "bold", True)
    require_filter("subtitles", "ve_burn_captions (needs libass)")
    job = Job(args, "captions", ext="av", need_video=True)
    dw, dh = display_size(job.info)
    font_px = int(font_px or max(14, round(min(dw, dh) * 0.055)))
    outline = outline if outline is not None else max(1.0, round(font_px * 0.08, 1))
    margin = int(margin if margin is not None else round(dh * 0.06))
    if reels_safe:
        margin = max(margin, int(dh * 0.18))
    vf = "subtitles=%s" % ff_escape_path(cap)
    native_style = cap.suffix.lower() in (".ass", ".ssa") and not any(
        k in args for k in ("font_size", "outline_px", "bottom_margin_px", "color", "font_name", "reels_safe"))
    if not native_style:
        vf += ":force_style='%s'" % caption_style(dw, dh, font_px, outline, margin, color, bold,
                                                   args.get("font_name"))
    return finish_vf(job, args, vf, op="burn_captions", captions=str(cap), font_size=font_px,
                     bottom_margin_px=margin, reels_safe=reels_safe, kept_native_ass_style=native_style)


# ------------------------------------------------------------------ add_image_overlay
@tool_handler
def add_image_overlay(args: Dict[str, Any]) -> Any:
    img = resolve_input(args.get("image"), "image")
    corner = get_choice(args, "corner", CORNERS, "bottom_right")
    pct = get_num(args, "scale_percent", 15, lo=1, hi=100)
    opacity = get_num(args, "opacity", 1.0, lo=0.0, hi=1.0)
    margin = int(get_num(args, "margin_px", 20, lo=0, hi=2000, integer=True))
    start, end = get_time(args, "start"), get_time(args, "end")
    check_window(start, end)
    job = Job(args, "overlay", ext="av", need_video=True)
    dw, _ = display_size(job.info)
    ow = max(2, int(dw * pct / 100) // 2 * 2)
    chain = "[1:v]scale=%d:-2,format=rgba" % ow
    if opacity < 1:
        chain += ",colorchannelmixer=aa=%s" % opacity
    en = enable_expr(start, end)
    graph = "%s[ov];[0:v][ov]overlay=%s%s[vt];[vt]%s[vo]" % (chain, corner_xy(corner, margin),
                                                              (":" + en) if en else "", EVEN)
    run_graph(job, [["-i", str(job.src)], ["-i", str(img)]], graph, crf=crf_of(args))
    return job.done(op="add_image_overlay", corner=corner, overlay_width_px=ow, opacity=opacity)


# ------------------------------------------------------------------ picture_in_picture
@tool_handler
def picture_in_picture(args: Dict[str, Any]) -> Any:
    pip, pip_info = second_input(args, "pip_input")
    if not pip_info["has_video"]:
        raise ToolError("pip_input has no video stream.")
    corner = get_choice(args, "corner", CORNERS, "bottom_right")
    pct = get_num(args, "scale_percent", 25, lo=5, hi=60)
    margin = int(get_num(args, "margin_px", 24, lo=0, hi=2000, integer=True))
    audio = get_choice(args, "audio", ("main", "pip", "mix", "none"), "main")
    start, end = get_time(args, "start"), get_time(args, "end")
    check_window(start, end)
    loop = get_bool(args, "loop_pip", False)
    job = Job(args, "pip", ext="av", need_video=True)
    dw, _ = display_size(job.info)
    pw = max(2, int(dw * pct / 100) // 2 * 2)
    has_m, has_p = job.info["has_audio"], pip_info["has_audio"]
    eff = audio
    if audio == "main" and not has_m:
        eff = "none"
    if audio == "pip" and not has_p:
        eff = "none"
    if audio == "mix":
        eff = "mix" if (has_m and has_p) else "main" if has_m else "pip" if has_p else "none"
        eff = {"main": "main", "pip": "pip"}.get(eff, eff)
    shift = ",setpts=PTS-STARTPTS+%.3f/TB" % start if start else ""
    en = enable_expr(None, end)
    graph = "[1:v]scale=%d:-2,setsar=1%s[p];[0:v][p]overlay=%s:eof_action=pass%s[vt];[vt]%s[vo]" % (
        pw, shift, corner_xy(corner, margin), (":" + en) if en else "", EVEN)
    alabel = None
    if eff == "pip":
        graph += ";[1:a]aresample=48000[ao]"
        alabel = "[ao]"
    elif eff == "mix":
        graph += ";[0:a][1:a]amix=inputs=2:duration=first[ao]"
        alabel = "[ao]"
    pip_in = (["-stream_loop", "-1"] if loop else []) + ["-i", str(pip)]
    out_opts = ["-t", "%.3f" % job.info["duration_s"]] if loop and job.info["duration_s"] else []
    run_graph(job, [["-i", str(job.src)], pip_in], graph, alabel=alabel, crf=crf_of(args),
              audio=(eff == "main"), out_opts=out_opts)
    return job.done(op="picture_in_picture", corner=corner, audio_used=eff, pip_width_px=pw)


# ------------------------------------------------------------------ stack_videos
@tool_handler
def stack_videos(args: Dict[str, Any]) -> Any:
    second, info2 = second_input(args, "input2")
    if not info2["has_video"]:
        raise ToolError("input2 has no video stream.")
    layout = get_choice(args, "layout", ("horizontal", "vertical"), "horizontal")
    audio = get_choice(args, "audio", ("first", "second", "mix", "none"), "first")
    job = Job(args, "stack", ext="av", need_video=True)
    dw, dh = display_size(job.info)
    w, h = dw // 2 * 2, dh // 2 * 2
    if layout == "horizontal":
        graph = ("[0:v]scale=-2:%d,setsar=1[a];[1:v]scale=-2:%d,setsar=1[b];"
                 "[a][b]hstack=inputs=2:shortest=1[vt]" % (h, h))
    else:
        graph = ("[0:v]scale=%d:-2,setsar=1[a];[1:v]scale=%d:-2,setsar=1[b];"
                 "[a][b]vstack=inputs=2:shortest=1[vt]" % (w, w))
    graph += ";[vt]%s[vo]" % EVEN
    has1, has2 = job.info["has_audio"], info2["has_audio"]
    alabel, eff = None, audio
    if audio == "first" and has1:
        graph += ";[0:a]anull[ao]"
        alabel = "[ao]"
    elif audio == "second" and has2:
        graph += ";[1:a]anull[ao]"
        alabel = "[ao]"
    elif audio == "mix" and has1 and has2:
        graph += ";[0:a][1:a]amix=inputs=2:duration=shortest[ao]"
        alabel = "[ao]"
    else:
        eff = "none"
    run_graph(job, [["-i", str(job.src)], ["-i", str(second)]], graph, alabel=alabel, crf=crf_of(args),
              audio=False if alabel is None else None, out_opts=["-shortest"])
    return job.done(op="stack_videos", layout=layout, audio_used=eff)


# ------------------------------------------------------------------ blur_region
@tool_handler
def blur_region(args: Dict[str, Any]) -> Any:
    x = int(get_num(args, "x", required=True, lo=0, integer=True))
    y = int(get_num(args, "y", required=True, lo=0, integer=True))
    w = int(get_num(args, "width", required=True, lo=8, integer=True))
    h = int(get_num(args, "height", required=True, lo=8, integer=True))
    mode = get_choice(args, "mode", ("blur", "pixelate"), "blur")
    strength = int(get_num(args, "strength", 20, lo=2, hi=200, integer=True))
    start, end = get_time(args, "start"), get_time(args, "end")
    check_window(start, end)
    job = Job(args, "blurred", ext="av", need_video=True)
    dw, dh = display_size(job.info)
    if x + w > dw or y + h > dh:
        raise ToolError("Region (x=%d,y=%d,%dx%d) exceeds the frame (%dx%d)." % (x, y, w, h, dw, dh))
    if mode == "blur":
        fx = "boxblur=%d:3" % max(1, min(strength, min(w, h) // 4))
    else:
        fx = "scale=%d:%d,scale=%d:%d:flags=neighbor" % (max(1, w // strength), max(1, h // strength), w, h)
    en = enable_expr(start, end)
    graph = "[0:v]split[a][b];[b]crop=%d:%d:%d:%d,%s[c];[a][c]overlay=%d:%d%s[vt];[vt]%s[vo]" % (
        w, h, x, y, fx, x, y, (":" + en) if en else "", EVEN)
    run_graph(job, [["-i", str(job.src)]], graph, crf=crf_of(args))
    return job.done(op="blur_region", mode=mode, region=[x, y, w, h])


# ------------------------------------------------------------------ specs
def _timing(prefix: str = "") -> Dict[str, Any]:
    return {"start": tprop("When the effect appears. Default: from the start."),
            "end": tprop("When the effect disappears. Default: until the end.")}


SPECS = [
    ToolSpec(
        name="ve_add_text",
        description=("Draw text on the video (title, lower third, label). Position by preset, size in pixels, optional "
                     "outline and background box, optional time window. Supports multi-line text and any language. "
                     "For subtitles from an SRT file use ve_burn_captions."),
        handler=add_text, required=["text"],
        properties={"text": {"type": "string", "description": "Text to show. Use \\n for line breaks. No % expansion."},
                    "position": {"type": "string", "enum": list(POSITIONS), "default": "bottom", "description": "Where to place the text."},
                    "font_size": {"type": "integer", "description": "Font size in pixels. Default: 6% of the short side."},
                    "color": {"type": "string", "default": "white", "description": "Name or hex, optionally with @opacity (white, #FFD400, white@0.8)."},
                    "outline_px": {"type": "integer", "default": 2, "description": "Black outline width in pixels (0 = none)."},
                    "box": {"type": "boolean", "default": False, "description": "Draw a background box behind the text."},
                    "box_color": {"type": "string", "default": "black", "description": "Box colour."},
                    "box_opacity": {"type": "number", "default": 0.5, "description": "Box opacity 0-1."},
                    "margin_px": {"type": "integer", "description": "Distance from the edge in pixels. Default 5% of the short side."},
                    "font_file": {"type": "string", "description": "Optional path to a .ttf/.otf font. Default: a system font per OS."},
                    **_timing(), "crf": CRF_PROP}),
    ToolSpec(
        name="ve_burn_captions",
        description=("Burn (hard-code) subtitles from an .srt, .vtt or .ass file into the picture. Style: size/outline/"
                     "margin in pixels of the output video. reels_safe=true lifts the captions above the Reels/TikTok/"
                     "Shorts interface (bottom ~18%). A .ass file keeps its own styling unless you pass style options. "
                     "Make the captions first with ve_transcribe_captions if you have none."),
        handler=burn_captions, required=["captions"],
        properties={"captions": {"type": "string", "description": "Path to the .srt / .vtt / .ass / .ssa file."},
                    "font_size": {"type": "integer", "description": "Font size in pixels. Default 5.5% of the short side."},
                    "outline_px": {"type": "number", "description": "Outline width in pixels. Default 8% of font size."},
                    "bottom_margin_px": {"type": "integer", "description": "Distance from the bottom edge. Default 6% of height."},
                    "reels_safe": {"type": "boolean", "default": False, "description": "Keep captions out of the bottom 18% (platform UI)."},
                    "color": {"type": "string", "default": "white", "description": "Text colour: hex (#FFD400) or basic name."},
                    "bold": {"type": "boolean", "default": True, "description": "Bold text."},
                    "font_name": {"type": "string", "description": "Optional installed font family name."},
                    "crf": CRF_PROP}),
    ToolSpec(
        name="ve_add_image_overlay",
        description=("Place a logo/watermark image (PNG with transparency works best) on the video: corner, size as % of "
                     "video width, opacity, optional time window."),
        handler=add_image_overlay, required=["image"],
        properties={"image": {"type": "string", "description": "Path to the logo/image file."},
                    "corner": {"type": "string", "enum": list(CORNERS), "default": "bottom_right", "description": "Where to put it."},
                    "scale_percent": {"type": "number", "default": 15, "description": "Overlay width as percent of video width (1-100)."},
                    "opacity": {"type": "number", "default": 1, "description": "0 (invisible) to 1 (solid)."},
                    "margin_px": {"type": "integer", "default": 20, "description": "Distance from the edge in pixels."},
                    **_timing(), "crf": CRF_PROP}),
    ToolSpec(
        name="ve_picture_in_picture",
        description=("Show a second video as a small inset on top of the main video (reaction/facecam style). Output length "
                     "follows the main video; the inset disappears when it ends unless loop_pip=true. For two videos "
                     "next to each other use ve_stack_videos."),
        handler=picture_in_picture, required=["pip_input"],
        properties={"pip_input": {"type": "string", "description": "Path to the inset video."},
                    "corner": {"type": "string", "enum": list(CORNERS), "default": "bottom_right", "description": "Inset position."},
                    "scale_percent": {"type": "number", "default": 25, "description": "Inset width as percent of main width (5-60)."},
                    "margin_px": {"type": "integer", "default": 24, "description": "Distance from the edge in pixels."},
                    "audio": {"type": "string", "enum": ["main", "pip", "mix", "none"], "default": "main", "description": "Which audio to keep."},
                    "loop_pip": {"type": "boolean", "default": False, "description": "Repeat the inset until the main video ends."},
                    **_timing(), "crf": CRF_PROP}),
    ToolSpec(
        name="ve_stack_videos",
        description=("Put two videos side by side (horizontal) or one above the other (vertical). The second is scaled to match "
                     "the first; output ends with the shorter video. For an inset use ve_picture_in_picture."),
        handler=stack_videos, required=["input2"],
        properties={"input2": {"type": "string", "description": "Path to the second video."},
                    "layout": {"type": "string", "enum": ["horizontal", "vertical"], "default": "horizontal",
                               "description": "horizontal = side by side, vertical = top/bottom."},
                    "audio": {"type": "string", "enum": ["first", "second", "mix", "none"], "default": "first", "description": "Which audio to keep."},
                    "crf": CRF_PROP}),
    ToolSpec(
        name="ve_blur_region",
        description=("Blur or pixelate a rectangle (faces, licence plates, passwords) for the whole clip or a time window. "
                     "The box is fixed on screen: it does NOT track a moving object. x,y = top-left in pixels."),
        handler=blur_region, required=["x", "y", "width", "height"],
        properties={"x": {"type": "integer", "minimum": 0, "description": "Left edge of the box in pixels."},
                    "y": {"type": "integer", "minimum": 0, "description": "Top edge of the box in pixels."},
                    "width": {"type": "integer", "minimum": 8, "description": "Box width in pixels."},
                    "height": {"type": "integer", "minimum": 8, "description": "Box height in pixels."},
                    "mode": {"type": "string", "enum": ["blur", "pixelate"], "default": "blur", "description": "blur = smooth, pixelate = mosaic."},
                    "strength": {"type": "integer", "default": 20, "description": "Blur radius or mosaic block size in pixels."},
                    **_timing(), "crf": CRF_PROP}),
]
