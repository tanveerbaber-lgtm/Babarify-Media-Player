"""Generate Babarify Media Player's logos and Windows app icons from the source artwork (0.12 branding).

Sources, 2048 x 2048, each on a dark textured background:

- branding/source/App Icon.jpg: the mark, a rainbow neon sound wave running into a play button in a circle;
- branding/source/Left Side Panel Icon.jpg: the mark with "BABARIFY MEDIA PLAYER" beside it.

The neon glows into its background, so a plain cut-out would leave a dark halo or lose the glow. Instead the
background behind every pixel is estimated (a wide blur of the pixels that are clearly background), and
each pixel's rise above it becomes its opacity ("colour to alpha"): the strokes stay solid, the glow becomes
a soft see-through glow that works on any theme, and the background's grain is dropped.

It writes, into branding/icon/ and the Windows app's resources:

- babarify-logo.png and babarify-wordmark.png: for the dark themes, with the full glow;
- babarify-logo-light.png and babarify-wordmark-light.png: for Crystal Light, with the glow trimmed back and
  the white letters of the name in dark navy, which a light page needs;
- PNG sizes and a multi-size Windows .ico of the mark, with the glow trimmed a little so they stay crisp on
  a light or dark taskbar.

and, for the Android app (android/player):

- the launcher icon: an adaptive icon (the mark on the artwork's dark navy) and a plain one for older phones;
- brand_icon.png: the mark on a dark tile, for the intro and the home-screen widget, which round its corners;
- brand_logo.png and brand_logo_light.png: the mark alone, for the top of the Home screen.

Usage:  python branding/generate_icon.py   (requires Pillow and numpy)
"""

import shutil
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).parent
MARK = ROOT / "source" / "App Icon.jpg"
WORDMARK = ROOT / "source" / "Left Side Panel Icon.jpg"
OUT = ROOT / "icon"
APP_RESOURCES = ROOT.parent / "src" / "babarify_frame" / "resources" / "icons"
APP_PNG_SIZES = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]  # every size a scaled taskbar asks for
PNG_SIZES = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256, 512, 1024]
ICO_SIZES = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]
LOGO_WIDTH = 1024
NAVY = (11, 27, 43)  # Crystal Light's text colour, for the name's white letters
ANDROID_RES = ROOT.parent / "android" / "player" / "app" / "src" / "main" / "res"
# Android densities: launcher icon size (48 dp) and adaptive layer size (108 dp) in pixels.
DENSITIES = {"mdpi": 1.0, "hdpi": 1.5, "xhdpi": 2.0, "xxhdpi": 3.0, "xxxhdpi": 4.0}
# The launcher shows a circle of about 66 dp of the 108 dp layer at the least; the round mark fits inside.
FOREGROUND_DP = 60
# Icons are small: the glow is trimmed further and the thin start of the sound wave left out, so the circle
# fills the square like other taskbar icons (0.12, the owner's request).
ICON_TRIM, ICON_CUT_LEFT = 0.3, 0.14
TILE_TOP, TILE_BOTTOM = (26, 30, 43), (14, 17, 26)  # the artwork's own background, lighter at the top


def lift(path: Path) -> Image.Image:
    """The artwork with its dark background turned into transparency, cropped to the artwork."""
    rgb = np.asarray(Image.open(path).convert("RGB")).astype(np.float32)
    lum = rgb.mean(axis=2)
    sat = rgb.max(axis=2) - rgb.min(axis=2)
    art = (sat > 28) | (lum > 70)  # clearly brighter or more colourful than the background
    grown = Image.fromarray((art * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(31))
    known = (np.asarray(grown) == 0).astype(np.float32)
    height, width = lum.shape
    step = 8

    def blur(values: np.ndarray, scale: float = 1.0) -> np.ndarray:
        image = Image.fromarray(np.clip(values * scale, 0, 255).astype(np.uint8), "L")
        image = image.resize((width // step, height // step), Image.Resampling.BILINEAR)
        image = image.filter(ImageFilter.GaussianBlur(24)).resize((width, height), Image.Resampling.BILINEAR)
        return np.asarray(image).astype(np.float32) / scale

    weight = blur(known, 255.0) + 1e-3
    background = np.stack([blur(rgb[..., c] * known) / weight for c in range(3)], axis=2)
    rise = np.clip((rgb - background) / np.maximum(255 - background, 1), 0, 1)
    alpha = np.clip((rise.max(axis=2) - 0.05) / 0.95, 0, 1)  # the grain and the faintest haze go
    colour = np.clip(background + (rgb - background) / np.maximum(alpha[..., None], 1e-3), 0, 255)
    image = Image.fromarray(np.dstack([colour, alpha * 255]).astype(np.uint8), "RGBA")
    box = image.getchannel("A").point(lambda v: 255 if v > 24 else 0).getbbox()
    return image.crop(box) if box else image


def trimmed(image: Image.Image, cut: float) -> Image.Image:
    """The glow trimmed back: opacity below ``cut`` goes, the rest is stretched to full."""
    rgba = np.asarray(image).astype(np.float32)
    alpha = np.clip((rgba[..., 3] / 255 - cut) / (1 - cut), 0, 1)
    rgba[..., 3] = alpha * 255
    return Image.fromarray(rgba.astype(np.uint8), "RGBA")


def dark_letters(image: Image.Image) -> Image.Image:
    """The name's white letters (and their pale edges) in navy, for a light page."""
    rgba = np.asarray(image).astype(np.float32)
    rgb = rgba[..., :3]
    pale = ((rgb.max(axis=2) - rgb.min(axis=2)) < 45) & (rgb.mean(axis=2) > 165) & (rgba[..., 3] > 40)
    rgba[pale, :3] = NAVY
    return Image.fromarray(rgba.astype(np.uint8), "RGBA")


def width(image: Image.Image, size: int) -> Image.Image:
    return image.resize((size, round(size * image.height / image.width)), Image.Resampling.LANCZOS)


def icon_art(mark: Image.Image) -> Image.Image:
    """The mark for icons: crisper, without the sound wave's thin tail, cropped to what is left."""
    art = trimmed(mark, ICON_TRIM)
    art = art.crop((round(art.width * ICON_CUT_LEFT), 0, art.width, art.height))
    box = art.getchannel("A").getbbox()
    return art.crop(box) if box else art


def square(image: Image.Image, margin: float = 0.03) -> Image.Image:
    side = int(max(image.size) * (1 + 2 * margin))
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(image, ((side - image.width) // 2, (side - image.height) // 2), image)
    return canvas


def sized(image: Image.Image, size: int) -> Image.Image:
    small = image.resize((size, size), Image.Resampling.LANCZOS)
    if size <= 48:
        small = small.filter(ImageFilter.UnsharpMask(radius=0.6, percent=60, threshold=1))
    return small


def tile(mark: Image.Image, size: int, fill: float) -> Image.Image:
    """The mark on a square of the artwork's dark navy, ``fill`` of the side wide."""
    top, bottom = np.array(TILE_TOP, np.float32), np.array(TILE_BOTTOM, np.float32)
    rows = np.linspace(0, 1, size, dtype=np.float32)[:, None, None]
    shade = np.broadcast_to(top + (bottom - top) * rows, (size, size, 3))
    canvas = Image.fromarray(
        np.dstack([shade, np.full((size, size), 255, np.float32)]).astype(np.uint8), "RGBA"
    )
    art = width(mark, round(size * fill))
    canvas.alpha_composite(art, ((size - art.width) // 2, (size - art.height) // 2))
    return canvas


def rounded(image: Image.Image, radius: float) -> Image.Image:
    mask = Image.new("L", (image.width * 4, image.height * 4), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, mask.width - 1, mask.height - 1), radius * mask.width, fill=255
    )
    out = image.copy()
    out.putalpha(mask.resize(image.size, Image.Resampling.LANCZOS))
    return out


def android(mark: Image.Image, light_mark: Image.Image) -> None:
    crisp = icon_art(mark)
    for name, scale in DENSITIES.items():
        folder = ANDROID_RES / f"mipmap-{name}"
        folder.mkdir(parents=True, exist_ok=True)
        rounded(tile(crisp, round(192 * scale), 0.8), 0.22).resize(
            (round(48 * scale),) * 2, Image.Resampling.LANCZOS
        ).save(folder / "ic_launcher.png")
        layer = round(108 * scale)
        foreground = Image.new("RGBA", (layer, layer), (0, 0, 0, 0))
        art = width(crisp, round(FOREGROUND_DP * scale))
        foreground.alpha_composite(art, ((layer - art.width) // 2, (layer - art.height) // 2))
        foreground.save(folder / "ic_launcher_foreground.png")
    nodpi = ANDROID_RES / "drawable-nodpi"
    nodpi.mkdir(parents=True, exist_ok=True)
    tile(crisp, 384, 0.8).save(nodpi / "brand_icon.png")
    width(mark, 384).save(nodpi / "brand_logo.png")
    width(light_mark, 384).save(nodpi / "brand_logo_light.png")
    r, g, b = (round((t + u) / 2) for t, u in zip(TILE_TOP, TILE_BOTTOM, strict=True))
    (ANDROID_RES / "values" / "ic_launcher_background.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n'
        f'    <color name="ic_launcher_background">#{r:02X}{g:02X}{b:02X}</color>\n</resources>\n',
        encoding="utf-8",
        newline="\n",
    )


def main() -> None:
    OUT.mkdir(exist_ok=True)
    (OUT / "png").mkdir(exist_ok=True)
    mark, wordmark = lift(MARK), lift(WORDMARK)
    files = {
        "babarify-logo.png": width(mark, LOGO_WIDTH),
        "babarify-logo-light.png": width(trimmed(mark, 0.35), LOGO_WIDTH),
        "babarify-wordmark.png": width(wordmark, LOGO_WIDTH),
        "babarify-wordmark-light.png": width(dark_letters(trimmed(wordmark, 0.35)), LOGO_WIDTH),
    }
    for name, image in files.items():
        image.save(OUT / name)
    icon = square(icon_art(mark), 0.0)
    icons = {size: sized(icon, size) for size in PNG_SIZES}
    for size, image in icons.items():
        image.save(OUT / "png" / f"babarify-frame-{size}.png")
    largest = icons[max(ICO_SIZES)]
    largest.save(OUT / "babarify-frame.ico", sizes=[(s, s) for s in ICO_SIZES],
                 append_images=[icons[s] for s in ICO_SIZES if s != max(ICO_SIZES)])  # fmt: skip
    APP_RESOURCES.mkdir(parents=True, exist_ok=True)
    for size in APP_PNG_SIZES:
        shutil.copy2(OUT / "png" / f"babarify-frame-{size}.png", APP_RESOURCES / f"babarify-frame-{size}.png")
    for name in ("babarify-frame.ico", *files):
        shutil.copy2(OUT / name, APP_RESOURCES / name)
    android(mark, files["babarify-logo-light.png"])
    print(
        f"{len(files)} logos, {len(PNG_SIZES)} PNG sizes and the .ico written to {OUT}, {APP_RESOURCES}"
        f" and {ANDROID_RES}"
    )


if __name__ == "__main__":
    main()
