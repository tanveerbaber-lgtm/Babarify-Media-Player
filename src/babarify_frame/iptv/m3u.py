"""IPTV channel lists in extended M3U (0.12). The whole file is untrusted.

Reads what IPTV players read::

    #EXTM3U url-tvg="https://example.com/guide.xml.gz"
    #EXTINF:-1 tvg-id="one.uk" tvg-name="One" tvg-logo="https://..." tvg-chno="1" group-title="UK",One
    #EXTVLCOPT:http-user-agent=Example/1.0
    https://example.com/live/bbc1.m3u8

Limits: the text is at most MAX_BYTES and MAX_CHANNELS channels; names and attributes are trimmed to sane
lengths; every stream address goes through ``validate_stream_url`` (the rules a typed address follows), and
logos and guides must be web addresses. Anything else is skipped and counted, never guessed at.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from babarify_frame.core.errors import PlaybackError
from babarify_frame.core.network import validate_stream_url

MAX_BYTES = 20 * 1024 * 1024
MAX_CHANNELS = 50_000
MAX_NAME = 200
MAX_GROUP = 120
MAX_HEADER = 300  # a user agent or referrer
WEB = frozenset({"http", "https"})
_ATTRIBUTE = re.compile(r'([A-Za-z0-9_-]+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^\s"\',]+))')


class PlaylistError(ValueError):
    """The file isn't an IPTV channel list Babarify can read (the message is worded for the user)."""


@dataclass(frozen=True)
class Channel:
    name: str
    url: str
    group: str = ""
    tvg_id: str = ""  # the guide's name for it
    logo: str = ""
    number: int | None = None
    user_agent: str = ""  # some providers need these (#EXTVLCOPT)
    referrer: str = ""


@dataclass(frozen=True)
class ChannelList:
    channels: tuple[Channel, ...]
    guide_urls: tuple[str, ...] = ()  # from url-tvg / x-tvg-url in the header
    skipped: int = 0  # entries left out: an address that isn't allowed, or past the limits
    notes: tuple[str, ...] = field(default=())


def decode(data: bytes) -> str:
    if len(data) > MAX_BYTES:
        raise PlaylistError(f"the channel list is larger than {MAX_BYTES // (1024 * 1024)} MB")
    if b"\0" in data[:4096]:
        raise PlaylistError("this isn't a channel list (it looks like a binary file)")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def parse(data: bytes | str) -> ChannelList:
    text = decode(data) if isinstance(data, bytes) else data
    if len(text) > MAX_BYTES:
        raise PlaylistError(f"the channel list is larger than {MAX_BYTES // (1024 * 1024)} MB")
    lines = text.splitlines()
    first = next((line.strip() for line in lines if line.strip()), "")
    if not first.upper().startswith("#EXTM3U") and not any(
        line.strip().upper().startswith("#EXTINF") for line in lines[:200]
    ):
        raise PlaylistError("this isn't an M3U channel list (no #EXTM3U or #EXTINF lines)")

    guides: list[str] = []
    channels: list[Channel] = []
    skipped = 0
    info: dict[str, str] = {}
    title = ""
    group_line = ""
    agent = referrer = ""
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        upper = line.upper()
        if upper.startswith("#EXTM3U"):
            attrs = attributes(line[7:])
            for key in ("url-tvg", "x-tvg-url"):
                for url in attrs.get(key, "").split(","):
                    web = _web(url.strip())
                    if web and web not in guides and len(guides) < 5:
                        guides.append(web)
        elif upper.startswith("#EXTINF"):
            head, _comma, name = line.partition(",") if '"' not in line else _split_extinf(line)
            info = attributes(head)
            title = name.strip()
        elif upper.startswith("#EXTGRP:"):
            group_line = line[8:].strip()
        elif upper.startswith("#EXTVLCOPT:"):
            option = line[11:].strip()
            key, _eq, value = option.partition("=")
            if key.strip().lower() == "http-user-agent":
                agent = _header(value)
            elif key.strip().lower() in ("http-referrer", "http-referer"):
                referrer = _header(value)
        elif line.startswith("#"):
            continue
        else:
            if len(channels) >= MAX_CHANNELS:
                skipped += 1
                continue
            try:
                url = validate_stream_url(line)
            except PlaybackError:
                skipped += 1
            else:
                name = _clean(title or info.get("tvg-name", "") or url, MAX_NAME)
                channels.append(
                    Channel(
                        name=name,
                        url=url,
                        group=_clean(info.get("group-title", "") or group_line, MAX_GROUP),
                        tvg_id=_clean(info.get("tvg-id", ""), MAX_NAME),
                        logo=_web(info.get("tvg-logo", "") or info.get("logo", "")),
                        number=_number(info.get("tvg-chno", "") or info.get("channel-number", "")),
                        user_agent=agent,
                        referrer=referrer,
                    )
                )
            info, title, group_line, agent, referrer = {}, "", "", "", ""
    notes: tuple[str, ...] = ()
    if skipped:
        notes = (f"{skipped} entries were left out (addresses that aren't allowed, or over the limits)",)
    return ChannelList(tuple(channels), tuple(guides), skipped, notes)


def attributes(text: str) -> dict[str, str]:
    """key="value" pairs (also 'single' quoted or bare), lower-case keys; the first of a key wins."""
    found: dict[str, str] = {}
    for match in _ATTRIBUTE.finditer(text[:4000]):
        key = match.group(1).lower()
        value = next((g for g in match.groups()[1:] if g is not None), "")
        found.setdefault(key, value.strip()[:2048])
    return found


def _split_extinf(line: str) -> tuple[str, str, str]:
    """The name follows the first comma that isn't inside a quoted attribute."""
    quoted = False
    for index, char in enumerate(line):
        if char == '"':
            quoted = not quoted
        elif char == "," and not quoted:
            return line[:index], ",", line[index + 1 :]
    return line, "", ""


def _clean(text: str, limit: int) -> str:
    return " ".join("".join(c for c in text if c.isprintable()).split())[:limit]


def _header(value: str) -> str:
    value = value.strip().strip('"')
    return value[:MAX_HEADER] if value.isprintable() and value.isascii() else ""


def _number(text: str) -> int | None:
    text = text.strip()
    return int(text) if text.isdigit() and 0 < int(text) < 100_000 else None


def _web(url: str) -> str:
    if not url:
        return ""
    try:
        return validate_stream_url(url, WEB)
    except PlaybackError:
        return ""
