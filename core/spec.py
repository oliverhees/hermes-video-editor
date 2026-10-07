"""ToolSpec: one declarative entry per tool; schemas.py turns it into a JSON schema."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Tuple

ALL_COMMON = ("input", "output", "output_dir", "overwrite", "timeout_s")


@dataclass
class ToolSpec:
    name: str
    description: str
    handler: Callable[..., str]
    properties: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    required: List[str] = field(default_factory=list)
    common: Tuple[str, ...] = ALL_COMMON
