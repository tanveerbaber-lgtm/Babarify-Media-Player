"""Update notifications (0.12): reading GitHub's release list safely."""

from __future__ import annotations

import json

import pytest

from babarify_frame.core.updates import RELEASES_PAGE, is_newer, newest_release, version_key


def release(tag: str, *, draft: bool = False, page: str | None = None, body: str = "What's new") -> dict:  # type: ignore[type-arg]
    return {
        "tag_name": tag,
        "name": f"Babarify Media Player {tag.lstrip('v')} (public beta)",
        "html_url": page if page is not None else f"{RELEASES_PAGE}tag/{tag}",
        "draft": draft,
        "prerelease": True,
        "body": body,
    }


def answer(*items: object) -> bytes:
    return json.dumps(list(items)).encode()


def test_versions_compare_as_numbers() -> None:
    assert version_key("v0.12.0") == (0, 12, 0, 0) and version_key("0.12.0.3") == (0, 12, 0, 3)
    assert is_newer("v0.12.0", "0.11.0") and is_newer("0.10.10", "0.10.9")
    assert not is_newer("v0.11.0", "0.11.0") and not is_newer("0.9.9", "0.11.0")
    assert not is_newer("latest", "0.11.0") and version_key("0.12") is None


def test_the_newest_newer_release_is_chosen() -> None:
    found = newest_release(
        answer(release("v0.11.0"), release("v0.12.1"), release("v0.12.0")), current="0.11.0"
    )
    assert found is not None and found.version == "0.12.1" and found.page.endswith("/tag/v0.12.1")
    assert found.name == "Babarify Media Player 0.12.1 (public beta)" and found.notes == "What's new"


def test_nothing_when_up_to_date() -> None:
    assert newest_release(answer(release("v0.11.0"), release("v0.10.0")), current="0.11.0") is None
    assert newest_release(answer(), current="0.11.0") is None


@pytest.mark.parametrize(
    "item",
    [
        release("v9.0.0", draft=True),
        release("v9.0.0", page="https://example.com/fake-release"),
        release("v9.0.0", page="https://github.com/someone-else/Babarify/releases/tag/v9.0.0"),
        release("nine"),
        {"tag_name": 9, "html_url": RELEASES_PAGE},
        "not a release",
    ],
    ids=["draft", "other site", "other repository", "not a version", "wrong types", "not an object"],
)
def test_untrusted_entries_are_ignored(item: object) -> None:
    assert newest_release(answer(item), current="0.11.0") is None


def test_notes_are_plain_trimmed_text() -> None:
    found = newest_release(answer(release("v0.12.0", body="Line one\n‮Tricky\u0007\n" + "x" * 9000)), "0.11.0")
    assert found is not None and "‮" not in found.notes and "\u0007" not in found.notes
    assert found.notes.startswith("Line one\nTricky") and len(found.notes) == 4000


@pytest.mark.parametrize(
    "data",
    [b"not json", b'{"message": "rate limited"}', b"\xff\xfe", b"[" * 2_000_000],
    ids=["not json", "an error object", "not utf-8", "too large"],
)
def test_unreadable_answers_are_reported(data: bytes) -> None:
    with pytest.raises(ValueError):
        newest_release(data, current="0.11.0")
