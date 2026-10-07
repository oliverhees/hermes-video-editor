#!/usr/bin/env python3
"""Regenerate plugin.yaml from the TOOLS table so manifest and registrations never drift.

Hermes' catalog rules require the `capabilities:` block to match what register() really registers.
Usage:  python scripts/sync_manifest.py          (rewrites plugin.yaml)
        python scripts/sync_manifest.py --check  (exit 1 if plugin.yaml is out of date)
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.2.0"


def load_tools():
    spec = importlib.util.spec_from_file_location("hermes_video_editor", ROOT / "__init__.py",
                                                  submodule_search_locations=[str(ROOT)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules["hermes_video_editor"] = mod
    spec.loader.exec_module(mod)
    from hermes_video_editor.schemas import TOOLS
    return [t["name"] for t in TOOLS]


def render(names):
    lines = [
        "name: hermes-video-editor",
        'version: "%s"' % VERSION,
        "description: Local FFmpeg video editor for your own footage, driven by chat. 45 tools to trim, cut "
        "silence, crop to 9:16, add text and captions, mix music, normalize loudness, export for "
        "Reels/TikTok/YouTube and check platform rules. No cloud, no API key.",
        "author: oliverhees",
        "license: PolyForm-Noncommercial-1.0.0",
        "homepage: https://github.com/oliverhees/hermes-video-editor",
        "provides_tools:",
    ]
    lines += ["  - %s" % n for n in names]
    lines += ["capabilities:", "  provides_tools:"]
    lines += ["    - %s" % n for n in names]
    lines += ["  provides_hooks: []", "  provides_middleware: []", "  requires_env: []", ""]
    return "\n".join(lines)


def main():
    text = render(load_tools())
    target = ROOT / "plugin.yaml"
    if "--check" in sys.argv:
        sys.exit(0 if target.read_text(encoding="utf-8") == text else 1)
    target.write_text(text, encoding="utf-8")
    print("wrote", target)


if __name__ == "__main__":
    main()
