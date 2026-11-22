"""Update notifications in the window (0.12), with GitHub's answer replaced by a fake one."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot

import babarify_frame.ui.update_notice as notice
from babarify_frame.configuration.preferences import PreferencesStore
from babarify_frame.core.updates import RELEASES_PAGE
from babarify_frame.iptv.fetch import FetchError
from babarify_frame.library.database import LibraryDatabase
from babarify_frame.library.service import LibraryService
from babarify_frame.playback.adapters.mock import MockEngine
from babarify_frame.playback.factory import EngineDescriptor, EngineFactory, EngineProbe
from babarify_frame.ui.app import load_icon
from babarify_frame.ui.main_window import MainWindow
from fakes import FakeProbe

NEWER = [{"tag_name": "v99.0.0", "name": "Babarify Media Player 99.0.0", "draft": False,
          "html_url": f"{RELEASES_PAGE}tag/v99.0.0", "body": "Lots of new things"}]  # fmt: skip


@pytest.fixture
def github(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    """What the fake GitHub answers next: a list of releases, or an exception to raise."""
    answer: list[object] = [NEWER]
    asked: list[str] = []

    def fake(url: str, _limit: int, _headers: object = None) -> bytes:
        asked.append(url)
        if isinstance(answer[0], Exception):
            raise answer[0]
        return json.dumps(answer[0]).encode()

    monkeypatch.setattr(notice, "fetch_bytes", fake)
    answer.append(asked)
    return answer


def make(qtbot: QtBot, tmp_path: Path, update_check: bool = True) -> MainWindow:
    factory = EngineFactory()
    factory.register(EngineDescriptor("mock", "Mock", MockEngine, lambda: EngineProbe("mock", True, "1")))
    win = MainWindow(
        factory, load_icon(), engine_name="mock", store=PreferencesStore(tmp_path / "settings.json"),
        library=LibraryService(LibraryDatabase(None), FakeProbe, tmp_path / "thumbs"),
        update_check=update_check,
    )  # fmt: skip
    qtbot.addWidget(win)
    win.show()
    return win


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    win = make(qtbot, tmp_path)
    yield win
    win.close()


def test_a_newer_version_is_offered(window: MainWindow, qtbot: QtBot, github: list[object]) -> None:
    assert window.check_for_updates(manual=False)
    qtbot.waitUntil(window.update_bar.isVisible, timeout=5000)
    assert "99.0.0 is available" in window.update_bar.text.text()
    assert window._prefs.last_update_check > 0


def test_download_opens_only_this_projects_release_page(
    window: MainWindow, qtbot: QtBot, github: list[object], monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[str] = []
    monkeypatch.setattr(notice.QDesktopServices, "openUrl", lambda url: opened.append(url.toString()) or True)
    window.check_for_updates(manual=False)
    qtbot.waitUntil(window.update_bar.isVisible, timeout=5000)
    window.update_bar.download.click()
    assert opened == [f"{RELEASES_PAGE}tag/v99.0.0"]


def test_skip_this_version_is_remembered(qtbot: QtBot, tmp_path: Path, github: list[object]) -> None:
    window = make(qtbot, tmp_path)
    window.check_for_updates(manual=False)
    qtbot.waitUntil(window.update_bar.isVisible, timeout=5000)
    window.update_bar.skip.click()
    assert PreferencesStore(tmp_path / "settings.json").load().skipped_update == "99.0.0"
    window._remember(last_update_check=0.0)  # a day later
    window.check_for_updates(manual=False)
    qtbot.wait(500)
    assert not window.update_bar.isVisible()  # the skipped version isn't mentioned again
    window.close()


def test_the_automatic_check_waits_a_day_and_can_be_switched_off(
    window: MainWindow, github: list[object]
) -> None:
    window._remember(last_update_check=time.time())
    assert not window.check_for_updates(manual=False)  # checked less than a day ago
    window._remember(last_update_check=0.0)
    window.settings.check_updates.setChecked(False)
    assert not window.check_for_updates(manual=False)  # switched off in Settings → Privacy


def test_tests_and_smoke_runs_never_check_on_their_own(
    qtbot: QtBot, tmp_path: Path, github: list[object]
) -> None:
    window = make(qtbot, tmp_path, update_check=False)
    assert not window.check_for_updates(manual=False)
    window.close()


def test_a_manual_check_answers_even_when_up_to_date(
    window: MainWindow, qtbot: QtBot, github: list[object], monkeypatch: pytest.MonkeyPatch
) -> None:
    said: list[str] = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: said.append(str(args[2])))
    github[0] = []
    window.check_for_updates(manual=True)
    qtbot.waitUntil(lambda: bool(said), timeout=5000)
    assert "newest version" in said[0]
    github[0] = FetchError("no answer from api.github.com within 20 s")
    window.check_for_updates(manual=True)
    qtbot.waitUntil(lambda: len(said) == 2, timeout=5000)
    assert "Couldn't check" in said[1]


def test_whats_new_shows_the_notes_as_plain_text(
    window: MainWindow, qtbot: QtBot, github: list[object]
) -> None:
    github[0] = [{**NEWER[0], "body": "<b>Bold?</b> <img src=x>"}]
    window.check_for_updates(manual=False)
    qtbot.waitUntil(window.update_bar.isVisible, timeout=5000)
    dialog = window.update_bar.show_notes()
    assert dialog is not None
    from PySide6.QtWidgets import QPlainTextEdit

    (notes,) = dialog.findChildren(QPlainTextEdit)
    assert notes.toPlainText() == "<b>Bold?</b> <img src=x>"  # shown as written, never rendered
    dialog.close()
