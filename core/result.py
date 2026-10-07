"""JSON result helpers. Every tool returns the output of ok() or fail()."""
from __future__ import annotations

import json
from typing import Any, Dict, Optional


class ToolError(Exception):
    """Expected, user-facing failure. Converted to a fail() JSON by the handler wrapper."""

    def __init__(self, message: str, hint: Optional[str] = None,
                 stderr_tail: Optional[str] = None, **extra: Any) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.stderr_tail = stderr_tail
        self.extra = extra


def _dump(data: Dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def ok(output: Optional[str] = None, duration_s: Optional[float] = None,
       info: Optional[Dict[str, Any]] = None, **extra: Any) -> str:
    data: Dict[str, Any] = {
        "ok": True,
        "output": str(output) if output is not None else None,
        "duration_s": duration_s,
        "info": info or {},
    }
    data.update(extra)
    return _dump(data)


def fail(error: str, hint: Optional[str] = None,
         ffmpeg_stderr_tail: Optional[str] = None, **extra: Any) -> str:
    data: Dict[str, Any] = {
        "ok": False,
        "error": error,
        "hint": hint or "",
        "ffmpeg_stderr_tail": ffmpeg_stderr_tail or "",
    }
    data.update(extra)
    return _dump(data)
