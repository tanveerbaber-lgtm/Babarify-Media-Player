"""Generate the Babarify Media Player app icons from the source artwork.

Source: branding/source/Babarify Media Player Logo Suite.png (1536 x 1024): the "Babarify Media Player"
wordmark, and below it two app tiles of a blue "B" with a play button, green sound bars and a green
swoosh. The app icon is the filled blue tile at the bottom left. That tile is a little wider than tall
and its anti-aliased corners hold white from the sheet, so the script rebuilds it: a fresh rounded square
in the tile's blues fills the whole icon, and the tile's artwork (inside its rim) is blended onto it with
soft edges. It writes:

- PNG sizes and a multi-size Windows .ico in branding/icon/, copied into the Windows app's resources;
- the Android launcher icon: an adaptive icon (the rounded tile on a matching blue background) and
  plain PNGs, plus a rounded copy for the opening intro and the home screen widget.

The tile is about 450 px wide in the suite, so the 512 and 1024 px sizes are enlarged and a little soft.

Usage:  python branding/generate_icon.py   (requires Pillow)
"""

import shutil
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = Path(__file__).parent
SOURCE = ROOT / "source" / "Babarify Media Player Logo Suite.png"
OUT = ROOT / "icon"
APP_RESOURCES = ROOT.parent / "src" / "babarify_frame" / "resources" / "icons"
ANDROID_RES = ROOT.parent / "android" / "player" / "app" / "src" / "main" / "res"
APP_PNG_SIZES = [16, 32, 64, 256]

# The filled tile, measured on the 1536 x 1024 suite.
CROP = (247, 504, 700, 913)
ART_INSET = 9  # px inside the tile's edge, past its rim and its white-tinted corners
ART_WIDTH = 0.92  # share of the icon's width the artwork takes
ART_FEATHER = 14  # px (at 1024) over which the artwork blends into the new background
SIZE = 1024
RADIUS = 0.2  # corner radius as a share of the icon's size
# The new background: a diagonal gradient through the tile's own blues.
TOP_LEFT = (12, 160, 255)
BOTTOM_RIGHT = (0, 22, 140)
RIM = (120, 220, 255, 150)

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


def gradient():
    small = Image.new("RGB", (256, 256))
    pixels = small.load()
    for y in range(256):
        for x in range(256):
            t = min(1.0, (x * 0.45 + y * 0.75) / (255 * 1.2))
            pixels[x, y] = tuple(round(a + (b - a) * t) for a, b in zip(TOP_LEFT, BOTTOM_RIGHT, strict=True))
    return small.resize((SIZE, SIZE), Image.BICUBIC).convert("RGBA")


def master():
    canvas = gradient()

    tile = tile_crop()
    art = tile.crop((ART_INSET, ART_INSET, tile.width - ART_INSET, tile.height - ART_INSET))
    scale = SIZE * ART_WIDTH / art.width
    art = art.resize((round(art.width * scale), round(art.height * scale)), Image.LANCZOS)
    mask = Image.new("L", art.size, 0)
    f = ART_FEATHER
    ImageDraw.Draw(mask).rounded_rectangle(
        (f, f, art.width - f, art.height - f), radius=int(SIZE * 0.12), fill=255
    )
    art.putalpha(mask.filter(ImageFilter.GaussianBlur(f / 2)))
    canvas.alpha_composite(art, ((SIZE - art.width) // 2, (SIZE - art.height) // 2))

    # A thin glossy line just inside the edge, like the original tile's rim.
    radius = int(SIZE * RADIUS)
    rim = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    ImageDraw.Draw(rim).rounded_rectangle(
        (10, 10, SIZE - 11, SIZE - 11), radius=radius - 10, outline=RIM, width=6
    )
    canvas.alpha_composite(rim.filter(ImageFilter.GaussianBlur(1.5)))

    # The rounded square, drawn large and reduced for a smooth edge.
    shape = Image.new("L", (SIZE * 4, SIZE * 4), 0)
    ImageDraw.Draw(shape).rounded_rectangle((0, 0, SIZE * 4 - 1, SIZE * 4 - 1), radius=radius * 4, fill=255)
    canvas.putalpha(ImageChops.multiply(canvas.getchannel("A"), shape.resize((SIZE, SIZE), Image.LANCZOS)))
    return canvas


def sized(art, px):
    im = art.resize((px, px), Image.LANCZOS)
    if px <= SHARPEN_MAX:
        im = im.filter(ImageFilter.UnsharpMask(radius=0.6, percent=60, threshold=0))
    return im


def edge_colour(art):
    """The icon's deep blue along its lower edge, for the adaptive icon's background."""
    w, h = art.size
    points = [
        (w // 2, h * 94 // 100),
        (w // 4, h * 92 // 100),
        (w * 3 // 4, h * 92 // 100),
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

    r, g, b = edge_colour(art)
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
