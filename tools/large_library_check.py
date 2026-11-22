"""Measure a large library (M3): 20,000 files, scanned and browsed through the real window.

Creates 10,000 songs and 10,000 videos (tiny files; tags are filled in as if read), scans them with the
library service while a 10 ms timer measures how long the window is ever unresponsive, then times the
database queries and the Music, Videos and search views. The playback engine is the test engine: this
measures the library and the interface, not decoding.

Usage:  python tools/large_library_check.py <work_dir> [songs] [videos]
"""

from __future__ import annotations

import json
import os
import random
import shutil
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("BABARIFY_CONFIG_DIR", tempfile.mkdtemp(prefix="babarify-large-"))
sys.path.insert(0, "src")
sys.path.insert(0, "tests")

from PySide6.QtCore import QElapsedTimer, QTimer
from PySide6.QtWidgets import QApplication

from babarify_frame.configuration.preferences import PreferencesStore
from babarify_frame.library.database import LibraryDatabase, ProbeRecord
from babarify_frame.library.music import GroupKind, group_songs
from babarify_frame.library.service import LibraryService
from babarify_frame.playback.adapters.mock import MockEngine
from babarify_frame.playback.factory import EngineDescriptor, EngineFactory, EngineProbe
from babarify_frame.ui.app import load_icon
from babarify_frame.ui.main_window import MainWindow

WORDS = "blue night sky river city golden rain moon summer dream fire ocean light road heart star".split()  # noqa: SIM905
GENRES = ["Rock", "Pop", "Jazz", "Classical", "Electronic", "Hip-Hop", "Folk", "Soul"]


def make_files(root: Path, songs: int, videos: int) -> None:
    rng = random.Random(7)
    for kind, count, ext in (("Music", songs, ".mp3"), ("Videos", videos, ".mkv")):
        for n in range(count):
            folder = root / kind / f"folder {n // 200:03d}"
            folder.mkdir(parents=True, exist_ok=True)
            name = f"{' '.join(rng.sample(WORDS, 3)).title()} {n:05d}{ext}"
            (folder / name).write_bytes(n.to_bytes(4, "little") * 64)


def main() -> None:
    work = Path(sys.argv[1])
    songs = int(sys.argv[2]) if len(sys.argv) > 2 else 10_000
    videos = int(sys.argv[3]) if len(sys.argv) > 3 else 10_000
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    results: dict[str, object] = {"files": songs + videos}
    started = time.perf_counter()
    make_files(work / "media", songs, videos)
    results["create_files_s"] = round(time.perf_counter() - started, 1)

    app = QApplication(sys.argv[:1])
    factory = EngineFactory()
    factory.register(EngineDescriptor("mock", "Mock", MockEngine, lambda: EngineProbe("mock", True, "1")))
    db = LibraryDatabase(work / "library.db")
    service = LibraryService(db, None, work / "thumbs")  # no probing: tags are filled in below
    store = PreferencesStore(work / "settings.json")
    window = MainWindow(factory, load_icon(), engine_name="mock", store=store, library=service)
    window.resize(1280, 800)
    window.show()
    window.start_engine()
    window.show_library("music")

    gaps: list[int] = []
    clock = QElapsedTimer()
    clock.start()
    timer = QTimer()
    timer.timeout.connect(lambda: gaps.append(clock.restart()))
    timer.start(10)
    started = time.perf_counter()
    window.library.add_folder(str(work / "media"))
    while service.busy and time.perf_counter() - started < 600:
        app.processEvents()
        time.sleep(0.002)
    timer.stop()
    results["scan_s"] = round(time.perf_counter() - started, 1)
    results["scan_worst_ui_gap_ms"] = max(gaps) if gaps else None
    results["scan_ui_gaps_over_100ms"] = sum(1 for g in gaps if g > 100)

    # Tags as the probe would have read them.
    rng = random.Random(11)
    started = time.perf_counter()
    for entry in db.media(limit=100_000):
        if entry.name.endswith(".mp3"):
            artist = f"Artist {rng.randrange(400):03d}"
            album, year, genre = (
                f"Album {rng.randrange(1500):04d}",
                2000 + rng.randrange(25),
                rng.choice(GENRES),
            )
            record = ProbeRecord(
                200_000, None, None, None, "mp3", None, entry.name[:-10], artist, album, year, genre
            )
        else:
            record = ProbeRecord(1_800_000, 1920, 1080, "h264", "aac", None)
        db.set_probe_result(entry.id, record)
    results["fill_tags_s"] = round(time.perf_counter() - started, 1)

    def timed(name: str, call) -> object:  # type: ignore[no-untyped-def]
        start = time.perf_counter()
        value = call()
        results[name] = round((time.perf_counter() - start) * 1000)
        return value

    all_songs = timed("db_songs_ms", db.songs)
    timed("db_videos_ms", lambda: db.media(view="videos"))
    timed("db_search_ms", lambda: db.search_everything("blue night"))
    timed("group_albums_ms", lambda: group_songs(all_songs, GroupKind.ALBUM))  # type: ignore[arg-type]
    timed("group_genres_ms", lambda: group_songs(all_songs, GroupKind.GENRE))  # type: ignore[arg-type]
    lib = window.library
    names = [lib.tabs.tabText(i) for i in range(lib.tabs.count())]

    def show_tab(name: str) -> None:
        lib.tabs.setCurrentIndex(names.index(name))
        lib.refresh_current_tab()
        app.processEvents()

    timed("ui_songs_tab_ms", lambda: show_tab("Songs"))
    timed("ui_albums_tab_ms", lambda: show_tab("Albums"))
    timed("ui_genres_tab_ms", lambda: show_tab("Genres"))
    timed("ui_videos_ms", lambda: (window.show_library("videos"), app.processEvents()))
    timed("ui_home_search_ms", lambda: (window.home.search_requested.emit("blue night"), app.processEvents()))
    results["songs_listed"] = len(lib.songs_panel.songs.entries)
    results["home_search_results"] = window.home.search_results.count()
    window.close()
    app.processEvents()
    db.close()
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
