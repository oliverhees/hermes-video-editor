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


def glow(img, cx, cy, r, color, alpha):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse([cx - r, cy - r, cx + r, cy + r], fill=color + (alpha,))
    from PIL import ImageFilter
    layer = layer.filter(ImageFilter.GaussianBlur(r // 2))
    img.paste(layer, (0, 0), layer)


def main():
    from PIL import ImageFilter
    ACC, TEAL = "#8b6cf0", "#4ecdc4"
    img = Image.new("RGB", (W, H), "#0b0d14")
    d = ImageDraw.Draw(img)
    for y in range(H):                                   # vertical gradient
        t = y / H
        d.line([(0, y), (W, y)], fill=(int(11 + 14 * t), int(13 + 8 * t), int(20 + 34 * t)))
    glow(img, 1250, 330, 430, (139, 108, 240), 120)       # violet glow behind the screenshot
    glow(img, 120, 760, 300, (78, 205, 196), 60)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([70, 54, 412, 96], radius=21, outline=ACC, width=2)
    d.text((92, 62), "100% LOCAL  \u00B7  FFMPEG", font=font(BOLD, 22), fill="#c9bdfb")
    d.text((72, 128), "Hermes", font=font(BOLD, 52), fill="#c9d1e0")
    d.text((68, 190), "Video Editor", font=font(BOLD, 88), fill="#ffffff")
    d.text((74, 320), "Cut, reframe, caption and master", font=font(REG, 26), fill="#c9d1e0")
    d.text((74, 356), "your own footage: visually or by chat.", font=font(REG, 26), fill="#c9d1e0")
    chips = ["Multi-clip timeline + waveform", "9:16 canvas, move and zoom clips", "Shapes, scenes, unlimited tracks", "45 FFmpeg tools for the agent"]
    for i, text in enumerate(chips):
        y = 450 + i * 62
        d.ellipse([74, y + 6, 98, y + 30], fill=TEAL)
        d.text((80, y + 4), "\u2713", font=font(BOLD, 22), fill="#0b0d14")
        d.text((116, y + 2), text, font=font(REG, 26), fill="#e6eaf2")
    d.text((74, 730), "Powered by Lokyy.de \u00B7 German Hermes Engineering", font=font(REG, 20), fill="#8d97ad")
    # real screenshot of the editor, bleeding off the right and bottom edges
    shot = Image.open(ROOT / "docs" / "editor.png").convert("RGB")
    sw = 940
    shot = shot.resize((sw, int(shot.height * sw / shot.width)), Image.LANCZOS)
    mask = Image.new("L", shot.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, shot.width, shot.height], radius=22, fill=255)
    px, py = 690, 170
    shadow = Image.new("RGBA", (shot.width + 80, shot.height + 80), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle([40, 50, shot.width + 40, shot.height + 50], radius=26, fill=(0, 0, 0, 170))
    shadow = shadow.filter(ImageFilter.GaussianBlur(24))
    img.paste(shadow, (px - 40, py - 40), shadow)
    img.paste(shot, (px, py), mask)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([px, py, px + shot.width, py + shot.height], radius=22, outline="#3a3f66", width=2)
    out = ROOT / "docs" / "banner.png"
    img.save(out, optimize=True)
    print("wrote", out, img.size)


if __name__ == "__main__":
    main()
