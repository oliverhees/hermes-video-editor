"""Small argument validators shared by all tools."""
from __future__ import annotations

import math
from typing import Any, Dict, Iterable, Optional

from .result import ToolError
from .timeparse import parse_time

DEFAULT_TIMEOUT_S = 600


def get_num(args: Dict[str, Any], key: str, default: Optional[float] = None,
            lo: Optional[float] = None, hi: Optional[float] = None,
            integer: bool = False, required: bool = False) -> Optional[float]:
    value = args.get(key)
    if value is None:
        if required:
            raise ToolError("Missing required parameter '%s'." % key)
        return default
    if isinstance(value, bool):
        raise ToolError("Parameter '%s' must be a number, got %r." % (key, value))
    try:
        num = float(value)
    except (TypeError, ValueError):
        raise ToolError("Parameter '%s' must be a number, got %r." % (key, value))
    if math.isnan(num) or math.isinf(num):
        raise ToolError("Parameter '%s' must be finite." % key)
    if integer:
        if num != int(num):
            raise ToolError("Parameter '%s' must be an integer, got %r." % (key, value))
        num = int(num)
    if lo is not None and num < lo:
        raise ToolError("Parameter '%s' must be >= %s (got %s)." % (key, lo, num))
    if hi is not None and num > hi:
        raise ToolError("Parameter '%s' must be <= %s (got %s)." % (key, hi, num))
    return num


def get_choice(args: Dict[str, Any], key: str, choices: Iterable[str],
               default: Optional[str] = None) -> Optional[str]:
    value = args.get(key)
    if value is None:
        return default
    choices = list(choices)
    if str(value) not in choices:
        raise ToolError("Parameter '%s' must be one of %s (got %r)." % (key, choices, value))
    return str(value)


def get_bool(args: Dict[str, Any], key: str, default: bool = False) -> bool:
    value = args.get(key)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in ("true", "false"):
        return value.lower() == "true"
    raise ToolError("Parameter '%s' must be true or false (got %r)." % (key, value))


def get_time(args: Dict[str, Any], key: str, default: Optional[float] = None,
             required: bool = False) -> Optional[float]:
    value = args.get(key)
    if value is None:
        if required:
            raise ToolError("Missing required parameter '%s'." % key)
        return default
    return parse_time(value, key)


def get_timeout(args: Dict[str, Any]) -> int:
    return int(get_num(args, "timeout_s", DEFAULT_TIMEOUT_S, lo=1, hi=86400, integer=True))
