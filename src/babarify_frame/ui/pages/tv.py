"""The TV page (0.12): IPTV channel lists the user added, with groups, search, favourites and the TV guide.

Shown only while network streams are switched on. Babarify never includes or suggests channel lists.
"""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from babarify_frame.core.errors import PlaybackError
from babarify_frame.core.network import validate_stream_url
from babarify_frame.iptv.service import IptvService, IptvUpdate
from babarify_frame.iptv.store import ChannelEntry, GuideEntry
from babarify_frame.ui import theme
from babarify_frame.ui.bridge import UiBridge
from babarify_frame.ui.widgets import plain_text

ALL, FAVOURITES = "\0all", "\0favourites"  # not group names: a list can't produce a NUL
MAX_SHOWN = 5000
GUIDE_TICK_MS = 60_000
WEB = frozenset({"http", "https"})


def _label(text: str, name: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName(name)
    label.setWordWrap(True)
    plain_text(label)  # channel names and programme text come from the internet
    return label


def clock(seconds: float) -> str:
    return time.strftime("%H:%M", time.localtime(seconds))


class AddListDialog(QDialog):
    """A channel list from a web address or a file on this PC."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add a channel list")
        self.setMinimumWidth(560)
        box = QVBoxLayout(self)
        box.addWidget(QLabel("Name"))
        self.name = QLineEdit()
        self.name.setAccessibleName("Name of the channel list")
        self.name.setPlaceholderText("For example: Home TV")
        self.name.setMaxLength(120)
        box.addWidget(self.name)
        box.addWidget(QLabel("Address or file (M3U)"))
        row = QHBoxLayout()
        self.location = QLineEdit()
        self.location.setAccessibleName("Address or file of the channel list")
        self.location.setPlaceholderText("https://example.com/channels.m3u, or choose a file")
        self.location.setMaxLength(2048)
        browse = QPushButton("Choose file…")
        browse.clicked.connect(self._browse)
        row.addWidget(self.location, stretch=1)
        row.addWidget(browse)
        box.addLayout(row)
        self.problem = _label("", "caption")
        box.addWidget(self.problem)
        box.addWidget(
            _label(
                "Use a list from your TV provider. Babarify doesn't include or suggest channels, and only "
                "connects to the addresses in lists you add.",
                "muted",
            )
        )
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        box.addWidget(self.buttons)
        self.location.textChanged.connect(self._check)
        self._check()

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Channel list", "", "Channel lists (*.m3u *.m3u8);;All files (*)"
        )
        if path:
            self.location.setText(path)

    @property
    def value(self) -> str:
        """The checked location: a web address, or the path of an existing file. "" when not valid."""
        text = self.location.text().strip()
        if not text:
            return ""
        if "://" in text:
            try:
                return validate_stream_url(text, WEB)
            except PlaybackError:
                return ""
        return text if Path(text).is_file() else ""

    def _check(self) -> None:
        text = self.location.text().strip()
        ok = bool(self.value)
        if not text:
            self.problem.setText("")
        elif not ok and "://" in text:
            try:
                validate_stream_url(text, WEB)
            except PlaybackError as exc:
                self.problem.setText(exc.detail[:1].upper() + exc.detail[1:])
        elif not ok:
            self.problem.setText("That file doesn't exist.")
        else:
            self.problem.setText("")
        ok_button = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setEnabled(ok)


class TvPage(QWidget):
    play_requested = Signal(object)  # ChannelEntry
    status_changed = Signal(str)

    def __init__(self, service: IptvService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("page")
        self._service = service
        self._shown: list[ChannelEntry] = []  # the channels on show, for channel up and down
        outer = QVBoxLayout(self)
        outer.setContentsMargins(theme.XL, theme.L, theme.XL, theme.L)
        outer.setSpacing(theme.M)

        header = QHBoxLayout()
        header.addWidget(_label("TV", "title"), stretch=1)
        self.source = QComboBox()
        self.source.setAccessibleName("Channel list")
        self.source.setMinimumWidth(220)
        self.add_button = QPushButton("Add channel list…")
        self.add_button.setObjectName("primary")
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setToolTip("Read the channel list and its TV guide again")
        self.manage_button = QToolButton()
        self.manage_button.setText("Manage")
        self.manage_button.setAccessibleName("Manage the channel list")
        self.manage_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        manage = QMenu(self.manage_button)
        self.rename_action = manage.addAction("Rename…", self._rename)
        self.guide_action = manage.addAction("TV guide address…", self._guide_address)
        manage.addSeparator()
        self.remove_action = manage.addAction("Remove list…", self._remove)
        self.manage_button.setMenu(manage)
        for widget in (self.source, self.add_button, self.refresh_button, self.manage_button):
            header.addWidget(widget)
        outer.addLayout(header)
        self.status = _label("", "caption")
        outer.addWidget(self.status)

        self.empty = _label(
            "Add a channel list (M3U) from your TV provider, by web address or as a file on this PC. "
            "Babarify doesn't include or suggest channels.",
            "muted",
        )
        outer.addWidget(self.empty)

        body = QHBoxLayout()
        body.setSpacing(theme.L)
        self.groups = QListWidget()
        self.groups.setAccessibleName("Channel groups")
        self.groups.setMaximumWidth(240)
        self.groups.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.groups.customContextMenuRequested.connect(self._group_menu)
        body.addWidget(self.groups)
        middle = QVBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search channels")
        self.search.setAccessibleName("Search channels")
        self.search.setClearButtonEnabled(True)
        middle.addWidget(self.search)
        self.channels = QListWidget()
        self.channels.setAccessibleName("Channels")
        self.channels.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.channels.customContextMenuRequested.connect(self._channel_menu)
        middle.addWidget(self.channels, stretch=1)
        body.addLayout(middle, stretch=2)
        details = QVBoxLayout()
        self.detail_name = _label("", "subtitle")
        self.detail_now = _label("", "")
        self.detail_text = _label("", "muted")
        buttons = QHBoxLayout()
        self.play_button = QPushButton("Play")
        self.play_button.setObjectName("primary")
        self.favourite_button = QPushButton("Add to favourites")
        buttons.addWidget(self.play_button)
        buttons.addWidget(self.favourite_button)
        buttons.addStretch(1)
        self.schedule = QListWidget()
        self.schedule.setAccessibleName("TV guide for this channel")
        for label in (self.detail_name, self.detail_now, self.detail_text):
            details.addWidget(label)
        details.addLayout(buttons)
        details.addWidget(_label("Coming up", "caption"))
        details.addWidget(self.schedule, stretch=1)
        body.addLayout(details, stretch=2)
        outer.addLayout(body, stretch=1)

        self._bridge = UiBridge(self)
        self._bridge.delivered.connect(self._on_update)
        service.add_listener(self._bridge.post)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(200)
        self._search_timer.timeout.connect(self._fill_channels)
        self._guide_timer = QTimer(self)
        self._guide_timer.setInterval(GUIDE_TICK_MS)
        self._guide_timer.timeout.connect(self._fill_channels)  # "Now" moves on

        self.source.currentIndexChanged.connect(lambda _i: self._fill_groups())
        self.groups.currentRowChanged.connect(lambda _r: self._fill_channels())
        self.search.textChanged.connect(lambda _t: self._search_timer.start())
        self.channels.currentRowChanged.connect(lambda _r: self._show_details())
        self.channels.itemActivated.connect(lambda _i: self._play_selected())
        self.add_button.clicked.connect(self.add_list)
        self.refresh_button.clicked.connect(self._refresh_list)
        self.play_button.clicked.connect(self._play_selected)
        self.favourite_button.clicked.connect(self._toggle_favourite)
        self.refresh()

    # ------------------------------------------------------------ showing
    def showEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().showEvent(event)
        self._guide_timer.start()
        self._fill_channels()

    def hideEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self._guide_timer.stop()
        super().hideEvent(event)

    def refresh(self) -> None:
        """Lists, groups and channels from the library (after a change, or when shown)."""
        chosen = self.source.currentData()
        self.source.blockSignals(True)
        try:
            self.source.clear()
            sources = self._service.store.sources()
            if len(sources) > 1:
                self.source.addItem("All lists", None)
            for source in sources:
                self.source.addItem(source.name, source.id)
            index = self.source.findData(chosen)
            self.source.setCurrentIndex(index if index >= 0 else 0)
        finally:
            self.source.blockSignals(False)
        has = bool(sources)
        self.empty.setVisible(not has)
        for widget in (self.source, self.refresh_button, self.manage_button):
            widget.setEnabled(has)
        self._fill_groups()

    @property
    def source_id(self) -> int | None:
        value = self.source.currentData()
        return int(value) if value is not None else None

    def _fill_groups(self) -> None:
        current = self.groups.currentItem()
        chosen = current.data(Qt.ItemDataRole.UserRole) if current is not None else ALL
        self.groups.blockSignals(True)
        try:
            self.groups.clear()
            for label, key in (("All channels", ALL), ("Favourites", FAVOURITES)):
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, key)
                self.groups.addItem(item)
            source = self.source_id
            if source is not None:
                for name, count, hidden in self._service.store.groups(source):
                    if not name:
                        continue
                    item = QListWidgetItem(f"{name} ({count})" + (" · hidden" if hidden else ""))
                    item.setData(Qt.ItemDataRole.UserRole, name)
                    item.setData(Qt.ItemDataRole.UserRole + 1, hidden)
                    self.groups.addItem(item)
            rows = [self.groups.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.groups.count())]
            self.groups.setCurrentRow(rows.index(chosen) if chosen in rows else 0)
        finally:
            self.groups.blockSignals(False)
        self._show_status()
        self._fill_channels()

    def _fill_channels(self) -> None:
        item = self.groups.currentItem()
        key = item.data(Qt.ItemDataRole.UserRole) if item is not None else ALL
        group = None if key in (ALL, FAVOURITES) else str(key)
        selected = self.selected
        entries = self._service.store.channels(
            self.source_id, group, self.search.text(), favourites_only=key == FAVOURITES, limit=MAX_SHOWN
        )
        self._shown = entries
        guide = self._service.store.now_next([e.tvg_id for e in entries if e.tvg_id])
        self.channels.blockSignals(True)
        try:
            self.channels.clear()
            for entry in entries:
                text = f"{entry.number}  {entry.name}" if entry.number is not None else entry.name
                on = guide.get(entry.tvg_id, [])
                if on:
                    text += f"\n    {clock(on[0].start)}  {on[0].title}"
                item = QListWidgetItem(("♥ " if entry.favourite else "") + text)
                item.setData(Qt.ItemDataRole.UserRole, entry.id)
                self.channels.addItem(item)
            ids = [e.id for e in entries]
            if selected is not None and selected.id in ids:
                self.channels.setCurrentRow(ids.index(selected.id))
        finally:
            self.channels.blockSignals(False)
        self._show_details()

    def _show_status(self) -> None:
        source = self._service.store.source(self.source_id) if self.source_id is not None else None
        if source is None:
            self.status.setText("")
        elif source.last_error:
            self.status.setText(f"Couldn't read {source.name}: {source.last_error}")
        elif source.refreshed_at is None:
            self.status.setText("Reading the channel list…" if self._service.enabled else "")
        else:
            self.status.setText(f"{source.channel_count} channels · read {clock(source.refreshed_at)}")

    @property
    def selected(self) -> ChannelEntry | None:
        row = self.channels.currentRow()
        return self._shown[row] if 0 <= row < len(self._shown) else None

    def _show_details(self) -> None:
        entry = self.selected
        has = entry is not None
        self.play_button.setEnabled(has)
        self.favourite_button.setEnabled(has)
        self.schedule.clear()
        if entry is None:
            self.detail_name.setText("")
            self.detail_now.setText("")
            self.detail_text.setText("")
            return
        self.detail_name.setText(entry.name)
        self.favourite_button.setText("Remove from favourites" if entry.favourite else "Add to favourites")
        now = time.time()
        programmes: list[GuideEntry] = (
            self._service.store.programmes(entry.tvg_id, now, now + 24 * 3600) if entry.tvg_id else []
        )
        if programmes:
            first = programmes[0]
            self.detail_now.setText(f"Now: {first.title} ({clock(first.start)} - {clock(first.stop)})")
            self.detail_text.setText(" · ".join(t for t in (first.subtitle, first.description) if t))
        else:
            self.detail_now.setText("No TV guide for this channel")
            self.detail_text.setText(entry.group)
        for programme in programmes[1:]:
            self.schedule.addItem(f"{clock(programme.start)}  {programme.title}")

    # ------------------------------------------------------------ actions
    def add_list(self) -> AddListDialog:
        """Returns the dialog (tests drive it); the list is added when accepted."""
        dialog = AddListDialog(self)

        def added() -> None:
            location = dialog.value
            if location:
                name = dialog.name.text().strip() or Path(location).stem or "Channels"
                try:
                    self._service.add_list(name, location)
                except ValueError as exc:
                    QMessageBox.information(self, "Add a channel list", str(exc).capitalize())
                    return
                self.status_changed.emit(f"Reading {name}…")
                self.refresh()
                self.source.setCurrentIndex(self.source.count() - 1)

        dialog.accepted.connect(added)
        dialog.open()
        return dialog

    def _refresh_list(self) -> None:
        if self.source_id is not None:
            self._service.refresh(self.source_id)
        else:
            for source in self._service.store.sources():
                self._service.refresh(source.id)
        self.status.setText("Reading the channel list…")

    def _rename(self) -> None:
        source = self._service.store.source(self.source_id) if self.source_id is not None else None
        if source is None:
            return
        name, ok = QInputDialog.getText(self, "Rename channel list", "Name", text=source.name)
        if ok and name.strip():
            self._service.store.rename_source(source.id, name)
            self.refresh()

    def _guide_address(self) -> None:
        source = self._service.store.source(self.source_id) if self.source_id is not None else None
        if source is None:
            return
        text, ok = QInputDialog.getText(
            self, "TV guide", "TV guide address (XMLTV, .xml or .xml.gz)", text=source.guide_url
        )
        if not ok:
            return
        text = text.strip()
        if text:
            try:
                text = validate_stream_url(text, WEB)
            except PlaybackError as exc:
                QMessageBox.information(self, "TV guide", exc.detail[:1].upper() + exc.detail[1:])
                return
        self._service.store.set_guide_url(source.id, text)
        if text:
            self._service.refresh(source.id, guide_only=True)

    def _remove(self) -> None:
        source = self._service.store.source(self.source_id) if self.source_id is not None else None
        if source is None:
            return
        answer = QMessageBox.question(
            self, "Remove channel list", f"Remove {source.name} and its {source.channel_count} channels?"
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._service.store.remove_source(source.id)
            self.refresh()

    def _play_selected(self) -> None:
        entry = self.selected
        if entry is not None:
            self.play_requested.emit(entry)

    def _toggle_favourite(self) -> None:
        entry = self.selected
        if entry is not None:
            self._service.store.set_favourite(entry.url, not entry.favourite)
            self._fill_channels()

    def _group_menu(self, point: QPoint) -> None:
        item = self.groups.itemAt(point)
        source = self.source_id
        if item is None or source is None or item.data(Qt.ItemDataRole.UserRole) in (ALL, FAVOURITES):
            return
        hidden = bool(item.data(Qt.ItemDataRole.UserRole + 1))
        menu = QMenu(self)
        action = menu.addAction("Show this group" if hidden else "Hide this group")
        if menu.exec(self.groups.mapToGlobal(point)) is action:
            self._service.store.set_group_hidden(source, str(item.data(Qt.ItemDataRole.UserRole)), not hidden)
            self._fill_groups()

    def _channel_menu(self, point: QPoint) -> None:
        if self.channels.itemAt(point) is None or self.selected is None:
            return
        menu = QMenu(self)
        play = menu.addAction("Play")
        favourite = menu.addAction(
            "Remove from favourites" if self.selected.favourite else "Add to favourites"
        )
        chosen = menu.exec(self.channels.mapToGlobal(point))
        if chosen is play:
            self._play_selected()
        elif chosen is favourite:
            self._toggle_favourite()

    def neighbour(self, url: str | None, step: int) -> ChannelEntry | None:
        """The channel ``step`` places from ``url`` among those on show, wrapping round (channel up/down)."""
        if not self._shown:
            return None
        urls = [e.url for e in self._shown]
        index = urls.index(url) if url in urls else (-1 if step > 0 else 0)
        return self._shown[(index + step) % len(self._shown)]

    def _on_update(self, payload: object) -> None:
        if not isinstance(payload, IptvUpdate):
            return
        self.status_changed.emit(payload.message[:1].upper() + payload.message[1:])
        self.refresh()
