"""Network streams in the window (0.12): off until switched on, then File → Open network stream (Ctrl+N)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QMessageBox
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


def test_streams_are_off_by_default(window: MainWindow, tmp_path: Path) -> None:
    assert not window.settings.network_streams.isChecked()
    assert not engine(window).options.network_streams
    assert not PreferencesStore(tmp_path / "settings.json").load().network_streams


def test_ctrl_n_while_off_asks_first_and_does_nothing_on_no(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[str] = []

    def answer(*args: object) -> QMessageBox.StandardButton:
        asked.append(str(args[1]))
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", answer)
    assert window.choose_stream() is None
    assert asked == ["Network streams are off"] and not window.settings.network_streams.isChecked()


def test_ctrl_n_switched_on_opens_a_stream(
    window: MainWindow, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(QMessageBox, "question", lambda *_a: QMessageBox.StandardButton.Yes)
    dialog = window.choose_stream()
    assert dialog is not None and window.settings.network_streams.isChecked()
    qtbot.waitUntil(lambda: window.player.engine_is_ready and engine(window).options.network_streams)
    dialog.address.setText("https://example.com/live/stream.m3u8")
    dialog.accept()
    qtbot.waitUntil(lambda: window.player.current_uri == "https://example.com/live/stream.m3u8", timeout=3000)


def drop(window: MainWindow, url: str) -> None:
    data = QMimeData()
    data.setUrls([QUrl(url)])
    event = QDropEvent(QPointF(10, 10), Qt.DropAction.CopyAction, data, Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier)  # fmt: skip
    window.dropEvent(event)


def test_a_dropped_link_plays_only_when_switched_on(window: MainWindow, qtbot: QtBot) -> None:
    drop(window, "https://example.com/radio.mp3")
    assert window.player.current_uri is None  # off: ignored
    window.settings.network_streams.setChecked(True)
    qtbot.waitUntil(lambda: window.player.engine_is_ready and engine(window).options.network_streams)
    drop(window, "https://example.com/radio.mp3")
    qtbot.waitUntil(lambda: window.player.current_uri == "https://example.com/radio.mp3", timeout=3000)


def test_recent_streams_never_join_the_library_lists(window: MainWindow) -> None:
    db = window.library_service.db
    db.record_play("https://example.com/live.m3u8", "Live", None)
    db.record_play("C:/film.mkv", "Film", 60_000)
    assert db.recent_streams() == ["https://example.com/live.m3u8"]
    assert [e.path for e in db.recent(10)] == ["C:/film.mkv"]


def playing_stream(window: MainWindow, qtbot: QtBot, url: str = "https://example.com/live.m3u8") -> None:
    window.settings.network_streams.setChecked(True)
    qtbot.waitUntil(lambda: window.player.engine_is_ready and engine(window).options.network_streams)
    window.open_path(url)
    qtbot.waitUntil(lambda: window.player.state.value == "playing", timeout=3000)


def test_a_dropped_live_stream_reconnects(
    window: MainWindow, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    import babarify_frame.ui.pages.player as player_module
    from babarify_frame.core.errors import ErrorCode

    monkeypatch.setattr(player_module, "RECONNECT_DELAYS_S", (0, 0))
    playing_stream(window, qtbot)
    statuses: list[str] = []
    window.player.status_changed.connect(statuses.append)
    engine(window).simulate_error(ErrorCode.NETWORK_ERROR, "connection reset")
    qtbot.waitUntil(lambda: any(s.startswith("Connection lost") for s in statuses), timeout=3000)
    qtbot.waitUntil(lambda: "Reconnected" in statuses, timeout=3000)
    assert window.player.current_uri == "https://example.com/live.m3u8"


def test_reconnecting_gives_up_after_its_tries(
    window: MainWindow, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    import babarify_frame.ui.pages.player as player_module
    from babarify_frame.core.errors import ErrorCode

    monkeypatch.setattr(player_module, "RECONNECT_DELAYS_S", (0, 0))
    playing_stream(window, qtbot)
    engine(window).auto_complete_loading = False  # the server is gone: opening never succeeds
    for _ in range(3):
        engine(window).simulate_error(ErrorCode.NETWORK_ERROR, "gone")
        qtbot.wait(100)
    qtbot.waitUntil(lambda: not window.player.reconnecting, timeout=3000)
    assert window.player.state.value == "error"


def test_stop_cancels_reconnecting(window: MainWindow, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    import babarify_frame.ui.pages.player as player_module
    from babarify_frame.core.errors import ErrorCode

    monkeypatch.setattr(player_module, "RECONNECT_DELAYS_S", (5,))
    playing_stream(window, qtbot)
    engine(window).simulate_error(ErrorCode.NETWORK_ERROR, "connection reset")
    qtbot.waitUntil(lambda: window.player.reconnecting, timeout=3000)
    window.player.stop()
    assert not window.player.reconnecting


def test_a_stream_that_never_played_is_not_retried(window: MainWindow, qtbot: QtBot) -> None:
    window.settings.network_streams.setChecked(True)
    qtbot.waitUntil(lambda: window.player.engine_is_ready and engine(window).options.network_streams)
    window.open_path("https://fail.invalid/live.m3u8")  # the test engine can't reach this server
    qtbot.waitUntil(lambda: window.player.state.value == "error", timeout=3000)
    assert not window.player.reconnecting


def test_a_stream_title_never_shows_its_query(window: MainWindow, qtbot: QtBot) -> None:
    playing_stream(window, qtbot, "https://tv.example.com/live/channel1.m3u8?token=SECRET")
    assert "SECRET" not in window.player.media_name and "channel1.m3u8" in window.player.media_name
