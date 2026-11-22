"""M3: one search across music and videos, playlists reordered by dragging, mini-player and always on top."""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from babarify_frame.configuration.preferences import PreferencesStore
from babarify_frame.core.models import PlaybackState as S
from babarify_frame.library.database import LibraryDatabase, ProbeRecord, ScanRecord
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
    win.resize(1200, 800)
    win.show()
    win.start_engine()
    qtbot.waitUntil(lambda: win.player.engine_is_ready, timeout=5000)
    yield win
    win.close()


def add(window: MainWindow, path: Path, title: str | None = None, artist: str | None = None) -> str:
    db = window.library_service.db
    folder = next((f.id for f in db.folders()), None) or db.add_folder(str(path.parent)).id
    path.write_bytes(b"\x00")
    db.upsert_media([ScanRecord(str(path), folder, 1, 1.0, None)], time.time())
    entry = db.media_by_path(str(path))
    assert entry is not None
    video = "h264" if path.suffix == ".mkv" else None
    db.set_probe_result(entry.id, ProbeRecord(60_000, None, None, video, "aac", None, title, artist))
    return str(path)


def test_home_searches_music_and_videos(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    song = add(window, tmp_path / "a.mp3", "Blue Train", "Coltrane")
    add(window, tmp_path / "Blue Planet.mkv")
    window.show_page(window.home)
    home = window.home
    assert not home.search_results.isVisible()
    home.search.setText("blue")
    qtbot.waitUntil(lambda: home.search_results.count() == 2, timeout=2000)
    texts = [home.search_results.item(i).text() for i in range(2)]
    assert texts[0].startswith("Blue Planet") and "Video" in texts[0]
    assert texts[1].startswith("Blue Train") and "Song · Coltrane" in texts[1]
    home.search.setText("nothing like this")
    qtbot.waitUntil(lambda: home.search_none.isVisible(), timeout=2000)
    home.search.setText("coltrane")
    qtbot.waitUntil(lambda: home.search_results.count() == 1, timeout=2000)
    home.search_results.itemActivated.emit(home.search_results.item(0))
    qtbot.waitUntil(lambda: window.player.state is S.PLAYING, timeout=3000)
    assert window.player.current_uri is not None and Path(window.player.current_uri) == Path(song)


def test_a_playlist_is_put_in_order_by_dragging(window: MainWindow) -> None:
    from PySide6.QtCore import QModelIndex

    db = window.library_service.db
    mix = db.create_playlist("Mix")
    db.add_to_playlist(mix.id, ["C:/a.mp3", "C:/b.mp3", "C:/c.mp3"])
    window.show_library("playlists")
    panel = window.library.playlists
    panel.refresh()
    panel.playlists.setCurrentRow(0)
    items = panel.items
    assert items.dragEnabled()
    assert items.model().moveRow(QModelIndex(), 0, QModelIndex(), 3)  # as a drop: the first song goes last
    assert [i.path for i in db.playlist_items(mix.id)] == ["C:/b.mp3", "C:/c.mp3", "C:/a.mp3"]
    panel.automatic.setCurrentRow(0)  # Favourites fills itself in: no dragging
    assert not items.dragEnabled()


def test_the_mini_player_takes_over_and_gives_back_the_window(
    qtbot: QtBot, window: MainWindow, tmp_path: Path
) -> None:
    song = add(window, tmp_path / "a.mp3", "Blue Train")
    window.open_path(song)
    qtbot.waitUntil(lambda: window.player.state is S.PLAYING, timeout=3000)
    window.mini_action.trigger()
    mini = window.mini
    assert mini.isVisible() and not window.isVisible()
    assert mini.title.text() == "a.mp3" or "Blue Train" in mini.title.text()
    mini.play_button.click()
    qtbot.waitUntil(lambda: window.player.state is S.PAUSED, timeout=3000)
    mini.close()  # closing the mini-player returns to the main window and never stops playback
    assert window.isVisible() and not mini.isVisible()
    assert window.player.state is S.PAUSED and window.player.has_media


def test_always_on_top_is_remembered(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    window.on_top_action.setChecked(True)
    assert PreferencesStore(tmp_path / "settings.json").load().always_on_top
    window.on_top_action.setChecked(False)
    assert not PreferencesStore(tmp_path / "settings.json").load().always_on_top


@pytest.mark.skipif(
    __import__("sys").platform != "win32" or __import__("os").environ.get("QT_QPA_PLATFORM") == "offscreen",
    reason="needs a real Windows desktop",
)
def test_always_on_top_reaches_windows_without_rebuilding_the_window(window: MainWindow) -> None:
    import ctypes

    from babarify_frame.ui.widgets import set_topmost

    hwnd = int(window.winId())  # libVLC draws video into windows under this one: it must not change
    topmost = lambda: bool(ctypes.windll.user32.GetWindowLongW(hwnd, -20) & 0x8)  # noqa: E731  WS_EX_TOPMOST
    if ctypes.windll.user32.GetForegroundWindow() != hwnd:
        # Windows ignores "on top" from a window that isn't in front, and won't bring a test's window in front
        # of what someone is using; the app asks again when its window becomes active (test below).
        pytest.skip("another window is in front on this desktop")
    set_topmost(window, True)
    assert topmost() and int(window.winId()) == hwnd
    set_topmost(window, False)
    assert not topmost()


def test_on_top_is_asked_again_when_a_window_becomes_active(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PySide6.QtCore import QEvent

    import babarify_frame.ui.main_window as main_window_module

    calls: list[tuple[object, bool]] = []
    monkeypatch.setattr(main_window_module, "set_topmost", lambda w, on: calls.append((w, on)))
    for target in (window, window.mini):
        monkeypatch.setattr(target, "isActiveWindow", lambda: True)
    window.changeEvent(QEvent(QEvent.Type.ActivationChange))
    assert calls == []  # off: nothing is asked
    window.on_top_action.setChecked(True)
    calls.clear()
    window.changeEvent(QEvent(QEvent.Type.ActivationChange))
    window.mini.changeEvent(QEvent(QEvent.Type.ActivationChange))
    assert calls == [(window, True), (window.mini, True)]
