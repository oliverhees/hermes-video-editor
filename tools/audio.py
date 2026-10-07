"""E. Audio tools. Video streams are stream-copied (never re-encoded) unless stated otherwise."""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.ffmpeg import (Job, audio_codec_args, filter_complex_args, has_encoder, new_tempdir, probe,
                           run_ffmpeg, tool_handler)
from ..core.paths import resolve_input
from ..core.result import ToolError
from ..core.spec import ToolSpec
from ..core.validate import get_bool, get_choice, get_num, get_time, get_timeout
from ._common import second_input, tprop

MOVFLAGS = (".mp4", ".mov", ".m4v")


def _tail(job: Job) -> List[str]:
    return ["-movflags", "+faststart"] if job.out.suffix.lower() in MOVFLAGS else []


def audio_edit(job: Job, af: str, extra_in: Optional[List[str]] = None, out_opts: Optional[List[str]] = None,
               bitrate: int = 192) -> None:
    """Apply an -af chain to the first audio stream; copy video untouched."""
    ff = ["-i", str(job.src)] + list(extra_in or [])
    if job.info["has_video"]:
        ff += ["-map", "0:v:0", "-c:v", "copy"]
    ff += ["-map", "0:a:0", "-af", af] + audio_codec_args(job.out.suffix.lower(), bitrate) + list(out_opts or []) + _tail(job)
    job.run(ff)


def audio_graph_edit(job: Job, inputs: List[List[str]], graph: str, label: str = "[ao]",
                     out_opts: Optional[List[str]] = None) -> None:
    ff: List[str] = []
    for item in inputs:
        ff += item
    with new_tempdir() as tmp:
        ff += filter_complex_args(graph, Path(tmp))
        if job.info["has_video"]:
            ff += ["-map", "0:v:0", "-c:v", "copy"]
        ff += ["-map", label] + audio_codec_args(job.out.suffix.lower()) + list(out_opts or []) + _tail(job)
        job.run(ff)


# ------------------------------------------------------------------ extract_audio
FORMATS = {"mp3": ".mp3", "wav": ".wav", "m4a": ".m4a", "flac": ".flac"}


@tool_handler
def extract_audio(args: Dict[str, Any]) -> Any:
    fmt = get_choice(args, "format", FORMATS, "mp3")
    kbps = int(get_num(args, "bitrate_kbps", 192, lo=32, hi=512, integer=True))
    track = int(get_num(args, "audio_track", 0, lo=0, hi=31, integer=True))
    job = Job(args, "audio", ext=FORMATS[fmt], need_audio=True)
    if track >= len(job.info["audio"]):
        raise ToolError("audio_track %d does not exist (file has %d audio streams)." % (track, len(job.info["audio"])))
    if fmt == "mp3" and not has_encoder("libmp3lame"):
        raise ToolError("This FFmpeg build has no MP3 encoder (libmp3lame).", hint="Use format 'm4a' or 'wav'.")
    job.run(["-i", str(job.src), "-vn", "-map", "0:a:%d" % track] + audio_codec_args(FORMATS[fmt], kbps))
    return job.done(op="extract_audio", format=fmt, audio_track=track)


# ------------------------------------------------------------------ replace_audio
@tool_handler
def replace_audio(args: Dict[str, Any]) -> Any:
    new, new_info = second_input(args, "audio")
    if not new_info["has_audio"]:
        raise ToolError("'audio' file has no audio stream.")
    mode = get_choice(args, "mode", ("trim", "shortest", "loop"), "trim")
    job = Job(args, "newaudio", ext="av", need_video=True)
    dur = job.info["duration_s"]
    ff: List[str] = ["-i", str(job.src)]
    ff += (["-stream_loop", "-1"] if mode == "loop" else []) + ["-i", str(new)]
    ff += ["-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy"]
    if mode == "trim":
        ff += ["-af", "apad"]
    ff += audio_codec_args(job.out.suffix.lower())
    ff += ["-shortest"] if mode == "shortest" else (["-t", "%.3f" % dur] if dur else [])
    ff += _tail(job)
    job.run(ff)
    return job.done(op="replace_audio", mode=mode, new_audio=str(new))


# ------------------------------------------------------------------ mix_music
DUCK = {"light": 3, "medium": 6, "strong": 12}


def music_graph(video_dur: float, has_main_audio: bool, volume_db: float, ducking: bool, ratio: int,
                fade_out_s: float) -> str:
    music = "[1:a]volume=%sdB" % volume_db
    if fade_out_s > 0 and video_dur > fade_out_s:
        music += ",afade=t=out:st=%.3f:d=%s" % (video_dur - fade_out_s, fade_out_s)
    if not has_main_audio:
        return music + "[ao]"
    if ducking:
        return (music + "[m];[0:a]asplit=2[vo][sc];"
                "[m][sc]sidechaincompress=threshold=0.04:ratio=%d:attack=20:release=400[duck];"
                "[vo][duck]amix=inputs=2:duration=first:normalize=0[ao]" % ratio)
    return music + "[m];[0:a][m]amix=inputs=2:duration=first:normalize=0[ao]"


@tool_handler
def mix_music(args: Dict[str, Any]) -> Any:
    music = resolve_input(args.get("music"), "music")
    m_info = probe(music)
    if not m_info["has_audio"]:
        raise ToolError("'music' file has no audio stream.")
    vol = get_num(args, "music_volume_db", -18, lo=-60, hi=12)
    ducking = get_bool(args, "ducking", True)
    strength = get_choice(args, "duck_strength", DUCK, "medium")
    fade = get_num(args, "fade_out_s", 2, lo=0, hi=60)
    job = Job(args, "music", ext="av")
    dur = job.info["duration_s"]
    if not dur:
        raise ToolError("Cannot determine the main clip duration.")
    graph = music_graph(dur, job.info["has_audio"], vol, ducking, DUCK[strength], fade)
    audio_graph_edit(job, [["-i", str(job.src)], ["-stream_loop", "-1", "-i", str(music)]], graph,
                     out_opts=["-t", "%.3f" % dur])
    return job.done(op="mix_music", music=str(music), music_volume_db=vol,
                    ducking=ducking and job.info["has_audio"], duck_strength=strength)


# ------------------------------------------------------------------ normalize_loudness
def parse_loudnorm_json(stderr: str) -> Dict[str, Any]:
    blocks = re.findall(r"\{[^{}]*\}", stderr, re.S)
    for block in reversed(blocks):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        if "input_i" in data:
            return data
    raise ToolError("Could not read loudness measurement from FFmpeg output.")


def measure_loudness(src: Path, timeout_s: float, target: float = -14.0, tp: float = -1.5,
                     lra: float = 11.0) -> Dict[str, float]:
    proc = run_ffmpeg(["-i", str(src), "-vn", "-map", "0:a:0", "-af",
                       "loudnorm=I=%s:TP=%s:LRA=%s:print_format=json" % (target, tp, lra), "-f", "null", "-"],
                      timeout_s, loglevel="info")
    raw = parse_loudnorm_json(proc.stderr)
    out = {k: float(raw[k]) for k in ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")}
    return out


@tool_handler
def normalize_loudness(args: Dict[str, Any]) -> Any:
    target = get_num(args, "target_lufs", -14, lo=-40, hi=-5)
    tp = get_num(args, "true_peak_db", -1.5, lo=-9, hi=0)
    lra = get_num(args, "lra", 11, lo=1, hi=50)
    verify = get_bool(args, "verify", True)
    job = Job(args, "loudnorm", ext="av", need_audio=True)
    m = measure_loudness(job.src, job.timeout, target, tp, lra)
    if any(math.isinf(v) or math.isnan(v) for v in (m["input_i"], m["input_thresh"])):
        raise ToolError("The audio is silent or too quiet to measure loudness.", hint="Nothing to normalise.")
    af = ("loudnorm=I=%s:TP=%s:LRA=%s:measured_I=%s:measured_TP=%s:measured_LRA=%s:measured_thresh=%s:"
          "offset=%s:linear=true,aresample=48000" % (target, tp, lra, m["input_i"], m["input_tp"],
                                                     m["input_lra"], m["input_thresh"], m["target_offset"]))
    audio_edit(job, af)
    extra: Dict[str, Any] = {"op": "normalize_loudness", "target_lufs": target, "measured_before_lufs": m["input_i"],
                             "true_peak_before_db": m["input_tp"]}
    if verify:
        after = measure_loudness(job.out, job.timeout, target, tp, lra)
        extra["measured_after_lufs"] = after["input_i"]
        extra["true_peak_after_db"] = after["input_tp"]
    return job.done(**extra)


# ------------------------------------------------------------------ sync_audio_offset
@tool_handler
def sync_audio_offset(args: Dict[str, Any]) -> Any:
    ms = get_num(args, "offset_ms", required=True, lo=-10000, hi=10000)
    if ms == 0:
        raise ToolError("offset_ms is 0; nothing to shift.")
    job = Job(args, "sync", ext="av", need_audio=True, need_video=True)
    dur = job.info["duration_s"]
    if ms > 0:   # audio later
        af = "adelay=%d:all=1" % round(ms)
    else:        # audio earlier: drop its first |ms|, pad the end with silence
        af = "atrim=start=%.3f,asetpts=PTS-STARTPTS,apad" % (-ms / 1000.0)
    audio_edit(job, af, out_opts=["-t", "%.3f" % dur] if dur else None)
    return job.done(op="sync_audio_offset", offset_ms=ms, direction="audio later" if ms > 0 else "audio earlier")


# ------------------------------------------------------------------ adjust_volume
@tool_handler
def adjust_volume(args: Dict[str, Any]) -> Any:
    db = get_num(args, "db", None, lo=-60, hi=40)
    factor = get_num(args, "factor", None, lo=0.0, hi=100)
    if (db is None) == (factor is None):
        raise ToolError("Give exactly one of 'db' or 'factor'.")
    limit = get_bool(args, "prevent_clipping", True)
    job = Job(args, "volume", ext="av", need_audio=True)
    af = ("volume=%sdB" % db) if db is not None else ("volume=%s" % factor)
    if limit:
        af += ",alimiter=limit=0.95"
    audio_edit(job, af)
    return job.done(op="adjust_volume", db=db, factor=factor, limiter=limit)


# ------------------------------------------------------------------ fade_audio
@tool_handler
def fade_audio(args: Dict[str, Any]) -> Any:
    fin = get_num(args, "fade_in_s", 0.0, lo=0, hi=300)
    fout = get_num(args, "fade_out_s", 0.0, lo=0, hi=300)
    if fin == 0 and fout == 0:
        raise ToolError("Set fade_in_s and/or fade_out_s (seconds).")
    job = Job(args, "afade", ext="av", need_audio=True)
    dur = job.info["audio"][0].get("duration_s") or job.info["duration_s"] or 0
    if fin + fout > dur:
        raise ToolError("Fades (%.2fs + %.2fs) are longer than the audio (%.2fs)." % (fin, fout, dur))
    parts = []
    if fin:
        parts.append("afade=t=in:st=0:d=%s" % fin)
    if fout:
        parts.append("afade=t=out:st=%.3f:d=%s" % (dur - fout, fout))
    audio_edit(job, ",".join(parts))
    return job.done(op="fade_audio", fade_in_s=fin, fade_out_s=fout)


# ------------------------------------------------------------------ denoise_audio
DENOISE = {"light": "afftdn=nr=8:nf=-45", "medium": "afftdn=nr=14:nf=-40",
           "strong": "afftdn=nr=24:nf=-35",
           "voice": "highpass=f=90,lowpass=f=9000,afftdn=nr=14:nf=-40"}


@tool_handler
def denoise_audio(args: Dict[str, Any]) -> Any:
    preset = get_choice(args, "preset", DENOISE, "medium")
    job = Job(args, "denoised", ext="av", need_audio=True)
    audio_edit(job, DENOISE[preset])
    return job.done(op="denoise_audio", preset=preset)


# ------------------------------------------------------------------ specs
@tool_handler
def mute_video(args: Dict[str, Any]) -> Any:
    job = Job(args, "muted", ext="av", need_video=True)
    if not job.info["has_audio"]:
        return {"output": str(job.src), "duration_s": job.info["duration_s"], "info": {"op": "mute_video", "unchanged": True}}
    job.run(["-i", str(job.src), "-map", "0:v:0", "-c:v", "copy", "-an"] + _tail(job))
    return job.done(op="mute_video")


SPECS = [
    ToolSpec(
        name="lk_extract_audio",
        description=("Save the audio track of a video as an audio file (mp3, wav, m4a or flac). The video is untouched. "
                     "Use before transcription or to reuse the sound elsewhere."),
        handler=extract_audio,
        properties={"format": {"type": "string", "enum": list(FORMATS), "default": "mp3", "description": "Audio file type."},
                    "bitrate_kbps": {"type": "integer", "default": 192, "description": "Bitrate for mp3/m4a in kbit/s."},
                    "audio_track": {"type": "integer", "default": 0, "description": "Which audio stream (0 = first)."}}),
    ToolSpec(
        name="lk_replace_audio",
        description=("Swap the soundtrack of a video for another audio file (voice-over, music). Video is not re-encoded. "
                     "mode 'trim' (default): result keeps the video length (audio cut, or padded with silence if shorter); "
                     "'shortest': ends when the shorter one ends; 'loop': repeats the audio to fill the video. "
                     "To ADD music under existing sound use lk_mix_music."),
        handler=replace_audio, required=["audio"],
        properties={"audio": {"type": "string", "description": "Path to the new audio (or a video whose audio to use)."},
                    "mode": {"type": "string", "enum": ["trim", "shortest", "loop"], "default": "trim",
                             "description": "How to fit audio length to the video."}}),
    ToolSpec(
        name="lk_mix_music",
        description=("Add background music under the video's own sound. Music is looped to the video length, lowered by "
                     "music_volume_db, faded out at the end, and with ducking=true it automatically gets quieter while "
                     "someone speaks. Works for silent clips too (music only). Video is not re-encoded."),
        handler=mix_music, required=["music"],
        properties={"music": {"type": "string", "description": "Path to the music file."},
                    "music_volume_db": {"type": "number", "default": -18, "description": "Music level relative to its original, in dB (-18 = quiet bed)."},
                    "ducking": {"type": "boolean", "default": True, "description": "Lower the music while the clip's audio is loud (speech)."},
                    "duck_strength": {"type": "string", "enum": list(DUCK), "default": "medium", "description": "How strongly the music dips."},
                    "fade_out_s": {"type": "number", "default": 2, "description": "Fade the music out over the last N seconds (0 = none)."}}),
    ToolSpec(
        name="lk_normalize_loudness",
        description=("Make the loudness consistent using two-pass EBU R128 loudnorm. target_lufs default -14 (YouTube/Reels/"
                     "TikTok-style streaming level); -16 for podcasts. Reports before/after LUFS. Video is not re-encoded. "
                     "For a simple gain change use lk_adjust_volume."),
        handler=normalize_loudness,
        properties={"target_lufs": {"type": "number", "default": -14, "description": "Target integrated loudness in LUFS."},
                    "true_peak_db": {"type": "number", "default": -1.5, "description": "Max true peak in dBTP."},
                    "lra": {"type": "number", "default": 11, "description": "Target loudness range."},
                    "verify": {"type": "boolean", "default": True, "description": "Measure the result again and report it."}}),
    ToolSpec(
        name="lk_sync_audio_offset",
        description=("Fix lip-sync: shift the audio relative to the picture by offset_ms milliseconds. Positive = audio plays "
                     "LATER (use when sound comes too early); negative = audio plays EARLIER. Video is not re-encoded."),
        handler=sync_audio_offset, required=["offset_ms"],
        properties={"offset_ms": {"type": "number", "minimum": -10000, "maximum": 10000,
                                  "description": "Milliseconds to shift the audio (+ later, - earlier)."}}),
    ToolSpec(
        name="lk_adjust_volume",
        description=("Make the audio louder or quieter by 'db' (e.g. 6 or -3) OR by a 'factor' (2 = double, 0.5 = half). "
                     "A limiter prevents clipping. For consistent loudness use lk_normalize_loudness instead."),
        handler=adjust_volume,
        properties={"db": {"type": "number", "description": "Gain in decibels (+ louder, - quieter)."},
                    "factor": {"type": "number", "description": "Linear multiplier (1 = unchanged)."},
                    "prevent_clipping": {"type": "boolean", "default": True, "description": "Apply a peak limiter."}}),
    ToolSpec(
        name="lk_fade_audio",
        description="Fade the audio in and/or out (seconds) without touching the picture. For picture fades use lk_fade_video.",
        handler=fade_audio,
        properties={"fade_in_s": {"type": "number", "default": 0, "description": "Fade-in length in seconds."},
                    "fade_out_s": {"type": "number", "default": 0, "description": "Fade-out length in seconds."}}),
    ToolSpec(
        name="lk_denoise_audio",
        description=("Reduce steady background noise (hiss, hum, fans) with a spectral denoiser. preset 'voice' also cuts "
                     "rumble below 90 Hz and hiss above 9 kHz for speech. Strong settings can make voices sound watery."),
        handler=denoise_audio,
        properties={"preset": {"type": "string", "enum": list(DENOISE), "default": "medium", "description": "Denoise amount / profile."}}),
    ToolSpec(
        name="lk_mute_video",
        description=("Remove the sound from a video (all audio tracks). The picture is copied without re-encoding, so it is "
                     "instant and lossless. Returns the input unchanged if there is no audio. To put new sound under it use "
                     "lk_replace_audio or lk_mix_music."),
        handler=mute_video),
]
