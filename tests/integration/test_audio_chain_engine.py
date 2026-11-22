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
    path = tmp_path_factory.mktemp("audio") / "loud.wav"
    amplitude = 0.89 * 32767  # -1 dBFS
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
        options: EngineOptions | None = None, equalizer: EqualizerSettings | None = None
    ) -> tuple[Any, Capture]:
        engine = default_factory().create("libvlc", options)
        engines.append(engine)
        capture = Capture()
        capture.install(engine._player, engine._vlc)
        if equalizer is not None:
            engine.set_equalizer(equalizer)
        engine.open_media(str(loud))
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
