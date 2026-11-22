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


# The eight themes of the reference design (M3), in its order. Accents are the design's own hexes, except
# where a button would fail 4.5:1 contrast with its icon: Ocean Blue #0B6EC7, Royal Purple #8A2BE2 and
# Rose Pink #E91E63 are lightened by 13 %, 21 % and 6 % for that use. Classic Dark's #2E3A46 is its panels.
THEMES = {
    "ocean": Palette(
        "Ocean Blue",
        "#070B15",
        "#0E1628",
        "#16213A",
        "#1E2B48",
        "#22304D",
        "#5E7096",
        "#8A9AB5",
        "#2B81CE",
        "#22D3EE",
    ),
    "forest": Palette(
        "Forest Green",
        "#06130F",
        "#0D211B",
        "#153228",
        "#1C4134",
        "#214A3B",
        "#568573",
        "#8DB0A2",
        "#00B894",
        "#5EEAD4",
    ),
    "violet": Palette(
        "Royal Purple",
        "#0E0A1C",
        "#191233",
        "#251B49",
        "#30245C",
        "#3A2C69",
        "#7566A8",
        "#A89CCB",
        "#A358E8",
        "#D8B4FE",
    ),
    "amber": Palette(
        "Amber Gold",
        "#11100B",
        "#1E1B12",
        "#2C281A",
        "#3A3522",
        "#443D27",
        "#80744B",
        "#AFA582",
        "#F4A261",
        "#FDE047",
    ),
    "teal": Palette(
        "Teal Breeze",
        "#051316",
        "#0A1F24",
        "#102C33",
        "#163941",
        "#1B424B",
        "#4F8592",
        "#8BB3BC",
        "#00D9FF",
        "#7DEBFF",
    ),
    "rose": Palette(
        "Rose Pink",
        "#170A10",
        "#27111B",
        "#3A1828",
        "#4A2033",
        "#55253C",
        "#94607A",
        "#BE95A9",
        "#EA2C6C",
        "#F9A8D4",
    ),
    "classic": Palette(
        "Classic Dark",
        "#0E1114",
        "#161B20",
        "#20272E",
        "#2E3A46",
        "#2E3A46",
        "#6E7B89",
        "#9AA6B2",
        "#A7B4C2",
        "#D5DDE5",
        swatch=("#2E3A46", "#A7B4C2"),
    ),
    "light": Palette(
        "Light",
        "#F4F7FC",
        "#FFFFFF",
        "#EAEEF5",
        "#DCE3EE",
        "#D5DCE8",
        "#7A8699",
        "#55627A",
        "#1D4ED8",
        "#0E7490",
        text="#111827",
        text_disabled="#94A0B3",
        on_accent="#FFFFFF",
        red="#C81E1E",
        amber="#B45309",
        green="#15803D",
        light=True,
    ),
}
# Themes that were retired, and the theme a saved choice moves to.
RETIRED_THEMES = {"sunset": "amber"}
