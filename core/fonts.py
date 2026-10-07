"""Per-OS font resolution for drawtext. Never hardcodes one path; may return None (FFmpeg default)."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Optional

LINUX = ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/TTF/DejaVuSans.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
         "/usr/share/fonts/liberation/LiberationSans-Regular.ttf"]
MACOS = ["/System/Library/Fonts/Helvetica.ttc", "/System/Library/Fonts/Supplemental/Arial.ttf",
         "/Library/Fonts/Arial.ttf"]


def candidates() -> List[str]:
    if sys.platform.startswith("win"):
        windir = os.environ.get("WINDIR", "C:/Windows")
        return [str(Path(windir) / "Fonts" / "arial.ttf"), str(Path(windir) / "Fonts" / "segoeui.ttf")]
    if sys.platform == "darwin":
        return MACOS
    return LINUX


def resolve_font(explicit: Optional[str] = None) -> Optional[str]:
    """Explicit path > $VE_FONT > per-OS candidates > None (let FFmpeg/fontconfig pick)."""
    for cand in [explicit, os.environ.get("VE_FONT")] + candidates():
        if cand and Path(cand).is_file():
            return str(Path(cand))
    return None
