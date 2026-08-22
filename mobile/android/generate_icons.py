# -*- coding: utf-8 -*-
"""Generate Android launcher icons from the existing 1024px app icon."""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "static" / "icons" / "app-icon-1024.png"
RES = Path(__file__).resolve().parent / "app" / "src" / "main" / "res"

DENSITIES = {
    "mdpi": 1,
    "hdpi": 1.5,
    "xhdpi": 2,
    "xxhdpi": 3,
    "xxxhdpi": 4,
}


def circle_mask(size: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size - 1, size - 1), fill=255)
    return mask


def make_padded(src: Image.Image, size: int, scale: float = 0.72) -> Image.Image:
    canvas = Image.new("RGBA", (size, size), (26, 58, 110, 255))
    inner = max(1, int(size * scale))
    img = src.resize((inner, inner), Image.Resampling.LANCZOS)
    offset = (size - inner) // 2
    canvas.paste(img, (offset, offset), img)
    return canvas


def main() -> None:
    src = Image.open(SRC).convert("RGBA")
    for name, factor in DENSITIES.items():
        folder = RES / f"mipmap-{name}"
        folder.mkdir(parents=True, exist_ok=True)

        launcher_size = int(48 * factor)
        launcher = src.resize((launcher_size, launcher_size), Image.Resampling.LANCZOS)
        launcher.save(folder / "ic_launcher.png", "PNG")

        round_icon = Image.new("RGBA", (launcher_size, launcher_size), (0, 0, 0, 0))
        round_icon.paste(launcher, (0, 0), circle_mask(launcher_size))
        round_icon.save(folder / "ic_launcher_round.png", "PNG")

        foreground_size = int(108 * factor)
        make_padded(src, foreground_size).save(folder / "ic_launcher_foreground.png", "PNG")
        print(f"wrote {folder}")


if __name__ == "__main__":
    main()
