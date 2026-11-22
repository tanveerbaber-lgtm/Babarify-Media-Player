"""One running copy (0.12): a later start hands its file to the open window over a local pipe."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from babarify_frame.ui import single_instance
from babarify_frame.ui.single_instance import InstanceServer, hand_over, parse_message, server_name


@pytest.fixture
def server(qtbot: QtBot) -> Iterator[tuple[InstanceServer, str]]:
    name = f"babarify-test-{uuid.uuid4().hex}"
    found = InstanceServer()
    assert found.listen(name)
    yield found, name
    found.close()


SECOND_START = """
import sys
from PySide6.QtWidgets import QApplication
app = QApplication([])
from babarify_frame.ui.single_instance import hand_over
print("handed over" if hand_over(sys.argv[2] or None, sys.argv[1]) else "not handed over")
"""


def later_start(path: str | None, name: str) -> subprocess.Popen[str]:
    """A second copy of the app: its own process, as when a file is opened from Explorer."""
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[2] / "src"))
    return subprocess.Popen(
        [sys.executable, "-c", SECOND_START, name, path or ""], stdout=subprocess.PIPE, text=True, env=env
    )


@pytest.mark.parametrize("path", [r"C:\Music\Ünïcode song (1).flac", None], ids=["file", "no file"])
def test_a_later_start_hands_its_file_over(
    server: tuple[InstanceServer, str], qtbot: QtBot, path: str | None
) -> None:
    listener, name = server
    with qtbot.waitSignal(listener.open_requested, timeout=15000) as signal:
        second = later_start(path, name)
    assert signal.args == [path or ""]  # no file: just show the window
    qtbot.waitUntil(lambda: second.poll() is not None, timeout=15000)
    assert second.stdout is not None and second.stdout.read().strip() == "handed over"  # it was confirmed


def test_no_running_copy_means_this_one_runs() -> None:
    assert not hand_over("C:/a.mp3", f"babarify-test-{uuid.uuid4().hex}")


@pytest.mark.parametrize(
    "data",
    [b"", b"not json", b"[1]", b'{"open": 5}', b'{"other": "x"}', json.dumps({"open": "a\0b"}).encode(),
     json.dumps({"open": "x" * 40_000}).encode(), b"\xff\xfe"],
    ids=["empty", "not json", "list", "number", "other key", "nul", "too long", "not utf-8"],
)  # fmt: skip
def test_anything_but_a_path_is_ignored(data: bytes) -> None:
    assert parse_message(data) is None


def test_each_settings_folder_has_its_own_copy(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BABARIFY_CONFIG_DIR", str(tmp_path / "one"))
    one = server_name()
    monkeypatch.setenv("BABARIFY_CONFIG_DIR", str(tmp_path / "two"))
    assert server_name() != one and one.startswith(single_instance.SERVER_PREFIX)
