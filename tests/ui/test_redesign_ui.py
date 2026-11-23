"""The 0.12 redesign: player bar, Now Playing panel, Home's banner and the top search (test engine)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget
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


def native_rect(widget: QWidget) -> tuple[int, int, int, int]:
    """Where Windows has the widget's own window, in screen pixels."""
    import ctypes
    from ctypes import wintypes

    rect = wintypes.RECT()
    ctypes.windll.user32.GetWindowRect(int(widget.winId()), ctypes.byref(rect))
    return rect.left, rect.top, rect.right, rect.bottom


def song(tmp_path: Path, name: str = "song.mp3") -> str:
    path = tmp_path / name
    path.write_bytes(b"x")
    return str(path)


def test_the_bar_and_panel_step_aside_on_the_playing_page(window: MainWindow) -> None:
    window.show_page(window.home)
    assert window.player_bar.isVisible() and window.now_panel.isVisible()
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


def test_home_has_its_own_search_again(window: MainWindow) -> None:
    """0.12, the owner's choice: no bar across the top; Home's own search box is back."""
    window.show_page(window.home)
    assert window.home.search.isVisible() and not hasattr(window, "top_bar")


def test_the_window_still_closes_cleanly(window: MainWindow, qtbot: QtBot, tmp_path: Path) -> None:
    """Regression (0.12 redesign): the old Home hero, left without a parent, kept the app from quitting."""
    from PySide6.QtWidgets import QApplication

    window.refresh_home()
    window.close()
    leftovers = [w for w in QApplication.topLevelWidgets() if w.isVisible() and w is not window]
    assert not [w for w in leftovers if type(w).__name__ in ("QLabel", "BrandTitle")]


def test_the_panel_animates_a_song_without_a_picture(
    window: MainWindow, qtbot: QtBot, tmp_path: Path
) -> None:
    window.open_path(song(tmp_path))
    window.show_page(window.home)
    qtbot.waitUntil(lambda: window.player.state is S.PLAYING, timeout=3000)
    qtbot.waitUntil(window.now_panel.visualizer.isVisible, timeout=3000)
    assert not window.now_panel.cover.isVisible()


def test_the_bar_volume_covers_boost_too(window: MainWindow, qtbot: QtBot) -> None:
    window.player.set_volume(150)
    qtbot.waitUntil(lambda: window.player_bar.volume.value() == min(150, window.player.volume_maximum))
    assert window.player_bar.volume.maximum() == window.player.volume_maximum


def test_a_video_plays_on_live_in_the_panel_and_comes_back(
    window: MainWindow, qtbot: QtBot, tmp_path: Path
) -> None:
    """0.12: the panel shows the video itself, not a picture taken once a second, which looked jerky."""
    surface = window.player.video
    native = int(surface.winId())
    window.open_path(song(tmp_path, "film.mp4"))
    qtbot.waitUntil(lambda: window.player.state is S.PLAYING and window.player.has_video, timeout=3000)
    window.show_page(window.home)
    slot = window.now_panel.video_slot
    qtbot.waitUntil(lambda: window.player.video_lent and slot.isVisible(), timeout=3000)
    assert surface.parentWidget() is window.now_panel.video_slot and surface.isVisible()
    assert int(surface.winId()) == native  # the engine goes on drawing into the same window
    assert not window.now_panel.cover.isVisible()
    # On screen, the video's own window sits exactly in its box, even after the cover above made way.
    qtbot.wait(100)
    assert native_rect(surface) == native_rect(slot)
    window.show_page(window.player)
    assert not window.player.video_lent and surface.isVisible()
    window.show_page(window.home)
    qtbot.waitUntil(lambda: window.player.video_lent, timeout=3000)
    qtbot.mouseClick(surface, Qt.MouseButton.LeftButton)  # a click opens the Playing page
    assert window.current_page() is window.player and not window.player.video_lent
    window.show_page(window.home)
    qtbot.waitUntil(lambda: window.player.video_lent, timeout=3000)
    window.now_panel_action.setChecked(False)
    assert not window.player.video_lent and int(surface.winId()) == native


def test_settings_buttons_are_never_squeezed(window: MainWindow, qtbot: QtBot) -> None:
    """0.12: Privacy's buttons were squeezed shorter than their text, which was cut off top and bottom."""
    from PySide6.QtWidgets import QPushButton

    window.show_page(window.settings)
    qtbot.wait(200)
    squeezed = [
        b.text()
        for b in window.settings.findChildren(QPushButton)
        if b.isVisible() and b.height() < b.sizeHint().height()
    ]
    assert not squeezed


def test_a_long_file_name_wraps_inside_the_panel(window: MainWindow) -> None:
    """0.12: a name with no spaces pushed the panel's contents wider: cut off, and the video past its box."""
    from babarify_frame.ui.now_playing import VIDEO_SIZE, breakable

    name = "Red_Dawn_(2012)_Hindi_Dubbed_Full_Movie_HD.mkv"
    window.now_panel.title.setText(breakable(name))
    window.now_panel.adjustSize()
    assert breakable(name).replace("​", "") == name
    title = window.now_panel.title
    assert title.width() == VIDEO_SIZE[0] and title.heightForWidth(VIDEO_SIZE[0]) > 0
    assert window.now_panel.minimumSizeHint().width() <= window.now_panel.width()


def test_the_panel_contents_stay_inside_its_card(window: MainWindow, qtbot: QtBot, tmp_path: Path) -> None:
    """0.12: the card has an outer margin, and the video and title, sized without it, ran past its edge."""
    window.open_path(song(tmp_path, "film.mp4"))
    qtbot.waitUntil(lambda: window.player.state is S.PLAYING and window.player.has_video, timeout=3000)
    window.show_page(window.home)
    panel = window.now_panel
    qtbot.waitUntil(lambda: panel.video_slot.isVisible(), timeout=3000)
    inside = panel.contentsRect()
    for part in (panel.video_slot, panel.title, panel.seek):
        assert inside.contains(part.geometry()), part
