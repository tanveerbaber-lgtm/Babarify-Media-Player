"""Generate Babarify Media Player's logo and Windows app icons from the source artwork (0.12 redesign).

Source: branding/source/Glossy Headphone Music Player Icon.png (1254 x 1254): headphones around a glowing play
button, with blue-to-green bars. Its "transparent" background is a grey checkerboard painted into the pixels,
so the script cuts the logo out:

- neutral mid-grey pixels are background candidates (the dark ear pads and white highlights fall outside);
- a candidate region is background if it touches the edge, or if it is large, pure grey (the ear pads'
  sheen is slightly blue) and holds both checker tones (the gap under the headband);
- the edge is trimmed by one pixel and softened, so no grey fringe shows on dark themes.

It writes:

- branding/icon/babarify-logo.png: the transparent logo, 1024 px wide, for the app's pages;
- PNG sizes and a multi-size Windows .ico in branding/icon/, copied into the Windows app's resources. The
  smallest sizes (up to 32 px) show the play button alone: the whole logo is a smudge at that size.

The Android icons are not touched.

Usage:  python branding/generate_icon.py   (requires Pillow and numpy)
"""

import shutil
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).parent
SOURCE = ROOT / "source" / "Glossy Headphone Music Player Icon.png"
OUT = ROOT / "icon"
APP_RESOURCES = ROOT.parent / "src" / "babarify_frame" / "resources" / "icons"
APP_PNG_SIZES = [16, 32, 64, 256]
PNG_SIZES = [16, 24, 32, 48, 64, 128, 256, 512, 1024]
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]
SMALL = 32  # this size and below: the play button alone
PLAY_BUTTON = (285, 305, 965, 985)  # the glowing circle, measured on the 1254 px source
LOGO_WIDTH = 1024


def cut_out(source: Image.Image) -> Image.Image:
    rgb = source.convert("RGB")
    a = np.asarray(rgb).astype(np.int16)
    sat = a.max(axis=2) - a.min(axis=2)
    lum = a.mean(axis=2)
    candidate = (sat < 24) & (lum > 118) & (lum < 238)
    mask = Image.fromarray((candidate * 255).astype(np.uint8), "L")
    background = np.zeros_like(candidate)
    visited = np.zeros_like(candidate)
    height, width = candidate.shape
    for y in range(0, height, 6):
        for x in range(0, width, 6):
            if not candidate[y, x] or visited[y, x]:
                continue
            filled = mask.copy()
            ImageDraw.floodfill(filled, (x, y), 100)
            region = np.asarray(filled) == 100
            visited |= region
            edge = region[0].any() or region[-1].any() or region[:, 0].any() or region[:, -1].any()
            tones = lum[region]
            both = (tones > 195).mean() > 0.3 and (tones < 175).mean() > 0.3
            neutral = sat[region].mean() < 6
            if edge or (region.sum() > 1500 and both and neutral):
                background |= region
    alpha = Image.fromarray(np.where(background, 0, 255).astype(np.uint8), "L")
    alpha = alpha.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.8))
    out = rgb.convert("RGBA")
    out.putalpha(alpha)
    return out


def round_crop(image: Image.Image) -> Image.Image:
    """Only the circle: the bars and ear cups around the play button are cut away."""
    mask = Image.new("L", image.size, 0)
    ImageDraw.Draw(mask).ellipse((6, 6, image.width - 7, image.height - 7), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(1.5))
    out = image.copy()
    out.putalpha(Image.fromarray(np.minimum(np.asarray(image.getchannel("A")), np.asarray(mask))))
    return out


def square(image: Image.Image, margin: float = 0.04) -> Image.Image:
    """The artwork centred on a transparent square, with a small margin."""
    box = image.getbbox() or (0, 0, image.width, image.height)
    art = image.crop(box)
    side = int(max(art.size) * (1 + 2 * margin))
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(art, ((side - art.width) // 2, (side - art.height) // 2), art)
    return canvas


def sized(image: Image.Image, size: int) -> Image.Image:
    small = image.resize((size, size), Image.Resampling.LANCZOS)
    if size <= 48:
        small = small.filter(ImageFilter.UnsharpMask(radius=0.6, percent=60, threshold=1))
    return small


def main() -> None:
    logo = cut_out(Image.open(SOURCE))
    OUT.mkdir(exist_ok=True)
    (OUT / "png").mkdir(exist_ok=True)
    box = logo.getbbox() or (0, 0, logo.width, logo.height)
    art = logo.crop(box)
    art.resize((LOGO_WIDTH, round(LOGO_WIDTH * art.height / art.width)), Image.Resampling.LANCZOS).save(
        OUT / "babarify-logo.png"
    )
    full = square(logo)
    button = square(round_crop(logo.crop(PLAY_BUTTON)), margin=0.02)
    icons = {size: sized(button if size <= SMALL else full, size) for size in PNG_SIZES}
    for size, image in icons.items():
        image.save(OUT / "png" / f"babarify-frame-{size}.png")
    largest = icons[max(ICO_SIZES)]
    largest.save(OUT / "babarify-frame.ico", sizes=[(s, s) for s in ICO_SIZES],
                 append_images=[icons[s] for s in ICO_SIZES if s != max(ICO_SIZES)])  # fmt: skip
    APP_RESOURCES.mkdir(parents=True, exist_ok=True)
    for size in APP_PNG_SIZES:
        shutil.copy2(OUT / "png" / f"babarify-frame-{size}.png", APP_RESOURCES / f"babarify-frame-{size}.png")
    shutil.copy2(OUT / "babarify-frame.ico", APP_RESOURCES / "babarify-frame.ico")
    shutil.copy2(OUT / "babarify-logo.png", APP_RESOURCES / "babarify-logo.png")
    print(f"logo, {len(PNG_SIZES)} PNG sizes and the .ico written to {OUT} and {APP_RESOURCES}")


if __name__ == "__main__":
    main()
