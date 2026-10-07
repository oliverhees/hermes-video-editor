"""Helpers shared by tool modules (not tools themselves)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..core.ffmpeg import Job, encode_args, even_filter  # noqa: F401  (re-exported)
from ..core.paths import resolve_input
from ..core.validate import get_num

EVEN = "scale=trunc(iw/2)*2:trunc(ih/2)*2"
TIME_PROP = {"type": ["number", "string"]}


def tprop(desc: str, **extra: Any) -> Dict[str, Any]:
    d = {"type": ["number", "string"], "description": desc + " Seconds (12.5), MM:SS or HH:MM:SS(.ms)."}
    d.update(extra)
    return d


def vchain(*parts: Optional[str]) -> str:
    """Join non-empty video filters with commas and finish with even-size rounding."""
    items = [p for p in parts if p]
    items.append(EVEN)
    return ",".join(items)


def crf_of(args: Dict[str, Any]) -> int:
    return int(get_num(args, "crf", 20, lo=0, hi=51, integer=True))


CRF_PROP = {"type": "integer", "minimum": 0, "maximum": 51, "default": 20,
            "description": "H.264 quality (lower = better/larger file). Default 20."}


def vf_edit(args: Dict[str, Any], op: str, vf: Optional[str], af: Optional[str] = None,
            need_audio: bool = False, **extra_info: Any) -> Dict[str, Any]:
    """Standard single filter-chain re-encode: -vf (+ -af when audio exists)."""
    crf = crf_of(args)
    job = Job(args, op, ext="av", need_video=True, need_audio=need_audio)
    ff: List[str] = ["-i", str(job.src), "-map", "0:v:0", "-map", "0:a?", "-vf", vchain(vf)]
    if af and job.info["has_audio"]:
        ff += ["-af", af]
    ff += encode_args(job.out.suffix.lower(), crf=crf, audio=job.info["has_audio"])
    job.run(ff)
    return job.done(op=op, **extra_info)


def display_size(info: Dict[str, Any]):
    v = info["video"]
    return v["display_width"], v["display_height"]


def second_input(args: Dict[str, Any], key: str):
    from ..core.ffmpeg import probe
    path = resolve_input(args.get(key), key)
    return path, probe(path)


def path_prop(desc: str) -> Dict[str, Any]:
    return {"type": "string", "description": desc}


def run_graph(job: Job, inputs: List[List[str]], graph: str, vlabel: Optional[str] = "[vo]",
              alabel: Optional[str] = None, crf: int = 20, audio: Optional[bool] = None) -> None:
    """Run a -filter_complex graph. inputs = list of full arg lists, e.g. [["-i", a], ["-stream_loop", "-1", "-i", b]].
    Audio: mapped from alabel when given, else from input 0 if it has audio (re-encoded to AAC)."""
    from pathlib import Path

    from ..core.ffmpeg import filter_complex_args, new_tempdir
    ff: List[str] = []
    for item in inputs:
        ff += item
    with new_tempdir() as tmp:
        ff += filter_complex_args(graph, Path(tmp))
        if vlabel:
            ff += ["-map", vlabel]
        has_a = alabel is not None or bool(job.info["has_audio"] and audio is not False)
        if alabel:
            ff += ["-map", alabel]
        elif has_a:
            ff += ["-map", "0:a?"]
        ff += encode_args(job.out.suffix.lower(), crf=crf, audio=has_a)
        job.run(ff)
