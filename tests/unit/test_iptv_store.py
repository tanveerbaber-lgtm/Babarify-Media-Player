"""IPTV in the library (0.12): channel lists, favourites, hidden groups and the TV guide."""

from __future__ import annotations

import time

import pytest

from babarify_frame.iptv.m3u import parse
from babarify_frame.iptv.store import MAX_SOURCES, IptvStore
from babarify_frame.iptv.xmltv import Programme
from babarify_frame.library.database import LibraryDatabase

LIST = """#EXTM3U url-tvg="https://guide.example.com/epg.xml"
#EXTINF:-1 tvg-id="one" tvg-chno="2" group-title="UK",One
https://tv.example.com/one.m3u8
#EXTINF:-1 tvg-id="two" tvg-chno="1" group-title="UK",Two
https://tv.example.com/two.m3u8
#EXTINF:-1 group-title="Music",Radio Jazz
https://radio.example.com/jazz.mp3
"""


@pytest.fixture
def store() -> IptvStore:
    return IptvStore(LibraryDatabase(None))


def names(entries: list) -> list[str]:  # type: ignore[type-arg]
    return [e.name for e in entries]


def test_a_list_is_stored_in_channel_number_order(store: IptvStore) -> None:
    sid = store.add_source("Home TV", "https://lists.example.com/tv.m3u")
    store.replace_channels(sid, parse(LIST))
    assert names(store.channels()) == ["Two", "One", "Radio Jazz"]  # numbered first, then the list's order
    (source,) = store.sources()
    assert (source.name, source.channel_count, source.guide_url) == (
        "Home TV",
        3,
        "https://guide.example.com/epg.xml",
    )
    assert source.refreshed_at is not None and source.last_error == ""


def test_favourites_survive_a_refresh(store: IptvStore) -> None:
    sid = store.add_source("TV", "https://lists.example.com/tv.m3u")
    store.replace_channels(sid, parse(LIST))
    store.set_favourite("https://tv.example.com/one.m3u8", True)
    store.replace_channels(sid, parse(LIST))  # read again: new rows, same addresses
    assert names(store.channels(favourites_only=True)) == ["One"]


def test_hidden_groups_and_search(store: IptvStore) -> None:
    sid = store.add_source("TV", "x.m3u")
    store.replace_channels(sid, parse(LIST))
    assert store.groups(sid) == [("UK", 2, False), ("Music", 1, False)]
    store.set_group_hidden(sid, "UK", True)
    assert names(store.channels()) == ["Radio Jazz"]
    assert store.groups(sid)[0] == ("UK", 2, True)
    store.set_group_hidden(sid, "UK", False)
    assert names(store.channels(search="jazz")) == ["Radio Jazz"]
    assert names(store.channels(search="100%")) == []  # % is a letter, not a wildcard
    assert names(store.channels(group="UK")) == ["Two", "One"]


def test_removing_a_list_removes_its_channels(store: IptvStore) -> None:
    keep, remove = store.add_source("A", "a.m3u"), store.add_source("B", "b.m3u")
    store.replace_channels(keep, parse(LIST))
    store.replace_channels(remove, parse("#EXTM3U\n#EXTINF:-1,Other\nhttps://other.example/x\n"))
    store.remove_source(remove)
    assert names(store.channels()) == ["Two", "One", "Radio Jazz"] and len(store.sources()) == 1


def test_the_number_of_lists_is_limited(store: IptvStore) -> None:
    for i in range(MAX_SOURCES):
        store.add_source(f"L{i}", f"{i}.m3u")
    with pytest.raises(ValueError):
        store.add_source("one too many", "x.m3u")


def test_now_and_next_from_the_guide(store: IptvStore) -> None:
    sid = store.add_source("TV", "x.m3u")
    store.replace_channels(sid, parse(LIST))
    now = time.time()
    guide = [
        Programme("one", now - 1800, now + 1800, "News"),
        Programme("one", now + 1800, now + 3600, "Film", "Part 1", "A film.", "Movie"),
        Programme("one", now + 3600, now + 7200, "Later"),
        Programme("two", now - 7200, now - 3600, "Over"),
    ]
    assert store.replace_programmes(sid, {"one", "two"}, iter(guide)) == 4
    found = store.now_next(["one", "two", "missing"], now)
    assert [e.title for e in found["one"]] == ["News", "Film"]
    assert "two" not in found  # nothing on now or later today
    assert [p.title for p in store.programmes("one", now, now + 4 * 3600)] == ["News", "Film", "Later"]
    assert store.source(sid) is not None and store.source(sid).guide_refreshed_at is not None  # type: ignore[union-attr]


def test_a_guide_refresh_replaces_only_its_channels_and_drops_old_programmes(store: IptvStore) -> None:
    sid = store.add_source("TV", "x.m3u")
    now = time.time()
    store.replace_programmes(sid, {"one", "two"}, iter([
        Programme("one", now, now + 60, "Old one"),
        Programme("two", now, now + 60, "Two stays"),
        Programme("one", now - 3 * 86400, now - 3 * 86400 + 60, "Long gone"),
    ]))  # fmt: skip
    store.replace_programmes(sid, {"one"}, iter([Programme("one", now, now + 60, "New one")]))
    assert [e.title for e in store.programmes("one", now - 4 * 86400, now + 60)] == ["New one"]
    assert [e.title for e in store.programmes("two", now, now + 60)] == ["Two stays"]
