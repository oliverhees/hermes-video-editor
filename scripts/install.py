#!/usr/bin/env python3
"""Install hermes-video-editor into ~/.hermes/plugins (symlink on Linux/macOS, copy on Windows).

  python scripts/install.py              install (symlink, or copy if symlinks are not allowed)
  python scripts/install.py --copy       force a copy
  python scripts/install.py --uninstall  remove the installed plugin
  python scripts/install.py --target DIR use another plugins folder (default: $HERMES_HOME/plugins or ~/.hermes/plugins)
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

NAME = "hermes-video-editor"
ROOT = Path(__file__).resolve().parents[1]
IGNORE = shutil.ignore_patterns(".git", ".github", "__pycache__", ".pytest_cache", "tests", "*.pyc", "dist")


def plugins_dir(override):
    if override:
        return Path(override).expanduser()
    home = os.environ.get("HERMES_HOME")
    return (Path(home).expanduser() if home else Path.home() / ".hermes") / "plugins"


def remove(path):
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(str(path))


def is_ours(path):
    if path.is_symlink():
        return Path(os.path.realpath(str(path))) == ROOT
    return (path / "plugin.yaml").is_file() and "name: %s" % NAME in (path / "plugin.yaml").read_text(encoding="utf-8")


def desktop_dir():
    home = os.environ.get("HERMES_HOME")
    return (Path(home).expanduser() if home else Path.home() / ".hermes") / "desktop-plugins" / NAME


def install_desktop_half(target_plugins_dir):
    """Copy desktop/plugin.js to $HERMES_HOME/desktop-plugins/<id>/ (the Desktop app loads it from there)."""
    src = ROOT / "desktop" / "plugin.js"
    if not src.is_file():
        return
    dest = desktop_dir() if not target_plugins_dir else Path(target_plugins_dir).parent / "desktop-plugins" / NAME
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(str(src), str(dest / "plugin.js"))
    print("Installed Desktop page: %s" % (dest / "plugin.js"))


def is_in_place(dest):
    """True when `dest` already IS this checkout (a real folder, or a link to it). Never delete or relink that."""
    return os.path.lexists(str(dest)) and os.path.realpath(str(dest)) == os.path.realpath(str(ROOT))


def install(target_dir, copy=False, explicit_target=False):
    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / NAME
    if is_in_place(dest):          # e.g. cloned there by `hermes plugins install`: only add the Desktop page
        print("Plugin is already installed in place: %s" % dest)
        install_desktop_half(target_dir if explicit_target else None)
        print("Next:  hermes plugins enable %s   then restart Hermes Desktop." % NAME)
        return 0
    if os.path.lexists(str(dest)):
        if not is_ours(dest):
            print("Refusing to replace %s: it is not this plugin. Remove it manually." % dest, file=sys.stderr)
            return 1
        remove(dest)
    mode = "copy"
    if not copy:
        try:
            os.symlink(str(ROOT), str(dest), target_is_directory=True)
            mode = "symlink"
        except (OSError, NotImplementedError):
            mode = "copy"      # Windows without developer mode, restricted filesystems
    if mode == "copy":
        shutil.copytree(str(ROOT), str(dest), ignore=IGNORE)
    print("Installed (%s): %s" % (mode, dest))
    install_desktop_half(target_dir if explicit_target else None)
    print("Next:  hermes plugins enable %s   then   hermes plugins list" % NAME)
    print("Then restart Hermes Desktop: the 'Video Editor' entry appears in the sidebar "
          "(enable it under Capabilities -> Plugins if it is off).")
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        print("NOTE: ffmpeg/ffprobe not found on PATH. Linux: apt install ffmpeg (as administrator) | macOS: brew install ffmpeg | "
              "Windows: winget install Gyan.FFmpeg", file=sys.stderr)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--copy", action="store_true")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--target")
    a = ap.parse_args()
    base = plugins_dir(a.target)
    if a.uninstall:
        dest = base / NAME
        desk = (Path(a.target).expanduser().parent / "desktop-plugins" / NAME) if a.target else desktop_dir()
        if desk.exists():
            shutil.rmtree(str(desk), ignore_errors=True)
            print("Removed", desk)
        if is_in_place(dest) and not dest.is_symlink():
            print("The plugin folder %s is this checkout; not deleting it. Use: hermes plugins remove %s" % (dest, NAME))
            return 0
        if os.path.lexists(str(dest)) and is_ours(dest):
            remove(dest)
            print("Removed", dest)
            return 0
        print("Nothing to remove at", dest)
        return 0
    return install(base, a.copy, bool(a.target))


if __name__ == "__main__":
    sys.exit(main())
