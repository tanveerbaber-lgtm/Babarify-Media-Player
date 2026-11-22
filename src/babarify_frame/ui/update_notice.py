"""Telling the user a new version is out (0.12): a quiet strip above the pages, and Help → Check for updates.

The check runs on a worker thread; the window never waits. Download opens the release page on github.com in
the browser; nothing is downloaded or installed by the app.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from babarify_frame.core.updates import MAX_ANSWER_BYTES, RELEASES_API, RELEASES_PAGE, Release, newest_release
from babarify_frame.iptv.fetch import FetchError, fetch_bytes
from babarify_frame.ui import theme
from babarify_frame.ui.bridge import UiBridge
from babarify_frame.ui.widgets import plain_text


@dataclass(frozen=True)
class UpdateResult:
    manual: bool
    release: Release | None
    error: str = ""


class UpdateChecker:
    """Asks GitHub once per call, on its own thread; the result arrives on the window's thread."""

    def __init__(self, bridge: UiBridge) -> None:
        self._bridge = bridge
        self._running = False

    def check(self, manual: bool) -> bool:
        if self._running:
            return False
        self._running = True
        threading.Thread(target=self._run, args=(manual,), name="update-check", daemon=True).start()
        return True

    def _run(self, manual: bool) -> None:
        try:
            answer = fetch_bytes(RELEASES_API, MAX_ANSWER_BYTES, {"Accept": "application/vnd.github+json"})
            result = UpdateResult(manual, newest_release(answer))
        except (FetchError, ValueError) as exc:
            result = UpdateResult(manual, None, str(exc))
        finally:
            self._running = False
        self._bridge.post(result)


def open_release_page(release: Release) -> bool:
    """Only this project's release pages on github.com are opened."""
    if not release.page.startswith(RELEASES_PAGE):
        return False
    return QDesktopServices.openUrl(QUrl(release.page))


class WhatsNewDialog(QDialog):
    def __init__(self, release: Release, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"What's new in {release.version}")
        self.setMinimumSize(560, 420)
        box = QVBoxLayout(self)
        title = QLabel(release.name)
        title.setObjectName("subtitle")
        plain_text(title)
        box.addWidget(title)
        notes = QPlainTextEdit(release.notes or "No release notes.")  # plain text: never rendered as HTML
        notes.setReadOnly(True)
        notes.setAccessibleName("Release notes")
        box.addWidget(notes, stretch=1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        download = buttons.addButton("Download", QDialogButtonBox.ButtonRole.AcceptRole)
        download.setObjectName("primary")
        download.clicked.connect(lambda: open_release_page(release))
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        box.addWidget(buttons)


class UpdateBar(QFrame):
    """A strip saying a newer version is available, with What's new, Download, Later and Skip."""

    skipped = Signal(str)  # the version not to mention again

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.release: Release | None = None
        row = QHBoxLayout(self)
        row.setContentsMargins(theme.L, theme.S, theme.L, theme.S)
        self.text = QLabel()
        self.text.setAccessibleName("Update available")
        plain_text(self.text)
        row.addWidget(self.text, stretch=1)
        self.whats_new = QPushButton("What's new")
        self.download = QPushButton("Download")
        self.download.setObjectName("primary")
        self.later = QPushButton("Later")
        self.skip = QPushButton("Skip this version")
        for button in (self.whats_new, self.download, self.later, self.skip):
            row.addWidget(button, alignment=Qt.AlignmentFlag.AlignVCenter)
        self.whats_new.clicked.connect(self.show_notes)
        self.download.clicked.connect(lambda: self.release is not None and open_release_page(self.release))
        self.later.clicked.connect(self.hide)
        self.skip.clicked.connect(self._skip)
        self.hide()

    def offer(self, release: Release) -> None:
        self.release = release
        self.text.setText(f"Babarify Media Player {release.version} is available.")
        self.show()

    def show_notes(self) -> WhatsNewDialog | None:
        if self.release is None:
            return None
        dialog = WhatsNewDialog(self.release, self)
        dialog.open()
        return dialog

    def _skip(self) -> None:
        if self.release is not None:
            self.skipped.emit(self.release.version)
        self.hide()
