"""Generate the Babarify Media Player app icons from the source artwork.

Source: branding/source/Babarify Media Player Icon Grid.png (1254 x 1254): nine colour versions of the
icon, headphones around a play button over "Babarify", in a 3 x 3 grid. The app icon is the bright blue
tile at the top left. The script crops that tile, makes the area outside its rounded corners
transparent, and writes:

- PNG sizes and a multi-size Windows .ico in branding/icon/, copied into the Windows app's resources;
- the Android launcher icon: an adaptive icon (the rounded tile on a matching blue background) and
  plain PNGs, plus a rounded copy for the opening intro and the home screen widget.

The tile is about 406 px in the grid, so the 512 and 1024 px sizes are enlarged and a little soft.

Usage:  python branding/generate_icon.py   (requires Pillow)
"""

import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).parent
SOURCE = ROOT / "source" / "Babarify Media Player Icon Grid.png"
OUT = ROOT / "icon"
APP_RESOURCES = ROOT.parent / "src" / "babarify_frame" / "resources" / "icons"
ANDROID_RES = ROOT.parent / "android" / "player" / "app" / "src" / "main" / "res"
APP_PNG_SIZES = [16, 32, 64, 256]

# The top-left tile, measured on the 1254 px grid: a square crop around it, then the tile's rounded
# edge inside that crop (just inside its glossy rim, so no white from the background shows).
CROP = (10, 7, 416, 413)
TILE = (1, 1, 404, 405)
TILE_RADIUS = 76
FEATHER = 0.8

PNG_SIZES = [16, 24, 32, 48, 64, 128, 256, 512, 1024]
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]
SHARPEN_MAX = 48  # light unsharp mask at small sizes

# Android densities: launcher icon size (48 dp) and adaptive layer size (108 dp) in pixels.
DENSITIES = {"mdpi": 1.0, "hdpi": 1.5, "xhdpi": 2.0, "xxhdpi": 3.0, "xxxhdpi": 4.0}
# The rounded tile covers this much of the 108 dp layer. The launcher shows the middle 72 dp through its
# own shape, which hides the tile's corners while the wordmark stays whole.
FOREGROUND_DP = 74


def tile_crop():
    return Image.open(SOURCE).convert("RGBA").crop(CROP)


def master():
    art = tile_crop()
    mask = Image.new("L", art.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(TILE, radius=TILE_RADIUS, fill=255)
    art.putalpha(mask.filter(ImageFilter.GaussianBlur(FEATHER)))
    return art


def sized(art, px):
    im = art.resize((px, px), Image.LANCZOS)
    if px <= SHARPEN_MAX:
        im = im.filter(ImageFilter.UnsharpMask(radius=0.6, percent=60, threshold=0))
    return im


def edge_colour(art):
    """The tile's deep blue along its lower part, for the adaptive icon's background."""
    w, h = art.size
    points = [
        (w // 2, h * 94 // 100),
        (w // 4, h * 92 // 100),
        (w * 3 // 4, h * 92 // 100),
        (w // 10, h * 64 // 100),
    ]
    pixels = [art.getpixel(p) for p in points]
    return tuple(sum(p[i] for p in pixels) // len(pixels) for i in range(3))


def windows(art):
    (OUT / "png").mkdir(parents=True, exist_ok=True)
    images = {px: sized(art, px) for px in PNG_SIZES}
    for px, im in images.items():
        im.save(OUT / "png" / f"babarify-frame-{px}.png")
    ico = [images[px] for px in ICO_SIZES]
    ico[-1].save(OUT / "babarify-frame.ico", sizes=[(p, p) for p in ICO_SIZES], append_images=ico[:-1])

    # Copies bundled with the application package.
    APP_RESOURCES.mkdir(parents=True, exist_ok=True)
    shutil.copy2(OUT / "babarify-frame.ico", APP_RESOURCES / "babarify-frame.ico")
    for px in APP_PNG_SIZES:
        shutil.copy2(OUT / "png" / f"babarify-frame-{px}.png", APP_RESOURCES / f"babarify-frame-{px}.png")


def android(art):
    for name, scale in DENSITIES.items():
        folder = ANDROID_RES / f"mipmap-{name}"
        folder.mkdir(parents=True, exist_ok=True)
        sized(art, round(48 * scale)).save(folder / "ic_launcher.png")
        layer = round(108 * scale)
        foreground = Image.new("RGBA", (layer, layer), (0, 0, 0, 0))
        px = round(FOREGROUND_DP * scale)
        offset = (layer - px) // 2
        foreground.alpha_composite(art.resize((px, px), Image.LANCZOS), (offset, offset))
        foreground.save(folder / "ic_launcher_foreground.png")

    # The rounded tile for the intro and the widget, which draw it themselves.
    nodpi = ANDROID_RES / "drawable-nodpi"
    nodpi.mkdir(parents=True, exist_ok=True)
    art.resize((384, 384), Image.LANCZOS).save(nodpi / "brand_icon.png")

    r, g, b = edge_colour(tile_crop())
    values = ANDROID_RES / "values" / "ic_launcher_background.xml"
    values.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n'
        f'    <color name="ic_launcher_background">#{r:02X}{g:02X}{b:02X}</color>\n</resources>\n',
        encoding="utf-8",
        newline="\n",
    )


def main():
    art = master()
    windows(art)
    android(art)
    print(f"Wrote icons to {OUT}, {APP_RESOURCES} and {ANDROID_RES}")


if __name__ == "__main__":
    main()
