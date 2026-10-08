"""Input resolution, output naming (never overwrite input), filter-path escaping."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from .result import ToolError


def resolve_input(value: Any, name: str = "input") -> Path:
    if not isinstance(value, (str, os.PathLike)) or not str(value).strip():
        raise ToolError("Missing required parameter '%s' (path to a media file)." % name)
    path = Path(str(value)).expanduser()
    if not path.exists():
        raise ToolError("File not found: %s" % path, hint="Check the path; quote paths with spaces.")
    if not path.is_file():
        raise ToolError("Not a file: %s" % path)
    return path.absolute()


def _same(a: Path, b: Path) -> bool:
    try:
        return a.exists() and b.exists() and os.path.samefile(str(a), str(b))
    except OSError:
        return a.absolute() == b.absolute()


def unique_path(path: Path) -> Path:
    """Return path, or path with _1, _2, ... suffix if it already exists."""
    if not path.exists():
        return path
    n = 1
    while True:
        cand = path.with_name("%s_%d%s" % (path.stem, n, path.suffix))
        if not cand.exists():
            return cand
        n += 1


# What a tool may write. An explicit `output` with any other suffix (.sh, .py, .bashrc, no dot ...) is refused,
# so a tool can never be pointed at a script or a config file.
VIDEO_OUT = {".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi", ".mpg", ".mpeg", ".ts", ".mts", ".m2ts", ".wmv", ".flv", ".3gp"}
AUDIO_OUT = {".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".opus"}
IMAGE_OUT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
ALLOWED_OUTPUT_EXTS = VIDEO_OUT | AUDIO_OUT | IMAGE_OUT | {".srt"}


def plan_output(input_path: Path, op: str, ext: Optional[str] = None,
                output: Any = None, output_dir: Any = None,
                overwrite: bool = False, strict_ext: bool = False) -> Path:
    """Decide where the result goes. Never returns the input path.
    An explicit `output` must end in a media, picture or .srt suffix; with strict_ext it must be exactly `ext`."""
    ext = ext if ext is not None else input_path.suffix
    if ext and not ext.startswith("."):
        ext = "." + ext
    if output:
        out = Path(str(output)).expanduser()
        if not out.suffix:
            out = out.with_suffix(ext)
        suffix = out.suffix.lower()
        if suffix not in ALLOWED_OUTPUT_EXTS:
            raise ToolError("Output files must end in a media, picture or .srt suffix, not '%s'." % (out.suffix or "(none)"),
                            hint="Allowed: %s" % ", ".join(sorted(ALLOWED_OUTPUT_EXTS)))
        if strict_ext and suffix != ext.lower():
            raise ToolError("This tool writes %s files, so 'output' must end in %s (got '%s')." % (ext, ext, out.suffix))
    else:
        directory = Path(str(output_dir)).expanduser() if output_dir else input_path.parent
        out = directory / ("%s_%s%s" % (input_path.stem, op, ext))
    out = out.absolute()
    if _same(out, input_path):
        raise ToolError("Output would overwrite the input file: %s" % input_path,
                        hint="Choose a different 'output' path; inputs are never modified.")
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ToolError("Cannot create output directory %s: %s" % (out.parent, exc))
    if out.is_dir():
        raise ToolError("Output path is an existing folder: %s" % out, hint="Give a file name, or use output_dir for a folder.")
    if out.exists() and not overwrite:
        out = unique_path(out)
    return out


def ff_escape_path(path: Any) -> str:
    """Escape a file path for use as an option value inside an ffmpeg -vf/-filter_complex
    string passed as ONE argv item (no shell).

    Handles both escaping levels (option level, then filtergraph level):
    backslashes become forward slashes (Windows), then ``\\ ' :`` are escaped for the
    option level and ``\\ ' [ ] , ;`` plus the escapes again for the graph level.
    ``C:\\Users\\me\\a.srt`` -> ``C\\\\:/Users/me/a.srt``.
    """
    text = str(path).replace("\\", "/")
    # level 1: filter option value
    text = text.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")
    # level 2: filtergraph description
    out = []
    for ch in text:
        if ch in "\\'[],;=":
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)
