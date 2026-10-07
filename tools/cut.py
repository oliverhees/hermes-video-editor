"""B. Cut & time tools."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..core.ffmpeg import (Job, encode_args, even_filter, filter_complex_args, new_tempdir, output_ext,
                           probe, run_ffmpeg, tool_handler)
from ..core.paths import plan_output, resolve_input
from ..core.result import ToolError
from ..core.spec import ToolSpec
from ..core.timeparse import format_time, parse_time
from ..core.validate import get_bool, get_choice, get_num, get_time, get_timeout
from ._common import CRF_PROP, EVEN, crf_of, tprop, vchain
from .info import detect_silence_ranges


def build_trim_args(src: str, start: float, duration: Any, mode: str, ext: str, crf: int,
                    has_audio: bool, vf: Any = None) -> list:
    """Pure function: ffmpeg arguments (without output path) for lk_trim."""
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
                        hint="Run lk_media_probe for the duration.")
    if end is not None:
        duration = end - start
    if duration is not None and total is not None:
        duration = min(duration, total - start)
    job.run(build_trim_args(str(job.src), start, duration, mode, ext, crf, job.info["has_audio"],
                                even_filter(job.info)))
    return job.done(op="trim", mode=mode, start=format_time(start), requested_duration_s=duration)


Seg = Tuple[float, float]


def keep_segments(total: float, cuts: List[Seg], min_keep: float = 0.05) -> List[Seg]:
    """Complement of 'cuts' (merged, clamped) inside [0, total]."""
    merged: List[List[float]] = []
    for a, b in sorted((max(0.0, a), min(total, b)) for a, b in cuts if b > a):
        if a >= b:
            continue
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    keep, pos = [], 0.0
    for a, b in merged:
        if a - pos >= min_keep:
            keep.append((pos, a))
        pos = b
    if total - pos >= min_keep:
        keep.append((pos, total))
    return keep


def cut_graph(segs: List[Seg], has_v: bool, has_a: bool) -> str:
    """filter_complex that keeps only 'segs' (in order) and concatenates them. Labels [vo]/[ao]."""
    parts, labels = [], ""
    for i, (a, b) in enumerate(segs):
        if has_v:
            parts.append("[0:v:0]trim=start=%.3f:end=%.3f,setpts=PTS-STARTPTS[v%d]" % (a, b, i))
            labels += "[v%d]" % i
        if has_a:
            parts.append("[0:a:0]atrim=start=%.3f:end=%.3f,asetpts=PTS-STARTPTS[a%d]" % (a, b, i))
            labels += "[a%d]" % i
    outs = ("[vc]" if has_v else "") + ("[ao]" if has_a else "")
    parts.append("%sconcat=n=%d:v=%d:a=%d%s" % (labels, len(segs), int(has_v), int(has_a), outs))
    if has_v:
        parts.append("[vc]%s[vo]" % EVEN)
    return ";".join(parts)


def run_cut(job: Job, segs: List[Seg], crf: int) -> None:
    has_v, has_a = job.info["has_video"], job.info["has_audio"]
    graph = cut_graph(segs, has_v, has_a)
    maps: List[str] = []
    if has_v:
        maps += ["-map", "[vo]"]
    if has_a:
        maps += ["-map", "[ao]"]
    with new_tempdir() as tmp:
        ff = ["-i", str(job.src)] + filter_complex_args(graph, Path(tmp)) + maps
        ff += encode_args(job.out.suffix.lower(), crf=crf, audio=has_a)
        job.run(ff)


@tool_handler
def split(args: Dict[str, Any]) -> Any:
    raw = args.get("times")
    if not isinstance(raw, list) or not raw:
        raise ToolError("'times' must be a non-empty list of split points.", hint='Example: ["00:10", 25.5]')
    times = sorted(parse_time(t, "times[]") for t in raw)
    mode = get_choice(args, "mode", ("accurate", "fast"), "accurate")
    crf = crf_of(args)
    job = Job(args, "part", ext=None, need_video=True)
    total = job.info["duration_s"]
    if total is None:
        raise ToolError("Cannot determine clip duration.")
    if times[0] <= 0 or times[-1] >= total or len(set(times)) != len(times):
        raise ToolError("Split points must be unique and strictly inside the clip (0 < t < %.2fs)." % total)
    bounds = [0.0] + times + [total]
    ext = job.src.suffix.lower() if mode == "fast" else output_ext(job.src)
    outputs = []
    try:
        for i in range(len(bounds) - 1):
            a, b = bounds[i], bounds[i + 1]
            out = plan_output(job.src, "part%d" % (i + 1), ext, None, args.get("output_dir"), job.overwrite)
            job.out = out
            job.run(build_trim_args(str(job.src), a, b - a, mode, ext, crf, job.info["has_audio"],
                                    even_filter(job.info)))
            outputs.append(str(out))
    except ToolError:
        for o in outputs:
            try:
                Path(o).unlink()
            except OSError:
                pass
        raise
    return {"output": outputs[0], "duration_s": total,
            "info": {"op": "split", "outputs": outputs, "parts": len(outputs), "mode": mode,
                     "boundaries_s": bounds}}


def _norm_fps(f: Optional[float]) -> float:
    return round(f, 2) if f else 30.0


def can_stream_copy(infos: List[Dict[str, Any]]) -> bool:
    def sig(i: Dict[str, Any]) -> tuple:
        v, a = i.get("video") or {}, (i["audio"][0] if i["audio"] else {})
        return (v.get("codec"), v.get("width"), v.get("height"), v.get("pix_fmt"), _norm_fps(v.get("fps")),
                v.get("rotation"), a.get("codec"), a.get("sample_rate"), a.get("channels"))
    return len({sig(i) for i in infos}) == 1 and all(i["has_video"] for i in infos)


def join_graph(infos: List[Dict[str, Any]], width: int, height: int, fps: float) -> Tuple[str, bool]:
    any_audio = any(i["has_audio"] for i in infos)
    parts, labels = [], ""
    for n, i in enumerate(infos):
        parts.append("[%d:v:0]scale=%d:%d:force_original_aspect_ratio=decrease,pad=%d:%d:(ow-iw)/2:(oh-ih)/2,"
                     "setsar=1,fps=%s,format=yuv420p[v%d]" % (n, width, height, width, height, fps, n))
        labels += "[v%d]" % n
        if any_audio:
            if i["has_audio"]:
                parts.append("[%d:a:0]aresample=48000,aformat=channel_layouts=stereo[a%d]" % (n, n))
            else:
                parts.append("anullsrc=r=48000:cl=stereo:d=%.3f[a%d]" % (i["duration_s"] or 1.0, n))
            labels += "[a%d]" % n
    parts.append("%sconcat=n=%d:v=1:a=%d[vo]%s" % (labels, len(infos), int(any_audio), "[ao]" if any_audio else ""))
    return ";".join(parts), any_audio


@tool_handler
def join(args: Dict[str, Any]) -> Any:
    raw = args.get("inputs")
    if not isinstance(raw, list) or len(raw) < 2:
        raise ToolError("'inputs' must be a list of at least 2 file paths, in play order.")
    mode = get_choice(args, "mode", ("auto", "copy", "reencode"), "auto")
    crf = crf_of(args)
    paths = [resolve_input(p, "inputs[]") for p in raw]
    infos = [probe(p) for p in paths]
    if not all(i["has_video"] for i in infos):
        raise ToolError("All inputs must contain a video stream.")
    job = Job(dict(args, input=str(paths[0])), "joined", ext="av", need_video=True)
    copy_ok = can_stream_copy(infos)
    if mode == "copy" and not copy_ok:
        raise ToolError("Clips differ in codec/size/fps/audio, so stream copy would break.",
                        hint="Use mode 'auto' or 'reencode'.")
    use_copy = copy_ok if mode == "auto" else mode == "copy"
    with new_tempdir() as tmp:
        if use_copy:
            listing = Path(tmp) / "list.txt"
            listing.write_text("".join("file '%s'\n" % str(p).replace("'", "'\\''") for p in paths),
                               encoding="utf-8")
            job.run(["-f", "concat", "-safe", "0", "-i", str(listing), "-map", "0:v:0", "-map", "0:a?",
                     "-c", "copy"] + (["-movflags", "+faststart"] if job.out.suffix.lower() in
                                      (".mp4", ".mov", ".m4v") else []))
        else:
            v = infos[0]["video"]
            width, height = v["display_width"] // 2 * 2, v["display_height"] // 2 * 2
            fps = _norm_fps(v["fps"])
            graph, any_audio = join_graph(infos, width, height, fps)
            ff: List[str] = []
            for p in paths:
                ff += ["-i", str(p)]
            ff += filter_complex_args(graph, Path(tmp)) + ["-map", "[vo]"] + (["-map", "[ao]"] if any_audio else [])
            ff += encode_args(job.out.suffix.lower(), crf=crf, audio=any_audio)
            job.run(ff)
    return job.done(op="join", method="stream_copy" if use_copy else "reencode", clips=len(paths))


XFADES = ('fade', 'fadeblack', 'fadewhite', 'dissolve', 'wipeleft', 'wiperight', 'slideleft', 'slideright', 'circleopen', 'circleclose', 'pixelize')


def crossfade_graph(infos: List[Dict[str, Any]], width: int, height: int, fps: float, transition: str, d: float) -> Tuple[str, bool, float]:
    """Pure: filter_complex that joins the clips with an xfade of d seconds between each pair. Returns (graph, has_audio, total_s)."""
    any_audio = any(i["has_audio"] for i in infos)
    parts: List[str] = []
    for n, i in enumerate(infos):
        parts.append("[%d:v:0]scale=%d:%d:force_original_aspect_ratio=decrease,pad=%d:%d:(ow-iw)/2:(oh-ih)/2,"
                     "setsar=1,fps=%s,format=yuv420p,settb=AVTB,setpts=PTS-STARTPTS[v%d]" % (n, width, height, width, height, fps, n))
        if any_audio:
            if i["has_audio"]:
                parts.append("[%d:a:0]aresample=48000,aformat=channel_layouts=stereo,apad,atrim=duration=%.3f,asetpts=PTS-STARTPTS[a%d]"
                             % (n, i["duration_s"], n))
            else:
                parts.append("anullsrc=r=48000:cl=stereo:d=%.3f[a%d]" % (i["duration_s"], n))
    length = infos[0]["duration_s"]
    vcur, acur = "v0", "a0"
    for k in range(1, len(infos)):
        last = k == len(infos) - 1
        vout, aout = ("vo" if last else "vx%d" % k), ("ao" if last else "ax%d" % k)
        parts.append("[%s][v%d]xfade=transition=%s:duration=%s:offset=%.3f[%s]" % (vcur, k, transition, round(d, 3), length - d, vout))
        if any_audio:
            parts.append("[%s][a%d]acrossfade=d=%s[%s]" % (acur, k, round(d, 3), aout))
        vcur, acur = vout, aout
        length += infos[k]["duration_s"] - d
    return ";".join(parts), any_audio, length


@tool_handler
def crossfade_join(args: Dict[str, Any]) -> Any:
    from ..core.ffmpeg import require_filter
    raw = args.get("inputs")
    if not isinstance(raw, list) or len(raw) < 2:
        raise ToolError("'inputs' must be a list of at least 2 file paths, in play order.")
    transition = get_choice(args, "transition", XFADES, "fade")
    d = get_num(args, "duration_s", 1.0, lo=0.1, hi=5.0)
    crf = crf_of(args)
    require_filter("xfade", "transitions between clips")
    paths = [resolve_input(p, "inputs[]") for p in raw]
    infos = [probe(p) for p in paths]
    if not all(i["has_video"] for i in infos):
        raise ToolError("All inputs must contain a video stream.")
    for n, i in enumerate(infos):
        need = d if n in (0, len(infos) - 1) else 2 * d              # a clip in the middle has a transition at both ends
        if not i["duration_s"] or i["duration_s"] <= need + 0.05:
            raise ToolError("Clip %d is too short for a %s s transition (needs more than %s s)." % (n + 1, d, round(need, 2)),
                            hint="Use a shorter duration_s or longer clips.")
    job = Job(dict(args, input=str(paths[0])), "crossfade", ext="av", need_video=True)
    v = infos[0]["video"]
    width, height = v["display_width"] // 2 * 2, v["display_height"] // 2 * 2
    graph, any_audio, total = crossfade_graph(infos, width, height, _norm_fps(v["fps"]), transition, d)
    with new_tempdir() as tmp:
        ff: List[str] = []
        for p in paths:
            ff += ["-i", str(p)]
        ff += filter_complex_args(graph, Path(tmp)) + ["-map", "[vo]"] + (["-map", "[ao]"] if any_audio else [])
        ff += encode_args(job.out.suffix.lower(), crf=crf, audio=any_audio)
        job.run(ff)
    return job.done(op="crossfade_join", transition=transition, transition_s=d, clips=len(paths), expected_duration_s=round(total, 3))


def silence_cuts(ranges: List[List[float]], padding: float) -> List[Seg]:
    cuts = []
    for s, e in ranges:
        if e - s > 2 * padding + 0.02:
            cuts.append((s + padding, e - padding))
    return cuts


@tool_handler
def remove_silence(args: Dict[str, Any]) -> Any:
    noise = get_num(args, "noise_db", -35, lo=-90, hi=0)
    min_d = get_num(args, "min_silence_s", 0.5, lo=0.05, hi=3600)
    padding = get_num(args, "padding_s", 0.1, lo=0, hi=5)
    crf = crf_of(args)
    job = Job(args, "nosilence", ext="av", need_video=False, need_audio=True)
    total = job.info["duration_s"]
    ranges = detect_silence_ranges(job.src, noise, min_d, job.timeout, total)
    cuts = silence_cuts(ranges, padding)
    keep = keep_segments(total, cuts)
    removed = sum(b - a for a, b in cuts)
    if not cuts:
        return {"output": str(job.src), "duration_s": total,
                "info": {"op": "remove_silence", "unchanged": True, "removed_s": 0,
                         "note": "No silence found with these settings; input returned as-is (not modified)."}}
    if not keep:
        raise ToolError("Everything is silent with these settings; nothing would remain.",
                        hint="Raise noise_db (e.g. -45) or min_silence_s.")
    run_cut(job, keep, crf)
    return job.done(op="remove_silence", removed_s=round(removed, 3), segments_kept=len(keep),
                    silences_found=len(ranges))


@tool_handler
def remove_segments(args: Dict[str, Any]) -> Any:
    raw = args.get("segments")
    if not isinstance(raw, list) or not raw:
        raise ToolError("'segments' must be a non-empty list of {start, end} ranges to REMOVE.",
                        hint='Example: [{"start": "00:05", "end": "00:08"}]')
    cuts = []
    for item in raw:
        if not isinstance(item, dict) or "start" not in item or "end" not in item:
            raise ToolError("Each segment needs 'start' and 'end'.")
        a, b = parse_time(item["start"], "start"), parse_time(item["end"], "end")
        if b <= a:
            raise ToolError("Segment end (%s) must be after start (%s)." % (item["end"], item["start"]))
        cuts.append((a, b))
    crf = crf_of(args)
    job = Job(args, "cut", ext="av", need_video=True)
    total = job.info["duration_s"]
    if total is None:
        raise ToolError("Cannot determine clip duration.")
    keep = keep_segments(total, cuts)
    if not keep:
        raise ToolError("These ranges remove the whole clip.")
    run_cut(job, keep, crf)
    return job.done(op="remove_segments", removed_s=round(total - sum(b - a for a, b in keep), 3),
                    segments_kept=len(keep))


def atempo_chain(factor: float) -> str:
    """atempo only takes 0.5-2.0 per stage; chain stages for 0.25-4x. Pitch stays unchanged."""
    stages, f = [], factor
    while f > 2.0:
        stages.append(2.0)
        f /= 2.0
    while f < 0.5:
        stages.append(0.5)
        f /= 0.5
    stages.append(f)
    return ",".join("atempo=%.6f" % s for s in stages)


@tool_handler
def change_speed(args: Dict[str, Any]) -> Any:
    factor = get_num(args, "factor", required=True, lo=0.25, hi=4.0)
    crf = crf_of(args)
    job = Job(args, "speed%s" % ("%g" % factor).replace(".", "p"), ext="av", need_video=True)
    has_a = job.info["has_audio"]
    ff = ["-i", str(job.src), "-map", "0:v:0", "-map", "0:a?", "-vf", vchain("setpts=PTS/%.6f" % factor)]
    if has_a:
        ff += ["-af", atempo_chain(factor)]
    ff += encode_args(job.out.suffix.lower(), crf=crf, audio=has_a)
    job.run(ff)
    return job.done(op="change_speed", factor=factor, audio_pitch_corrected=has_a)


MAX_REVERSE_S = 300


@tool_handler
def reverse(args: Dict[str, Any]) -> Any:
    crf = crf_of(args)
    job = Job(args, "reversed", ext="av", need_video=True)
    if (job.info["duration_s"] or 0) > MAX_REVERSE_S:
        raise ToolError("Clip is longer than %ds; reversing buffers the whole clip in RAM." % MAX_REVERSE_S,
                        hint="Use lk_trim to cut a shorter section first.")
    has_a = job.info["has_audio"]
    ff = ["-i", str(job.src), "-map", "0:v:0", "-map", "0:a?", "-vf", vchain("reverse")]
    if has_a:
        ff += ["-af", "areverse"]
    ff += encode_args(job.out.suffix.lower(), crf=crf, audio=has_a)
    job.run(ff)
    return job.done(op="reverse")


@tool_handler
def loop(args: Dict[str, Any]) -> Any:
    count = get_num(args, "count", None, lo=2, hi=200, integer=True)
    target = get_time(args, "target_duration_s")
    if (count is None) == (target is None):
        raise ToolError("Give exactly one of 'count' (total plays) or 'target_duration_s'.")
    crf = crf_of(args)
    job = Job(args, "loop", ext="av", need_video=True)
    dur = job.info["duration_s"]
    if not dur:
        raise ToolError("Cannot determine clip duration.")
    total = dur * count if count else target
    if total > 6 * 3600:
        raise ToolError("Result would be longer than 6 hours.")
    plays = int(math.ceil(total / dur))
    has_a = job.info["has_audio"]
    ff = ["-stream_loop", str(plays - 1), "-i", str(job.src), "-t", "%.3f" % total,
          "-map", "0:v:0", "-map", "0:a?", "-vf", vchain()]
    ff += encode_args(job.out.suffix.lower(), crf=crf, audio=has_a)
    job.run(ff)
    return job.done(op="loop", plays=plays, target_s=round(total, 3))


SPECS = [
    ToolSpec(
        name="lk_trim",
        description=("Keep one section of a video: from 'start' to 'end' (or start + 'duration'), all "
                     "in seconds or MM:SS / HH:MM:SS. mode 'accurate' (default) re-encodes with frame-exact "
                     "cuts; mode 'fast' stream-copies (instant, lossless, but cuts snap to keyframes). "
                     "Use lk_split to cut into several parts and lk_remove_segments to delete middle sections."),
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
    ToolSpec(
        name="lk_split",
        description=("Cut one video into consecutive parts at the given timestamps (N split points -> N+1 "
                     "files named <name>_part1, _part2...). Result 'output' is the first part; all files are in "
                     "info.outputs. To keep only one section use lk_trim instead."),
        handler=split, common=("input", "output_dir", "overwrite", "timeout_s"), required=["times"],
        properties={"times": {"type": "array", "items": {"type": ["number", "string"]},
                              "description": "Split points inside the clip, e.g. [10, \"00:25\"]. Seconds or MM:SS."},
                    "mode": {"type": "string", "enum": ["accurate", "fast"], "default": "accurate",
                             "description": "accurate = re-encode (frame-exact); fast = stream copy (keyframe-snapped)."},
                    "crf": CRF_PROP}),
    ToolSpec(
        name="lk_join",
        description=("Concatenate clips in the order given. If all clips share codec/size/fps/audio format they "
                     "are joined by stream copy (instant); otherwise they are re-encoded to the first clip's size "
                     "(letterboxed) and fps. Clips without audio get silence when others have audio."),
        handler=join, common=("output", "output_dir", "overwrite", "timeout_s"), required=["inputs"],
        properties={"inputs": {"type": "array", "items": {"type": "string"}, "minItems": 2,
                               "description": "Paths of the clips in play order (at least 2)."},
                    "mode": {"type": "string", "enum": ["auto", "copy", "reencode"], "default": "auto",
                             "description": "auto = copy when compatible else re-encode."},
                    "crf": CRF_PROP}),
    ToolSpec(
        name="lk_remove_silence",
        description=("Automatically cut silent stretches out of a clip with a little padding so speech is not "
                     "clipped (tighten talking-head/podcast videos). Needs an audio track. Returns the input "
                     "path unchanged if no silence is found. Use lk_detect_silence first to preview."),
        handler=remove_silence,
        properties={"noise_db": {"type": "number", "default": -35, "description": "Silence level in dB (-35 default, -45 stricter)."},
                    "min_silence_s": {"type": "number", "default": 0.5, "description": "Only cut silences at least this long (seconds)."},
                    "padding_s": {"type": "number", "default": 0.1, "description": "Seconds of silence kept around speech on each side."},
                    "crf": CRF_PROP}),
    ToolSpec(
        name="lk_remove_segments",
        description=("Delete one or more time ranges from the middle of a clip and keep the rest (joined "
                     "seamlessly). To keep ONE range use lk_trim."),
        handler=remove_segments, required=["segments"],
        properties={"segments": {"type": "array", "description": "Ranges to REMOVE.",
                                 "items": {"type": "object", "required": ["start", "end"],
                                           "properties": {"start": tprop("Range start."),
                                                          "end": tprop("Range end.")}}},
                    "crf": CRF_PROP}),
    ToolSpec(
        name="lk_change_speed",
        description=("Speed up or slow down video and audio together (0.25x-4x). Audio pitch is preserved. "
                     "factor 2 = twice as fast, 0.5 = half speed."),
        handler=change_speed, required=["factor"],
        properties={"factor": {"type": "number", "minimum": 0.25, "maximum": 4,
                               "description": "Speed multiplier. 2 = 2x faster, 0.5 = slow motion."},
                    "crf": CRF_PROP}),
    ToolSpec(
        name="lk_reverse",
        description=("Play a clip backwards (video and audio). Whole clip is held in RAM, so it refuses clips "
                     "over 300 s: trim first."),
        handler=reverse, properties={"crf": CRF_PROP}),
    ToolSpec(
        name="lk_loop",
        description=("Repeat a clip. Give 'count' (total number of plays, e.g. 3 = original + 2 repeats) OR "
                     "'target_duration_s' (loop and cut to this length). Exactly one of them."),
        handler=loop,
        properties={"count": {"type": "integer", "minimum": 2, "maximum": 200,
                              "description": "Total number of plays including the first."},
                    "target_duration_s": tprop("Final length to reach."), "crf": CRF_PROP}),
    ToolSpec(
        name="lk_crossfade_join",
        description=("Join clips in the order given with a smooth transition between each pair (fade, dissolve, wipe, slide, "
                     "circle, pixelize). Picture and sound cross-fade; the result is shorter than the sum of the clips by one "
                     "transition each. Always re-encodes to the first clip's size and fps (letterboxed). Every clip must be "
                     "longer than the transition (clips in the middle: twice as long). For hard cuts use lk_join."),
        handler=crossfade_join, common=("output", "output_dir", "overwrite", "timeout_s"), required=["inputs"],
        properties={"inputs": {"type": "array", "items": {"type": "string"}, "minItems": 2,
                               "description": "Paths of the clips in play order (at least 2)."},
                    "transition": {"type": "string", "enum": list(XFADES), "default": "fade", "description": "Transition style."},
                    "duration_s": {"type": "number", "default": 1.0, "description": "Length of each transition in seconds (0.1 to 5)."},
                    "crf": CRF_PROP}),
]
