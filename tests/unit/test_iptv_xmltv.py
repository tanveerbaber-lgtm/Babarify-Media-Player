# ruff: noqa: E501
"""The TV guide (0.12): XMLTV read piece by piece, with guards against hostile or broken files."""

from __future__ import annotations

import gzip
import io
from datetime import UTC, datetime

import pytest

import babarify_frame.iptv.xmltv as xmltv
from babarify_frame.iptv.xmltv import GuideError, parse_time, read

NOW = datetime(2026, 11, 22, 18, 0, tzinfo=UTC).timestamp()
GUIDE = b"""<?xml version="1.0" encoding="UTF-8"?>
<tv>
  <channel id="one.uk"><display-name>One</display-name></channel>
  <channel id="two.uk"><display-name>Two</display-name></channel>
  <programme start="20261122170000 +0000" stop="20261122180000 +0000" channel="one.uk">
    <title>Earlier</title></programme>
  <programme start="20261122190000 +0100" stop="20261122200000 +0100" channel="one.uk">
    <title>News</title><sub-title>Evening</sub-title><desc>The day's news.</desc><category>News</category>
  </programme>
  <programme start="20261101180000 +0000" stop="20261101190000 +0000" channel="one.uk"><title>Old</title></programme>
  <programme start="20261210180000 +0000" stop="20261210190000 +0000" channel="one.uk"><title>Far</title></programme>
  <programme start="20261122180000 +0000" stop="20261122190000 +0000" channel="other"><title>Not ours</title></programme>
  <programme start="bad" stop="20261122190000" channel="one.uk"><title>Broken time</title></programme>
  <programme start="20261122183000" channel="two.uk"><title>No stop</title></programme>
</tv>
"""


def titles(data: bytes, wanted: set[str] | None = None) -> list[str]:
    _channels, programmes = read(io.BytesIO(data), wanted, now=NOW)
    return [p.title for p in programmes]


def test_times_with_offsets() -> None:
    assert parse_time("20261122190000 +0100") == datetime(2026, 11, 22, 18, 0, tzinfo=UTC).timestamp()
    assert parse_time("20261122180000") == datetime(2026, 11, 22, 18, 0, tzinfo=UTC).timestamp()  # UTC
    assert parse_time("20261122180000 -0500") == datetime(2026, 11, 22, 23, 0, tzinfo=UTC).timestamp()
    assert parse_time("garbage") is None and parse_time("20261340990000") is None


def test_a_guide_keeps_the_window_and_the_channels_asked_for() -> None:
    channels, programmes = read(io.BytesIO(GUIDE), {"one.uk", "two.uk"}, now=NOW)
    found = list(programmes)
    assert [p.title for p in found] == ["Earlier", "News", "No stop"]  # 6 h back to 7 days ahead
    news = found[1]
    assert (news.subtitle, news.description, news.category) == ("Evening", "The day's news.", "News")
    assert news.start == NOW and news.stop == NOW + 3600
    assert found[2].stop - found[2].start == 1800  # no stop time: half an hour
    assert [(c.id, c.name) for c in channels] == [("one.uk", "One"), ("two.uk", "Two")]


def test_a_gzip_guide_is_read_by_its_content_not_its_name() -> None:
    assert titles(gzip.compress(GUIDE), {"one.uk"}) == ["Earlier", "News"]


def test_entity_declarations_are_refused() -> None:
    bomb = b"""<?xml version="1.0"?><!DOCTYPE tv [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;">]>
<tv><programme start="20261122180000" channel="x"><title>&b;</title></programme></tv>"""
    with pytest.raises(GuideError):
        titles(bomb)


def test_a_compressed_guide_cannot_expand_without_end(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(xmltv, "MAX_UNPACKED_BYTES", 100_000)
    huge = b"<tv>" + b"<!-- padding -->" * 50_000 + b"</tv>"
    with pytest.raises(GuideError):
        titles(gzip.compress(huge))


@pytest.mark.parametrize(
    "data",
    [
        b"<html><body>Not found</body></html>",
        b"",
        b"<tv><programme channel='a' start='20261122180000'><title>x",
    ],
    ids=["web page", "empty", "cut off"],
)
def test_other_or_broken_files_are_refused(data: bytes) -> None:
    with pytest.raises(GuideError):
        titles(data)


def test_text_is_trimmed_and_printable() -> None:
    long = "x" * 5000
    data = f"""<tv><programme start="20261122180000" channel="a"><title>A‮B</title><desc>{long}</desc>
</programme></tv>""".encode()
    _channels, programmes = read(io.BytesIO(data), None, now=NOW)
    (programme,) = list(programmes)
    assert programme.title == "AB" and len(programme.description) == 2000


def test_the_number_of_programmes_is_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(xmltv, "MAX_PROGRAMMES", 3)
    many = "".join(
        f'<programme start="2026112218{m:02d}00" channel="a"><title>P{m}</title></programme>'
        for m in range(10)
    )
    assert len(titles(f"<tv>{many}</tv>".encode())) == 3
