#!/usr/bin/env python3
"""Print a plugin-catalog/<name>.yaml entry (for a PR to NousResearch/hermes-agent) for the current commit.

The catalog pins an exact 40-char commit SHA, so push your commit first, then run this.
Validate before submitting:  hermes plugins validate . --install-deps
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from sync_manifest import VERSION, load_tools  # noqa: E402


def main():
    sha = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    names = load_tools()
    print("\n".join([
        "name: hermes-video-editor",
        "repo: https://github.com/oliverhees/hermes-video-editor",
        "sha: %s" % sha,
        'version: "%s"' % VERSION,
        "title: Video Editor (local FFmpeg)",
        "description: Edit your own local footage with FFmpeg - 42 tools for cutting, cropping, captions, audio and platform export. No cloud, no API key.",
        "maintainer: oliverhees",
        "category: tools",
        'requires_hermes: ">=0.21.5"   # SemVer floor; lower/adjust to the oldest Hermes you tested',
        "capabilities:",
        "  provides_tools:",
        *["    - %s" % n for n in names],
        "  provides_hooks: []",
        "  provides_middleware: []",
        "  requires_env: []",
        "known_issues:",
        "  - Requires FFmpeg and ffprobe on PATH (apt install ffmpeg / brew install ffmpeg / winget install Gyan.FFmpeg).",
        "  - ve_transcribe_captions is optional and needs 'pip install faster-whisper' plus a model already on disk.",
        ""]))


if __name__ == "__main__":
    main()
