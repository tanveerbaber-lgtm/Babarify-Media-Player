"""The libVLC 3 audio filter chain: equalizer, sound effects and the clipping limiter (M2).

libVLC 3's public API offers only the equalizer, and ``libvlc_media_player_set_equalizer`` replaces the
audio output's whole filter list with "equalizer". A per-media ``:audio-filter`` option is ignored (measured
in M2: the effects of 0.10 never loaded). Babarify therefore sets the ``audio-filter`` variable itself through
``libvlccore``'s exported ``var_SetChecked``, the call VLC's own interfaces use:

* on the media player, before playback starts, so the audio output is created with the chain;
* on the playing audio output (a child object of the player), after every live equalizer change.

Volume above 100 % is done as extra equalizer preamp before the limiter, never with libVLC's own gain,
which comes after every filter and clipped 41 % of a loud signal's samples at 126 % (tools/clipping_check.py).
"""

from __future__ import annotations

import ctypes
import logging
import math
from pathlib import Path
from typing import Any

from babarify_frame.core.enhancements import PREAMP_UNITY_DB, EqualizerSettings

_log = logging.getLogger(__name__)

VLC_VAR_STRING = 0x0040
MAX_ENGINE_PREAMP_DB = 20.0  # libVLC's equalizer limit
# libVLC's compressor set up as a limiter: fast attack, high ratio, ceiling just under full scale. It only
# runs while the volume is above 100 %. Instance options: they apply wherever the compressor is in a chain.
LIMITER_ARGS = (
    "--compressor-rms-peak=1",
    "--compressor-attack=1.5",
    "--compressor-release=50",
    "--compressor-threshold=-1.5",
    "--compressor-ratio=20",
    "--compressor-knee=1",
    "--compressor-makeup-gain=0",
)


class _Value(ctypes.Union):
    _fields_ = (("i_int", ctypes.c_int64), ("psz_string", ctypes.c_char_p), ("p_address", ctypes.c_void_p))


class _List(ctypes.Structure):
    _fields_ = (("i_type", ctypes.c_int), ("i_count", ctypes.c_int), ("p_values", ctypes.POINTER(_Value)))


def boost_db(level: int) -> float:
    """Extra gain for a volume above 100 % (200 % = +6 dB, twice the amplitude)."""
    return 20 * math.log10(level / 100) if level > 100 else 0.0


def engine_equalizer(eq: EqualizerSettings, boost: float) -> tuple[float, tuple[float, ...]] | None:
    """libVLC preamp and bands for the person's equalizer plus a volume boost; None = no equalizer needed."""
    if not eq.enabled and boost <= 0:
        return None
    relative = eq.preamp_db if eq.enabled else 0.0
    bands = eq.bands_db if eq.enabled else (0.0,) * len(eq.bands_db)
    preamp = min(MAX_ENGINE_PREAMP_DB, PREAMP_UNITY_DB + relative + boost)
    return preamp, bands


def filter_chain(equalizer: bool, effect: str, limiter: bool) -> str:
    """The audio-filter value, in order: equalizer (and boost), sound effect, limiter last."""
    parts = (["equalizer"] if equalizer else []) + [p for p in effect.split(":") if p]
    if limiter:
        parts.append("compressor")
    return ":".join(parts)


class FilterChain:
    """Sets the audio-filter variable on a libVLC 3 media player and its live audio output."""

    def __init__(self, vlc_dir: Path) -> None:
        core = ctypes.CDLL(str(vlc_dir / "libvlccore.dll"))
        core.var_SetChecked.argtypes = (ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int, _Value)
        core.var_SetChecked.restype = ctypes.c_int
        core.var_Type.argtypes = (ctypes.c_void_p, ctypes.c_char_p)
        core.var_Type.restype = ctypes.c_int
        core.vlc_list_children.argtypes = (ctypes.c_void_p,)
        core.vlc_list_children.restype = ctypes.POINTER(_List)
        core.vlc_list_release.argtypes = (ctypes.POINTER(_List),)
        core.vlc_list_release.restype = None
        self._core = core

    @staticmethod
    def _pointer(player: Any) -> ctypes.c_void_p:
        raw = player._as_parameter_
        return ctypes.c_void_p(raw.value if hasattr(raw, "value") else raw)

    def _set(self, obj: ctypes.c_void_p, chain: str, name: bytes = b"audio-filter") -> bool:
        result: int = self._core.var_SetChecked(obj, name, VLC_VAR_STRING, _Value(psz_string=chain.encode()))
        return result == 0

    def apply(self, player: Any, chain: str) -> None:
        """Set the chain for the next audio output and, if one is playing, for it too."""
        self.set_variable(player, b"audio-filter", chain, on_player=True)  # no output yet is normal

    def set_variable(self, player: Any, name: bytes, value: str, *, on_player: bool = False) -> bool:
        """Set a string variable on the player's live audio output (and on the player itself, so the next
        output starts with it). False if no audio output had the variable to set."""
        pointer = self._pointer(player)
        if on_player and not self._set(pointer, value, name):
            _log.warning("%s could not be set on the player", name.decode())
        children = self._core.vlc_list_children(pointer)
        if not children:
            return False
        done = False
        try:
            for i in range(children.contents.i_count):
                child = ctypes.c_void_p(children.contents.p_values[i].p_address)
                # The audio output is the child with a variable of that name of its own.
                if self._core.var_Type(child, name) & 0xFF == VLC_VAR_STRING:
                    done = self._set(child, value, name) or done
        finally:
            self._core.vlc_list_release(children)  # releases the references the list holds
        return done
