"""The TV page (0.12): adding a channel list, browsing, playing and changing channels (test engine)."""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from babarify_frame.configuration.preferences import PreferencesStore
from babarify_frame.iptv.xmltv import Programme
from babarify_frame.library.database import LibraryDatabase
from babarify_frame.library.service import LibraryService
from babarify_frame.playback.adapters.mock import MockEngine
from babarify_frame.playback.factory import EngineDescriptor, EngineFactory, EngineProbe
from babarify_frame.ui.app import load_icon
from babarify_frame.ui.main_window import MainWindow
from fakes import FakeProbe

LIST = """#EXTM3U
#EXTINF:-1 tvg-id="one" tvg-chno="1" group-title="UK",One
https://tv.example.com/one.m3u8
#EXTINF:-1 tvg-id="two" tvg-chno="2" group-title="UK",Two
#EXTVLCOPT:http-user-agent=ExampleBox/2.0
https://tv.example.com/two.m3u8
#EXTINF:-1 tvg-chno="3" group-title="Radio",Jazz
https://radio.example.com/jazz.mp3
"""


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
    win.settings.network_streams.setChecked(True)
    qtbot.waitUntil(lambda: win.player.engine_is_ready and win.iptv.enabled)
    yield win
    win.close()


def add_list(window: MainWindow, qtbot: QtBot, tmp_path: Path) -> None:
    file = tmp_path / "home.m3u"
    file.write_text(LIST, encoding="utf-8")
    window.show_page(window.tv)
    dialog = window.tv.add_list()
    dialog.name.setText("Home TV")
    dialog.location.setText(str(file))
    dialog.accept()
    qtbot.waitUntil(lambda: window.tv.channels.count() == 3, timeout=10_000)


def test_an_empty_tv_page_explains_itself(window: MainWindow) -> None:
    window.show_page(window.tv)
    assert window.tv.empty.isVisible() and "doesn't include or suggest" in window.tv.empty.text()


def test_the_add_dialog_checks_the_address(window: MainWindow, tmp_path: Path) -> None:
    dialog = window.tv.add_list()
    ok = dialog.buttons.button(dialog.buttons.StandardButton.Ok)
    dialog.location.setText("file:///C:/Windows/win.ini")
    assert not ok.isEnabled() and dialog.problem.text()
    dialog.location.setText(str(tmp_path / "missing.m3u"))
    assert not ok.isEnabled() and "doesn't exist" in dialog.problem.text()
    dialog.location.setText("https://lists.example.com/tv.m3u")
    assert ok.isEnabled() and dialog.value == "https://lists.example.com/tv.m3u"
    dialog.reject()


def test_a_list_shows_its_channels_groups_and_guide(window: MainWindow, qtbot: QtBot, tmp_path: Path) -> None:
    add_list(window, qtbot, tmp_path)
    tv = window.tv
    now = time.time()
    sid = window.iptv.store.sources()[0].id
    window.iptv.store.replace_programmes(sid, {"one"}, iter([Programme("one", now - 60, now + 600, "News")]))
    tv.refresh()
    assert [tv.channels.item(i).text().splitlines()[0] for i in range(3)] == ["1  One", "2  Two", "3  Jazz"]
    assert "News" in tv.channels.item(0).text()
    groups = [tv.groups.item(i).text() for i in range(tv.groups.count())]
    assert groups == ["All channels", "Favourites", "UK (2)", "Radio (1)"]
    tv.groups.setCurrentRow(3)
    assert tv.channels.count() == 1
    tv.groups.setCurrentRow(0)
    tv.search.setText("two")
    qtbot.waitUntil(lambda: tv.channels.count() == 1)
    tv.channels.setCurrentRow(0)
    assert tv.detail_name.text() == "Two" and "No TV guide" in tv.detail_now.text()
    tv.favourite_button.click()
    tv.search.clear()
    tv.groups.setCurrentRow(1)
    qtbot.waitUntil(lambda: tv.channels.count() == 1)
    assert "Two" in tv.channels.item(0).text()


def test_playing_and_changing_channels(window: MainWindow, qtbot: QtBot, tmp_path: Path) -> None:
    add_list(window, qtbot, tmp_path)
    tv = window.tv
    tv.channels.setCurrentRow(1)
    tv.play_button.click()
    qtbot.waitUntil(lambda: window.player.current_uri == "https://tv.example.com/two.m3u8")
    assert window.current_page() is window.player and window.player.media_name == "Two"
    engine = window.player._controller.engine
    assert isinstance(engine, MockEngine) and engine.stream_headers == ("ExampleBox/2.0", "")
    window.step_channel(1)  # Page Down
    qtbot.waitUntil(lambda: window.player.current_uri == "https://radio.example.com/jazz.mp3")
    assert engine.stream_headers == ("", "")  # the last channel's headers don't follow
    window.step_channel(1)  # wraps round to the first
    qtbot.waitUntil(lambda: window.player.current_uri == "https://tv.example.com/one.m3u8")
    window.previous_channel()  # Backspace: the one before
    qtbot.waitUntil(lambda: window.player.current_uri == "https://radio.example.com/jazz.mp3")


def test_channel_keys_belong_to_the_player_only(window: MainWindow) -> None:
    from PySide6.QtCore import Qt

    keys = {a.text(): a for a in window.player.actions()}
    for name in ("Next channel", "Previous channel", "Last channel"):
        assert keys[name].shortcutContext() is Qt.ShortcutContext.WidgetWithChildrenShortcut
