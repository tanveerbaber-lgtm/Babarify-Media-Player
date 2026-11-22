"""Keeping IPTV lists and guides up to date (0.12): read in the background, nothing while switched off."""

from __future__ import annotations

import gzip
import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from babarify_frame.iptv.service import IptvService, IptvUpdate
from babarify_frame.iptv.store import IptvStore
from babarify_frame.library.database import LibraryDatabase
from netserver import LocalServer


def guide_now() -> bytes:
    start = datetime.now(UTC).strftime("%Y%m%d%H0000 +0000")
    programme = f'<programme start="{start}" channel="one"><title>Now on One</title></programme>'
    return f"<tv>{programme}</tv>".encode()


@pytest.fixture
def server(tmp_path: Path) -> Iterator[LocalServer]:
    web = tmp_path / "web"
    web.mkdir()
    srv = LocalServer(web)
    guide = srv.url("/guide.xml.gz")
    (web / "tv.m3u").write_text(
        f'#EXTM3U url-tvg="{guide}"\n#EXTINF:-1 tvg-id="one",One\nhttps://tv.example.com/one.m3u8\n'
        "#EXTINF:-1,Bad\nfile:///C:/Windows/win.ini\n",
        encoding="utf-8",
    )
    (web / "guide.xml.gz").write_bytes(gzip.compress(guide_now()))
    (web / "broken.m3u").write_text("<html>not a list</html>", encoding="utf-8")
    yield srv
    srv.close()


@pytest.fixture
def service(tmp_path: Path) -> Iterator[tuple[IptvService, list[IptvUpdate]]]:
    found = IptvService(IptvStore(LibraryDatabase(None)), tmp_path / "cache")
    updates: list[IptvUpdate] = []
    done = threading.Event()
    found.add_listener(lambda u: (updates.append(u), done.set()))
    yield found, updates
    found.shutdown()


def wait_for(updates: list[IptvUpdate], count: int) -> None:
    deadline = time.monotonic() + 20
    while len(updates) < count and time.monotonic() < deadline:
        time.sleep(0.05)
    assert len(updates) >= count, updates


def test_a_list_and_its_guide_are_read(
    service: tuple[IptvService, list[IptvUpdate]], server: LocalServer
) -> None:
    iptv, updates = service
    iptv.set_enabled(True)
    sid = iptv.add_list("Home TV", server.url("/tv.m3u"))
    wait_for(updates, 2)
    assert [(u.what, u.ok) for u in updates] == [("list", True), ("guide", True)]
    assert "1 channels" in updates[0].message and "1 entries left out" in updates[0].message
    (channel,) = iptv.store.channels()
    assert channel.name == "One"
    assert [e.title for e in iptv.store.now_next(["one"])["one"]] == ["Now on One"]
    source = iptv.store.source(sid)
    assert source is not None and source.last_error == "" and source.guide_refreshed_at is not None


def test_nothing_is_fetched_while_switched_off(
    service: tuple[IptvService, list[IptvUpdate]], server: LocalServer
) -> None:
    iptv, updates = service
    iptv.add_list("Home TV", server.url("/tv.m3u"))  # stored, but not read: network streams are off
    iptv.refresh_due()
    time.sleep(0.5)
    assert updates == [] and iptv.store.channels() == []


def test_a_failure_is_recorded_with_its_reason(
    service: tuple[IptvService, list[IptvUpdate]], server: LocalServer
) -> None:
    iptv, updates = service
    iptv.set_enabled(True)
    sid = iptv.add_list("Broken", server.url("/broken.m3u"))
    wait_for(updates, 1)
    assert not updates[0].ok and "M3U" in updates[0].message
    source = iptv.store.source(sid)
    assert source is not None and "M3U" in source.last_error


def test_a_list_from_a_file_on_this_pc(service: tuple[IptvService, list[IptvUpdate]], tmp_path: Path) -> None:
    iptv, updates = service
    iptv.set_enabled(True)
    file = tmp_path / "mine.m3u8"
    file.write_text("#EXTM3U\n#EXTINF:-1,Local\nudp://@239.1.1.1:1234\n", encoding="utf-8")
    iptv.add_list("Mine", str(file))
    wait_for(updates, 1)
    assert updates[0].ok and [c.name for c in iptv.store.channels()] == ["Local"]


def test_only_what_is_due_is_read_again(
    service: tuple[IptvService, list[IptvUpdate]], server: LocalServer
) -> None:
    iptv, updates = service
    iptv.set_enabled(True)
    iptv.add_list("Home TV", server.url("/tv.m3u"))
    wait_for(updates, 2)
    updates.clear()
    iptv.refresh_due()  # just read: nothing is due
    time.sleep(0.5)
    assert updates == []
    iptv.refresh_due(now=time.time() + 13 * 3600)  # the guide is due, the list not yet
    wait_for(updates, 1)
    assert [u.what for u in updates] == ["guide"]
