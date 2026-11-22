"""The mini-player (M3): a small window with what is playing and its controls, instead of the main window.

It controls the same player as the main window, so playback carries on unchanged when switching between them.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QHideEvent, QIcon, QShowEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSlider, QToolButton, QVBoxLayout, QWidget

from babarify_frame.core.models import PlaybackState
from babarify_frame.ui import theme
from babarify_frame.ui.pages.player import PlayerPage
from babarify_frame.ui.widgets import format_time, glyph_icon, plain_text

SIZE = (420, 128)
POSITION_POLL_MS = 500


def _button(glyph: str, name: str, fallback: str) -> QToolButton:
    button = QToolButton()
    button.setAccessibleName(name)
    button.setToolTip(name)
    icon = glyph_icon(glyph, theme.TEXT, theme.TEXT_DISABLED, size=48)
    if icon is not None:
        button.setIcon(icon)
    else:
        button.setText(fallback)
    button.setAutoRaise(True)
    button.setFixedSize(40, 40)
    return button


class MiniPlayer(QWidget):
    back_requested = Signal()  # back to the main window
    activated = Signal()  # it became the active window

    def __init__(self, player: PlayerPage, icon: QIcon) -> None:
        super().__init__(None, Qt.WindowType.Window)
        self.setObjectName("page")
        self.setWindowTitle("Babarify mini player")
        self.setWindowIcon(icon)
        self.setFixedSize(*SIZE)
        self._player = player
        box = QVBoxLayout(self)
        box.setContentsMargins(theme.M, theme.S, theme.M, theme.S)
        box.setSpacing(theme.XS)
        self.title = QLabel("Nothing is playing")
        self.title.setAccessibleName("Now playing")
        plain_text(self.title)  # file names are untrusted text
        box.addWidget(self.title)
        seek_row = QHBoxLayout()
        self.seek = QSlider(Qt.Orientation.Horizontal)
        self.seek.setAccessibleName("Position")
        self.seek.sliderReleased.connect(lambda: self._player.seek_to(self.seek.value()))
        self.time = QLabel("00:00")
        seek_row.addWidget(self.seek, stretch=1)
        seek_row.addWidget(self.time)
        box.addLayout(seek_row)
        buttons = QHBoxLayout()
        self.previous_button = _button("previous", "Previous", "⏮")
        self.play_button = _button("play", "Play or pause", "⏯")
        self.next_button = _button("next", "Next", "⏭")
        self.back_button = _button("fullscreen", "Back to the full window", "⤢")
        self.previous_button.clicked.connect(self._player.previous_in_queue)
        self.play_button.clicked.connect(self._player.toggle_play_pause)
        self.next_button.clicked.connect(self._player.next_in_queue)
        self.back_button.clicked.connect(self.back_requested)
        buttons.addStretch(1)
        for button in (self.previous_button, self.play_button, self.next_button):
            buttons.addWidget(button)
        buttons.addStretch(1)
        buttons.addWidget(self.back_button)
        box.addLayout(buttons)
        player.title_changed.connect(self._set_title)
        player.state_changed.connect(lambda _state: self._update())
        player.queue_changed.connect(self._update)
        self._timer = QTimer(self)
        self._timer.setInterval(POSITION_POLL_MS)
        self._timer.timeout.connect(self._update)
        self._set_title(player.media_name)

    def _set_title(self, name: str) -> None:
        self.title.setText(name or "Nothing is playing")

    def showEvent(self, event: QShowEvent) -> None:
        self._timer.start()
        self._update()
        super().showEvent(event)

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.ActivationChange and self.isActiveWindow():
            self.activated.emit()

    def hideEvent(self, event: QHideEvent) -> None:
        self._timer.stop()
        super().hideEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Closing the mini-player brings the main window back; it never ends playback."""
        event.ignore()
        self.back_requested.emit()

    def _update(self) -> None:
        player = self._player
        playing = player.state is PlaybackState.PLAYING
        icon = glyph_icon("pause" if playing else "play", theme.TEXT, theme.TEXT_DISABLED, size=48)
        if icon is not None:
            self.play_button.setIcon(icon)
        self.play_button.setAccessibleName("Pause" if playing else "Play")
        self.play_button.setEnabled(player.has_media)
        self.previous_button.setEnabled(player.can_go_previous)
        self.next_button.setEnabled(player.can_go_next)
        duration = player.duration_ms or 0
        position = player.position_ms if player.has_media else 0
        self.seek.setEnabled(player.is_seekable and duration > 0)
        if not self.seek.isSliderDown():
            self.seek.setRange(0, max(0, duration))
            self.seek.setValue(min(position, duration))
        self.time.setText(
            f"{format_time(position)} / {format_time(duration)}" if duration else format_time(position)
        )
