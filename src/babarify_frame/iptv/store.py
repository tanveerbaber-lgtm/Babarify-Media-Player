"""IPTV in the library database (0.12): channel lists the user added, their channels, favourites, hidden
groups and the TV guide. Channels never mix with Music or Videos."""

from __future__ import annotations

import time
from collections.abc import Iterable
from dataclasses import dataclass

from babarify_frame.iptv.m3u import ChannelList
from babarify_frame.iptv.xmltv import WINDOW_BEFORE, Programme
from babarify_frame.library.database import LibraryDatabase

MAX_SOURCES = 20
BATCH = 2000


@dataclass(frozen=True)
class Source:
    id: int
    name: str
    location: str  # a web address or a file on this PC
    guide_url: str
    refreshed_at: float | None
    guide_refreshed_at: float | None
    last_error: str
    channel_count: int


@dataclass(frozen=True)
class ChannelEntry:
    id: int
    source_id: int
    name: str
    url: str
    group: str
    tvg_id: str
    logo: str
    number: int | None
    user_agent: str
    referrer: str
    favourite: bool


@dataclass(frozen=True)
class GuideEntry:
    title: str
    start: float
    stop: float
    subtitle: str = ""
    description: str = ""
    category: str = ""


class IptvStore:
    def __init__(self, db: LibraryDatabase) -> None:
        self._db = db

    # ------------------------------------------------------------ sources
    def add_source(self, name: str, location: str, guide_url: str = "") -> int:
        if len(self.sources()) >= MAX_SOURCES:
            raise ValueError(f"at most {MAX_SOURCES} channel lists")
        with self._db._transaction() as conn:
            cur = conn.execute(
                "INSERT INTO iptv_sources(name, location, guide_url, added_at) VALUES (?, ?, ?, ?)",
                (name.strip()[:120] or "Channels", location, guide_url, time.time()),
            )
            return int(cur.lastrowid or 0)

    def sources(self) -> list[Source]:
        rows = self._db._query(
            """SELECT s.*, (SELECT COUNT(*) FROM iptv_channels c WHERE c.source_id = s.id) AS n
               FROM iptv_sources s ORDER BY s.name COLLATE NOCASE, s.id"""
        )
        return [
            Source(r["id"], r["name"], r["location"], r["guide_url"], r["refreshed_at"],
                   r["guide_refreshed_at"], r["last_error"], r["n"])
            for r in rows
        ]  # fmt: skip

    def source(self, source_id: int) -> Source | None:
        return next((s for s in self.sources() if s.id == source_id), None)

    def rename_source(self, source_id: int, name: str) -> None:
        with self._db._transaction() as conn:
            conn.execute("UPDATE iptv_sources SET name = ? WHERE id = ?", (name.strip()[:120], source_id))

    def set_guide_url(self, source_id: int, url: str) -> None:
        with self._db._transaction() as conn:
            conn.execute("UPDATE iptv_sources SET guide_url = ? WHERE id = ?", (url, source_id))

    def remove_source(self, source_id: int) -> None:
        with self._db._transaction() as conn:
            conn.execute("DELETE FROM iptv_sources WHERE id = ?", (source_id,))  # channels go with it

    def set_error(self, source_id: int, message: str) -> None:
        with self._db._transaction() as conn:
            conn.execute("UPDATE iptv_sources SET last_error = ? WHERE id = ?", (message[:300], source_id))

    def replace_channels(self, source_id: int, found: ChannelList) -> None:
        """A list was read again: its channels are replaced as one change (favourites are kept by address)."""
        with self._db._transaction() as conn:
            conn.execute("DELETE FROM iptv_channels WHERE source_id = ?", (source_id,))
            conn.executemany(
                """INSERT INTO iptv_channels(source_id, position, name, url, group_name, tvg_id, logo, number,
                   user_agent, referrer) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        source_id,
                        i,
                        c.name,
                        c.url,
                        c.group,
                        c.tvg_id,
                        c.logo,
                        c.number,
                        c.user_agent,
                        c.referrer,
                    )
                    for i, c in enumerate(found.channels)
                ],
            )
            conn.execute(
                """UPDATE iptv_sources SET refreshed_at = ?, last_error = '',
                   guide_url = CASE WHEN guide_url = '' THEN ? ELSE guide_url END WHERE id = ?""",
                (time.time(), found.guide_urls[0] if found.guide_urls else "", source_id),
            )

    # ------------------------------------------------------------ channels
    def channels(
        self,
        source_id: int | None = None,
        group: str | None = None,
        search: str = "",
        favourites_only: bool = False,
        limit: int = 50_000,
    ) -> list[ChannelEntry]:
        clauses = [
            "NOT EXISTS (SELECT 1 FROM iptv_hidden_groups h WHERE h.source_id = c.source_id"
            " AND h.group_name = c.group_name)"
        ]
        params: list[object] = []
        if source_id is not None:
            clauses.append("c.source_id = ?")
            params.append(source_id)
        if group is not None:
            clauses.append("c.group_name = ?")
            params.append(group)
        for word in search.split()[:8]:
            clauses.append("(c.name LIKE ? ESCAPE '\\' OR c.group_name LIKE ? ESCAPE '\\')")
            like = "%" + word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            params += [like, like]
        if favourites_only:
            clauses.append("f.url IS NOT NULL")
        rows = self._db._query(
            f"""SELECT c.*, f.url AS fav FROM iptv_channels c LEFT JOIN iptv_favourites f ON f.url = c.url
                WHERE {" AND ".join(clauses)}
                ORDER BY c.number IS NULL, c.number, c.source_id, c.position LIMIT ?""",
            (*params, limit),
        )
        return [self._entry(r) for r in rows]

    def channel(self, channel_id: int) -> ChannelEntry | None:
        rows = self._db._query(
            """SELECT c.*, f.url AS fav FROM iptv_channels c LEFT JOIN iptv_favourites f ON f.url = c.url
               WHERE c.id = ?""",
            (channel_id,),
        )
        return self._entry(rows[0]) if rows else None

    @staticmethod
    def _entry(r) -> ChannelEntry:  # type: ignore[no-untyped-def]
        return ChannelEntry(
            r["id"], r["source_id"], r["name"], r["url"], r["group_name"], r["tvg_id"], r["logo"],
            r["number"], r["user_agent"], r["referrer"], r["fav"] is not None,
        )  # fmt: skip

    def groups(self, source_id: int) -> list[tuple[str, int, bool]]:
        """(group, channels, hidden), in the list's own order."""
        rows = self._db._query(
            """SELECT c.group_name AS g, COUNT(*) AS n, MIN(c.position) AS first,
                      EXISTS (SELECT 1 FROM iptv_hidden_groups h
                              WHERE h.source_id = ? AND h.group_name = c.group_name) AS hidden
               FROM iptv_channels c WHERE c.source_id = ? GROUP BY c.group_name ORDER BY first""",
            (source_id, source_id),
        )
        return [(r["g"], r["n"], bool(r["hidden"])) for r in rows]

    def set_group_hidden(self, source_id: int, group: str, hidden: bool) -> None:
        with self._db._transaction() as conn:
            if hidden:
                conn.execute(
                    "INSERT OR IGNORE INTO iptv_hidden_groups(source_id, group_name) VALUES (?, ?)",
                    (source_id, group),
                )
            else:
                conn.execute(
                    "DELETE FROM iptv_hidden_groups WHERE source_id = ? AND group_name = ?",
                    (source_id, group),
                )

    def set_favourite(self, url: str, favourite: bool) -> None:
        with self._db._transaction() as conn:
            if favourite:
                conn.execute(
                    "INSERT OR IGNORE INTO iptv_favourites(url, added_at) VALUES (?, ?)", (url, time.time())
                )
            else:
                conn.execute("DELETE FROM iptv_favourites WHERE url = ?", (url,))

    # ------------------------------------------------------------ TV guide
    def tvg_ids(self) -> set[str]:
        return {r[0] for r in self._db._query("SELECT DISTINCT tvg_id FROM iptv_channels WHERE tvg_id <> ''")}

    def replace_programmes(self, source_id: int, tvg_ids: set[str], programmes: Iterable[Programme]) -> int:
        """A guide was read again: its channels' programmes are replaced. Returns how many were stored.
        Reading happens while storing (in batches), so a large guide is never in memory at once."""
        stored = 0
        with self._db._transaction() as conn:
            cutoff = time.time() - WINDOW_BEFORE.total_seconds()
            conn.execute("DELETE FROM iptv_programmes WHERE stop < ?", (cutoff,))
            conn.executemany("DELETE FROM iptv_programmes WHERE tvg_id = ?", [(t,) for t in tvg_ids])
            batch: list[tuple[object, ...]] = []
            for p in programmes:
                batch.append((p.channel, p.start, p.stop, p.title, p.subtitle, p.description, p.category))
                if len(batch) >= BATCH:
                    conn.executemany("INSERT INTO iptv_programmes VALUES (?, ?, ?, ?, ?, ?, ?)", batch)
                    stored += len(batch)
                    batch.clear()
            conn.executemany("INSERT INTO iptv_programmes VALUES (?, ?, ?, ?, ?, ?, ?)", batch)
            stored += len(batch)
            conn.execute(
                "UPDATE iptv_sources SET guide_refreshed_at = ? WHERE id = ?", (time.time(), source_id)
            )
        return stored

    def now_next(self, tvg_ids: Iterable[str], now: float | None = None) -> dict[str, list[GuideEntry]]:
        """For each channel id: what's on now and what's next (one or two entries)."""
        when = time.time() if now is None else now
        found: dict[str, list[GuideEntry]] = {}
        ids = [t for t in set(tvg_ids) if t]
        for start in range(0, len(ids), 500):
            chunk = ids[start : start + 500]
            marks = ",".join("?" * len(chunk))
            rows = self._db._query(
                f"""SELECT * FROM iptv_programmes WHERE tvg_id IN ({marks}) AND stop > ? AND start < ?
                    ORDER BY tvg_id, start""",
                (*chunk, when, when + 12 * 3600),
            )
            for r in rows:
                entries = found.setdefault(r["tvg_id"], [])
                if len(entries) < 2:
                    entries.append(self._guide(r))
        return found

    def programmes(self, tvg_id: str, start: float, stop: float) -> list[GuideEntry]:
        rows = self._db._query(
            "SELECT * FROM iptv_programmes WHERE tvg_id = ? AND stop > ? AND start < ?"
            " ORDER BY start LIMIT 500",
            (tvg_id, start, stop),
        )
        return [self._guide(r) for r in rows]

    @staticmethod
    def _guide(r) -> GuideEntry:  # type: ignore[no-untyped-def]
        return GuideEntry(r["title"], r["start"], r["stop"], r["subtitle"], r["description"], r["category"])
