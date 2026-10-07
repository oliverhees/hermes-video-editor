"""Time parsing: SS, SS.ms, MM:SS, HH:MM:SS(.ms) -> float seconds."""
from __future__ import annotations

import math
import re
from typing import Any

from .result import ToolError

_INT = re.compile(r"^\d+$")
_SEC = re.compile(r"^\d+(\.\d+)?$")
HELP = "Use seconds (12.5) or MM:SS (01:30) or HH:MM:SS(.ms) (00:01:30.250)."


def parse_time(value: Any, name: str = "time") -> float:
    """Parse a time value into seconds. Raises ToolError on bad input."""
    if isinstance(value, bool) or value is None:
        raise ToolError("Invalid %s: %r" % (name, value), hint=HELP)
    if isinstance(value, (int, float)):
        seconds = float(value)
    else:
        text = str(value).strip()
        parts = text.split(":")
        if not text or len(parts) > 3 or not _SEC.match(parts[-1]) \
                or not all(_INT.match(p) for p in parts[:-1]):
            raise ToolError("Invalid %s: %r" % (name, value), hint=HELP)
        if len(parts) > 1 and (float(parts[-1]) >= 60 or
                               (len(parts) == 3 and int(parts[1]) >= 60)):
            raise ToolError("Invalid %s: %r (minutes/seconds must be < 60)" % (name, value),
                            hint=HELP)
        seconds = 0.0
        for part in parts:
            seconds = seconds * 60 + float(part)
    if math.isnan(seconds) or math.isinf(seconds) or seconds < 0:
        raise ToolError("Invalid %s: %r (must be a finite number >= 0)" % (name, value),
                        hint=HELP)
    return seconds


def format_time(seconds: float) -> str:
    """Seconds -> HH:MM:SS.mmm."""
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return "%02d:%02d:%02d.%03d" % (h, m, s, ms)
