"""Measure clipping at boosted volume with the real libVLC engine (M2 evidence).

Plays a loud test tone (a -1 dBFS sine) and captures the 16-bit samples libVLC hands to the audio output
(amem callbacks; libVLC then applies its software volume, as it does for real output above 100 %). For
each case it reports the peak level (1.0 = full scale) and the share of samples stuck at full scale, which
is audible clipping.

Usage:  python tools/clipping_check.py <loud.wav>
"""

from __future__ import annotations

import ctypes
import json
import sys
import time
from typing import Any

sys.path.insert(0, "src")
from babarify_frame.playback.adapters.libvlc import _load_vlc

vlc = _load_vlc()
RATE, CHANNELS = 48000, 2

# libVLC's compressor set up as a limiter: fast attack, high ratio, ceiling just under full scale.
LIMITER = ("--compressor-rms-peak=1", "--compressor-attack=1.5", "--compressor-release=50",
           "--compressor-threshold=-1.5", "--compressor-ratio=20", "--compressor-knee=1",
           "--compressor-makeup-gain=0")  # fmt: skip


def run(
    src: str,
    volume: int,
    args: tuple[str, ...] = (),
    filters: str = "",
    preamp: float | None = None,
    seconds: float = 3.0,
) -> dict[str, Any]:
    instance = vlc.Instance(["--no-video", "--no-lua", "--quiet", *args])
    player = instance.media_player_new()
    peaks: list[float] = []
    counts = [0, 0]  # samples at full scale, samples seen

    @vlc.CallbackDecorators.AudioPlayCb
    def play(_opaque: Any, samples: int, count: int, _pts: int) -> None:
        data = ctypes.cast(samples, ctypes.POINTER(ctypes.c_int16 * (count * CHANNELS))).contents
        values = [abs(v) for v in data]
        peaks.append((max(values) if values else 0) / 32767)
        counts[0] += sum(1 for v in values if v >= 32767)
        counts[1] += len(values)

    player.audio_set_callbacks(play, None, None, None, None, None)
    player.audio_set_format("S16N", RATE, CHANNELS)
    media = instance.media_new_path(src)
    if filters:
        media.add_option(f":audio-filter={filters}")
    player.set_media(media)
    if preamp is not None:
        eq = vlc.AudioEqualizer()
        eq.set_preamp(preamp)
        for band in range(vlc.libvlc_audio_equalizer_get_band_count()):
            eq.set_amp_at_index(0.0, band)
        player.set_equalizer(eq)
    player.play()
    time.sleep(0.4)
    player.audio_set_volume(volume)
    time.sleep(seconds)
    player.stop()
    player.release()
    instance.release()
    steady = peaks[len(peaks) // 3 :] or peaks
    return {"peak": round(max(steady), 3), "clipped_percent": round(100 * counts[0] / max(1, counts[1]), 2)}


def main() -> None:
    src = sys.argv[1]
    cases = {
        "volume 100": dict(volume=100),
        "volume 126 (0.10 boost, x2 gain)": dict(volume=126),
        "volume 200 (0.10 boost, x8 gain)": dict(volume=200),
        "volume 200 + limiter in filter chain": dict(volume=200, args=LIMITER, filters="compressor"),
        "volume 100, flat equalizer, preamp 0": dict(volume=100, preamp=0.0, filters="equalizer"),
        "volume 100, preamp +6 dB": dict(volume=100, preamp=6.0, filters="equalizer"),
        "volume 100, preamp +12 dB": dict(volume=100, preamp=12.0, filters="equalizer"),
        "volume 100, preamp +6 dB, then limiter": dict(volume=100, preamp=6.0, args=LIMITER,
                                                       filters="equalizer:compressor"),
        "volume 100, preamp +12 dB, then limiter": dict(volume=100, preamp=12.0, args=LIMITER,
                                                        filters="equalizer:compressor"),
    }  # fmt: skip
    print(json.dumps({name: run(src, **kw) for name, kw in cases.items()}, indent=2))


if __name__ == "__main__":
    main()
