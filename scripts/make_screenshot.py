#!/usr/bin/env python3
"""Render docs/editor.png: a REAL screenshot of the editor UI on a synthetic demo clip.
Dev tool: needs ffmpeg, playwright (+ chromium) and a free scratch folder. Usage: python scripts/make_screenshot.py
"""
import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    spec = importlib.util.spec_from_file_location("hermes_video_editor", ROOT / "__init__.py",
                                                  submodule_search_locations=[str(ROOT)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules["hermes_video_editor"] = mod
    spec.loader.exec_module(mod)
    from hermes_video_editor.editor.server import EditorServer
    from playwright.sync_api import sync_playwright

    shot_dir = Path(tempfile.gettempdir()) / "Videos"
    shot_dir.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ve_shot_") as scratch:
        tmp = str(shot_dir)
        clip = shot_dir / "interview.mp4"
        broll = shot_dir / "b-roll.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                        "gradients=s=1280x720:d=24:speed=0.02:r=25:c0=0x1b1464:c1=0xff6b35:c2=0x4ecdc4:nb_colors=3",
                        "-f", "lavfi", "-i", "anoisesrc=c=pink:d=24:a=0.5:r=44100", "-af",
                        "tremolo=f=4:d=0.8,volume=enable='between(t,4,6.5)+between(t,11,13.2)+between(t,18,19.5)':volume=0",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(clip)], check=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                        "gradients=s=1280x720:d=8:speed=0.05:r=25:c0=0x0b6e4f:c1=0xf7c948:c2=0xff5d8f:nb_colors=3",
                        "-f", "lavfi", "-i", "sine=frequency=330:d=8", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                        "-shortest", str(broll)], check=True)
        srv = EditorServer(roots=[tmp])
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page(viewport={"width": 1500, "height": 860})
                page.goto(srv.url(str(clip)))
                page.wait_for_selector("#video[data-src]", state="attached", timeout=90000)
                page.wait_for_timeout(2500)
                page.click("#btn-silence")                       # cut the silent parts out of the interview
                page.wait_for_timeout(4000)
                page.click("#btn-open")                          # add a second clip behind it
                page.fill("#dlg-path", str(broll))
                page.press("#dlg-path", "Enter")
                page.wait_for_timeout(5000)
                page.click("#tabs button[data-tab=picture]")             # 9:16 canvas, the 16:9 picture fitted on a blurred background
                page.select_option("#in-aspect", "9:16")
                page.evaluate("window.__ve.seek(3.0)")
                page.click("#clips .clip >> nth=1")
                page.wait_for_timeout(1500)
                page.screenshot(path=str(ROOT / "docs" / "editor.png"))
                browser.close()
        finally:
            srv.stop()
            clip.unlink(missing_ok=True)
            try:
                shot_dir.rmdir()
            except OSError:
                pass
    print("wrote", ROOT / "docs" / "editor.png")


if __name__ == "__main__":
    main()
