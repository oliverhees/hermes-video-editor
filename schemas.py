"""JSON schemas, generated from the ToolSpec table. TOOLS is the single registry."""
from __future__ import annotations

from typing import Any, Dict, List

from .core.spec import ToolSpec
from .tools import cut, info, overlay, picture

TOOLSET = "video_editor"

COMMON_PROPERTIES: Dict[str, Dict[str, Any]] = {
    "input": {"type": "string",
              "description": "Path to the source media file. Never modified; the result is a new file."},
    "output": {"type": "string",
               "description": ("Optional output file path. Default: <input name>_<op>.<ext> next to the "
                               "input. If it exists and overwrite=false, _1, _2... is appended.")},
    "output_dir": {"type": "string",
                   "description": "Optional folder for the default output name (created if missing)."},
    "overwrite": {"type": "boolean", "default": False,
                  "description": "Replace an existing output file instead of adding a _1/_2 suffix."},
    "timeout_s": {"type": "integer", "minimum": 1, "default": 600,
                  "description": "Kill FFmpeg after this many seconds. Default 600."},
}

SPECS: List[ToolSpec] = [*info.SPECS, *cut.SPECS, *picture.SPECS, *overlay.SPECS]


def build_schema(spec: ToolSpec) -> Dict[str, Any]:
    props: Dict[str, Any] = {k: dict(COMMON_PROPERTIES[k]) for k in spec.common}
    props.update(spec.properties)
    required = ([k for k in ("input",) if k in spec.common] + list(spec.required))
    params: Dict[str, Any] = {"type": "object", "properties": props}
    if required:
        params["required"] = required
    return {"name": spec.name, "description": spec.description, "parameters": params}


TOOLS: List[Dict[str, Any]] = [
    {"name": s.name, "schema": build_schema(s), "handler": s.handler, "toolset": TOOLSET}
    for s in SPECS
]
