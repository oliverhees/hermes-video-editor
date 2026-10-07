"""C. Picture tools."""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from ..core.ffmpeg import Job, tool_handler
from ..core.result import ToolError
from ..core.spec import ToolSpec
from ..core.validate import get_bool, get_choice, get_num
from ._common import CRF_PROP, crf_of, display_size, finish_vf as _finish_vf, run_graph, tprop, vf_edit

ASPECTS = {"9:16": (9, 16), "1:1": (1, 1), "4:5": (4, 5), "16:9": (16, 9)}
ANCHORS = ("center", "top", "bottom", "left", "right")
RESIZE_PRESETS = ("480p", "720p", "1080p", "1440p", "2160p", "1080x1920", "1920x1080", "1080x1080")


def _even(n: float) -> int:
    return max(2, int(n) // 2 * 2)


# ------------------------------------------------------------------ crop
@tool_handler
def crop(args: Dict[str, Any]) -> Any:
    w = int(get_num(args, "width", required=True, lo=2, integer=True))
    h = int(get_num(args, "height", required=True, lo=2, integer=True))
    x = int(get_num(args, "x", 0, lo=0, integer=True))
    y = int(get_num(args, "y", 0, lo=0, integer=True))
    job = Job(args, "crop", ext="av", need_video=True)
    dw, dh = display_size(job.info)
    if x + w > dw or y + h > dh:
        raise ToolError("Crop box (x=%d,y=%d,%dx%d) exceeds the frame (%dx%d)." % (x, y, w, h, dw, dh),
                        hint="Check ve_media_probe for the real size (rotation is already applied).")
    return _finish_vf(job, args, "crop=%d:%d:%d:%d" % (w, h, x, y), crop_box=[x, y, w, h])


# ------------------------------------------------------------------ crop_to_aspect
def crop_geometry(iw: int, ih: int, aspect: str, anchor: str) -> Tuple[int, int, int, int]:
    """Largest crop of the requested aspect inside iw x ih. Returns (w, h, x, y), even w/h."""
    aw, ah = ASPECTS[aspect]
    if iw * ah > ih * aw:           # frame is wider than target -> trim width
        h, w = ih, ih * aw / ah
    else:                            # frame is taller/equal -> trim height
        w, h = iw, iw * ah / aw
    w, h = _even(w), _even(h)
    x, y = (iw - w) // 2, (ih - h) // 2
    if w < iw:
        x = {"left": 0, "right": iw - w}.get(anchor, x)
    if h < ih:
        y = {"top": 0, "bottom": ih - h}.get(anchor, y)
    return w, h, x, y


@tool_handler
def crop_to_aspect(args: Dict[str, Any]) -> Any:
    aspect = get_choice(args, "aspect", ASPECTS, None)
    if not aspect:
        raise ToolError("Missing required parameter 'aspect'.", hint="One of %s" % list(ASPECTS))
    anchor = get_choice(args, "anchor", ANCHORS, "center")
    out_w = get_num(args, "output_width", None, lo=16, hi=8192, integer=True)
    job = Job(args, "crop_%s" % aspect.replace(":", "x"), ext="av", need_video=True)
    dw, dh = display_size(job.info)
    w, h, x, y = crop_geometry(dw, dh, aspect, anchor)
    vf = "crop=%d:%d:%d:%d" % (w, h, x, y)
    if out_w:
        vf += ",scale=%d:-2" % _even(out_w)
    return _finish_vf(job, args, vf, aspect=aspect, anchor=anchor, crop_box=[x, y, w, h])


# ------------------------------------------------------------------ resize
def resize_filter(iw: int, ih: int, width: Optional[int], height: Optional[int],
                  preset: Optional[str], keep_aspect: bool) -> str:
    if preset:
        if preset.endswith("p"):                      # NNNp = short side
            n = int(preset[:-1])
            return "scale=%d:-2" % n if iw < ih else "scale=-2:%d" % n
        width, height = (int(v) for v in preset.split("x"))
        keep_aspect = True
    if width and height:
        if keep_aspect:
            return "scale=%d:%d:force_original_aspect_ratio=decrease" % (_even(width), _even(height))
        return "scale=%d:%d" % (_even(width), _even(height))
    if width:
        return "scale=%d:-2" % _even(width)
    if height:
        return "scale=-2:%d" % _even(height)
    raise ToolError("Give 'preset', or 'width' and/or 'height'.")


@tool_handler
def resize(args: Dict[str, Any]) -> Any:
    width = get_num(args, "width", None, lo=16, hi=16384, integer=True)
    height = get_num(args, "height", None, lo=16, hi=16384, integer=True)
    preset = get_choice(args, "preset", RESIZE_PRESETS, None)
    keep = get_bool(args, "keep_aspect", True)
    job = Job(args, "resize", ext="av", need_video=True)
    dw, dh = display_size(job.info)
    return _finish_vf(job, args, resize_filter(dw, dh, width and int(width), height and int(height), preset, keep),
                      preset=preset, source_size=[dw, dh])


# ------------------------------------------------------------------ rotate_flip
@tool_handler
def rotate_flip(args: Dict[str, Any]) -> Any:
    rot = int(get_num(args, "rotate", 0))
    if rot not in (0, 90, 180, 270):
        raise ToolError("'rotate' must be 0, 90, 180 or 270 (clockwise degrees).")
    hflip, vflip = get_bool(args, "hflip"), get_bool(args, "vflip")
    if rot == 0 and not hflip and not vflip:
        raise ToolError("Nothing to do: set rotate (90/180/270), hflip or vflip.")
    parts = {90: ["transpose=1"], 180: ["hflip", "vflip"], 270: ["transpose=2"], 0: []}[rot]
    if hflip:
        parts.append("hflip")
    if vflip:
        parts.append("vflip")
    return vf_edit(args, "rotflip", ",".join(parts), rotate=rot, hflip=hflip, vflip=vflip)


# ------------------------------------------------------------------ pad_blur_background
def blur_bg_graph(w: int, h: int, strength: int) -> str:
    radius = max(1, min(strength, w // 8, h // 8))
    return ("[0:v]split[a][b];"
            "[a]scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,boxblur=%d:3,setsar=1[bg];"
            "[b]scale=%d:%d:force_original_aspect_ratio=decrease[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2[vo]" % (w, h, w, h, radius, w, h))


@tool_handler
def pad_blur_background(args: Dict[str, Any]) -> Any:
    w = _even(get_num(args, "width", 1080, lo=64, hi=8192, integer=True))
    h = _even(get_num(args, "height", 1920, lo=64, hi=8192, integer=True))
    strength = int(get_num(args, "blur_strength", 25, lo=1, hi=100, integer=True))
    job = Job(args, "blurbg", ext="av", need_video=True)
    run_graph(job, [["-i", str(job.src)]], blur_bg_graph(w, h, strength), crf=crf_of(args))
    return job.done(op="pad_blur_background", target_size=[w, h], blur_strength=strength)


# ------------------------------------------------------------------ color_adjust
@tool_handler
def color_adjust(args: Dict[str, Any]) -> Any:
    b = get_num(args, "brightness", 0.0, lo=-1.0, hi=1.0)
    c = get_num(args, "contrast", 1.0, lo=0.0, hi=3.0)
    s = get_num(args, "saturation", 1.0, lo=0.0, hi=3.0)
    g = get_num(args, "gamma", 1.0, lo=0.1, hi=10.0)
    if (b, c, s, g) == (0.0, 1.0, 1.0, 1.0):
        raise ToolError("All values are neutral; nothing to adjust.",
                        hint="Set at least one of brightness, contrast, saturation, gamma.")
    return vf_edit(args, "color", "eq=brightness=%s:contrast=%s:saturation=%s:gamma=%s" % (b, c, s, g),
                   brightness=b, contrast=c, saturation=s, gamma=g)


# ------------------------------------------------------------------ denoise_video
HQDN3D = {"light": "2:1.5:3:2.25", "medium": "4:3:6:4.5", "strong": "8:6:12:9"}


@tool_handler
def denoise_video(args: Dict[str, Any]) -> Any:
    level = get_choice(args, "strength", HQDN3D, "medium")
    return vf_edit(args, "denoise", "hqdn3d=" + HQDN3D[level], strength=level)


# ------------------------------------------------------------------ fade_video
@tool_handler
def fade_video(args: Dict[str, Any]) -> Any:
    fin = get_num(args, "fade_in_s", 0.0, lo=0, hi=60)
    fout = get_num(args, "fade_out_s", 0.0, lo=0, hi=60)
    with_audio = get_bool(args, "audio", True)
    if fin == 0 and fout == 0:
        raise ToolError("Set fade_in_s and/or fade_out_s (seconds).")
    job = Job(args, "fade", ext="av", need_video=True)
    dur = job.info["duration_s"] or 0
    if fin + fout > dur:
        raise ToolError("Fades (%.2fs + %.2fs) are longer than the clip (%.2fs)." % (fin, fout, dur))
    vf, af = [], []
    if fin:
        vf.append("fade=t=in:st=0:d=%s" % fin)
        af.append("afade=t=in:st=0:d=%s" % fin)
    if fout:
        vf.append("fade=t=out:st=%.3f:d=%s" % (dur - fout, fout))
        af.append("afade=t=out:st=%.3f:d=%s" % (dur - fout, fout))
    return _finish_vf(job, args, ",".join(vf), ",".join(af) if with_audio else None,
                      fade_in_s=fin, fade_out_s=fout, audio_faded=with_audio and job.info["has_audio"])


# ------------------------------------------------------------------ stabilize
SHAKE = {"low": 16, "medium": 32, "high": 64}  # deshake: rx/ry must be multiples of 16


@tool_handler
def stabilize(args: Dict[str, Any]) -> Any:
    level = get_choice(args, "strength", SHAKE, "medium")
    edge = get_choice(args, "edge", ("blank", "original", "clamp", "mirror"), "mirror")
    r = SHAKE[level]
    return vf_edit(args, "stab", "deshake=rx=%d:ry=%d:edge=%s" % (r, r, edge), strength=level, edge=edge)


# ------------------------------------------------------------------ specs
SPECS = [
    ToolSpec(
        name="ve_crop",
        description=("Cut out a rectangle of the picture. x,y = top-left corner in pixels, width/height in pixels "
                     "(measured on the displayed frame, rotation already applied). For 9:16/1:1/4:5 use "
                     "ve_crop_to_aspect instead; to hide something use ve_blur_region."),
        handler=crop, required=["width", "height"],
        properties={"width": {"type": "integer", "minimum": 2, "description": "Crop width in pixels."},
                    "height": {"type": "integer", "minimum": 2, "description": "Crop height in pixels."},
                    "x": {"type": "integer", "minimum": 0, "default": 0, "description": "Left edge in pixels."},
                    "y": {"type": "integer", "minimum": 0, "default": 0, "description": "Top edge in pixels."},
                    "crf": CRF_PROP}),
    ToolSpec(
        name="ve_crop_to_aspect",
        description=("Crop to a standard aspect ratio, keeping as much picture as possible (no black bars, "
                     "no stretching). 9:16 for Reels/TikTok/Shorts, 1:1 square, 4:5 feed, 16:9 landscape. "
                     "anchor picks which part is kept. To KEEP the whole landscape picture in a vertical "
                     "frame use ve_pad_blur_background instead."),
        handler=crop_to_aspect, required=["aspect"],
        properties={"aspect": {"type": "string", "enum": list(ASPECTS), "description": "Target aspect ratio (width:height)."},
                    "anchor": {"type": "string", "enum": list(ANCHORS), "default": "center",
                               "description": "Which part to keep: left/right when cutting width, top/bottom when cutting height."},
                    "output_width": {"type": "integer", "description": "Optional: scale the result to this width in pixels (e.g. 1080)."},
                    "crf": CRF_PROP}),
    ToolSpec(
        name="ve_resize",
        description=("Scale the video. Use 'preset' (480p/720p/1080p/1440p/2160p = SHORT side in pixels, so it works "
                     "for vertical clips too; or 1080x1920 / 1920x1080 / 1080x1080 = fit inside that box) or "
                     "'width' and/or 'height' in pixels. Aspect ratio is kept by default; sizes are made even."),
        handler=resize,
        properties={"preset": {"type": "string", "enum": list(RESIZE_PRESETS), "description": "Named size."},
                    "width": {"type": "integer", "minimum": 16, "description": "Target width in pixels."},
                    "height": {"type": "integer", "minimum": 16, "description": "Target height in pixels."},
                    "keep_aspect": {"type": "boolean", "default": True,
                                    "description": "When both width and height are given: fit inside the box (true) or stretch to it (false)."},
                    "crf": CRF_PROP}),
    ToolSpec(
        name="ve_rotate_flip",
        description="Rotate by 90/180/270 degrees clockwise and/or mirror horizontally/vertically.",
        handler=rotate_flip,
        properties={"rotate": {"type": "integer", "enum": [0, 90, 180, 270], "default": 0,
                               "description": "Clockwise degrees."},
                    "hflip": {"type": "boolean", "default": False, "description": "Mirror left-right (after rotating)."},
                    "vflip": {"type": "boolean", "default": False, "description": "Mirror top-bottom (after rotating)."},
                    "crf": CRF_PROP}),
    ToolSpec(
        name="ve_pad_blur_background",
        description=("Reels/TikTok style: fit the WHOLE clip inside a frame (default 1080x1920 vertical) and fill the "
                     "empty areas with a blurred, enlarged copy of the same video. Use this instead of cropping when "
                     "you do not want to lose any of the picture."),
        handler=pad_blur_background,
        properties={"width": {"type": "integer", "default": 1080, "description": "Output width in pixels."},
                    "height": {"type": "integer", "default": 1920, "description": "Output height in pixels."},
                    "blur_strength": {"type": "integer", "default": 25, "minimum": 1, "maximum": 100,
                                      "description": "Blur radius of the background in pixels. Default 25."},
                    "crf": CRF_PROP}),
    ToolSpec(
        name="ve_color_adjust",
        description=("Basic colour correction. brightness -1..1 (0 = unchanged), contrast 0..3 (1 = unchanged), "
                     "saturation 0..3 (1 = unchanged, 0 = black&white), gamma 0.1..10 (1 = unchanged). "
                     "Set only what you want to change."),
        handler=color_adjust,
        properties={"brightness": {"type": "number", "default": 0, "minimum": -1, "maximum": 1, "description": "Added brightness."},
                    "contrast": {"type": "number", "default": 1, "minimum": 0, "maximum": 3, "description": "Contrast factor."},
                    "saturation": {"type": "number", "default": 1, "minimum": 0, "maximum": 3, "description": "Saturation factor."},
                    "gamma": {"type": "number", "default": 1, "minimum": 0.1, "maximum": 10, "description": "Gamma (>1 brightens midtones)."},
                    "crf": CRF_PROP}),
    ToolSpec(
        name="ve_denoise_video",
        description="Reduce grain/noise in the picture (hqdn3d). For audio noise use ve_denoise_audio. Can soften fine detail at 'strong'.",
        handler=denoise_video,
        properties={"strength": {"type": "string", "enum": list(HQDN3D), "default": "medium", "description": "Denoise amount."},
                    "crf": CRF_PROP}),
    ToolSpec(
        name="ve_fade_video",
        description=("Fade the picture in from black at the start and/or out to black at the end. Seconds. "
                     "Optionally fades the audio too (audio=true, default). For audio-only fades use ve_fade_audio."),
        handler=fade_video,
        properties={"fade_in_s": {"type": "number", "default": 0, "minimum": 0, "description": "Fade-in length in seconds."},
                    "fade_out_s": {"type": "number", "default": 0, "minimum": 0, "description": "Fade-out length in seconds."},
                    "audio": {"type": "boolean", "default": True, "description": "Also fade the audio track."},
                    "crf": CRF_PROP}),
    ToolSpec(
        name="ve_stabilize",
        description=("Reduce camera shake with FFmpeg's built-in 'deshake' filter (single pass; moderate quality, "
                     "may crop/mirror the edges). Not a replacement for gimbal footage."),
        handler=stabilize,
        properties={"strength": {"type": "string", "enum": list(SHAKE), "default": "medium",
                                 "description": "Search range: low=16px, medium=32px, high=64px of shake."},
                    "edge": {"type": "string", "enum": ["blank", "original", "clamp", "mirror"], "default": "mirror",
                             "description": "How to fill the borders that appear after shifting."},
                    "crf": CRF_PROP}),
]
