"""The colour themes. Each sets its own text colours, so tests can hold every theme to the same rules."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_THEME = "ocean"


@dataclass(frozen=True)
class Palette:
    label: str
    bg: str
    surface: str
    raised: str
    pressed: str
    border: str
    control_border: str
    muted: str
    accent: str  # BLUE in the default theme: buttons and gradients
    accent2: str  # CYAN in the default theme: focus, selection and highlights
    text: str = "#E6EDF7"
    text_disabled: str = "#4A5875"
    on_accent: str = "#04101F"  # icons and text on accent-coloured buttons
    red: str = "#F87171"
    amber: str = "#F59E0B"
    green: str = "#22C55E"
    light: bool = False
    swatch: tuple[str, str] | None = None  # the colours of its square in theme lists, when not the accents


# The seven themes of the theme gallery (0.12 redesign), in its order. Page, accent and highlight are the
# gallery's own colours, except where text or an icon would fail the contrast rules: Ocean Glow's accent is
# #0881D8 (was #087BCE), Royal Purple's #A055EC (#8528E8) and Midnight Glass's #6D7D96 (#64748B). Crystal
# Light's sky blues are too pale for text, so it works with deeper blues of the same family and keeps the sky
# blues in its swatch. Panels are the page colour mixed towards the accent (Neon Spectrum: its violet).
THEMES = {
    "ocean": Palette(
        "Ocean Glow",
        "#061A35",
        "#062444",
        "#062B51",
        "#07335D",
        "#073763",
        "#0779CF",
        "#58B6CC",
        "#0881D8",
        "#00D9FF",
        swatch=("#087BCE", "#00D9FF"),
    ),
    "aurora": Palette(
        "Aurora Dream",
        "#052B27",
        "#043B31",
        "#044738",
        "#045440",
        "#045A44",
        "#02A071",
        "#7BC6A7",
        "#00C987",
        "#55F5AE",
        swatch=("#00C987", "#55F5AE"),
    ),
    "violet": Palette(
        "Royal Purple",
        "#180B35",
        "#230E47",
        "#2C1055",
        "#341364",
        "#39146B",
        "#8D4DDE",
        "#B292CC",
        "#A055EC",
        "#D18AFF",
        swatch=("#8528E8", "#D18AFF"),
    ),
    "amber": Palette(
        "Golden Horizon",
        "#281606",
        "#3A2208",
        "#482C09",
        "#56360B",
        "#5D3B0B",
        "#AD7214",
        "#C9B384",
        "#D99118",
        "#FFD36B",
        swatch=("#D99118", "#FFD36B"),
    ),
    "midnight": Palette(
        "Midnight Glass",
        "#101820",
        "#18212B",
        "#1F2933",
        "#26303C",
        "#293440",
        "#5E738B",
        "#B5BDC7",
        "#6D7D96",
        "#DCEBFF",
        swatch=("#64748B", "#DCEBFF"),
    ),
    "neon": Palette(
        "Neon Spectrum",
        "#10102D",
        "#1C1542",
        "#261953",
        "#301D64",
        "#351F6C",
        "#7F55D1",
        "#C375B0",
        "#00CFFF",
        "#FF42BD",
        swatch=("#00CFFF", "#FF42BD"),
    ),
    "light": Palette(
        "Crystal Light",
        "#EAF6FF",
        "#FFFFFF",
        "#DCEFFB",
        "#C7E5F8",
        "#B9DCF3",
        "#5C86A6",
        "#3F5F78",
        "#0369A1",
        "#0E7490",
        text="#0B1B2B",
        text_disabled="#8EA4B8",
        on_accent="#FFFFFF",
        red="#C81E1E",
        amber="#B45309",
        green="#15803D",
        light=True,
        swatch=("#7DD3FC", "#0EA5E9"),
    ),
}
# Themes that were retired, and the theme a saved choice moves to (0.12: the nearest of the gallery's seven).
RETIRED_THEMES = {
    "sunset": "amber",
    "forest": "aurora",
    "teal": "ocean",
    "rose": "neon",
    "classic": "midnight",
}
