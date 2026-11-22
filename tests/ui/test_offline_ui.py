"""0.11: a local-only player. No network or AI features remain, and data left by them can be removed."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDropEvent, QKeySequence
from PySide6.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot

from babarify_frame.configuration.preferences import Preferences, PreferencesStore
from babarify_frame.library.database import LibraryDatabase
from babarify_frame.library.service import LibraryService
from babarify_frame.playback.adapters.mock import MockEngine
from babarify_frame.playback.factory import EngineDescriptor, EngineFactory, EngineProbe
from babarify_frame.ui.app import load_icon
from babarify_frame.ui.main_window import MainWindow
from fakes import FakeProbe


def make_window(qtbot: QtBot, tmp_path: Path) -> MainWindow:
    factory = EngineFactory()
    factory.register(EngineDescriptor("mock", "Mock", MockEngine, lambda: EngineProbe("mock", True, "1")))
    store = PreferencesStore(tmp_path / "settings.json")
    service = LibraryService(LibraryDatabase(None), FakeProbe, tmp_path / "thumbs")
    win = MainWindow(factory, load_icon(), engine_name="mock", store=store, library=service)
    qtbot.addWidget(win)
    win.show()
    win.start_engine()
    qtbot.waitUntil(lambda: win.player.engine_is_ready, timeout=5000)
    return win


@pytest.fixture
def old_ai_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, Path]:
    """Folders the AI feature of 0.9 and 0.10 left behind, plus a file of the app's own beside them."""
    local, roaming = tmp_path / "local", tmp_path / "roaming"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.setenv("APPDATA", str(roaming))
    monkeypatch.delenv("BABARIFY_CONFIG_DIR", raising=False)
    models = local / "Babarify" / "Frame" / "models" / "base"
    models.mkdir(parents=True)
    (models / "model.bin").write_bytes(b"\x00" * 3_000_000)
    generated = roaming / "Babarify" / "Frame" / "subtitles" / "abc"
    generated.mkdir(parents=True)
    (generated / "film.machine.en.srt").write_text("1\n00:00:01,000 --> 00:00:02,000\nHi\n", encoding="utf-8")
    keep = local / "Babarify" / "Frame" / "logs" / "app.log"
    keep.parent.mkdir(parents=True)
    keep.write_text("log", encoding="utf-8")
    return models.parent, generated.parent, keep


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    win = make_window(qtbot, tmp_path)
    yield win
    win.close()


def test_old_ai_data_is_offered_and_deleted_on_request(
    qtbot: QtBot, tmp_path: Path, old_ai_data: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    models, generated, keep = old_ai_data
    win = make_window(qtbot, tmp_path)
    win.show_page(win.settings)
    button = win.settings.old_ai_button
    assert button.isVisible() and "(3 MB)" in button.text()
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    button.click()
    assert models.exists() and generated.exists()  # declined: nothing deleted
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    button.click()
    assert not models.exists() and not generated.exists()
    assert keep.read_text(encoding="utf-8") == "log"  # the rest of Babarify's folder is untouched
    assert not button.isVisible()
    win.close()


def test_no_old_ai_button_without_old_data(
    window: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "empty"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "empty"))
    monkeypatch.delenv("BABARIFY_CONFIG_DIR", raising=False)
    window.show_page(window.settings)
    assert not window.settings.old_ai_button.isVisible()


def test_no_ai_commands_remain_and_streams_start_switched_off(window: MainWindow) -> None:
    """0.11 removed AI; 0.12 brought network streams back, off until the user switches them on."""
    names = [a.text().replace("&", "").lower() for a in window.findChildren(type(window.open_action))]
    assert not [n for n in names if "spoken" in n or "generate" in n]
    keys = {s.toString() for a in window.findChildren(type(window.open_action)) for s in a.shortcuts()}
    for removed in ("Ctrl+Shift+G", "Ctrl+Shift+F"):
        assert QKeySequence(removed).toString() not in keys
    assert QKeySequence("Ctrl+N").toString() in keys  # Open network stream: asks first while off
    assert not window.settings.network_streams.isChecked()


def test_a_dropped_web_link_is_ignored_while_streams_are_off(window: MainWindow) -> None:
    mime = QMimeData()
    mime.setUrls([QUrl("https://example.com/video.mp4")])
    event = QDropEvent(
        QPointF(10, 10),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    window.dropEvent(event)
    assert not event.isAccepted() and window.player.current_uri is None


def test_old_settings_with_ai_options_still_load(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        '{"ai_enabled": true, "ai_model": "base", "ai_language": "en", "volume": 40}', encoding="utf-8"
    )
    prefs = PreferencesStore(path).load()
    assert prefs.volume == 40 and prefs == Preferences(volume=40)
