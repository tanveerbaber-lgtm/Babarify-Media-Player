"""The player bar along the bottom and the Now Playing panel on the right (0.12 redesign).

Both show and control the same player as the Playing page. They read it twice a second (as the mini player
does) and stay out of the way on the Playing page itself, which has its own controls.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from babarify_frame.core.models import PlaybackState
from babarify_frame.ui import theme
from babarify_frame.ui.pages.player import PlayerPage
from babarify_frame.ui.widgets import format_time, glyph_icon, plain_text

POLL_MS = 500
COVER = 220  # the panel's picture; the panel is 300 wide with its margins


class NowPlaying(QObject):
    """What's playing, read from the player and sent to the bar and the panel whenever it changes."""

    changed = Signal()

    def __init__(self, player: PlayerPage) -> None:
        super().__init__(player)
        self.player = player
        self._timer = QTimer(self)
        self._timer.setInterval(POLL_MS)
        self._timer.timeout.connect(self.changed)
        self._timer.start()
        player.state_changed.connect(lambda _s: self.changed.emit())
        player.title_changed.connect(lambda _t: self.changed.emit())
        player.queue_changed.connect(self.changed)
        player.favourites_changed.connect(self.changed)

    def stop(self) -> None:
        """When the window closes: no more reading the player, or the library it is about to close."""
        self._timer.stop()
        self.blockSignals(True)

    @property
    def playing(self) -> bool:
        return self.player.state is PlaybackState.PLAYING


def _button(glyph: str, name: str, fallback: str, size: int = 36) -> QToolButton:
    button = QToolButton()
    button.setAccessibleName(name)
    button.setToolTip(name)
    button.setAutoRaise(True)
    button.setFixedSize(size, size)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    icon = glyph_icon(glyph, theme.TEXT, theme.TEXT_DISABLED, size=48)
    if icon is not None:
        button.setIcon(icon)
        button.setIconSize(QSize(size // 2, size // 2))
    else:
        button.setText(fallback)
    button.setProperty("glyph", glyph)
    return button


def _cover(image: QImage | None, side: int, video: bool) -> QPixmap:
    """The song's picture, or a calm placeholder with a note or a film glyph."""
    if image is not None and not image.isNull():
        return QPixmap.fromImage(image).scaled(
            side,
            side,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
    icon = glyph_icon("now_playing" if video else "music", theme.TEXT_MUTED, theme.TEXT_DISABLED, size=96)
    pixmap = QPixmap(side, side)
    pixmap.fill(Qt.GlobalColor.transparent)
    if icon is not None:
        from PySide6.QtGui import QPainter

        painter = QPainter(pixmap)
        inner = side // 2
        painter.drawPixmap((side - inner) // 2, (side - inner) // 2, icon.pixmap(inner, inner))
        painter.end()
    return pixmap


class _Controls:
    """Shared: the buttons and position bar both views have, and how they follow the player."""

    def _build_controls(self, now: NowPlaying, big_play: int) -> None:
        self._now = now
        player = now.player
        self.shuffle_button = _button("shuffle", "Shuffle", "⤨")
        self.previous_button = _button("previous", "Previous", "⏮")
        self.play_button = _button("play", "Play or pause", "⏯", big_play)
        self.play_button.setObjectName("playButton")
        self.next_button = _button("next", "Next", "⏭")
        self.repeat_button = _button("repeat", "Repeat", "↻")
        self.seek = QSlider(Qt.Orientation.Horizontal)
        self.seek.setAccessibleName("Position")
        self.seek.sliderReleased.connect(lambda: player.seek_to(self.seek.value()))
        self.time = QLabel("00:00")
        self.time.setObjectName("time")
        self.shuffle_button.clicked.connect(player.toggle_shuffle)
        self.previous_button.clicked.connect(player.previous_in_queue)
        self.play_button.clicked.connect(player.toggle_play_pause)
        self.next_button.clicked.connect(player.next_in_queue)
        self.repeat_button.clicked.connect(player.cycle_repeat)
        now.changed.connect(self._follow)

    def _follow(self) -> None:
        player = self._now.player
        playing = self._now.playing
        icon = glyph_icon("pause" if playing else "play", theme.TEXT, theme.TEXT_DISABLED, size=48)
        if icon is not None:
            self.play_button.setIcon(icon)
        self.play_button.setAccessibleName("Pause" if playing else "Play")
        self.play_button.setEnabled(player.has_media)
        self.previous_button.setEnabled(player.can_go_previous)
        self.next_button.setEnabled(player.can_go_next)
        self.shuffle_button.setChecked(player.shuffle_on)
        duration = player.duration_ms or 0
        position = player.position_ms if player.has_media else 0
        self.seek.setEnabled(player.is_seekable and duration > 0)
        if not self.seek.isSliderDown():
            self.seek.setRange(0, max(0, duration))
            self.seek.setValue(min(position, duration))
        self.time.setText(
            f"{format_time(position)} / {format_time(duration)}" if duration else format_time(position)
        )
        self._follow_details()

    def _follow_details(self) -> None:  # each view shows the title and picture its own way
        raise NotImplementedError

    def refresh_theme(self) -> None:
        """Icons are drawn in the theme's text colour: draw them again when the theme changes."""
        assert isinstance(self, QWidget)
        for button in self.findChildren(QToolButton):
            glyph = button.property("glyph")
            if glyph:
                icon = glyph_icon(str(glyph), theme.TEXT, theme.TEXT_DISABLED, size=48)
                if icon is not None:
                    button.setIcon(icon)
        self._follow()


class PlayerBar(QFrame, _Controls):
    """Along the bottom of every page but Playing: what's playing, its controls, position and volume."""

    open_player = Signal()  # the cover or title was clicked: show the Playing page
    queue_requested = Signal()
    mini_requested = Signal()

    def __init__(self, now: NowPlaying, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("playerBar")
        row = QHBoxLayout(self)
        row.setContentsMargins(theme.L, theme.S, theme.L, theme.S)
        row.setSpacing(theme.M)
        self.cover = QPushButton()
        self.cover.setObjectName("barCover")
        self.cover.setFixedSize(52, 52)
        self.cover.setIconSize(QSize(52, 52))
        self.cover.setAccessibleName("Show the Playing page")
        self.cover.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cover.clicked.connect(self.open_player)
        row.addWidget(self.cover)
        text = QVBoxLayout()
        text.setSpacing(0)
        self.title = QLabel("Nothing is playing")
        self.title.setObjectName("mediaTitle")
        self.artist = QLabel("")
        self.artist.setObjectName("caption")
        plain_text(self.title, self.artist)
        for label in (self.title, self.artist):
            label.setMaximumWidth(260)
            text.addWidget(label)
        row.addLayout(text)
        self.favourite_button = _button("heart", "Favourite", "♥")
        self.favourite_button.clicked.connect(now.player.toggle_favourite)
        row.addWidget(self.favourite_button)
        row.addStretch(1)
        self._build_controls(now, 48)
        for button in (self.shuffle_button, self.previous_button, self.play_button, self.next_button,
                       self.repeat_button):  # fmt: skip
            row.addWidget(button)
        self.seek.setMinimumWidth(180)
        row.addWidget(self.seek, stretch=2)
        row.addWidget(self.time)
        row.addStretch(1)
        self._volume_by_user: bool = False  # only the user's moves change the volume
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setAccessibleName("Volume")
        self.volume.setFixedWidth(110)
        self.volume.setRange(0, 100)
        self.volume.valueChanged.connect(lambda v: now.player.set_volume(v) if self._volume_by_user else None)
        self.volume_icon = _button("volume", "Mute", "🔊")
        self.volume_icon.clicked.connect(now.player.toggle_mute)
        self.queue_button = _button("queue", "Queue", "≡")
        self.queue_button.clicked.connect(self.queue_requested)
        self.mini_button = _button("fullscreen", "Mini player", "⤢")
        self.mini_button.clicked.connect(self.mini_requested)
        for widget in (self.volume_icon, self.volume, self.queue_button, self.mini_button):
            row.addWidget(widget)
        self._follow()

    def _follow_details(self) -> None:
        player = self._now.player
        self.title.setText(player.display_title or "Nothing is playing")
        self.artist.setText(player.display_artist)
        self.artist.setVisible(bool(player.display_artist))
        self.cover.setIcon(_cover(player.cover_image, 52, player.has_video))
        self.favourite_button.setEnabled(player.can_favourite)
        heart = "heart_filled" if player.is_favourite else "heart"
        icon = glyph_icon(
            heart, theme.CYAN if player.is_favourite else theme.TEXT, theme.TEXT_DISABLED, size=48
        )
        if icon is not None:
            self.favourite_button.setIcon(icon)
        level, _muted = player.volume_state()
        if not self.volume.isSliderDown() and self.volume.value() != min(100, level):
            self._volume_by_user = False
            self.volume.setValue(min(100, level))
        self._volume_by_user = True


class NowPanel(QFrame, _Controls):
    """On the right of the pages: a large picture of what's playing, with its controls and the queue."""

    queue_requested = Signal()
    open_player = Signal()

    def __init__(self, now: NowPlaying, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("nowPanel")
        self.setFixedWidth(300)
        box = QVBoxLayout(self)
        box.setContentsMargins(theme.L, theme.L, theme.L, theme.L)
        box.setSpacing(theme.S)
        heading = QLabel("Now playing")
        heading.setObjectName("subtitle")
        box.addWidget(heading)
        self.cover = QPushButton()
        self.cover.setObjectName("panelCover")
        self.cover.setFixedSize(COVER, COVER)
        self.cover.setIconSize(QSize(COVER - 8, COVER - 8))
        self.cover.setAccessibleName("Show the Playing page")
        self.cover.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cover.clicked.connect(self.open_player)
        box.addWidget(self.cover, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.title = QLabel("Nothing is playing")
        self.title.setObjectName("subtitle")
        self.title.setWordWrap(True)
        self.title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.artist = QLabel("")
        self.artist.setObjectName("muted")
        self.artist.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        plain_text(self.title, self.artist)
        box.addWidget(self.title)
        box.addWidget(self.artist)
        self._build_controls(now, 52)
        box.addWidget(self.seek)
        box.addWidget(self.time, alignment=Qt.AlignmentFlag.AlignRight)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        for button in (self.shuffle_button, self.previous_button, self.play_button, self.next_button,
                       self.repeat_button):  # fmt: skip
            buttons.addWidget(button)
        buttons.addStretch(1)
        box.addLayout(buttons)
        self.queue_button = QPushButton("View queue")
        self.queue_button.clicked.connect(self.queue_requested)
        box.addWidget(self.queue_button, alignment=Qt.AlignmentFlag.AlignHCenter)
        box.addStretch(1)
        self._follow()

    def _follow_details(self) -> None:
        player = self._now.player
        self.title.setText(player.display_title or "Nothing is playing")
        self.artist.setText(player.display_artist)
        self.cover.setIcon(_cover(player.cover_image, COVER - 8, player.has_video))
