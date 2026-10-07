#!/usr/bin/env python3
"""Print a plugin-catalog/<name>.yaml entry (for a PR to NousResearch/hermes-agent) pinned to a commit.

This entry is what makes the Hermes Desktop plugin card rich (banner image, Repository/Documentation links,
"Requires Hermes", "Reviewed commit"). The catalog pins an exact 40-char SHA and the image URL must contain it,
so push your commit first.   Usage: python scripts/make_catalog_entry.py [SHA]   (default: HEAD)
Validate before submitting:  hermes plugins validate . --install-deps
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from sync_manifest import VERSION, load_tools  # noqa: E402

REPO = "https://github.com/oliverhees/hermes-video-editor"
RAW = "https://raw.githubusercontent.com/oliverhees/hermes-video-editor"


def main():
    rev = sys.argv[1] if len(sys.argv) > 1 else "HEAD"
    sha = subprocess.run(["git", "-C", str(ROOT), "rev-parse", rev], capture_output=True, text=True, check=True).stdout.strip()
    names = load_tools()
    print("\n".join([
        "name: hermes-video-editor",
        "title: Video Editor (local FFmpeg)",
        "repo: %s" % REPO,
        "sha: %s" % sha,
        'version: "%s"' % VERSION,
        "description: >-",
        "  Local FFmpeg video editor for your own footage, driven by chat. 42 tools: trim, split, join, remove",
        "  silence, crop to 9:16, blurred-background vertical, text and captions, picture-in-picture, music with",
        "  ducking, EBU R128 loudness, GIF, contact sheets, platform export presets (Reels, TikTok, Shorts,",
        "  YouTube, X, Discord) and a platform rule check. 100% local: no cloud, no API key, no network calls.",
        "  Requires ffmpeg and ffprobe on PATH. Disclosure - runs ffmpeg/ffprobe as subprocesses on the files you",
        "  name and writes new output files next to them; never modifies inputs. Optional captions tool needs",
        "  faster-whisper and a model already on disk.",
        "maintainer: oliverhees",
        "category: tools",
        "tier: community",
        'requires_hermes: ">=0.21.5"',
        "docs_url: %s/blob/%s/README.md" % (REPO, sha),
        "image: %s/%s/docs/banner.png" % (RAW, sha),
        "readme: true",
        "capabilities:",
        "  provides_tools:",
        *["    - %s" % n for n in names],
        "  provides_hooks: []",
        "  provides_middleware: []",
        "  requires_env: []",
        "known_issues:",
        "  - Requires FFmpeg and ffprobe on PATH (apt install ffmpeg / brew install ffmpeg / winget install Gyan.FFmpeg).",
        "  - ve_transcribe_captions is optional and needs 'pip install faster-whisper' plus a model already on disk.",
        "  - There is no visual editor UI; you edit by chatting with the agent.",
        ""]))


if __name__ == "__main__":
    main()
