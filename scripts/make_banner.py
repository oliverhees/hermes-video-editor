#!/usr/bin/env python3
"""Render docs/banner.png (2:1, for the Hermes plugin catalog `image` field). Dev tool: needs Pillow."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
W, H = 1600, 800
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def font(path, size):
    return ImageFont.truetype(path, size)


def main():
    img = Image.new("RGB", (W, H), "#0e1117")
    d = ImageDraw.Draw(img)
    for y in range(H):                                   # vertical gradient
        t = y / H
        d.line([(0, y), (W, y)], fill=(int(14 + 22 * t), int(17 + 10 * t), int(23 + 40 * t)))
    d.text((70, 38), "LOCAL \u00B7 FFMPEG \u00B7 NO CLOUD", font=font(BOLD, 26), fill="#ff6b35")
    d.text((70, 76), "Video Editor", font=font(BOLD, 104), fill="#ffffff")
    d.text((74, 196), "Cut, reframe and export your own footage - in the editor or by chat.", font=font(REG, 30), fill="#c9d1e0")
    bullets = ["Clips timeline with waveform", "9:16 canvas: move and zoom each clip", "Remove silences in one click",
               "42 FFmpeg tools for the agent"]
    for i, text in enumerate(bullets):
        d.text((70, 330 + i * 64), "\u2713", font=font(BOLD, 34), fill="#4ecdc4")
        d.text((120, 332 + i * 64), text, font=font(REG, 30), fill="#e6eaf2")
    # real screenshot of the editor, bleeding off the right and bottom edges
    shot = Image.open(ROOT / "docs" / "editor.png").convert("RGB")
    sw = 930
    shot = shot.resize((sw, int(shot.height * sw / shot.width)), Image.LANCZOS)
    mask = Image.new("L", shot.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, shot.width, shot.height], radius=22, fill=255)
    px, py = 640, 262
    shadow = Image.new("RGBA", (shot.width + 80, shot.height + 80), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle([40, 50, shot.width + 40, shot.height + 50], radius=26, fill=(0, 0, 0, 150))
    from PIL import ImageFilter
    shadow = shadow.filter(ImageFilter.GaussianBlur(24))
    img.paste(shadow, (px - 40, py - 40), shadow)
    img.paste(shot, (px, py), mask)
    d.rounded_rectangle([px, py, px + shot.width, py + shot.height], radius=22, outline="#2c3550", width=2)
    out = ROOT / "docs" / "banner.png"
    img.save(out, optimize=True)
    print("wrote", out, img.size)


if __name__ == "__main__":
    main()
