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
        "  Local video editor for your own footage: 42 FFmpeg tools for the agent (cut, silence removal, 9:16 reframe,",
        "  captions, music with ducking, loudness, platform export and checks) plus a visual editor in Hermes Desktop",
        "  with canvas, overlay, text and music tracks and an English/German help. 100% local, no API key.",
        "  Licence: PolyForm Noncommercial 1.0.0.",
        "maintainer: oliverhees",
        "category: tools",
        "tier: community",
        'requires_hermes: ">=0.21.5"',
        "docs_url: %s/blob/%s/README.md" % (REPO, sha),   # bilingual README, links the EN/DE guides
        "image: %s/%s/docs/banner.png" % (RAW, sha),
        "screenshots:",
        "  - %s/%s/docs/editor.png" % (RAW, sha),
        "readme: true",
        "capabilities:",
        "  provides_tools:",
        *["    - %s" % n for n in names],
        "  provides_hooks: []",
        "  provides_middleware: []",
        "  requires_env: []",
        "known_issues:",
        "  - Requires FFmpeg and ffprobe on PATH (apt install ffmpeg / brew install ffmpeg / winget install Gyan.FFmpeg).",
        "  - lk_transcribe_captions is optional and needs 'pip install faster-whisper' plus a model already on disk.",
        "  - The visual editor has one main video track plus an overlay track, a text layer and an audio track; texts, overlays and audio items sit at fixed times.",
        "  - Licence is PolyForm Noncommercial 1.0.0 (source-available): free for non-commercial use, commercial use needs a separate licence from Lokyy.de.",
        "  - The editor preview needs H.264 or VP8 playback in the app's browser engine; editing and export work without it.",
        ""]))


if __name__ == "__main__":
    main()
