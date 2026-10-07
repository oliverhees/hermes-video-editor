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
    # film strip on the right
    x0 = 1060
    d.rectangle([x0, -10, W + 10, H + 10], fill="#171b26")
    for i in range(0, H, 80):
        for xx in (x0 + 24, W - 56):
            d.rounded_rectangle([xx, i + 20, xx + 32, i + 52], radius=6, fill="#0e1117")
    colors = ["#ff6b35", "#f7c948", "#4ecdc4", "#7b6cff", "#ff5d8f"]
    for n, c in enumerate(colors):
        top = 40 + n * 150
        d.rounded_rectangle([x0 + 90, top, W - 90, top + 128], radius=14, fill=c)
        shade = tuple(int(int(c.lstrip("#")[i:i + 2], 16) * 0.65) for i in (0, 2, 4))
        d.rectangle([x0 + 90, top + 88, W - 90, top + 128], fill=shade)
    # play triangle
    cx, cy = (x0 + W) // 2, H // 2
    d.ellipse([cx - 62, cy - 62, cx + 62, cy + 62], fill="#0e1117")
    d.polygon([(cx - 18, cy - 32), (cx - 18, cy + 32), (cx + 36, cy)], fill="#ffffff")
    # text
    d.text((80, 130), "LOCAL", font=font(BOLD, 36), fill="#ff6b35")
    d.text((80, 180), "Video Editor", font=font(BOLD, 128), fill="#ffffff")
    d.text((84, 335), "Edit your OWN footage from chat. FFmpeg only.", font=font(REG, 40), fill="#c9d1e0")
    chips = ["42 tools", "no cloud", "no API key", "cross-platform"]
    x = 84
    for text in chips:
        f = font(BOLD, 30)
        w = d.textlength(text, font=f)
        d.rounded_rectangle([x, 440, x + w + 44, 500], radius=30, outline="#4ecdc4", width=3)
        d.text((x + 22, 450), text, font=f, fill="#4ecdc4")
        x += w + 44 + 18
    for i, line in enumerate(["trim · crop 9:16 · captions · music ducking",
                              "loudness · export presets · platform check"]):
        d.text((84, 570 + i * 52), line, font=font(REG, 34), fill="#8a94a8")
    d.text((84, 720), "hermes-video-editor", font=font(BOLD, 30), fill="#5b667c")
    out = ROOT / "docs" / "banner.png"
    img.save(out, optimize=True)
    print("wrote", out, img.size)


if __name__ == "__main__":
    main()
