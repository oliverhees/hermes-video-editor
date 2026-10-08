"""F. Export & check tools."""
from __future__ import annotations

import math
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..core.ffmpeg import Job, new_tempdir, probe, run_ffmpeg, tool_handler
from ..core.paths import resolve_input
from ..core.result import ToolError
from ..core.spec import ToolSpec
from ..core.timeparse import format_time
from ..core.validate import get_bool, get_choice, get_num, get_time
from ..platform_rules import PLATFORM_RULES
from ._common import CRF_PROP, EVEN, display_size, tprop

# --------------------------------------------------------------------------- presets
# fps_cap: output fps is limited to this (never raised). maxrate in kbit/s.
EXPORT_PRESETS: Dict[str, Dict[str, Any]] = {
    "reels": {"size": (1080, 1920), "fps_cap": 30, "crf": 20, "maxrate": 9000, "audio_kbps": 128},
    "tiktok": {"size": (1080, 1920), "fps_cap": 30, "crf": 20, "maxrate": 9000, "audio_kbps": 128},
    "shorts": {"size": (1080, 1920), "fps_cap": 30, "crf": 19, "maxrate": 10000, "audio_kbps": 160},
    "youtube_1080p": {"size": (1920, 1080), "fps_cap": 60, "crf": 18, "maxrate": 16000, "audio_kbps": 192},
    "youtube_4k": {"size": (3840, 2160), "fps_cap": 60, "crf": 18, "maxrate": 45000, "audio_kbps": 192},
    "x_twitter": {"size": (1280, 720), "fps_cap": 30, "crf": 22, "maxrate": 6000, "audio_kbps": 128},
    "discord_8mb": {"size": (1280, 720), "fps_cap": 30, "target_mb": 7.6, "audio_kbps": 96},
    "web_mp4": {"size": None, "fps_cap": 60, "crf": 23, "maxrate": None, "audio_kbps": 160},
}


def fit_filter(w: int, h: int, fit: str) -> str:
    if fit == "cover":
        return "scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,setsar=1" % (w, h, w, h)
    return ("scale=%d:%d:force_original_aspect_ratio=decrease,pad=%d:%d:(ow-iw)/2:(oh-ih)/2:black,setsar=1"
            % (w, h, w, h))


def evaluate(info: Dict[str, Any], rules: Dict[str, Any], loudness: Optional[Dict[str, float]] = None) -> List[Dict[str, Any]]:
    """Pure: compare a probe summary with one PLATFORM_RULES entry. Returns a list of check dicts."""
    checks: List[Dict[str, Any]] = []

    def add(name: str, status: str, value: Any, limit: Any, fix: str = "") -> None:
        checks.append({"check": name, "status": status, "value": value, "limit": limit, "fix": fix})

    v, dur = info.get("video") or {}, info.get("duration_s")
    if not v:
        add("video_stream", "fail", None, "required", "Pick a file that contains video.")
        return checks
    w, h = v["display_width"], v["display_height"]
    if rules.get("max_duration_s") is not None and dur is not None:
        ok_ = dur <= rules["max_duration_s"]
        add("duration_max", "pass" if ok_ else "fail", round(dur, 2), rules["max_duration_s"],
            "" if ok_ else "Shorten with lk_trim (or lk_remove_silence / lk_change_speed).")
    if rules.get("min_duration_s") is not None and dur is not None:
        ok_ = dur >= rules["min_duration_s"]
        add("duration_min", "pass" if ok_ else "fail", round(dur, 2), rules["min_duration_s"],
            "" if ok_ else "Clip is too short; use lk_loop or a longer take.")
    if rules.get("aspects"):
        ratio = w / float(h)
        names = list(rules["aspects"])
        match = any(abs(ratio / (int(a.split(":")[0]) / float(a.split(":")[1])) - 1) <= 0.02 for a in names)
        first = names[0]
        add("aspect_ratio", "pass" if match else "fail", "%dx%d (%.3f)" % (w, h, ratio), names,
            "" if match else "Use lk_crop_to_aspect aspect=%s, or lk_pad_blur_background to keep the whole picture." % first)
    for key, label, val in (("min_width", "width_min", w), ("min_height", "height_min", h)):
        if rules.get(key):
            ok_ = val >= rules[key]
            add(label, "pass" if ok_ else "fail", val, rules[key], "" if ok_ else "Source is too small; re-shoot or upscale with lk_resize.")
    for key, label, val in (("max_width", "width_max", w), ("max_height", "height_max", h)):
        if rules.get(key):
            ok_ = val <= rules[key]
            add(label, "pass" if ok_ else "fail", val, rules[key], "" if ok_ else "Downscale with lk_resize.")
    rec = rules.get("recommended_size")
    if rec and (w, h) != tuple(rec) and not any(c["status"] == "fail" and c["check"].startswith(("aspect", "width", "height")) for c in checks):
        add("recommended_size", "warn", "%dx%d" % (w, h), "%dx%d" % tuple(rec),
            "Optional: lk_export_preset gives the recommended size.")
    fps = v.get("fps")
    if rules.get("max_fps") and fps:
        ok_ = fps <= rules["max_fps"] + 0.01
        add("fps_max", "pass" if ok_ else "fail", fps, rules["max_fps"], "" if ok_ else "Re-export with lk_export_preset (caps fps).")
    if rules.get("max_size_mb") and info.get("size_bytes") is not None:
        mb = info["size_bytes"] / 1e6
        ok_ = mb <= rules["max_size_mb"]
        add("file_size", "pass" if ok_ else "fail", round(mb, 2), rules["max_size_mb"],
            "" if ok_ else "Use lk_compress_to_size target_mb=%s." % rules["max_size_mb"])
    if rules.get("video_codecs"):
        ok_ = v.get("codec") in rules["video_codecs"]
        add("video_codec", "pass" if ok_ else "fail", v.get("codec"), rules["video_codecs"],
            "" if ok_ else "Re-encode with lk_export_preset (H.264).")
    if v.get("pix_fmt") and v["pix_fmt"] != "yuv420p":
        add("pixel_format", "warn", v["pix_fmt"], "yuv420p", "Re-encode with lk_export_preset for maximum compatibility.")
    if rules.get("audio_codecs"):
        if not info.get("has_audio"):
            add("audio_stream", "warn", "none", "recommended", "Clip is silent; add sound with lk_mix_music or lk_replace_audio.")
        else:
            codec = info["audio"][0].get("codec")
            ok_ = codec in rules["audio_codecs"]
            add("audio_codec", "pass" if ok_ else "fail", codec, rules["audio_codecs"],
                "" if ok_ else "Re-encode with lk_export_preset (AAC).")
    if loudness is not None and rules.get("loudness_lufs") is not None:
        target, tol = rules["loudness_lufs"], rules.get("loudness_tolerance") or 2
        lufs = loudness["input_i"]
        ok_ = abs(lufs - target) <= tol
        add("loudness", "pass" if ok_ else "fail", round(lufs, 1), "%s +/- %s LUFS" % (target, tol),
            "" if ok_ else "Run lk_normalize_loudness target_lufs=%s." % target)
        tp_max = rules.get("max_true_peak_db")
        if tp_max is not None:
            ok_ = loudness["input_tp"] <= tp_max
            add("true_peak", "pass" if ok_ else "warn", round(loudness["input_tp"], 1), "<= %s dBTP" % tp_max,
                "" if ok_ else "Run lk_normalize_loudness (limits the peak).")
    return checks


# --------------------------------------------------------------------------- export_preset
@tool_handler
def export_preset(args: Dict[str, Any]) -> Any:
    name = get_choice(args, "preset", EXPORT_PRESETS, None)
    if not name:
        raise ToolError("Missing required parameter 'preset'.", hint="One of %s" % list(EXPORT_PRESETS))
    fit = get_choice(args, "fit", ("contain", "cover"), "contain")
    cfg = EXPORT_PRESETS[name]
    job = Job(args, name, ext=".mp4", need_video=True)
    if "target_mb" in cfg:
        return _compress(job, args, cfg["target_mb"], cfg["audio_kbps"], True, cfg["size"][1], name,
                         fit=(fit, cfg["size"]), fps_cap=cfg["fps_cap"])
    v = job.info["video"]
    vf = []
    if cfg["size"]:
        vf.append(fit_filter(cfg["size"][0], cfg["size"][1], fit))
    if (v.get("fps") or 0) > cfg["fps_cap"] + 0.01:
        vf.append("fps=%s" % cfg["fps_cap"])
    vf.append("format=yuv420p")
    if not cfg["size"]:
        vf.append(EVEN)
    crf = int(get_num(args, "crf", cfg["crf"], lo=0, hi=51, integer=True))
    ff = ["-i", str(job.src), "-map", "0:v:0", "-map", "0:a?", "-vf", ",".join(vf),
          "-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-profile:v", "high"]
    if cfg["maxrate"]:
        ff += ["-maxrate", "%dk" % cfg["maxrate"], "-bufsize", "%dk" % (cfg["maxrate"] * 2)]
    if job.info["has_audio"]:
        ff += ["-c:a", "aac", "-b:a", "%dk" % cfg["audio_kbps"], "-ar", "48000", "-ac", "2"]
    ff += ["-movflags", "+faststart"]
    job.run(ff)
    result = job.done(op="export_preset", preset=name, fit=fit, crf=crf)
    warnings = [c for c in evaluate(probe(job.out), PLATFORM_RULES.get(name, {})) if c["status"] == "fail"]
    result["info"]["platform_warnings"] = warnings
    return result


# --------------------------------------------------------------------------- platform_check
@tool_handler
def platform_check(args: Dict[str, Any]) -> Any:
    platform = get_choice(args, "platform", PLATFORM_RULES, None)
    if not platform:
        raise ToolError("Missing required parameter 'platform'.", hint="One of %s" % list(PLATFORM_RULES))
    measure = get_bool(args, "check_loudness", True)
    src = resolve_input(args.get("input"))
    info = probe(src)
    rules = PLATFORM_RULES[platform]
    loud = None
    if measure and info["has_audio"] and rules.get("loudness_lufs") is not None:
        from .audio import measure_loudness
        from ..core.validate import get_timeout
        try:
            loud = measure_loudness(src, get_timeout(args), rules["loudness_lufs"])
            if math.isinf(loud["input_i"]):
                loud = None
        except ToolError:
            loud = None
    checks = evaluate(info, rules, loud)
    failed = [c for c in checks if c["status"] == "fail"]
    warned = [c for c in checks if c["status"] == "warn"]
    return {"output": None, "duration_s": info["duration_s"],
            "info": {"platform": platform, "label": rules["label"], "passed": not failed, "checks": checks,
                     "failed": [c["check"] for c in failed], "warnings": [c["check"] for c in warned],
                     "fixes": [c["fix"] for c in failed + warned if c["fix"]],
                     "rules_note": "Limits live in platform_rules.PLATFORM_RULES - verify current platform limits."}}


# --------------------------------------------------------------------------- compress_to_size
def plan_video_kbps(duration_s: float, target_mb: float, audio_kbps: int, safety: float = 0.96) -> float:
    return target_mb * 8000.0 * safety / duration_s - audio_kbps


def choose_height(video_kbps: float, w: int, h: int, fps: float, min_bpp: float = 0.07) -> int:
    """Largest standard height (<= source) whose bits-per-pixel stays acceptable; else the smallest."""
    ladder = [2160, 1440, 1080, 720, 480, 360, 240]
    for cand in [x for x in ladder if x <= h] or [h]:
        cw = cand * w / float(h)
        if video_kbps * 1000.0 / (cw * cand * max(fps, 1.0)) >= min_bpp:
            return cand
    return min(ladder[-1], h)


def _compress(job: Job, args: Dict[str, Any], target_mb: float, audio_kbps: int, allow_downscale: bool,
              max_height: Optional[int], op: str, fit: Optional[Tuple[str, Tuple[int, int]]] = None,
              fps_cap: Optional[float] = None) -> Dict[str, Any]:
    dur = job.info["duration_s"]
    if not dur or dur <= 0:
        raise ToolError("Cannot determine clip duration.")
    has_a = job.info["has_audio"]
    a_kbps = audio_kbps if has_a else 0
    v = job.info["video"]
    dw, dh = display_size(job.info)
    fps = min(v.get("fps") or 30.0, fps_cap or 1000)
    vk = plan_video_kbps(dur, target_mb, a_kbps)
    if vk < 40:
        raise ToolError("Target %.1f MB is too small for %.0f s of video." % (target_mb, dur),
                        hint="Raise target_mb, or shorten the clip with lk_trim first.")
    if has_a and vk < 250 and a_kbps > 48:
        a_kbps = 48
        vk = plan_video_kbps(dur, target_mb, a_kbps)
    height = min(dh, max_height or dh)
    if allow_downscale:
        height = min(height, choose_height(vk, dw, dh, fps))
    attempts = 0
    final_size = 0
    with new_tempdir() as tmp:
        while True:
            attempts += 1
            vf = []
            if fit:
                vf.append(fit_filter(fit[1][0], fit[1][1], fit[0]))
                if height < fit[1][1]:
                    vf.append("scale=-2:%d" % height)
            elif height < dh:
                vf.append("scale=-2:%d" % height)
            if fps_cap and (v.get("fps") or 0) > fps_cap + 0.01:
                vf.append("fps=%s" % fps_cap)
            vf += ["format=yuv420p", EVEN]
            base = ["-i", str(job.src), "-map", "0:v:0", "-vf", ",".join(vf), "-c:v", "libx264", "-preset", "medium",
                    "-b:v", "%dk" % vk, "-maxrate", "%dk" % (vk * 1.5), "-bufsize", "%dk" % (vk * 3),
                    "-passlogfile", str(Path(tmp) / "pass")]
            run_ffmpeg(["-y"] + base + ["-pass", "1", "-an", "-f", "null", "-"], job.timeout)
            ff = base + ["-pass", "2", "-movflags", "+faststart"]
            if has_a:
                ff += ["-map", "0:a:0", "-c:a", "aac", "-b:a", "%dk" % a_kbps, "-ar", "48000"]
                ff += ["-ac", "1"] if a_kbps <= 64 else []
            job.run(ff, commit=False)                              # the result stays a temporary file until the size is right
            final_size = job.tmp.stat().st_size
            if final_size <= target_mb * 1e6 or attempts >= 3:
                break
            vk = vk * (target_mb * 1e6 / final_size) * 0.93
            job._cleanup()
            if vk < 40:
                break
    if final_size > target_mb * 1e6:
        job.discard()
        raise ToolError("Could not reach %.1f MB (got %.2f MB)." % (target_mb, final_size / 1e6),
                        hint="Raise target_mb or shorten the clip.")
    job.commit()
    return job.done(op=op, target_mb=target_mb, result_mb=round(final_size / 1e6, 3), video_kbps=int(vk),
                    audio_kbps=a_kbps, attempts=attempts, scaled_to_height=height if height < dh else None)


@tool_handler
def compress_to_size(args: Dict[str, Any]) -> Any:
    target = get_num(args, "target_mb", required=True, lo=0.2, hi=100000)
    a_kbps = int(get_num(args, "audio_kbps", 96, lo=16, hi=320, integer=True))
    down = get_bool(args, "allow_downscale", True)
    job = Job(args, "%gmb" % target, ext=".mp4", need_video=True)
    return _compress(job, args, target, a_kbps, down, None, "compress_to_size")


# --------------------------------------------------------------------------- to_gif
@tool_handler
def to_gif(args: Dict[str, Any]) -> Any:
    start = get_time(args, "start", 0.0)
    end, duration = get_time(args, "end"), get_time(args, "duration")
    if end is not None and duration is not None:
        raise ToolError("Give either 'end' or 'duration', not both.")
    fps = int(get_num(args, "fps", 12, lo=1, hi=30, integer=True))
    width = int(get_num(args, "width", 480, lo=16, hi=2000, integer=True))
    colors = int(get_num(args, "max_colors", 256, lo=2, hi=256, integer=True))
    loops = int(get_num(args, "loop", 0, lo=0, hi=1000, integer=True))
    dither = get_choice(args, "dither", ("bayer", "sierra2_4a", "none"), "bayer")
    job = Job(args, "gif", ext=".gif", need_video=True)
    total = job.info["duration_s"] or 0
    if start >= total:
        raise ToolError("'start' is beyond the clip length (%.2fs)." % total)
    length = (end - start) if end is not None else (duration if duration is not None else total - start)
    length = min(length, total - start)
    if length <= 0:
        raise ToolError("Selected range is empty.")
    if length > 60:
        raise ToolError("GIFs longer than 60 s get enormous (%.0f s requested)." % length,
                        hint="Select a shorter range with start/end, or export a short MP4 instead.")
    dither_opt = {"bayer": "dither=bayer:bayer_scale=5", "sierra2_4a": "dither=sierra2_4a", "none": "dither=none"}[dither]
    vf = ("fps=%d,scale=%d:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=%d[p];[s1][p]paletteuse=%s"
          % (fps, min(width, job.info["video"]["display_width"]), colors, dither_opt))
    job.run(["-ss", "%.3f" % start, "-t", "%.3f" % length, "-i", str(job.src), "-an", "-vf", vf, "-loop", str(loops)])
    return job.done(op="to_gif", fps=fps, start=format_time(start), length_s=round(length, 3))


# --------------------------------------------------------------------------- contact_sheet
@tool_handler
def contact_sheet(args: Dict[str, Any]) -> Any:
    cols = int(get_num(args, "columns", 4, lo=1, hi=12, integer=True))
    rows = int(get_num(args, "rows", 3, lo=1, hi=12, integer=True))
    thumb = int(get_num(args, "thumb_width", 320, lo=48, hi=1000, integer=True))
    fmt = get_choice(args, "format", ("png", "jpg"), "jpg")
    job = Job(args, "contact", ext="." + fmt, need_video=True)
    dur = job.info["duration_s"]
    if not dur:
        raise ToolError("Cannot determine clip duration.")
    n = cols * rows
    thumb -= thumb % 2
    vf = "fps=%.6f,scale=%d:-2,tile=%dx%d:padding=4:margin=4:color=black" % (n / dur, thumb, cols, rows)
    ff = ["-ss", "%.3f" % (dur / (2.0 * n)), "-i", str(job.src), "-map", "0:v:0", "-an", "-vf", vf, "-frames:v", "1"]
    if fmt == "jpg":
        ff += ["-q:v", "3"]
    job.run(ff)
    return job.done(op="contact_sheet", columns=cols, rows=rows, frames=n)


# --------------------------------------------------------------------------- transcribe_captions
def srt_time(seconds: float) -> str:
    ms = int(round(max(0.0, seconds) * 1000))
    h, rem = divmod(ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)


def segments_to_srt(segments: List[Tuple[float, float, str]]) -> str:
    blocks = []
    for i, (start, end, text) in enumerate(segments, 1):
        text = " ".join(text.split())
        if text:
            blocks.append("%d\n%s --> %s\n%s\n" % (i, srt_time(start), srt_time(end), text))
    return "\n".join(blocks)


MODELS = ("tiny", "base", "small", "medium", "large-v3")


@tool_handler
def transcribe_captions(args: Dict[str, Any]) -> Any:
    try:
        from faster_whisper import WhisperModel  # optional dependency
    except ImportError:
        raise ToolError("Optional package 'faster-whisper' is not installed.",
                        hint="Install it with:  pip install faster-whisper   (then restart Hermes). "
                             "This is the only tool that needs it.")
    model_name = get_choice(args, "model", MODELS, "base")
    model_path = args.get("model_path")
    lang = args.get("language")
    if lang is not None and not (isinstance(lang, str) and 2 <= len(lang) <= 3 and lang.isalpha()):
        raise ToolError("'language' must be a 2-3 letter code like 'de' or 'en' (omit to auto-detect).")
    job = Job(args, "captions", ext=".srt", need_audio=True, strict_ext=True)
    with new_tempdir() as tmp:
        wav = Path(tmp) / "audio.wav"
        run_ffmpeg(["-y", "-i", str(job.src), "-vn", "-map", "0:a:0", "-ac", "1", "-ar", "16000", str(wav)], job.timeout)
        try:
            model = WhisperModel(str(model_path) if model_path else model_name, device="auto", compute_type="auto",
                                 local_files_only=True)
        except Exception as exc:  # noqa: BLE001 - missing weights, bad device, ...
            raise ToolError("Whisper model '%s' is not available locally: %s" % (model_path or model_name, exc),
                            hint="This plugin never downloads anything. Fetch the model ONCE yourself: "
                                 "python -c \"from faster_whisper import WhisperModel; WhisperModel('%s')\" "
                                 "- or pass model_path pointing to an existing model folder." % model_name)
        seg_iter, tinfo = model.transcribe(str(wav), language=lang, vad_filter=True)
        segments = [(s.start, s.end, s.text) for s in seg_iter]
    if not segments:
        raise ToolError("No speech was detected.", hint="Check that the audio contains speech; try a larger model.")
    job.tmp = job.temp_path()                                      # written next to the target, moved into place when complete
    try:
        job.tmp.write_text(segments_to_srt(segments), encoding="utf-8")
    except OSError as exc:
        job.discard()
        raise ToolError("Could not write the captions file: %s" % exc)
    job.commit()
    return {"output": str(job.out), "duration_s": job.info["duration_s"],
            "info": {"op": "transcribe_captions", "segments": len(segments), "model": str(model_path or model_name),
                     "language": getattr(tinfo, "language", lang), "next_step": "lk_burn_captions with this .srt"}}


# --------------------------------------------------------------------------- specs
SPECS = [
    ToolSpec(
        name="lk_export_preset",
        description=("Final export for a platform: H.264 + AAC, yuv420p, fast-start MP4, with the platform's size and fps cap. "
                     "Presets: reels, tiktok, shorts (1080x1920), youtube_1080p, youtube_4k, x_twitter (1280x720), "
                     "discord_8mb (auto-compressed to ~7.6 MB), web_mp4 (keeps size). fit=contain adds black bars, "
                     "fit=cover crops to fill; for vertical from landscape first use lk_crop_to_aspect or "
                     "lk_pad_blur_background. Follow with lk_platform_check."),
        handler=export_preset, required=["preset"],
        properties={"preset": {"type": "string", "enum": list(EXPORT_PRESETS), "description": "Target platform preset."},
                    "fit": {"type": "string", "enum": ["contain", "cover"], "default": "contain",
                            "description": "contain = fit inside (black bars), cover = fill and crop."},
                    "crf": {"type": "integer", "minimum": 0, "maximum": 51,
                            "description": "Override the preset's quality (lower = better/larger)."}}),
    ToolSpec(
        name="lk_platform_check",
        description=("Check a finished file against a platform's rules: duration, resolution, aspect ratio, fps, file size, "
                     "codecs, pixel format and loudness. Returns pass/fail per check plus concrete fixes (which lk_* tool to "
                     "run). ALWAYS run this last for social clips. Limits are editable defaults: verify current platform "
                     "limits. Does not create a file."),
        handler=platform_check, common=("input", "timeout_s"), required=["platform"],
        properties={"platform": {"type": "string", "enum": list(PLATFORM_RULES), "description": "Platform to check against."},
                    "check_loudness": {"type": "boolean", "default": True, "description": "Also measure LUFS (needs audio; a bit slower)."}}),
    ToolSpec(
        name="lk_compress_to_size",
        description=("Shrink a video to fit under target_mb megabytes (decimal MB) using two-pass H.264 bitrate planning; "
                     "downscales automatically if the size budget is too low for the resolution. Use for Discord/email "
                     "limits. Fails with a clear message if the target is unrealistic for the duration."),
        handler=compress_to_size, required=["target_mb"],
        properties={"target_mb": {"type": "number", "minimum": 0.2, "description": "Maximum output size in megabytes."},
                    "audio_kbps": {"type": "integer", "default": 96, "description": "Audio bitrate in kbit/s."},
                    "allow_downscale": {"type": "boolean", "default": True,
                                        "description": "Reduce resolution when bitrate would otherwise look blocky."}}),
    ToolSpec(
        name="lk_to_gif",
        description=("Convert a section of a video to an animated GIF with an optimised palette (no audio). Max 60 s. "
                     "GIFs are large: keep it short, width <= 480, fps 10-15."),
        handler=to_gif,
        properties={"start": tprop("Start of the section. Default 0."), "end": tprop("End of the section (exclusive with duration)."),
                    "duration": tprop("Length of the section (exclusive with end)."),
                    "fps": {"type": "integer", "default": 12, "description": "Frames per second (1-30)."},
                    "width": {"type": "integer", "default": 480, "description": "Width in pixels (never upscaled)."},
                    "max_colors": {"type": "integer", "default": 256, "description": "Palette size 2-256."},
                    "loop": {"type": "integer", "default": 0, "description": "Repeats; 0 = loop forever."},
                    "dither": {"type": "string", "enum": ["bayer", "sierra2_4a", "none"], "default": "bayer",
                               "description": "bayer = smaller files, sierra2_4a = smoother gradients."}}),
    ToolSpec(
        name="lk_contact_sheet",
        description="Make one image with a grid of evenly spaced frames from the video (overview / thumbnail picking). columns x rows frames.",
        handler=contact_sheet,
        properties={"columns": {"type": "integer", "default": 4, "description": "Frames per row (1-12)."},
                    "rows": {"type": "integer", "default": 3, "description": "Number of rows (1-12)."},
                    "thumb_width": {"type": "integer", "default": 320, "description": "Width of each frame in pixels."},
                    "format": {"type": "string", "enum": ["png", "jpg"], "default": "jpg", "description": "Image format."}}),
    ToolSpec(
        name="lk_transcribe_captions",
        description=("OPTIONAL. Transcribe speech to an .srt file with local faster-whisper (no cloud). Needs "
                     "`pip install faster-whisper` and a model already on disk (the plugin never downloads). Returns "
                     "ok:false with install hints otherwise. Feed the .srt to lk_burn_captions. Slow on CPU for long videos."),
        handler=transcribe_captions,
        properties={"model": {"type": "string", "enum": list(MODELS), "default": "base",
                              "description": "Whisper model size: bigger = more accurate and slower."},
                    "model_path": {"type": "string", "description": "Optional folder of a locally stored model."},
                    "language": {"type": "string", "description": "Language code (de, en, ...). Omit to auto-detect."}}),
]
