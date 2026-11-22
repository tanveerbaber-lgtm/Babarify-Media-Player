"""Downloads for IPTV (0.12): channel lists, TV guides and channel logos.

Everything goes through ``stream_proxy.open_web``: certificates are checked, there are time limits, and
redirects go only to other web addresses. Each download has a size limit and stops as soon as it is
passed. The only identification sent is a generic client name; a channel list's own user agent or referrer
is sent only to its own streams. Callers run these on a worker thread, never the window's.
"""

from __future__ import annotations

import http.client
import os
from collections.abc import Iterator, Mapping
from pathlib import Path

from babarify_frame import __version__
from babarify_frame.core.errors import PlaybackError
from babarify_frame.core.network import validate_stream_url
from babarify_frame.playback.stream_proxy import ProxyRefusal, open_web

USER_AGENT = f"Babarify Media Player/{__version__}"
CHUNK = 64 * 1024
WEB = frozenset({"http", "https"})


class FetchError(Exception):
    """A download failed; the message is worded for the user."""


def fetch_bytes(url: str, max_bytes: int, headers: Mapping[str, str] | None = None) -> bytes:
    chunks: list[bytes] = []
    for chunk in _stream(url, max_bytes, headers):
        chunks.append(chunk)
    return b"".join(chunks)


def fetch_to_file(url: str, target: Path, max_bytes: int) -> None:
    """Download into ``target`` through a temporary file, so a failed download never leaves half a file."""
    partial = target.with_name(target.name + ".partial")
    try:
        with partial.open("wb") as out:
            for chunk in _stream(url, max_bytes, None):
                out.write(chunk)
        os.replace(partial, target)
    finally:
        partial.unlink(missing_ok=True)


def read_local(path: str, max_bytes: int) -> bytes:
    """A channel list or guide chosen from this PC's files."""
    file = Path(path)
    try:
        size = file.stat().st_size
        if size > max_bytes:
            raise FetchError(f"the file is larger than {max_bytes // (1024 * 1024)} MB")
        return file.read_bytes()
    except OSError as exc:
        raise FetchError(f"the file could not be read ({exc.strerror or exc})") from exc


def _stream(url: str, max_bytes: int, headers: Mapping[str, str] | None) -> Iterator[bytes]:
    try:
        safe = validate_stream_url(url, WEB)
    except PlaybackError as exc:
        raise FetchError(exc.detail) from exc
    sent = {"User-Agent": USER_AGENT, "Accept-Encoding": "identity", **(headers or {})}
    conn: http.client.HTTPConnection | None = None
    try:
        try:
            _final, conn, response = open_web(safe, "GET", sent)
        except ProxyRefusal as exc:
            raise FetchError(exc.reason) from exc
        length = response.getheader("Content-Length")
        if length and length.isdigit() and int(length) > max_bytes:
            raise FetchError(f"the download is larger than {max_bytes // (1024 * 1024)} MB")
        received = 0
        while True:
            try:
                chunk = response.read(CHUNK)
            except (OSError, http.client.HTTPException) as exc:
                raise FetchError(f"the download stopped ({exc})") from exc
            if not chunk:
                return
            received += len(chunk)
            if received > max_bytes:
                raise FetchError(f"the download is larger than {max_bytes // (1024 * 1024)} MB")
            yield chunk
    finally:
        if conn is not None:
            conn.close()
