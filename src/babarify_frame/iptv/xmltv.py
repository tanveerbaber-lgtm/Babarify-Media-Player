"""The TV guide in XMLTV (0.12). The file is untrusted and can be large, so it is read piece by piece.

    <tv>
      <channel id="one.uk"><display-name>One</display-name><icon src="https://..."/></channel>
      <programme start="20261122180000 +0000" stop="20261122190000 +0000" channel="one.uk">
        <title>News</title><sub-title>...</sub-title><desc>...</desc><category>News</category>
      </programme>
    </tv>

Guards: plain or gzip text, at most MAX_UNPACKED_BYTES once unpacked (a small .gz can't expand without
end); a document type that declares entities is refused (the XML tricks that make a file explode or reach
outside it); only the channels asked for, and only programmes from WINDOW_BEFORE before now to WINDOW_AFTER
ahead, at most MAX_PROGRAMMES; text is trimmed and made printable.
"""

from __future__ import annotations

import gzip
import io
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import BinaryIO

MAX_UNPACKED_BYTES = 400 * 1024 * 1024
MAX_PROGRAMMES = 400_000
WINDOW_BEFORE = timedelta(hours=6)
WINDOW_AFTER = timedelta(days=7)
CHUNK = 64 * 1024
_TIME = re.compile(r"^(\d{14})(?:\s*([+-])(\d{2})(\d{2}))?")


class GuideError(ValueError):
    """The file isn't a TV guide Babarify can read (the message is worded for the user)."""


@dataclass(frozen=True)
class Programme:
    channel: str  # the guide's channel id (a channel list's tvg-id)
    start: float  # seconds since 1970, UTC
    stop: float
    title: str
    subtitle: str = ""
    description: str = ""
    category: str = ""


@dataclass(frozen=True)
class GuideChannel:
    id: str
    name: str


class _Limited(io.RawIOBase):
    """Reads at most ``limit`` bytes from ``source``, then fails: an unpacked guide can't grow without end."""

    def __init__(self, source: BinaryIO, limit: int) -> None:
        self._source, self._left = source, limit

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: memoryview) -> int:  # type: ignore[override]
        data = self._source.read(min(len(buffer), CHUNK))
        if len(data) > self._left:
            raise GuideError("the TV guide is too large once unpacked")
        self._left -= len(data)
        buffer[: len(data)] = data
        return len(data)


def open_guide(raw: BinaryIO) -> io.BufferedReader:
    """Plain XML or gzip, chosen by the first bytes, never by a file name or server."""
    head = raw.read(2)
    rest = io.BufferedReader(_Prefixed(head, raw))
    if head == b"\x1f\x8b":
        return io.BufferedReader(_Limited(gzip.GzipFile(fileobj=rest), MAX_UNPACKED_BYTES))  # type: ignore[arg-type]
    return io.BufferedReader(_Limited(rest, MAX_UNPACKED_BYTES))


class _Prefixed(io.RawIOBase):
    def __init__(self, head: bytes, source: BinaryIO) -> None:
        self._head, self._source = head, source

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: memoryview) -> int:  # type: ignore[override]
        if self._head:
            n = min(len(buffer), len(self._head))
            buffer[:n] = self._head[:n]
            self._head = self._head[n:]
            return n
        data = self._source.read(min(len(buffer), CHUNK))
        buffer[: len(data)] = data
        return len(data)


def parse_time(text: str) -> float | None:
    """XMLTV time, "YYYYMMDDhhmmss +hhmm" (the offset is optional and means UTC when missing)."""
    match = _TIME.match((text or "").strip())
    if not match:
        return None
    try:
        when = datetime.strptime(match.group(1), "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    except ValueError:
        return None
    if match.group(2):
        offset = timedelta(hours=int(match.group(3)), minutes=int(match.group(4)))
        when = when - offset if match.group(2) == "+" else when + offset
    return when.timestamp()


def read(
    raw: BinaryIO, wanted: set[str] | None = None, now: float | None = None
) -> tuple[list[GuideChannel], Iterator[Programme]]:
    """Channels named in the guide, and its programmes for the ``wanted`` channel ids (all when None).

    The programmes are produced as the file is read, so a large guide never sits in memory at once."""
    stream = open_guide(raw)
    first = stream.peek(64 * 1024)[: 64 * 1024]
    if b"<!ENTITY" in first.upper():
        raise GuideError("the TV guide declares XML entities, which Babarify doesn't read")
    if b"<tv" not in first and b"<?xml" not in first:
        raise GuideError("this isn't an XMLTV guide")
    channels: list[GuideChannel] = []
    current = datetime.now(UTC).timestamp() if now is None else now
    earliest, latest = current - WINDOW_BEFORE.total_seconds(), current + WINDOW_AFTER.total_seconds()

    def programmes() -> Iterator[Programme]:
        count = 0
        try:
            for _event, element in ET.iterparse(stream, events=("end",)):
                tag = element.tag
                if tag == "channel":
                    cid = _text(element.get("id"), 200)
                    if cid and len(channels) < 100_000:
                        channels.append(
                            GuideChannel(cid, _text(element.findtext("display-name"), 200) or cid)
                        )
                    element.clear()
                elif tag == "programme":
                    programme = _programme(element, wanted, earliest, latest)
                    element.clear()
                    if programme is not None:
                        count += 1
                        if count > MAX_PROGRAMMES:
                            return
                        yield programme
        except ET.ParseError as exc:
            raise GuideError(f"the TV guide is not valid XML ({exc})") from exc

    return channels, programmes()


def _programme(
    element: ET.Element, wanted: set[str] | None, earliest: float, latest: float
) -> Programme | None:
    channel = element.get("channel") or ""
    if not channel or (wanted is not None and channel not in wanted):
        return None
    start, stop = parse_time(element.get("start", "")), parse_time(element.get("stop", ""))
    if start is None:
        return None
    if stop is None or stop <= start:
        stop = start + 30 * 60
    if stop < earliest or start > latest or stop - start > 24 * 3600:
        return None
    return Programme(
        channel=channel[:200],
        start=start,
        stop=stop,
        title=_text(element.findtext("title"), 200) or "Untitled",
        subtitle=_text(element.findtext("sub-title"), 200),
        description=_text(element.findtext("desc"), 2000),
        category=_text(element.findtext("category"), 80),
    )


def _text(value: str | None, limit: int) -> str:
    return " ".join("".join(c for c in (value or "") if c.isprintable() or c == " ").split())[:limit]
