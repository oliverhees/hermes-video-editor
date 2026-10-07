"""Run any of the ve_* tools from the editor UI, with every path argument confined to the allowed folders."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

from ..core.result import ToolError
from .security import AUDIO_EXTS, MEDIA_EXTS, VIDEO_EXTS, inside, safe_dir, safe_media_file

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
CAPTION_EXTS = {".srt", ".vtt", ".ass", ".ssa"}
FONT_EXTS = {".ttf", ".otf", ".ttc"}
OUTPUT_EXTS = MEDIA_EXTS | IMAGE_EXTS | {".srt"}

# parameter name -> kind of path it holds
PATH_KEYS = {"input": "media", "input2": "media", "pip_input": "media", "audio": "media", "music": "media",
             "image": "image", "captions": "captions", "font_file": "font", "model_path": "dir",
             "output": "outfile", "output_dir": "dir_create"}
LIST_PATH_KEYS = {"inputs": "media"}
READ_ONLY = {"ve_media_doctor", "ve_media_probe", "ve_detect_silence", "ve_detect_scenes", "ve_platform_check"}
GROUPS = [("info", "Inspect"), ("cut", "Cut & time"), ("picture", "Picture"), ("overlay", "Overlays & text"),
          ("audio", "Audio"), ("export", "Export & check")]
KIND_EXTS = {"project": {".json"}, "media": MEDIA_EXTS, "image": IMAGE_EXTS | VIDEO_EXTS, "captions": CAPTION_EXTS, "font": FONT_EXTS,
             "audio": AUDIO_EXTS}


def tool_catalog() -> List[Dict[str, Any]]:
    """All registered tools with their schema, group and read-only flag (for building the UI forms)."""
    from ..schemas import TOOLS
    from ..tools import audio, cut, export, info, overlay, picture
    modules = {"info": info, "cut": cut, "picture": picture, "overlay": overlay, "audio": audio, "export": export}
    group_of = {}
    for key, title in GROUPS:
        for spec in modules[key].SPECS:
            group_of[spec.name] = title
    out = []
    for t in TOOLS:
        schema = t["schema"]
        out.append({"name": t["name"], "group": group_of.get(t["name"], "Other"), "description": schema["description"],
                    "read_only": t["name"] in READ_ONLY, "properties": schema["parameters"]["properties"],
                    "required": schema["parameters"].get("required", [])})
    return out


def _file_with_ext(raw: Any, roots: List[str], exts: set, what: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise ToolError("Missing %s path." % what)
    real = os.path.realpath(os.path.expanduser(raw))
    if not inside(real, roots):
        raise ToolError("%s is outside the folders the editor may access." % what.capitalize())
    if Path(real).suffix.lower() not in exts:
        raise ToolError("%s must be one of: %s" % (what.capitalize(), ", ".join(sorted(exts))))
    if not os.path.isfile(real):
        raise ToolError("File not found: %s" % raw)
    return real


def sanitize_args(name: str, args: Any, roots: List[str], videos_dir: str, upload_dir: str) -> Dict[str, Any]:
    """Validate a tool call coming from the browser. Only schema parameters, every path inside the roots."""
    spec = next((t for t in tool_catalog() if t["name"] == name), None)
    if spec is None:
        raise ToolError("Unknown tool: %s" % name)
    if not isinstance(args, dict):
        raise ToolError("Tool arguments must be an object.")
    allowed = set(spec["properties"])
    clean: Dict[str, Any] = {}
    for key, value in args.items():
        if key not in allowed:
            raise ToolError("Unknown parameter '%s' for %s." % (key, name))
        if value is None or value == "":
            continue
        kind = PATH_KEYS.get(key)
        if key in LIST_PATH_KEYS:
            if not isinstance(value, list):
                raise ToolError("'%s' must be a list of file paths." % key)
            clean[key] = [str(safe_media_file(v, roots)) for v in value]
        elif kind == "media":
            clean[key] = str(safe_media_file(value, roots))
        elif kind == "image":
            clean[key] = _file_with_ext(value, roots, IMAGE_EXTS | MEDIA_EXTS, "image")
        elif kind == "captions":
            clean[key] = _file_with_ext(value, roots, CAPTION_EXTS, "captions file")
        elif kind == "font":
            clean[key] = _file_with_ext(value, roots, FONT_EXTS, "font file")
        elif kind == "dir":
            clean[key] = str(safe_dir(value, roots))
        elif kind == "dir_create":
            clean[key] = str(safe_dir(value, roots, create=True))
        elif kind == "outfile":
            real = os.path.realpath(os.path.expanduser(str(value)))
            if not inside(real, roots) or Path(real).suffix.lower() not in OUTPUT_EXTS:
                raise ToolError("Output must be a media/image file path inside the allowed folders.")
            clean[key] = real
        else:
            clean[key] = value
    if "timeout_s" in clean:
        try:
            clean["timeout_s"] = max(1, min(3600, int(clean["timeout_s"])))
        except (TypeError, ValueError):
            raise ToolError("timeout_s must be a number.")
    # files that live in the editor's upload cache should not get results written next to them
    src = clean.get("input") or (clean.get("inputs") or [None])[0]
    if src and "output" not in clean and "output_dir" not in clean and "output_dir" in allowed \
            and inside(src, [upload_dir]):
        clean["output_dir"] = videos_dir
    return clean


def run_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    from ..schemas import TOOLS
    handler = next(t["handler"] for t in TOOLS if t["name"] == name)
    result = json.loads(handler(args))
    if not result.get("ok"):
        raise ToolError(result.get("error", "Tool failed"), result.get("hint"), result.get("ffmpeg_stderr_tail"))
    result["tool"] = name
    return result
