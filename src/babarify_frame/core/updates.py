"""Is there a newer Babarify Media Player? (0.12)

Asks GitHub for the project's recent releases, at most once a day, unless switched off in Settings. Only a
generic client name is sent. The answer is untrusted: it is size-limited, only releases of this repository
count, the release page must be on github.com under it, and the notes are shown as plain text. Nothing is
downloaded or installed: the user opens the release page in their browser.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from babarify_frame import __version__

OWNER_REPO = "tanveerbaber-lgtm/Babarify-Media-Player"
RELEASES_API = f"https://api.github.com/repos/{OWNER_REPO}/releases?per_page=10"
RELEASES_PAGE = f"https://github.com/{OWNER_REPO}/releases/"
MAX_ANSWER_BYTES = 1024 * 1024
MAX_NOTES = 4000
CHECK_EVERY_S = 24 * 3600
_VERSION = re.compile(r"^v?(\d{1,4})\.(\d{1,4})\.(\d{1,4})(?:\.(\d{1,6}))?$")


@dataclass(frozen=True)
class Release:
    version: str  # "0.12.0"
    name: str
    page: str  # the release page on github.com
    notes: str  # plain text, trimmed


def version_key(text: str) -> tuple[int, int, int, int] | None:
    """(major, minor, patch, build) for "0.12.0", "v0.12.0" or a test build "0.12.0.3"; None otherwise."""
    match = _VERSION.match(text.strip())
    if not match:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)), int(match.group(4) or 0))


def is_newer(candidate: str, current: str = __version__) -> bool:
    new, old = version_key(candidate), version_key(current)
    return new is not None and old is not None and new > old


def newest_release(answer: bytes, current: str = __version__) -> Release | None:
    """The newest published release newer than ``current`` in GitHub's answer, or None."""
    if len(answer) > MAX_ANSWER_BYTES:
        raise ValueError("the answer from GitHub is too large")
    try:
        releases = json.loads(answer.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError("the answer from GitHub could not be read") from exc
    if not isinstance(releases, list):
        raise ValueError("the answer from GitHub could not be read")
    best: Release | None = None
    best_key: tuple[int, int, int, int] | None = None
    for item in releases[:50]:
        if not isinstance(item, dict) or item.get("draft"):
            continue
        tag, page = item.get("tag_name"), item.get("html_url")
        if not isinstance(tag, str) or not isinstance(page, str) or not page.startswith(RELEASES_PAGE):
            continue
        key = version_key(tag)
        if key is None or not is_newer(tag, current) or (best_key is not None and key <= best_key):
            continue
        name = item.get("name") if isinstance(item.get("name"), str) else tag
        notes = item.get("body") if isinstance(item.get("body"), str) else ""
        best_key = key
        best = Release(
            tag.lstrip("v"), _plain(str(name), 200), page, _plain(str(notes), MAX_NOTES, lines=True)
        )
    return best


def _plain(text: str, limit: int, lines: bool = False) -> str:
    kept = "".join(c for c in text if c.isprintable() or (lines and c in "\n\t"))
    return kept.strip()[:limit]
