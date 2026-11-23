"""The 0.12 redesign: player bar, Now Playing panel, Home's banner and the top search (test engine)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from babarify_frame.configuration.preferences import PreferencesStore
from babarify_frame.core.models import PlaybackState as S
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
    win = MainWindow(
        factory, load_icon(), engine_name="mock", store=PreferencesStore(tmp_path / "settings.json"),
        library=LibraryService(LibraryDatabase(None), FakeProbe, tmp_path / "thumbs"),
    )  # fmt: skip
    qtbot.addWidget(win)
    win.resize(1440, 900)
    win.show()
    win.start_engine()
    qtbot.waitUntil(lambda: win.player.engine_is_ready, timeout=5000)
    yield win
    win.close()


def song(tmp_path: Path, name: str = "song.mp3") -> str:
    path = tmp_path / name
    path.write_bytes(b"x")
    return str(path)


def test_the_bar_and_panel_step_aside_on_the_playing_page(window: MainWindow) -> None:
    window.show_page(window.home)
    assert window.player_bar.isVisible() and window.now_panel.isVisible() and window.top_bar.isVisible()
    window.show_page(window.player)
    assert not window.player_bar.isVisible() and not window.now_panel.isVisible()
    window.show_page(window.settings)
    assert window.player_bar.isVisible()


def test_the_panel_can_be_hidden_and_stays_hidden(window: MainWindow, tmp_path: Path) -> None:
    window.now_panel_action.setChecked(False)
    assert not window.now_panel.isVisible()
    assert not PreferencesStore(tmp_path / "settings.json").load().show_now_panel
    window.now_panel_action.setChecked(True)
    assert window.now_panel.isVisible()


def test_a_narrow_window_gives_the_panels_room_to_the_page(window: MainWindow, qtbot: QtBot) -> None:
    window.resize(1000, 700)
    qtbot.waitUntil(lambda: not window.now_panel.isVisible())
    assert window.player_bar.isVisible()


def test_the_bar_follows_and_controls_the_player(window: MainWindow, qtbot: QtBot, tmp_path: Path) -> None:
    assert (
        window.player_bar.title.text() == "Nothing is playing"
        and not window.player_bar.play_button.isEnabled()
    )
    window.open_path(song(tmp_path))
    window.show_page(window.home)
    qtbot.waitUntil(lambda: window.player.state is S.PLAYING, timeout=3000)
    qtbot.waitUntil(lambda: window.player_bar.play_button.accessibleName() == "Pause", timeout=3000)
    assert window.player_bar.title.text() and window.now_panel.title.text() == window.player_bar.title.text()
    window.player_bar.play_button.click()
    qtbot.waitUntil(lambda: window.player.state is S.PAUSED, timeout=3000)
    window.now_panel.play_button.click()
    qtbot.waitUntil(lambda: window.player.state is S.PLAYING, timeout=3000)
    window.player_bar.cover.click()
    assert window.current_page() is window.player


def test_play_now_carries_on_with_the_last_file(window: MainWindow, qtbot: QtBot, tmp_path: Path) -> None:
    path = song(tmp_path)
    window.open_path(path)
    qtbot.waitUntil(lambda: window.player.state is S.PLAYING, timeout=3000)
    window.player.stop()
    window.show_page(window.home)
    window.home.play_now_button.click()
    qtbot.waitUntil(lambda: window.player.current_uri == path, timeout=3000)
    assert window.current_page() is window.player


def test_the_top_search_shows_its_results_on_home(window: MainWindow, qtbot: QtBot) -> None:
    window.show_page(window.settings)
    window.top_search.setText("anything")
    assert window.current_page() is window.home and window.home.search.text() == "anything"


def test_the_window_still_closes_cleanly(window: MainWindow, qtbot: QtBot, tmp_path: Path) -> None:
    """Regression (0.12 redesign): the old Home hero, left without a parent, kept the app from quitting."""
    from PySide6.QtWidgets import QApplication

    window.refresh_home()
    window.close()
    leftovers = [w for w in QApplication.topLevelWidgets() if w.isVisible() and w is not window]
    assert not [w for w in leftovers if type(w).__name__ in ("QLabel", "BrandTitle")]
