"""The audio filter chain with the real libVLC engine (M2): no clipping above 100 %, effects that load,
and an equalizer that keeps the normal level.

The engine's audio goes to a capture callback instead of the sound card; libVLC still applies its
software volume, as it does for real output. The test signal is a -1 dB sine, as loud as most music peaks.
"""

from __future__ import annotations

import ctypes
import math
import struct
import time
import wave
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from babarify_frame.core.enhancements import EqualizerSettings
from babarify_frame.core.models import EngineOptions
from babarify_frame.core.models import PlaybackState as S
from babarify_frame.playback.factory import default_factory

RATE, CHANNELS = 48000, 2
probe = default_factory().probe("libvlc")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not probe.available, reason=f"libvlc unavailable: {probe.detail}"),
]


class Capture:
    """Peak level and clipped share of what libVLC hands to the audio output, per phase."""

    def __init__(self) -> None:
        self.phase = "start"
        self.stats: dict[str, list[float]] = {}

    def install(self, player: Any, vlc: Any) -> None:
        @vlc.CallbackDecorators.AudioPlayCb  # type: ignore[untyped-decorator]
        def play(_opaque: Any, samples: int, count: int, _pts: int) -> None:
            data = ctypes.cast(samples, ctypes.POINTER(ctypes.c_int16 * (count * CHANNELS))).contents
            values = [abs(v) for v in data]
            stat = self.stats.setdefault(self.phase, [0.0, 0, 0])
            stat[0] = max(stat[0], (max(values) if values else 0) / 32767)
            stat[1] += sum(1 for v in values if v >= 32767)
            stat[2] += len(values)

        self._callback = play  # keep a reference: libVLC holds a raw pointer
        player.audio_set_callbacks(play, None, None, None, None, None)
        player.audio_set_format("S16N", RATE, CHANNELS)

    def mark(self, phase: str, settle_s: float = 0.6, measure_s: float = 1.5) -> None:
        self.phase = "settling"
        time.sleep(settle_s)
        self.phase = phase
        time.sleep(measure_s)

    def peak(self, phase: str) -> float:
        return self.stats[phase][0]

    def clipped_percent(self, phase: str) -> float:
        stat = self.stats[phase]
        return 100 * stat[1] / max(1, stat[2])


@pytest.fixture(scope="module")
def loud(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tone(tmp_path_factory.mktemp("audio") / "loud.wav", 0.89)  # -1 dBFS


@pytest.fixture(scope="module")
def quiet(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tone(tmp_path_factory.mktemp("audio") / "quiet.wav", 0.1)  # -20 dBFS: under the limiter at 200 %


def tone(path: Path, level: float) -> Path:
    amplitude = level * 32767
    frames = b"".join(
        struct.pack("<hh", s, s)
        for s in (round(amplitude * math.sin(2 * math.pi * 440 * n / RATE)) for n in range(RATE * 8))
    )
    with wave.open(str(path), "wb") as w:
        w.setnchannels(CHANNELS)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(frames)
    return path


@pytest.fixture
def run(loud: Path) -> Iterator[Any]:
    engines: list[Any] = []

    def start(
        options: EngineOptions | None = None,
        equalizer: EqualizerSettings | None = None,
        media: Path | None = None,
    ) -> tuple[Any, Capture]:
        engine = default_factory().create("libvlc", options)
        engines.append(engine)
        capture = Capture()
        capture.install(engine._player, engine._vlc)
        if equalizer is not None:
            engine.set_equalizer(equalizer)
        engine.open_media(str(media or loud))
        deadline = time.monotonic() + 10
        while engine.get_playback_state().state is not S.PLAYING and time.monotonic() < deadline:
            time.sleep(0.05)
        return engine, capture

    yield start
    for engine in engines:
        engine.close()


def test_volume_above_100_does_not_clip(run: Any) -> None:
    engine, capture = run()
    engine.set_volume(100)
    capture.mark("100")
    engine.set_volume(200)  # 0.10 clipped 60 % of these samples
    capture.mark("200")
    assert capture.clipped_percent("100") == 0 and capture.peak("100") == pytest.approx(0.89, abs=0.02)
    assert capture.clipped_percent("200") < 0.1
    assert capture.peak("200") > capture.peak("100") * 0.9  # still as loud as it can be without clipping


def test_volume_boost_then_equalizer_change_keeps_the_limiter(run: Any) -> None:
    engine, capture = run()
    engine.set_volume(200)
    engine.set_equalizer(
        EqualizerSettings(enabled=True, preamp_db=0.0)
    )  # a live change resets libVLC's chain
    capture.mark("boosted, equalizer changed")
    assert capture.clipped_percent("boosted, equalizer changed") < 0.1


def test_equalizer_on_at_default_settings_keeps_the_level(run: Any) -> None:
    engine, capture = run(equalizer=EqualizerSettings(enabled=True))
    engine.set_volume(100)
    capture.mark("flat equalizer")
    # 0.10 sent the preamp to libVLC unchanged, so this was 12 dB quieter (peak 0.22).
    assert capture.peak("flat equalizer") == pytest.approx(0.89, abs=0.03)


def test_room_effect_is_applied(run: Any) -> None:
    plain_engine, plain = run()
    plain_engine.set_volume(100)
    plain.mark("plain")
    plain_engine.close()
    engine, capture = run(EngineOptions(audio_effect="room"))
    engine.set_volume(100)
    capture.mark("room")
    # The room effect changes the signal; in 0.10 the effect never loaded and the level was identical.
    assert abs(capture.peak("room") - plain.peak("plain")) > 0.05


# ---------------------------------------------------------------- volume levelling and output (0.12)
def _ffmpeg(tmp: Path, name: str, *args: str) -> Path:
    import shutil
    import subprocess

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        pytest.skip("ffmpeg is needed to make tagged test files")
    path = tmp / name
    subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *args, str(path)], check=True, timeout=120
    )
    return path


def _level(path: Path, levelling: str) -> tuple[float, str]:
    engine = default_factory().create("libvlc", EngineOptions(volume_levelling=levelling))
    try:
        capture = Capture()
        capture.install(engine._player, engine._vlc)
        engine.open_media(str(path))
        deadline = time.monotonic() + 10
        while engine.get_playback_state().state is not S.PLAYING and time.monotonic() < deadline:
            time.sleep(0.05)
        engine.set_volume(100)
        capture.mark("level")
        return capture.peak("level"), engine.levelling_applied
    finally:
        engine.close()


def test_volume_levelling_follows_a_songs_tag_and_leaves_videos_alone(tmp_path: Path) -> None:
    tone = ["-f", "lavfi", "-i", "sine=frequency=440:duration=6,volume=0.5", "-ac", "2", "-ar", "48000"]
    song = _ffmpeg(tmp_path, "tagged.mp3", *tone, "-metadata", "REPLAYGAIN_TRACK_GAIN=-12.00 dB")
    video = _ffmpeg(
        tmp_path, "film.mkv", "-f", "lavfi", "-i", "testsrc=duration=6:size=160x120:rate=25", *tone,
        "-c:v", "libx264", "-c:a", "aac", "-shortest",
    )  # fmt: skip
    song_off, applied_off = _level(song, "off")
    song_on, applied_song = _level(song, "track")
    video_off, _ = _level(video, "off")
    video_on, applied_video = _level(video, "track")
    assert (applied_off, applied_song, applied_video) == ("none", "track", "none")
    assert song_on == pytest.approx(song_off / 4, rel=0.25)  # -12 dB, as its tag says
    assert video_on == pytest.approx(video_off, rel=0.15)  # never turned down (-7 dB would be -55 %)


def test_the_chosen_output_device_is_used_while_connected() -> None:
    engine = default_factory().create("libvlc", EngineOptions())
    try:
        devices = engine.audio_devices()
    finally:
        engine.close()
    if not devices:
        pytest.skip("no sound outputs on this PC")
    chosen = devices[-1][0]
    engine = default_factory().create("libvlc", EngineOptions(audio_device=chosen))
    try:
        assert engine._player.audio_output_device_get() == chosen
    finally:
        engine.close()
    missing = default_factory().create("libvlc", EngineOptions(audio_device="{not-connected}"))
    try:  # an unplugged device is never asked for: Windows' default plays instead
        assert missing._player.audio_output_device_get() != "{not-connected}"
    finally:
        missing.close()


def test_dragging_the_volume_through_boost_rebuilds_the_sound_chain_once(run: Any) -> None:
    """0.12: each boost change rebuilt libVLC's audio filters, and on real speakers each rebuild restarts the
    sound for a moment, so dragging above 100 % made it stutter. The equalizer and limiter are now added once,
    on the first step past 100 %, and kept: up, down and back up again, nothing more is rebuilt.
    (A capture can't hear that restart, so the rebuilds themselves are counted.)"""
    engine, capture = run()
    engine.set_volume(100)
    capture.mark("steady")
    rebuilds: list[int] = []
    original = engine._apply_equalizer
    engine._apply_equalizer = lambda: (rebuilds.append(engine._level), original())[1]
    for level in [*range(101, 201, 2), *range(199, 79, -4), *range(84, 200, 3)]:  # up, down past 100, up
        engine.set_volume(level)
        time.sleep(0.02)
    engine.set_volume(199)
    time.sleep(0.6)
    assert rebuilds == [101], f"{len(rebuilds)} rebuilds while dragging"  # once, on the first step past 100
    capture.mark("boosted")
    assert capture.clipped_percent("boosted") < 0.1  # the limiter is in place once the boost settles
    assert capture.peak("boosted") > 0.8  # and the sound is as loud as it can be without clipping


def test_changing_a_boost_that_is_on_follows_live_without_a_rebuild(run: Any, quiet: Path) -> None:
    """0.12: from 100 % to 200 % the sound still caught at every rest of the slider, as each boost change
    rebuilt the filters. Once boost is on, the equalizer now takes the new boost as it plays."""
    engine, capture = run(media=quiet)
    engine.set_volume(120)
    capture.mark("on")  # turning boost on adds the equalizer and limiter: one rebuild, as before
    capture.phase = "dragging"
    rebuilds: list[int] = []
    original = engine._apply_equalizer
    engine._apply_equalizer = lambda: (rebuilds.append(engine._level), original())[1]
    for step in range(41):  # about one second of dragging from 120 % to 200 %, with rests
        engine.set_volume(120 + step * 2)
        time.sleep(0.02 if step % 10 else 0.4)
    capture.mark("louder")
    assert rebuilds == [], f"{len(rebuilds)} rebuilds while the boost stayed on"
    ratio = capture.peak("louder") / capture.peak("on")
    assert 1.5 < ratio < 1.8, ratio  # 200 % against 120 %: 1.67 times as loud, live
