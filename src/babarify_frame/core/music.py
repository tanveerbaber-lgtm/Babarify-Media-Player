"""Rules for playing music, free of any UI: repeat, shuffle and the animations' movement."""

from __future__ import annotations

import math
import os
import random
import re
from enum import StrEnum

AUTO_SWITCH_MS = 20_000
REST_LEVEL = 0.08
SLEEP_MINUTES = (15, 30, 45, 60, 90, 120)
_PEAK_FALL = 0.012
_ENVELOPE_FLOOR = 0.45


class RepeatMode(StrEnum):
    OFF = "off"
    ONE = "one"
    ALL = "all"

    def next(self) -> RepeatMode:
        order = list(RepeatMode)
        return order[(order.index(self) + 1) % len(order)]


class VisualStyle(StrEnum):
    """How audio with no picture is animated. AUTO moves through the others while it plays."""

    AUTO = "auto"
    MIRROR = "mirror"
    CAPSULES = "capsules"
    WAVES = "waves"
    CIRCLE = "circle"
    LIGHTS = "lights"


STYLE_LABELS = {
    VisualStyle.AUTO: "Change automatically",
    VisualStyle.MIRROR: "Mirror bars",
    VisualStyle.CAPSULES: "Capsules",
    VisualStyle.WAVES: "Waves",
    VisualStyle.CIRCLE: "Circle",
    VisualStyle.LIGHTS: "Lights",
}
STYLE_CYCLE = tuple(style for style in VisualStyle if style is not VisualStyle.AUTO)


FADE_CHOICES_S = (0, 2, 4, 6)
# Sound effects, as libVLC audio filters. "none" adds nothing.
AUDIO_EFFECTS = {
    "none": "",
    "room": "spatializer",
    "wide": "stereo_widen",
    "both": "spatializer:stereo_widen",
}
AUDIO_EFFECT_LABELS = {
    "none": "None",
    "room": "Room",
    "wide": "Wider stereo",
    "both": "Room and wider stereo",
}


def fade_level(base: int, ms: int, fade_ms: int) -> int:
    """The volume ``ms`` into a fade in, or ``ms`` before the end of a fade out."""
    if fade_ms <= 0:
        return base
    return round(base * max(0, min(ms, fade_ms)) / fade_ms)


def index_after_end(index: int, length: int, mode: RepeatMode) -> int | None:
    """Which queue item plays when the current one ends; None means playback stops."""
    if length <= 0:
        return None
    if mode is RepeatMode.ONE:
        return index
    if index + 1 < length:
        return index + 1
    return 0 if mode is RepeatMode.ALL else None


def natural_key(name: str) -> list[tuple[int, int | str]]:
    """Sort key that puts numbers in number order: "Episode 2" before "Episode 10"."""
    return [
        (0, int(part)) if part.isdigit() else (1, part.casefold())
        for part in re.split(r"(\d+)", name)
        if part
    ]


def next_in_folder(path: str, extensions: frozenset[str]) -> str | None:
    """The file after ``path`` in its folder, among files with these extensions, in natural name order."""
    folder = os.path.dirname(path)
    try:
        names = [
            entry.name
            for entry in os.scandir(folder)
            if entry.is_file()
            and not entry.name.startswith(".")
            and os.path.splitext(entry.name)[1].lower() in extensions
        ]
    except OSError:
        return None
    names.sort(key=natural_key)
    current = os.path.basename(path)
    following = [n for n in names if natural_key(n) > natural_key(current)]
    return os.path.join(folder, following[0]) if following else None


def shuffled(items: list[str], index: int, rng: random.Random | None = None) -> list[str]:
    """The same items in a random order, starting with the current one so it carries on playing."""
    if not 0 <= index < len(items):
        return list(items)
    others = items[:index] + items[index + 1 :]
    (rng or random).shuffle(others)
    return [items[index], *others]


def level(bar: int, time_ms: int) -> float:
    """How high an animated bar stands, from REST_LEVEL to 1. Decoration, not a measurement of the sound."""
    t = time_ms / 1000
    wave = (
        0.55 * abs(math.sin(t * 2.3 + bar * 0.9))
        + 0.3 * abs(math.sin(t * 4.1 + bar * 1.7))
        + 0.15 * abs(math.sin(t * math.pi * 2.7 + bar * 2.9))
    )
    return max(REST_LEVEL, min(1.0, REST_LEVEL + (1 - REST_LEVEL) * wave))


def envelope(bar: int, count: int) -> float:
    """Taller in the middle and lower at the ends, so a row of bars makes a shape."""
    if count <= 1:
        return 1.0
    return _ENVELOPE_FLOOR + (1 - _ENVELOPE_FLOOR) * math.sin(bar / (count - 1) * math.pi)


def peak(previous: float, current: float) -> float:
    """A peak jumps up with its bar and then falls slowly back to it."""
    return max(current, previous - _PEAK_FALL)


def auto_style(elapsed_ms: int) -> VisualStyle:
    return STYLE_CYCLE[(max(0, elapsed_ms) // AUTO_SWITCH_MS) % len(STYLE_CYCLE)]
