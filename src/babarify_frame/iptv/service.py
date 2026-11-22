"""Keeping IPTV channel lists and TV guides up to date (0.12), on one worker thread.

Nothing happens while network streams are switched off: jobs are refused, and nothing is fetched. Lists are
read again once a day, guides once every GUIDE_REFRESH_S; both on request too. Results reach the window
through ``UiBridge``; the window never waits for a download.
"""

from __future__ import annotations

import logging
import queue
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from babarify_frame.core.network import is_network_uri
from babarify_frame.iptv import m3u, xmltv
from babarify_frame.iptv.fetch import FetchError, fetch_bytes, fetch_to_file, read_local
from babarify_frame.iptv.store import IptvStore

log = logging.getLogger(__name__)

LIST_REFRESH_S = 24 * 3600
GUIDE_REFRESH_S = 12 * 3600
MAX_GUIDE_DOWNLOAD = 150 * 1024 * 1024  # compressed or not; unpacked, xmltv's own limit applies


@dataclass(frozen=True)
class IptvUpdate:
    """Sent to listeners when something changed: a list or guide was read, or failed."""

    source_id: int
    what: str  # "list" or "guide"
    ok: bool
    message: str


class IptvService:
    def __init__(self, store: IptvStore, cache_dir: Path | None = None) -> None:
        self.store = store
        self._cache = cache_dir or Path(tempfile.gettempdir())
        self._jobs: queue.Queue[tuple[str, int] | None] = queue.Queue()
        self._pending: set[tuple[str, int]] = set()
        self._lock = threading.Lock()
        self._listeners: list[Callable[[IptvUpdate], None]] = []
        self._enabled = False
        self._thread: threading.Thread | None = None
        self.busy = False

    # ------------------------------------------------------------ control
    def add_listener(self, listener: Callable[[IptvUpdate], None]) -> None:
        self._listeners.append(listener)

    def set_enabled(self, enabled: bool) -> None:
        """Network streams switched on or off. Off: queued jobs are dropped and nothing new starts."""
        self._enabled = enabled
        if not enabled:
            with self._lock:
                self._pending.clear()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def add_list(self, name: str, location: str) -> int:
        source_id = self.store.add_source(name, location)
        self.refresh(source_id)
        return source_id

    def refresh(self, source_id: int, guide_only: bool = False) -> None:
        self._queue("guide" if guide_only else "list", source_id)

    def refresh_due(self, now: float | None = None) -> None:
        """Lists not read for a day, guides not read for GUIDE_REFRESH_S (at start, and now and then)."""
        when = time.time() if now is None else now
        for source in self.store.sources():
            if not source.refreshed_at or when - source.refreshed_at > LIST_REFRESH_S:
                self._queue("list", source.id)
            elif source.guide_url and (
                not source.guide_refreshed_at or when - source.guide_refreshed_at > GUIDE_REFRESH_S
            ):
                self._queue("guide", source.id)

    def shutdown(self) -> None:
        self._enabled = False
        self._jobs.put(None)
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _queue(self, what: str, source_id: int) -> None:
        if not self._enabled:
            return
        with self._lock:
            if (what, source_id) in self._pending:
                return
            self._pending.add((what, source_id))
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="iptv", daemon=True)
            self._thread.start()
        self._jobs.put((what, source_id))

    # ------------------------------------------------------------ worker
    def _run(self) -> None:
        while True:
            job = self._jobs.get()
            if job is None:
                return
            with self._lock:
                if job not in self._pending:
                    continue  # switched off meanwhile
                self._pending.discard(job)
            if not self._enabled:
                continue
            what, source_id = job
            self.busy = True
            try:
                update = self._read_list(source_id) if what == "list" else self._read_guide(source_id)
            except Exception as exc:  # a list or guide must never take the app down
                log.exception("iptv %s failed", what)
                update = IptvUpdate(source_id, what, False, f"something went wrong ({exc})")
            finally:
                self.busy = False
            if not update.ok:
                self.store.set_error(source_id, update.message)
            for listener in list(self._listeners):
                try:
                    listener(update)
                except Exception:
                    log.exception("iptv listener failed")

    def _read_list(self, source_id: int) -> IptvUpdate:
        source = self.store.source(source_id)
        if source is None:
            return IptvUpdate(source_id, "list", False, "the channel list was removed")
        try:
            data = (
                fetch_bytes(source.location, m3u.MAX_BYTES)
                if is_network_uri(source.location)
                else read_local(source.location, m3u.MAX_BYTES)
            )
            found = m3u.parse(data)
        except (FetchError, m3u.PlaylistError) as exc:
            return IptvUpdate(source_id, "list", False, str(exc))
        self.store.replace_channels(source_id, found)
        message = f"{len(found.channels)} channels"
        if found.skipped:
            message += f" · {found.skipped} entries left out"
        refreshed = self.store.source(source_id)
        if refreshed is not None and refreshed.guide_url:
            self._queue("guide", source_id)
        return IptvUpdate(source_id, "list", True, message)

    def _read_guide(self, source_id: int) -> IptvUpdate:
        source = self.store.source(source_id)
        if source is None or not source.guide_url:
            return IptvUpdate(source_id, "guide", False, "this channel list has no TV guide")
        self._cache.mkdir(parents=True, exist_ok=True)
        target = self._cache / f"guide-{source_id}.download"
        try:
            if is_network_uri(source.guide_url):
                fetch_to_file(source.guide_url, target, MAX_GUIDE_DOWNLOAD)
            else:
                target.write_bytes(read_local(source.guide_url, MAX_GUIDE_DOWNLOAD))
            wanted = self.store.tvg_ids()
            with target.open("rb") as raw:
                _channels, programmes = xmltv.read(raw, wanted)
                stored = self.store.replace_programmes(source_id, wanted, programmes)
        except (FetchError, xmltv.GuideError, OSError) as exc:
            return IptvUpdate(source_id, "guide", False, f"TV guide: {exc}")
        finally:
            target.unlink(missing_ok=True)
        return IptvUpdate(source_id, "guide", True, f"TV guide: {stored} programmes")
