"""The queue is saved when the app closes and restored, paused, when it starts (M2)."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot

from babarify_frame.configuration.preferences import Preferences, PreferencesStore
from babarify_frame.core.models import PlaybackState as S
from babarify_frame.library import backup
from babarify_frame.library.database import LibraryDatabase
from babarify_frame.library.service import LibraryService
from babarify_frame.playback.adapters.mock import MockEngine
from babarify_frame.playback.factory import EngineDescriptor, EngineFactory, EngineProbe
from babarify_frame.ui.app import load_icon
from babarify_frame.ui.main_window import MainWindow
from fakes import FakeProbe


def songs(tmp_path: Path, count: int = 3) -> list[str]:
    paths = []
    for n in range(count):
        path = tmp_path / f"song {n}.mp3"
        path.write_bytes(b"\x00")
        paths.append(str(path))
    return paths


def make_window(qtbot: QtBot, tmp_path: Path, open_file: str | None = None) -> MainWindow:
    factory = EngineFactory()
    factory.register(EngineDescriptor("mock", "Mock", MockEngine, lambda: EngineProbe("mock", True, "1")))
    store = PreferencesStore(tmp_path / "settings.json")
    service = LibraryService(LibraryDatabase(tmp_path / "library.db"), FakeProbe, tmp_path / "thumbs")
    win = MainWindow(factory, load_icon(), engine_name="mock", store=store, library=service)
    qtbot.addWidget(win)
    win.show()
    win.start_engine()
    if open_file:
        win.open_path(open_file)
    qtbot.waitUntil(lambda: win.player.engine_is_ready, timeout=5000)
    return win


def saved(tmp_path: Path) -> Preferences:
    return PreferencesStore(tmp_path / "settings.json").load()


def test_the_queue_comes_back_paused_where_it_was(qtbot: QtBot, tmp_path: Path) -> None:
    paths = songs(tmp_path)
    win = make_window(qtbot, tmp_path)
    win.play_list(paths, 1)
    qtbot.waitUntil(lambda: win.player.state is S.PLAYING, timeout=3000)
    win.close()
    assert saved(tmp_path).last_queue == tuple(paths) and saved(tmp_path).last_queue_index == 1

    Path(paths[2]).unlink()  # a file that has gone is left out
    again = make_window(qtbot, tmp_path)
    qtbot.waitUntil(lambda: again.player.current_uri is not None, timeout=3000)
    queue, index = again.player.queue
    assert queue == paths[:2] and index == 1
    assert Path(again.player.current_uri or "").name == "song 1.mp3"
    qtbot.wait(300)
    assert again.player.state is not S.PLAYING  # ready, but nothing plays until asked
    again.close()


def test_a_file_opened_at_start_wins_over_the_saved_queue(qtbot: QtBot, tmp_path: Path) -> None:
    paths = songs(tmp_path)
    PreferencesStore(tmp_path / "settings.json").save(
        Preferences(last_queue=tuple(paths), last_queue_index=0)
    )
    other = tmp_path / "film.mp4"
    other.write_bytes(b"\x00")
    win = make_window(qtbot, tmp_path, open_file=str(other))
    qtbot.waitUntil(lambda: win.player.state is S.PLAYING, timeout=3000)
    assert Path(win.player.current_uri or "").name == "film.mp4" and win.player.queue[0] == []
    win.close()


def test_no_queue_is_kept_without_history(qtbot: QtBot, tmp_path: Path) -> None:
    paths = songs(tmp_path)
    PreferencesStore(tmp_path / "settings.json").save(
        Preferences(remember_history=False, last_queue=tuple(paths), last_queue_index=0)
    )
    win = make_window(qtbot, tmp_path)
    qtbot.wait(300)
    assert win.player.current_uri is None
    win.play_list(paths, 0)
    qtbot.waitUntil(lambda: win.player.state is S.PLAYING, timeout=3000)
    win.close()
    assert saved(tmp_path).last_queue == ()


def test_clearing_history_forgets_the_saved_queue(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = songs(tmp_path)
    PreferencesStore(tmp_path / "settings.json").save(
        Preferences(last_queue=tuple(paths), last_queue_index=0)
    )
    win = make_window(qtbot, tmp_path)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    win.clear_history()
    assert saved(tmp_path).last_queue == ()
    win.player.stop()
    win.close()


def test_a_backup_never_contains_the_queue(tmp_path: Path) -> None:
    prefs = Preferences(last_queue=("C:/Music/a.mp3",), last_queue_index=0)
    data = backup.build_backup(prefs, LibraryDatabase(None))
    assert "last_queue" not in data["preferences"] and "last_queue_index" not in data["preferences"]


@pytest.mark.parametrize(
    ("enabled", "start", "expected"),
    [
        (True, "Episode 1.mkv", "Episode 2.mkv"),
        (False, "Episode 1.mkv", "Episode 1.mkv"),
        (True, "song.mp3", "song.mp3"),  # songs never start a video
    ],
)
def test_the_next_video_in_the_folder_follows_when_switched_on(
    qtbot: QtBot, tmp_path: Path, enabled: bool, start: str, expected: str
) -> None:
    media = tmp_path / "media"
    media.mkdir()
    for name in ("Episode 1.mkv", "Episode 2.mkv", "song.mp3"):
        (media / name).write_bytes(b"\x00")
    PreferencesStore(tmp_path / "settings.json").save(Preferences(autoplay_next_video=enabled))
    win = make_window(qtbot, tmp_path)
    win.open_path(str(media / start))
    qtbot.waitUntil(lambda: win.player.state is S.PLAYING, timeout=3000)
    engine = win.controller.engine
    assert isinstance(engine, MockEngine)
    engine.advance(10_000_000)  # to the end
    qtbot.wait(400)
    assert Path(win.player.current_uri or "").name == expected
    win.player.stop()
    win.close()
