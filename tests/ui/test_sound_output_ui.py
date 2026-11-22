"""Sound output and volume levelling in Settings (0.12), with the test engine."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from babarify_frame.configuration.preferences import PreferencesStore
from babarify_frame.library.database import LibraryDatabase
from babarify_frame.library.service import LibraryService
from babarify_frame.playback.adapters.mock import MockEngine
from babarify_frame.playback.factory import EngineDescriptor, EngineFactory, EngineProbe
from babarify_frame.ui.app import load_icon
from babarify_frame.ui.main_window import MainWindow
from fakes import FakeProbe


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    factory = EngineFactory()
    factory.register(EngineDescriptor("mock", "Mock", MockEngine, lambda: EngineProbe("mock", True, "1")))
    service = LibraryService(LibraryDatabase(None), FakeProbe, tmp_path / "thumbs")
    win = MainWindow(
        factory,
        load_icon(),
        engine_name="mock",
        store=PreferencesStore(tmp_path / "settings.json"),
        library=service,
    )
    qtbot.addWidget(win)
    win.show()
    win.start_engine()
    qtbot.waitUntil(lambda: win.player.engine_is_ready, timeout=5000)
    yield win
    win.close()


def engine(window: MainWindow) -> MockEngine:
    found = window.player._controller.engine
    assert isinstance(found, MockEngine)
    return found


def test_settings_lists_the_connected_outputs(window: MainWindow) -> None:
    combo = window.settings.audio_device
    assert [combo.itemText(i) for i in range(combo.count())] == ["Windows default", "Mock speakers"]
    assert combo.currentData() == ""


def test_choosing_an_output_restarts_the_engine_with_it(
    window: MainWindow, qtbot: QtBot, tmp_path: Path
) -> None:
    combo = window.settings.audio_device
    combo.setCurrentIndex(combo.findData("mock-speakers"))
    qtbot.waitUntil(
        lambda: window.player.engine_is_ready and engine(window).options.audio_device == "mock-speakers"
    )
    assert PreferencesStore(tmp_path / "settings.json").load().audio_device == "mock-speakers"


def test_an_unplugged_output_stays_chosen_and_comes_back(window: MainWindow, qtbot: QtBot) -> None:
    combo = window.settings.audio_device
    combo.setCurrentIndex(combo.findData("mock-speakers"))
    qtbot.waitUntil(
        lambda: window.player.engine_is_ready and engine(window).options.audio_device == "mock-speakers"
    )
    engine(window).devices = ()  # unplugged
    window.show_page(window.settings)  # the page reads the devices again when shown
    assert combo.currentText() == "Chosen device (not connected)"
    assert window.settings.preferences.audio_device == "mock-speakers"  # not lost
    engine(window).devices = (("mock-speakers", "Mock speakers"),)  # plugged in again
    window.show_page(window.settings)
    assert combo.currentText() == "Mock speakers"


def test_volume_levelling_reaches_the_engine(window: MainWindow, qtbot: QtBot) -> None:
    combo = window.settings.volume_levelling
    assert [combo.itemText(i) for i in range(combo.count())] == ["Off", "By song", "By album"]
    combo.setCurrentIndex(combo.findData("album"))
    qtbot.waitUntil(
        lambda: window.player.engine_is_ready and engine(window).options.volume_levelling == "album"
    )


def test_bad_saved_values_fall_back(tmp_path: Path) -> None:
    import json

    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"volume_levelling": "loud", "audio_device": "x" * 600}), encoding="utf-8")
    prefs = PreferencesStore(path).load()
    assert (prefs.volume_levelling, prefs.audio_device) == ("off", "")


def test_a_file_from_another_start_plays_here(window: MainWindow, qtbot: QtBot, tmp_path: Path) -> None:
    """One running copy (0.12): the window comes back from the mini player and plays the file."""
    song = tmp_path / "song.mp3"
    song.write_bytes(b"x")
    window.enter_mini_player()
    window.open_from_another_start(str(song))
    assert window.isVisible() and not window.mini.isVisible()
    assert window._pages.currentWidget() is window.player
    qtbot.waitUntil(lambda: window.player.current_uri == str(song), timeout=3000)
