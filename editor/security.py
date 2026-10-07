"""Path policy for the editor server: only media files below allowed roots are ever read or written."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, List

from ..core.result import ToolError

VIDEO_EXTS = {".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi", ".mpg", ".mpeg", ".ts", ".mts", ".m2ts",
              ".wmv", ".flv", ".3gp"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".opus"}
MEDIA_EXTS = VIDEO_EXTS | AUDIO_EXTS


def default_roots() -> List[str]:
    roots = [str(Path.home())]
    for extra in os.environ.get("VE_EDITOR_ROOTS", "").split(os.pathsep):
        if extra.strip():
            roots.append(extra.strip())
    return roots


def _norm(p: str) -> str:
    return os.path.normcase(os.path.realpath(os.path.expanduser(p)))


def inside(path: str, roots: Iterable[str]) -> bool:
    target = _norm(path)
    for root in roots:
        r = _norm(root)
        try:
            if os.path.commonpath([target, r]) == r:
                return True
        except ValueError:          # different drives on Windows
            continue
    return False


def safe_media_file(raw: object, roots: Iterable[str]) -> Path:
    """Existing media file below one of the roots (symlinks resolved)."""
    if not isinstance(raw, str) or not raw.strip():
        raise ToolError("Missing file path.")
    real = _norm(raw)
    if not inside(real, roots):
        raise ToolError("Path is outside the folders the editor may access.",
                        hint="Allowed: your home folder. Add more with the VE_EDITOR_ROOTS environment variable.")
    p = Path(real)
    if p.suffix.lower() not in MEDIA_EXTS:
        raise ToolError("Not a media file type: %s" % p.suffix)
    if not p.is_file():
        raise ToolError("File not found: %s" % raw)
    return p


def safe_dir(raw: object, roots: Iterable[str], create: bool = False) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise ToolError("Missing folder path.")
    real = _norm(raw)
    if not inside(real, roots):
        raise ToolError("Folder is outside the folders the editor may access.")
    p = Path(real)
    if create:
        p.mkdir(parents=True, exist_ok=True)
    if not p.is_dir():
        raise ToolError("Folder not found: %s" % raw)
    return p
