# ruff: noqa: E501  (sample lists keep their real line lengths)
"""IPTV channel lists (0.12): what IPTV players read, and nothing a hostile list could slip in."""

from __future__ import annotations

import pytest

from babarify_frame.iptv.m3u import MAX_CHANNELS, PlaylistError, attributes, parse

TYPICAL = """#EXTM3U url-tvg="https://guide.example.com/epg.xml.gz,https://guide.example.com/more.xml" x-tvg-url="ftp://bad"
#EXTINF:-1 tvg-id="one.uk" tvg-name="One HD" tvg-logo="https://logos.example.com/one.png" tvg-chno="1" group-title="UK",One HD
https://tv.example.com/live/one.m3u8
#EXTINF:-1 tvg-id="news" tvg-logo="file:///C:/Windows/logo.png" group-title="News, Weather",News, Sport & Weather
#EXTVLCOPT:http-user-agent=ExampleBox/2.0
#EXTVLCOPT:http-referrer=https://portal.example.com/
http://tv.example.com:8080/live/news.ts
#EXTINF:-1,Multicast TV
#EXTGRP:Provider
udp://@239.1.1.1:1234
"""


def test_a_typical_channel_list() -> None:
    result = parse(TYPICAL.encode("utf-8"))
    assert result.guide_urls == ("https://guide.example.com/epg.xml.gz", "https://guide.example.com/more.xml")
    one, news, multicast = result.channels
    assert (one.name, one.tvg_id, one.number, one.group) == ("One HD", "one.uk", 1, "UK")
    assert one.logo == "https://logos.example.com/one.png"
    assert news.name == "News, Sport & Weather" and news.group == "News, Weather"  # commas in quotes
    assert news.logo == ""  # only web addresses are fetched for logos
    assert (news.user_agent, news.referrer) == ("ExampleBox/2.0", "https://portal.example.com/")
    assert (multicast.name, multicast.group, multicast.url) == (
        "Multicast TV",
        "Provider",
        "udp://@239.1.1.1:1234",
    )
    assert multicast.user_agent == ""  # options belong to one entry only
    assert result.skipped == 0


@pytest.mark.parametrize(
    "address",
    [
        "file:///C:/Users/me/secret.mp4",
        "C:\\Windows\\win.ini",
        "\\\\server\\share\\film.mkv",
        "smb://server/share/film.mkv",
        "dshow://",
        "vlc://quit",
        "udp://@:1234",
        "https://user:password@tv.example.com/live.m3u8",
        "screen://",
        "NUL",
    ],
)
def test_entries_that_are_not_allowed_are_skipped(address: str) -> None:
    result = parse(f"#EXTM3U\n#EXTINF:-1,Bad\n{address}\n#EXTINF:-1,Good\nhttps://tv.example.com/a.m3u8\n")
    assert [c.name for c in result.channels] == ["Good"]
    assert result.skipped == 1 and result.notes


def test_a_list_without_the_header_but_with_entries_is_read() -> None:
    assert [c.name for c in parse("#EXTINF:-1,A\nhttps://tv.example.com/a\n").channels] == ["A"]


@pytest.mark.parametrize(
    "data",
    [
        b"<html><body>Not found</body></html>",
        b"\x00\x01\x02binary",
        b"",
        b"just some text\nhttps://a.example/b",
    ],
    ids=["web page", "binary", "empty", "plain text"],
)
def test_other_files_are_refused_with_a_reason(data: bytes) -> None:
    with pytest.raises(PlaylistError):
        parse(data)


def test_oversized_lists_are_refused() -> None:
    with pytest.raises(PlaylistError):
        parse(b"#EXTM3U\n" + b"#" * (21 * 1024 * 1024))


def test_the_number_of_channels_is_limited() -> None:
    entries = "".join(f"#EXTINF:-1,C{i}\nhttps://tv.example.com/{i}\n" for i in range(MAX_CHANNELS + 3))
    result = parse("#EXTM3U\n" + entries)
    assert len(result.channels) == MAX_CHANNELS and result.skipped == 3


def test_names_are_cleaned_and_trimmed() -> None:
    result = parse("#EXTM3U\n#EXTINF:-1,Bad\u0007  name\u202e" + "x" * 500 + "\nhttps://tv.example.com/a\n")
    (channel,) = result.channels
    assert "\u0007" not in channel.name and "\u202e" not in channel.name and len(channel.name) == 200


def test_latin1_lists_and_bom_are_read() -> None:
    assert (
        parse("#EXTM3U\n#EXTINF:-1,Télé\nhttps://a.example/b\n".encode("latin-1")).channels[0].name == "Télé"
    )
    assert parse("\ufeff#EXTM3U\n#EXTINF:-1,A\nhttps://a.example/b\n".encode()).channels[0].name == "A"


def test_attribute_styles() -> None:
    assert attributes('tvg-id="a b" tvg-logo=\'https://x/y.png\' tvg-chno=7 GROUP-TITLE="G"') == {
        "tvg-id": "a b",
        "tvg-logo": "https://x/y.png",
        "tvg-chno": "7",
        "group-title": "G",
    }


def test_headers_must_be_plain_text() -> None:
    """A line break ends the option line, so nothing can be slipped into a request as a second header."""
    result = parse(
        "#EXTM3U\n#EXTINF:-1,A\n#EXTVLCOPT:http-user-agent=Bad\r\nInjected: yes\nhttps://a.example/b\n"
        "#EXTINF:-1,B\n#EXTVLCOPT:http-user-agent=Ünïcode\nhttps://a.example/c\n"
    )
    assert all("Injected" not in c.user_agent and "\n" not in c.user_agent for c in result.channels)
    assert result.channels[-1].user_agent == ""  # not plain ASCII: not sent
