# -*- coding: utf-8 -*-
"""Generate web favicons and the Windows exe icon from app-icon-1024.png."""
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "static" / "icons" / "app-icon-1024.png"
ICONS = ROOT / "static" / "icons"
DESKTOP_ICO = ROOT / "desktop" / "windows" / "Shuran.Desktop" / "app.ico"


def resize_png(src, size, dest):
    img = src.resize((size, size), Image.Resampling.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, "PNG")
    print("wrote %s" % dest)


def write_ico(src, dest, sizes):
    dest.parent.mkdir(parents=True, exist_ok=True)
    src.save(dest, format="ICO", sizes=[(s, s) for s in sizes])
    print("wrote %s" % dest)


def main():
    src = Image.open(SRC).convert("RGBA")
    resize_png(src, 32, ICONS / "app-icon-32.png")
    resize_png(src, 192, ICONS / "app-icon-192.png")
    resize_png(src, 512, ICONS / "app-icon-512.png")
    write_ico(src, ICONS / "favicon.ico", [16, 32, 48])
    write_ico(src, DESKTOP_ICO, [16, 24, 32, 48, 64, 128, 256])


if __name__ == "__main__":
    main()
