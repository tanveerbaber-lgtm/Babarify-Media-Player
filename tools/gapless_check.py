"""Measure the gap between two songs with the real libVLC engine (M2 evidence for gapless and crossfade).

Two 3-second tones play back to back. Each player's audio goes to a capture callback that records, by the
wall clock, when it first and last delivered sound. Three ways of moving to the second song are compared:

* sequential: one player; when the first song ends, the second is opened (how the app works in 0.10).
* preloaded: a second player has the next song open and paused at its start; it is started as the first ends.
* crossfade: the second player starts before the first ends and the volumes cross (overlap expected).

The gap is (first sound of song 2) - (last sound of song 1); negative means overlap. Each method runs several
times. Timing is measured at the capture callback, which runs ahead of the sound card by the output buffer
(the same for both songs, so it cancels out of the gap).

Usage:  python tools/gapless_check.py <out_dir> [runs]
"""

from __future__ import annotations

import ctypes
import json
import math
import statistics
import struct
import sys
import threading
import time
import wave
from pathlib import Path
from typing import Any

sys.path.insert(0, "src")
from babarify_frame.playback.adapters.libvlc import _load_vlc

vlc = _load_vlc()
RATE, CHANNELS = 48000, 2


def tone(path: Path, hz: int, seconds: float = 3.0) -> None:
    frames = b"".join(
        struct.pack("<hh", v, v)
        for v in (
            round(0.5 * 32767 * math.sin(2 * math.pi * hz * n / RATE)) for n in range(int(RATE * seconds))
        )
    )
    with wave.open(str(path), "wb") as w:
        w.setnchannels(CHANNELS)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(frames)


class Tap:
    """First and last wall-clock time a player delivered non-silent audio."""

    def __init__(self, player: Any) -> None:
        self.first: float | None = None
        self.last: float | None = None

        @vlc.CallbackDecorators.AudioPlayCb
        def play(_opaque: Any, samples: int, count: int, _pts: int) -> None:
            data = ctypes.cast(samples, ctypes.POINTER(ctypes.c_int16 * (count * CHANNELS))).contents
            if any(abs(v) > 300 for v in data):
                now = time.perf_counter()
                self.first = self.first if self.first is not None else now
                self.last = now + count / RATE  # the end of this block

        self._cb = play
        player.audio_set_callbacks(play, None, None, None, None, None)
        player.audio_set_format("S16N", RATE, CHANNELS)


def wait_end(player: Any, timeout: float = 10) -> None:
    deadline = time.perf_counter() + timeout
    while player.get_state() not in (vlc.State.Ended, vlc.State.Error) and time.perf_counter() < deadline:
        time.sleep(0.002)


def sequential(instance: Any, a: Path, b: Path) -> float:
    player = instance.media_player_new()
    tap_a = Tap(player)
    player.set_media(instance.media_new_path(str(a)))
    player.play()
    wait_end(player)
    first_last = tap_a.last
    tap_b = Tap(player)  # same player: new callbacks record song 2
    player.set_media(instance.media_new_path(str(b)))
    player.play()
    time.sleep(1.0)
    player.stop()
    player.release()
    return (tap_b.first or 0) - (first_last or 0)


def preloaded(instance: Any, a: Path, b: Path) -> float:
    one, two = instance.media_player_new(), instance.media_player_new()
    tap_a, tap_b = Tap(one), Tap(two)
    two.set_media(instance.media_new_path(str(b)))
    two.audio_set_volume(0)
    two.play()
    time.sleep(0.3)
    two.set_pause(1)
    two.set_time(0)
    time.sleep(0.2)
    tap_b.first = tap_b.last = None  # forget the silent preroll
    two.audio_set_volume(100)
    one.set_media(instance.media_new_path(str(a)))
    one.play()
    # Start the second player just before the first runs out, by its reported time.
    started = threading.Event()
    deadline = time.perf_counter() + 10
    while not started.is_set() and time.perf_counter() < deadline:
        length, now = one.get_length(), one.get_time()
        if (length > 0 and now >= length - 60) or one.get_state() == vlc.State.Ended:
            two.set_pause(0)
            started.set()
        time.sleep(0.002)
    wait_end(one)
    time.sleep(1.0)
    gap = (tap_b.first or 0) - (tap_a.last or 0)
    for p in (one, two):
        p.stop()
        p.release()
    return gap


def crossfade(instance: Any, a: Path, b: Path, fade_s: float = 1.0) -> float:
    one, two = instance.media_player_new(), instance.media_player_new()
    tap_a, tap_b = Tap(one), Tap(two)
    one.set_media(instance.media_new_path(str(a)))
    one.play()
    deadline = time.perf_counter() + 10
    while not (one.get_length() > 0 and one.get_time() >= one.get_length() - fade_s * 1000):
        if one.get_state() in (vlc.State.Ended, vlc.State.Error) or time.perf_counter() > deadline:
            break
        time.sleep(0.005)
    two.set_media(instance.media_new_path(str(b)))
    two.audio_set_volume(0)
    two.play()
    start = time.perf_counter()
    while (t := time.perf_counter() - start) < fade_s:
        share = min(1.0, t / fade_s)
        one.audio_set_volume(round(100 * (1 - share)))
        two.audio_set_volume(round(100 * share))
        time.sleep(0.02)
    two.audio_set_volume(100)
    wait_end(one)
    time.sleep(0.5)
    gap = (tap_b.first or 0) - (tap_a.last or 0)
    for p in (one, two):
        p.stop()
        p.release()
    return gap


def main() -> None:
    out = Path(sys.argv[1])
    runs = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    out.mkdir(parents=True, exist_ok=True)
    a, b = out / "song-a.wav", out / "song-b.wav"
    tone(a, 440)
    tone(b, 660)
    instance = vlc.Instance(["--no-video", "--no-lua", "--quiet"])
    results = {}
    for name, method in (("sequential (0.10)", sequential), ("preloaded second player", preloaded),
                         ("crossfade, 1 s", crossfade)):  # fmt: skip
        gaps = []
        for run in range(runs):
            print(f"{name}: run {run + 1}", file=sys.stderr, flush=True)
            gaps.append(round(1000 * method(instance, a, b)))
        results[name] = {"gap_ms": gaps, "median_ms": statistics.median(gaps), "worst_ms": max(gaps)}
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
