#!/usr/bin/env python3
"""Launch the visual editor on its own (no Hermes needed).

  python scripts/editor.py                 start and print the URL
  python scripts/editor.py video.mp4       start with a file preloaded
  python scripts/editor.py --no-browser    do not open a browser window

The server listens on 127.0.0.1 only; the URL contains a random one-time token. Press Ctrl+C to stop.
"""
import argparse
import importlib.util
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_package():
    spec = importlib.util.spec_from_file_location("hermes_video_editor", ROOT / "__init__.py",
                                                  submodule_search_locations=[str(ROOT)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules["hermes_video_editor"] = mod
    spec.loader.exec_module(mod)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", nargs="?")
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    load_package()
    from hermes_video_editor.editor.server import get_server
    srv = get_server()
    target = None
    if a.file:
        target = str(Path(a.file).expanduser().resolve())
        srv.add_root(str(Path(target).parent))
    url = srv.url(target)
    print("Video Editor running at:\n  %s\nPress Ctrl+C to stop." % url)
    if not a.no_browser:
        webbrowser.open(url)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        srv.stop()


if __name__ == "__main__":
    main()
