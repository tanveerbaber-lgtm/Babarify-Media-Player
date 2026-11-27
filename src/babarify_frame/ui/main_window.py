"""Main application shell (M3): navigation rail, page stack, menus, shortcuts, fullscreen, preferences.

Pages:
* Home — "Open file", plus Continue watching and Recently played once there is history (M6).
* Library — folders the user chose, search, sort and playlists (M6).
* Now Playing — ``PlayerPage``; owns the playback controller.
* Settings — persisted UI preferences.

Keyboard model: playback shortcuts (Space, arrows, M, S, F, the M5 track keys V, B, G, H,
J, K and the M7 keys Shift+S, period, comma, L) are active only while the Now Playing page
is shown, so they never fight with form controls elsewhere. Ctrl+O, Ctrl+Q, Ctrl+1/2/3, F1
and Esc work everywhere.
"""

from __future__ import annotations

import contextlib
import random
import tempfile
import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QRect, QSize, Qt, QTimer
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QColor,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDropEvent,
    QGuiApplication,
    QIcon,
    QImage,
    QKeySequence,
    QPainter,
    QResizeEvent,
    QShowEvent,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QButtonGroup,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from babarify_frame import PRODUCT_NAME, TAGLINE, __version__
from babarify_frame.configuration.preferences import Preferences, PreferencesStore, WindowGeometry
from babarify_frame.core.enhancements import EqualizerSettings
from babarify_frame.core.models import MEDIA_EXTENSIONS, SUBTITLE_EXTENSIONS, MediaInfo, PlaybackState
from babarify_frame.core.music import SLEEP_MINUTES, STYLE_LABELS, VisualStyle
from babarify_frame.core.network import STREAM_SCHEMES, is_network_uri
from babarify_frame.core.themes import THEMES
from babarify_frame.core.updates import CHECK_EVERY_S
from babarify_frame.iptv.service import IptvService
from babarify_frame.iptv.store import ChannelEntry, IptvStore
from babarify_frame.library import backup, legacy_ai
from babarify_frame.library.database import LibraryDatabase
from babarify_frame.library.models import HistoryEntry, SortOrder
from babarify_frame.library.service import LibraryService
from babarify_frame.playback.controller import PlaybackController
from babarify_frame.playback.factory import EngineFactory
from babarify_frame.playback.preview import FramePreview
from babarify_frame.ui import theme
from babarify_frame.ui.audio_view import QueueDialog
from babarify_frame.ui.bookmarks import BookmarksDialog
from babarify_frame.ui.bridge import UiBridge
from babarify_frame.ui.diagnostics import PlaybackInfoDialog
from babarify_frame.ui.enhancements import EnhancementsDialog
from babarify_frame.ui.lyrics_dialog import LyricsDialog
from babarify_frame.ui.media_info import MediaInfoDialog
from babarify_frame.ui.mini_player import MiniPlayer
from babarify_frame.ui.network import NetworkStreamDialog
from babarify_frame.ui.now_playing import NowPanel, NowPlaying, PlayerBar
from babarify_frame.ui.pages.home import ADDED_LIMIT, SHORTCUTS, HomePage
from babarify_frame.ui.pages.library import HiddenFilesDialog, LibraryPage
from babarify_frame.ui.pages.player import VOLUME_STEP, PlayerPage
from babarify_frame.ui.pages.settings import SettingsPage, theme_swatch
from babarify_frame.ui.pages.tv import TvPage
from babarify_frame.ui.report import ReportDialog
from babarify_frame.ui.subtitles import SUBTITLE_FILTER
from babarify_frame.ui.update_notice import UpdateBar, UpdateChecker, UpdateResult
from babarify_frame.ui.widgets import brand_logo, brand_wordmark, format_time, glyph_icon, set_topmost

RAIL_WIDTH = 196  # the side bar (0.12 redesign)
RAIL_FOLDED = 64  # folded: icons only
RAIL_TAB = QSize(18, 48)  # the arrow on the side bar's edge that folds and opens it
PANEL_MIN_WIDTH = 1180  # narrower windows give the pages the Now Playing panel's room
# The same types the library scans, so the Open dialog and the library always agree.
MEDIA_FILTER = f"Media files ({' '.join('*' + ext for ext in sorted(MEDIA_EXTENSIONS))});;All files (*)"
MIN_SIZE = QSize(560, 400)
DEFAULT_SIZE = QSize(1180, 740)


class MainWindow(QMainWindow):
    def __init__(
        self,
        factory: EngineFactory,
        icon: QIcon,
        engine_name: str = "libvlc",
        store: PreferencesStore | None = None,
        library: LibraryService | None = None,
        preview_factory: Callable[[], FramePreview] | None = None,
        update_check: bool = False,
    ) -> None:
        super().__init__()
        self._update_check = update_check  # only the real app asks GitHub on its own; never tests or checks
        self._store = store or PreferencesStore()
        self._prefs = self._store.load()
        self._apply_colour_theme(self._prefs.colour_theme)
        # Without a service (tests, or a library that could not open) the app keeps an in-memory one.
        self.library_service = library or LibraryService(LibraryDatabase(None))
        self._was_maximized = False
        self._info_dialog: PlaybackInfoDialog | None = None
        self._enhancements: EnhancementsDialog | None = None
        self._media_info_dialog: MediaInfoDialog | None = None
        self._bookmarks_dialog: BookmarksDialog | None = None

        self.setWindowTitle(PRODUCT_NAME)
        self.setWindowIcon(icon)
        self.setMinimumSize(MIN_SIZE)
        self.setAcceptDrops(True)

        self.home = HomePage(icon)
        db = self.library_service.db
        self.player = PlayerPage(
            factory, engine_name, self._prefs, history=db, preview_factory=preview_factory
        )
        self.library = LibraryPage(self.library_service, self._prefs.library_sort)
        self.library.set_section("music")  # M3: the side bar opens Music, Videos or Playlists
        self.settings = SettingsPage(self._prefs, self._store.path, library_path=db.path)
        # IPTV (0.12): idle, and its page hidden, until network streams are switched on.
        self.iptv = IptvService(IptvStore(db), Path(tempfile.gettempdir()) / "Babarify IPTV")
        self.iptv.set_enabled(self._prefs.network_streams)
        self.tv = TvPage(self.iptv)
        self._last_channel: ChannelEntry | None = None  # for "previous channel"
        self._current_channel: ChannelEntry | None = None
        self._pages = QStackedWidget()
        for page in (self.home, self.library, self.player, self.settings, self.tv):
            self._pages.addWidget(page)

        root = QWidget()
        root.setObjectName("root")
        frame = QVBoxLayout(root)
        frame.setContentsMargins(0, 0, 0, 0)
        frame.setSpacing(0)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        frame.addLayout(row, stretch=1)
        self._nav_icons: list[tuple[QAbstractButton, str]] = []
        self._rail = self._build_rail(icon)
        row.addWidget(self._rail)
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        self.update_bar = UpdateBar()
        self.update_bar.skipped.connect(lambda version: self._remember(skipped_update=version))
        column.addWidget(self.update_bar)
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._pages, stretch=1)
        self._now = NowPlaying(self.player)
        # Before the panel follows the player, so a video that starts shows in it at once (0.12).
        self._now.changed.connect(lambda: self._place_video())
        self.player.video.clicked.connect(self._on_video_clicked)
        self.now_panel = NowPanel(self._now)
        body.addWidget(self.now_panel)
        column.addLayout(body, stretch=1)
        row.addLayout(column, stretch=1)
        self.player_bar = PlayerBar(self._now)
        frame.addWidget(self.player_bar)
        for view in (self.player_bar, self.now_panel):
            view.open_player.connect(lambda: self.show_page(self.player))
            view.queue_requested.connect(self.show_queue)
        self.player_bar.mini_requested.connect(self.enter_mini_player)
        self._update_bridge = UiBridge(self)
        self._update_bridge.delivered.connect(self._on_update_result)
        self._updates = UpdateChecker(self._update_bridge)
        self.setCentralWidget(root)
        if self._prefs.background_picture:
            self._apply_background()

        self.mini = MiniPlayer(self.player, icon)
        self.mini.back_requested.connect(self.leave_mini_player)
        self.mini.activated.connect(lambda: self._keep_on_top(self.mini))
        self._build_actions()
        self._connect_pages()
        self.statusBar().showMessage(f"Version {__version__} · No account · No telemetry")
        self._restore_geometry()
        self.statusBar().setVisible(self._prefs.show_status_bar)
        self.set_rail_folded(self._prefs.rail_folded)
        self.show_page(self.home)

    # ------------------------------------------------------------ layout
    def _build_rail(self, icon: QIcon) -> QFrame:
        """The side bar (0.12 redesign): the pages, then "Your library" and "Tools", the theme at the foot."""
        rail = QFrame()
        rail.setObjectName("navRail")
        rail.setFixedWidth(RAIL_WIDTH)
        outer = QVBoxLayout(rail)
        outer.setContentsMargins(0, 0, 0, 0)
        # In a short window the side bar scrolls rather than squeezing its entries together.
        scroll = QScrollArea()
        scroll.setObjectName("railScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("seeThrough")
        scroll.viewport().setObjectName("seeThrough")
        scroll.setWidget(content)
        outer.addWidget(scroll)
        box = QVBoxLayout(content)
        box.setContentsMargins(theme.M, theme.L, theme.M, theme.M)
        box.setSpacing(2)
        # The name in the new branding (0.12): the neon mark with "BABARIFY MEDIA PLAYER"; folded, the mark.
        self._brand_icon = icon
        self._rail_wordmark = QLabel()
        self._rail_wordmark.setAccessibleName(PRODUCT_NAME)
        self._rail_wordmark.setToolTip(f"{PRODUCT_NAME} · {TAGLINE}")
        self._rail_mark = QLabel()
        self._rail_mark.setAccessibleName(PRODUCT_NAME)
        self._rail_mark.hide()
        box.addWidget(self._rail_wordmark, alignment=Qt.AlignmentFlag.AlignHCenter)
        box.addWidget(self._rail_mark, alignment=Qt.AlignmentFlag.AlignHCenter)
        self._draw_rail_brand()
        self._rail_texts: list[QWidget] = []
        # Folding: an arrow tab on the side bar's edge, halfway down, over its contents (0.12, the owner's
        # choice, in place of a menu button at the top). It follows the side bar's size.
        self.rail_toggle = QToolButton(rail)
        self.rail_toggle.setObjectName("railToggle")
        self.rail_toggle.setFixedSize(RAIL_TAB)
        self.rail_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.rail_toggle.clicked.connect(lambda: self.set_rail_folded(not self._prefs.rail_folded))
        rail.installEventFilter(self)
        box.addSpacing(theme.M)
        self._nav = QButtonGroup(self)
        self._nav.setExclusive(True)
        self.nav_home = self._nav_button("home", "Home", "Home (Ctrl+1)", self.home)
        self.nav_music = self._nav_button("music", "Music", "Songs, albums, artists, genres (Ctrl+L)", None)
        self.nav_videos = self._nav_button("now_playing", "Videos", "Your videos", None)
        self.nav_tv = self._nav_button("tv", "TV", "TV channels from your lists", self.tv)
        self.nav_tv.setVisible(self._prefs.network_streams)
        self.nav_player = self._nav_button("play", "Now Playing", "Now Playing (Ctrl+2)", self.player)
        self.nav_albums = self._nav_button("album", "Albums", "Your albums", None)
        self.nav_artists = self._nav_button("artist", "Artists", "Your artists", None)
        self.nav_playlists = self._nav_button("playlists", "Playlists", "Your playlists", None)
        self.nav_favourites = self._nav_button("heart", "Favourites", "Your favourite songs", None)
        self.nav_recent = self._nav_button("history", "Recently Played", "Songs you played lately", None)
        self.nav_equalizer = self._nav_button("equalizer", "Equalizer", "Equalizer and sound (Ctrl+E)", None)
        self.nav_equalizer.setCheckable(False)
        self.nav_equalizer.clicked.connect(self.show_enhancements)
        self.nav_settings = self._nav_button("settings", "Settings", "Settings (Ctrl+3)", self.settings)
        # (button, section, tab, automatic playlist): what each library button shows (0.12)
        self._library_buttons = (
            (self.nav_music, "music", "Songs", None),
            (self.nav_videos, "videos", None, None),
            (self.nav_albums, "music", "Albums", None),
            (self.nav_artists, "music", "Artists", None),
            (self.nav_playlists, "playlists", None, None),
            (self.nav_favourites, "playlists", None, "Favourites"),
            (self.nav_recent, "playlists", None, "Recently played"),
        )
        for button, section, tab, automatic in self._library_buttons:
            self._nav.addButton(button)
            button.clicked.connect(
                lambda _=False, s=section, t=tab, a=automatic: self.show_library(s, tab=t, automatic=a)
            )
        self.nav_library = self.nav_music  # its name before M3
        for button in (self.nav_home, self.nav_music, self.nav_videos, self.nav_tv, self.nav_player):
            box.addWidget(button)
        box.addSpacing(theme.M)
        # "Your Library" opens and closes like a drop-down; the choice is remembered (0.12).
        self.library_toggle = QPushButton("Your Library")
        self.library_toggle.setObjectName("railSectionToggle")
        self.library_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.library_toggle.setCheckable(True)
        self.library_toggle.setChecked(self._prefs.library_open)
        self.library_toggle.toggled.connect(self.set_library_open)
        self._rail_texts.append(self.library_toggle)
        box.addWidget(self.library_toggle)
        self._library_entries = (
            self.nav_albums,
            self.nav_artists,
            self.nav_playlists,
            self.nav_favourites,
            self.nav_recent,
        )
        for button in self._library_entries:
            box.addWidget(button)
        box.addSpacing(theme.M)
        box.addWidget(self._rail_section("Tools"))
        box.addWidget(self.nav_equalizer)
        box.addWidget(self.nav_settings)
        box.addStretch(1)
        self.nav_theme = self._nav_button("theme", "Theme", "Colour theme", None)
        self.nav_theme.setCheckable(False)
        box.addWidget(self.nav_theme)
        # The theme list opens from a click: a menu attached to the button would shift its icon and text.
        self.nav_theme.clicked.connect(
            lambda: self.theme_menu.exec(self.nav_theme.mapToGlobal(self.nav_theme.rect().topRight()))
        )
        self._rail = rail
        self._rail_box = box
        return rail

    def set_library_open(self, opened: bool) -> None:
        """Your Library's entries shown or folded away. The folded side bar always shows every icon."""
        if opened != self._prefs.library_open:
            self._remember(library_open=opened)
        if self.library_toggle.isChecked() != opened:
            self.library_toggle.setChecked(opened)
        for button in self._library_entries:
            button.setVisible(opened or self._prefs.rail_folded)
        chevron = "chevron_down" if opened else "chevron_right"
        arrow = glyph_icon(chevron, theme.TEXT_MUTED, theme.TEXT_DISABLED, size=48)
        if arrow is not None:
            self.library_toggle.setIcon(arrow)
            self.library_toggle.setIconSize(QSize(12, 12))
        self.library_toggle.setToolTip(
            "Hide your library's entries" if opened else "Show your library's entries"
        )
        self.library_toggle.setAccessibleName(f"Your Library, {'open' if opened else 'closed'}")

    def _draw_rail_toggle(self) -> None:
        """The arrow points the way the side bar will go: left to fold it, right to open it."""
        glyph = "chevron_right" if self._prefs.rail_folded else "chevron_left"
        arrow = glyph_icon(glyph, theme.TEXT, theme.TEXT_DISABLED, size=48, weight=0.04)
        if arrow is not None:
            self.rail_toggle.setIcon(arrow)
            self.rail_toggle.setIconSize(QSize(14, 14))
        else:
            self.rail_toggle.setText(">" if self._prefs.rail_folded else "<")

    def _place_rail_toggle(self) -> None:
        tab = self.rail_toggle
        tab.move(self._rail.width() - tab.width(), (self._rail.height() - tab.height()) // 2)
        tab.raise_()

    def _draw_rail_brand(self) -> None:
        """The side bar's logo, in the version for the theme on show (light themes have their own)."""
        self._rail_wordmark.setPixmap(brand_wordmark(self._brand_icon, RAIL_WIDTH - 2 * theme.M - 8))
        self._rail_mark.setPixmap(brand_logo(self._brand_icon, RAIL_FOLDED - 18))

    def _rail_section(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("railSection")
        self._rail_texts.append(label)
        return label

    def set_rail_folded(self, folded: bool) -> None:
        """The side bar shown in full, or folded to its icons (names on hover) for more room (0.12)."""
        if folded != self._prefs.rail_folded:
            self._remember(rail_folded=folded)
        self._rail.setFixedWidth(RAIL_FOLDED if folded else RAIL_WIDTH)
        for widget in self._rail_texts:
            widget.setVisible(not folded)
        for button, _glyph in self._nav_icons:
            if isinstance(button, QPushButton) and button.objectName() == "navButton":
                name = button.property("label") or button.text()
                button.setProperty("label", name)
                button.setText("" if folded else str(name))
                button.setProperty("folded", folded)
                button.style().unpolish(button)
                button.style().polish(button)
        self.rail_toggle.setToolTip("Show the side bar" if folded else "Fold the side bar to its icons")
        self.rail_toggle.setAccessibleName(self.rail_toggle.toolTip())
        self._draw_rail_toggle()
        self._place_rail_toggle()
        self._rail_wordmark.setVisible(not folded)
        self._rail_mark.setVisible(folded)
        self.set_library_open(self._prefs.library_open)  # folded, every icon shows
        if hasattr(self, "rail_action"):
            self.rail_action.setChecked(not folded)

    def _nav_button(self, glyph: str, text: str, tip: str, page: QWidget | None) -> QPushButton:
        """A side bar entry: icon and name, left aligned (0.12 redesign)."""
        button = QPushButton(text)
        button.setObjectName("navButton")
        button.setToolTip(tip)
        button.setAccessibleName(text)
        self._nav_icons.append((button, glyph))
        nav_icon = glyph_icon(glyph, theme.TEXT, theme.TEXT_DISABLED, size=64, weight=0.03)
        if nav_icon is not None:
            button.setIcon(nav_icon)
            button.setIconSize(QSize(20, 20))
        button.setCheckable(True)
        button.setFixedHeight(34)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        if page is not None:
            self._nav.addButton(button)
            button.clicked.connect(lambda _=False, p=page: self.show_page(p))
        return button

    def _action(self, text: str, keys: list[QKeySequence], slot: Callable[[], object]) -> QAction:
        action = QAction(text, self)
        action.setShortcuts(keys)
        action.triggered.connect(slot)
        self.addAction(action)  # shortcuts keep working while menus and rail are hidden in fullscreen
        return action

    def _build_actions(self) -> None:
        K = QKeySequence
        p = self.player
        self.open_action = self._action("&Open file…", [K(K.StandardKey.Open)], self.choose_file)
        quit_action = self._action("E&xit", [K("Ctrl+Q")], self.close)
        self.home_action = self._action("&Home", [K("Ctrl+1")], lambda: self.show_page(self.home))
        self.player_action = self._action("&Now Playing", [K("Ctrl+2")], lambda: self.show_page(self.player))
        self.settings_action = self._action("&Settings", [K("Ctrl+3")], lambda: self.show_page(self.settings))
        self.library_action = self._action("&Music", [K("Ctrl+L")], lambda: self.show_library("music"))
        self.videos_action = self._action("&Videos", [], lambda: self.show_library("videos"))
        self.playlists_action = self._action("Pla&ylists", [], lambda: self.show_library("playlists"))
        self.tv_action = self._action("&TV", [], lambda: self.show_page(self.tv))
        self.tv_action.setVisible(self._prefs.network_streams)
        # Channel up and down, and back to the last channel (0.12): on the player only, so lists and text
        # boxes elsewhere keep their own Page Up, Page Down and Backspace.
        for text, key, slot in (
            ("Next channel", "PgDown", lambda: self.step_channel(1)),
            ("Previous channel", "PgUp", lambda: self.step_channel(-1)),
            ("Last channel", "Backspace", self.previous_channel),
        ):
            channel_action = QAction(text, self.player)
            channel_action.setShortcut(K(key))
            channel_action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            channel_action.triggered.connect(slot)
            self.player.addAction(channel_action)
        self.add_folder_action = self._action("Add folder to &library…", [], self.choose_library_folder)
        self.next_action = self._action("&Next in playlist", [K(Qt.Key.Key_N)], p.next_in_queue)
        self.previous_action = self._action("P&revious in playlist", [K(Qt.Key.Key_P)], p.previous_in_queue)
        self.start_over_action = self._action("Start &over", [K(Qt.Key.Key_Home)], p.start_over)
        self.shuffle_action = self._action("S&huffle", [K(Qt.Key.Key_Z)], p.toggle_shuffle)
        self.repeat_action = self._action("&Repeat: off, this file, all", [K(Qt.Key.Key_R)], p.cycle_repeat)
        self.queue_action = self._action("&Queue…", [K(Qt.Key.Key_Q)], self.show_queue)
        self.lyrics_action = self._action("L&yrics…", [K(Qt.Key.Key_Y)], self.show_lyrics)
        self.favourite_action = self._action(
            "Add to or remove from fa&vourites", [K(Qt.Key.Key_U)], p.toggle_favourite
        )
        # Playback actions: enabled only on the Now Playing page (see module docstring).
        self.play_action = self._action(
            "&Play/Pause", [K(Qt.Key.Key_Space), K(Qt.Key.Key_MediaTogglePlayPause)], p.toggle_play_pause
        )
        self.stop_action = self._action("&Stop", [K(Qt.Key.Key_S), K(Qt.Key.Key_MediaStop)], p.stop)
        self.back_action = self._action("Seek &back", [K(Qt.Key.Key_Left)], lambda: p.seek_step(-1))
        self.forward_action = self._action("Seek &forward", [K(Qt.Key.Key_Right)], lambda: p.seek_step(1))
        self.volume_up_action = self._action(
            "Volume &up", [K(Qt.Key.Key_Up)], lambda: p.step_volume(VOLUME_STEP)
        )
        self.volume_down_action = self._action(
            "Volume &down", [K(Qt.Key.Key_Down)], lambda: p.step_volume(-VOLUME_STEP)
        )
        self.mute_action = self._action("&Mute", [K(Qt.Key.Key_M)], p.toggle_mute)
        self.fullscreen_action = self._action(
            "&Fullscreen", [K(Qt.Key.Key_F), K(Qt.Key.Key_F11)], self.toggle_fullscreen
        )
        self._action("Exit fullscreen", [K(Qt.Key.Key_Escape)], self.exit_fullscreen)
        shortcuts_action = self._action("&Keyboard shortcuts", [K(Qt.Key.Key_F1)], self._show_shortcuts)
        self.info_action = self._action("Playback &info…", [K("Ctrl+I")], self.show_playback_info)
        # Audio and subtitles (M5)
        self.load_subtitle_action = self._action(
            "Load &subtitle file…", [K("Ctrl+Shift+O")], self.choose_subtitle_file
        )
        self.next_subtitle_action = self._action("Next su&btitle track", [K(Qt.Key.Key_V)], p.cycle_subtitles)
        self.next_audio_action = self._action("Next &audio track", [K(Qt.Key.Key_B)], p.cycle_audio)
        self.subtitle_earlier_action = self._action(
            "Subtitles 50 ms earlier", [K(Qt.Key.Key_G)], lambda: p.step_subtitle_delay(-1)
        )
        self.subtitle_later_action = self._action(
            "Subtitles 50 ms later", [K(Qt.Key.Key_H)], lambda: p.step_subtitle_delay(1)
        )
        self.audio_earlier_action = self._action(
            "Audio 50 ms earlier", [K(Qt.Key.Key_J)], lambda: p.step_audio_delay(-1)
        )
        self.audio_later_action = self._action(
            "Audio 50 ms later", [K(Qt.Key.Key_K)], lambda: p.step_audio_delay(1)
        )
        self.sync_action = self._action("Sync and &delay…", [K("Ctrl+D")], p.show_sync_dialog)
        # Picture and sound (M7)
        self.enhancements_action = self._action("&Picture && Sound…", [K("Ctrl+E")], self.show_enhancements)
        self.snapshot_action = self._action("Take &snapshot", [K("Shift+S")], lambda: p.take_snapshot())
        self.next_frame_action = self._action("Next &frame", [K(Qt.Key.Key_Period)], lambda: p.frame_step())
        self.previous_frame_action = self._action(
            "Pre&vious frame", [K(Qt.Key.Key_Comma)], lambda: p.frame_step(backward=True)
        )
        self.ab_action = self._action("&A-B repeat", [K(Qt.Key.Key_L)], p.ab_loop_step)
        # Advanced media (M8)
        self.next_chapter_action = self._action("Next c&hapter", [K("Ctrl+Right")], p.next_chapter)
        self.previous_chapter_action = self._action("Previous chap&ter", [K("Ctrl+Left")], p.previous_chapter)
        self.add_bookmark_action = self._action("Add &bookmark", [K("Ctrl+B")], lambda: p.add_bookmark())
        self.bookmarks_action = self._action("Boo&kmarks…", [K("Ctrl+Shift+B")], self.show_bookmarks)
        self.media_info_action = self._action(
            "&Media information…", [K("Ctrl+Shift+I")], self.show_media_info
        )
        self._track_actions = (
            self.next_subtitle_action,
            self.next_audio_action,
            self.subtitle_earlier_action,
            self.subtitle_later_action,
            self.audio_earlier_action,
            self.audio_later_action,
        )
        self.report_action = self._action("&Report a problem…", [], self.show_report)
        self.update_action = self._action(
            "Check for &updates…", [], lambda: self.check_for_updates(manual=True)
        )
        about_action = QAction(f"&About {PRODUCT_NAME}", self)
        about_action.triggered.connect(self._show_about)
        self._playback_actions = (
            self.play_action,
            self.stop_action,
            self.back_action,
            self.forward_action,
            self.volume_up_action,
            self.volume_down_action,
            self.mute_action,
            self.fullscreen_action,
        )

        menus = self.menuBar()
        file_menu = menus.addMenu("&File")
        file_menu.addAction(self.open_action)
        self.open_stream_action = self._action("Open network &stream…", [K("Ctrl+N")], self.choose_stream)
        file_menu.addAction(self.open_stream_action)
        file_menu.addAction(self.load_subtitle_action)
        file_menu.addAction(self.add_folder_action)
        file_menu.addSeparator()
        file_menu.addAction(quit_action)
        play_menu = menus.addMenu("&Playback")
        for action in self._playback_actions[:4]:
            play_menu.addAction(action)
        play_menu.addAction(self.start_over_action)
        play_menu.addSeparator()
        play_menu.addAction(self.next_chapter_action)
        play_menu.addAction(self.previous_chapter_action)
        self.chapters_menu = play_menu.addMenu("&Chapters")
        self.chapters_menu.aboutToShow.connect(self._fill_chapters_menu)
        play_menu.addAction(self.add_bookmark_action)
        play_menu.addAction(self.bookmarks_action)
        play_menu.addSeparator()
        play_menu.addAction(self.next_action)
        play_menu.addAction(self.previous_action)
        play_menu.addAction(self.shuffle_action)
        play_menu.addAction(self.repeat_action)
        play_menu.addAction(self.queue_action)
        play_menu.addAction(self.lyrics_action)
        play_menu.addAction(self.favourite_action)
        self.sleep_menu = play_menu.addMenu("S&leep timer")
        self.sleep_menu.aboutToShow.connect(self._fill_sleep_menu)
        play_menu.addSeparator()
        for action in (self.volume_up_action, self.volume_down_action, self.mute_action):
            play_menu.addAction(action)
        tracks_menu = menus.addMenu("&Audio && Subtitles")
        tracks_menu.addAction(self.next_audio_action)
        tracks_menu.addAction(self.next_subtitle_action)
        tracks_menu.addAction(self.load_subtitle_action)
        tracks_menu.addSeparator()
        for action in self._track_actions[2:]:
            tracks_menu.addAction(action)
        tracks_menu.addAction(self.sync_action)
        video_menu = menus.addMenu("Vi&deo")
        video_menu.addAction(self.enhancements_action)
        video_menu.addSeparator()
        for action in (
            self.snapshot_action,
            self.next_frame_action,
            self.previous_frame_action,
            self.ab_action,
        ):
            video_menu.addAction(action)
        view_menu = menus.addMenu("&View")
        for action in (
            self.home_action,
            self.library_action,
            self.videos_action,
            self.playlists_action,
            self.tv_action,
            self.player_action,
            self.settings_action,
        ):
            view_menu.addAction(action)
        view_menu.addSeparator()
        view_menu.addAction(self.fullscreen_action)
        view_menu.addAction(self.info_action)
        view_menu.addAction(self.media_info_action)
        self.mini_action = self._action("&Mini player", [K("Ctrl+Shift+M")], self.enter_mini_player)
        view_menu.addAction(self.mini_action)
        self.on_top_action = QAction("Always on &top", self)
        self.on_top_action.setCheckable(True)
        self.on_top_action.setChecked(self._prefs.always_on_top)
        self.on_top_action.toggled.connect(self.set_always_on_top)
        view_menu.addAction(self.on_top_action)
        self.status_bar_action = QAction("Status &bar", self)
        self.status_bar_action.setCheckable(True)
        self.status_bar_action.setChecked(self._prefs.show_status_bar)
        self.status_bar_action.toggled.connect(self._choose_status_bar)
        view_menu.addAction(self.status_bar_action)
        # The colour theme and the animation used to have buttons on the side bar (until M3).
        self.theme_menu = view_menu.addMenu("Colour &theme")
        self.theme_menu.aboutToShow.connect(self._fill_theme_menu)
        self.rail_action = QAction("Side &bar names", self)
        self.rail_action.setCheckable(True)
        self.rail_action.setShortcut(K("Ctrl+Shift+B"))
        self.rail_action.setChecked(not self._prefs.rail_folded)
        self.rail_action.toggled.connect(lambda shown: self.set_rail_folded(not shown))
        self.addAction(self.rail_action)
        view_menu.addAction(self.rail_action)
        self.now_panel_action = QAction("&Now Playing panel", self)
        self.now_panel_action.setCheckable(True)
        self.now_panel_action.setChecked(self._prefs.show_now_panel)
        self.now_panel_action.toggled.connect(self.set_now_panel)
        view_menu.addAction(self.now_panel_action)
        self.animation_menu = view_menu.addMenu("&Animation for audio")
        self.animation_menu.aboutToShow.connect(self._fill_animation_menu)
        help_menu = menus.addMenu("&Help")
        help_menu.addAction(shortcuts_action)
        help_menu.addAction(self.report_action)
        help_menu.addAction(self.update_action)
        help_menu.addAction(about_action)

    def _connect_pages(self) -> None:
        self.home.open_requested.connect(self.choose_file)
        self.player.open_requested.connect(self.choose_file)
        self.player.subtitle_file_requested.connect(self.choose_subtitle_file)
        self.player.fullscreen_requested.connect(self.toggle_fullscreen)
        self.player.status_changed.connect(self.statusBar().showMessage)
        self.player.title_changed.connect(self._set_media_title)
        self.player.state_changed.connect(lambda _state: self._update_actions())
        self.player.queue_changed.connect(self._update_actions)
        self.player.queue_requested.connect(self.show_queue)
        self.player.repeat_changed.connect(self._on_repeat_changed)
        self.player.engine_ready.connect(self._on_engine_ready)
        self.tv.play_requested.connect(self.play_channel)
        self.tv.status_changed.connect(lambda text: self.statusBar().showMessage(text, 6000))
        self._iptv_timer = QTimer(self)
        self._iptv_timer.setInterval(3600 * 1000)  # lists and guides that are due are read again
        self._iptv_timer.timeout.connect(self.iptv.refresh_due)
        self._iptv_timer.start()
        if self._prefs.network_streams:
            QTimer.singleShot(5000, self.iptv.refresh_due)  # after start-up, not during it
        if self._update_check:
            QTimer.singleShot(60_000, lambda: self.check_for_updates(manual=False))  # a minute after start
            self._iptv_timer.timeout.connect(lambda: self.check_for_updates(manual=False))  # and hourly
        self.player.video_started.connect(self._on_video_started)
        self.settings.preferences_changed.connect(self._on_preferences_changed)
        # Library and history (M6)
        self.settings.clear_history_requested.connect(self.clear_history)
        self.settings.hidden_files_requested.connect(self.show_hidden_files)
        self.settings.backup_requested.connect(self.back_up)
        self.settings.restore_requested.connect(self.restore_from_backup)
        self.library.play_requested.connect(self.open_path)
        self.library.play_list_requested.connect(self.play_list)
        self.library.shuffle_requested.connect(self.shuffle_list)
        self.library.play_next_requested.connect(self.player.play_next)
        self.library.add_to_queue_requested.connect(self.player.add_to_queue)
        self.player.favourites_changed.connect(self.library.refresh_current_tab)
        self.library.status_changed.connect(self.statusBar().showMessage)
        self.library.sort_changed.connect(self._on_library_sort)
        self.home.play_requested.connect(self.open_path)
        self.home.play_now_requested.connect(self.play_now)
        self.home.library_requested.connect(lambda: self.show_library("music", tab="Songs"))
        self.home.search_requested.connect(
            lambda text: self.home.set_search_results(self.library_service.db.search_everything(text))
        )
        self.home.forget_requested.connect(self._forget)
        self.player.history_changed.connect(self._history_changed)
        self.player.bookmarks_changed.connect(self._refresh_bookmarks)
        self.settings.delete_old_ai_requested.connect(self.delete_old_ai_data)
        self.player.media_info_changed.connect(self._refresh_media_info)
        self.player.media_info_changed.connect(self._update_actions)
        self.player.picture_changed.connect(lambda v: self._remember(picture=v))
        self.player.equalizer_changed.connect(lambda v: self._remember(equalizer=v))
        self.player.enhancements_reset.connect(self._refresh_enhancements)
        self.player.state_changed.connect(lambda _s: self._refresh_enhancements())
        self.player.state_changed.connect(
            lambda state: self.library_service.set_playback_active(state is PlaybackState.PLAYING)
        )
        self._home_dirty = True
        self._update_actions()

    # --------------------------------------------------------- navigation
    @property
    def controller(self) -> PlaybackController:
        return self.player.controller

    def start_engine(self) -> None:
        self.player.start_engine()
        db = self.library_service.db
        if db.folders():
            self.library.rescan()  # background: picks up new, changed and missing files

    def current_page(self) -> QWidget:
        page = self._pages.currentWidget()
        assert page is not None
        return page

    def show_page(self, page: QWidget) -> None:
        if page is not self.player and self.isFullScreen():
            self.exit_fullscreen()
        self._pages.setCurrentWidget(page)
        for button, target in (
            (self.nav_home, self.home),
            (self.nav_player, self.player),
            (self.nav_settings, self.settings),
            (self.nav_tv, self.tv),
        ):
            button.setChecked(target is page)
        self._sync_library_buttons(page)
        self._update_chrome(page)
        if page is self.player:
            self.player.setFocus()
        elif page is self.home and self._home_dirty:
            self.refresh_home()
        elif page is self.library:
            self.library.refresh()
            self.library.refresh_current_tab()  # the tab on show may be Songs, Albums... (M3)
        elif page is self.settings:
            self._refresh_old_ai_data()
            self.settings.set_audio_devices(self.player.audio_devices())  # headphones come and go
        self._update_actions()

    def _update_actions(self) -> None:
        p = self.player
        on_player = self.current_page() is self.player
        ready = p.engine_is_ready
        self.open_action.setEnabled(ready)
        self.open_stream_action.setEnabled(ready)
        self.home.set_engine_ready(ready)
        self.play_action.setEnabled(on_player and p.has_media and p.state is not PlaybackState.ERROR)
        self.stop_action.setEnabled(on_player and (p.has_media or p.state is PlaybackState.ERROR))
        self.back_action.setEnabled(on_player and p.is_seekable)
        self.forward_action.setEnabled(on_player and p.is_seekable)
        for action in (self.volume_up_action, self.volume_down_action, self.mute_action):
            action.setEnabled(on_player and ready)
        self.fullscreen_action.setEnabled(on_player)
        queue, _index = p.queue
        self.next_action.setEnabled(on_player and p.can_go_next)
        self.previous_action.setEnabled(on_player and p.can_go_previous)
        self.shuffle_action.setEnabled(on_player and len(queue) > 1)
        self.repeat_action.setEnabled(on_player)
        self.queue_action.setEnabled(on_player and len(queue) > 1)
        self.lyrics_action.setEnabled(self.player.current_uri is not None)
        self.favourite_action.setEnabled(on_player and p.has_media)
        self.start_over_action.setEnabled(on_player and p.is_seekable)
        caps = p.capabilities_or_none()
        playing_video = p.has_media and p.state in (PlaybackState.PLAYING, PlaybackState.PAUSED)
        self.snapshot_action.setEnabled(on_player and playing_video and bool(caps and caps.supports_snapshot))
        self.next_frame_action.setEnabled(
            on_player and playing_video and bool(caps and caps.supports_frame_step)
        )
        self.previous_frame_action.setEnabled(
            on_player and playing_video and bool(caps and caps.supports_frame_back_step)
        )
        self.ab_action.setEnabled(on_player and p.is_seekable)
        self.load_subtitle_action.setEnabled(p.can_load_subtitles)
        for action in self._track_actions:
            action.setEnabled(on_player and p.can_change_tracks)
        self.sync_action.setEnabled(p.has_media and p.state is not PlaybackState.ERROR)
        has_chapters = on_player and p.is_seekable and len(p.chapters) > 1
        for action in (self.next_chapter_action, self.previous_chapter_action):
            action.setEnabled(has_chapters)
        self.chapters_menu.setEnabled(has_chapters)
        self.add_bookmark_action.setEnabled(on_player and p.can_bookmark)
        self.bookmarks_action.setEnabled(p.has_media)
        self.media_info_action.setEnabled(ready)

    # ---------------------------------------------------------- commands
    def choose_file(self) -> None:
        if not self.player.engine_is_ready:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open media", "", MEDIA_FILTER)
        if path:
            self.open_path(path)

    def choose_stream(self) -> NetworkStreamDialog | None:
        """File → Open network stream (0.12, as in 0.10). While network streams are off, it explains and
        offers to switch them on; nothing connects until the user agrees. Returns the dialog for tests."""
        if not self.player.engine_is_ready:
            return None
        if not self._prefs.network_streams:
            answer = QMessageBox.question(
                self,
                "Network streams are off",
                "Babarify plays files on this PC unless you allow network streams and IPTV.\n\n"
                "Turn them on now? You can turn them off again in Settings → Network.",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return None
            self.settings.network_streams.setChecked(True)  # saves, and restarts the engine with streams on
        recent = self.library_service.db.recent_streams() if self._prefs.remember_history else []
        dialog = NetworkStreamDialog(STREAM_SCHEMES, recent, self)
        dialog.accepted.connect(lambda: self.open_path(dialog.url) if dialog.url else None)
        dialog.open()
        return dialog

    # ------------------------------------------------------- updates (0.12)
    def check_for_updates(self, manual: bool) -> bool:
        """Ask GitHub whether a newer version is out. On its own: at most once a day, and only while the
        user allows it. Help → Check for updates always asks, and always answers."""
        if not manual and (
            not self._update_check
            or not self._prefs.check_updates
            or time.time() - self._prefs.last_update_check < CHECK_EVERY_S
        ):
            return False
        if manual:
            self.statusBar().showMessage("Checking for updates…", 4000)
        return self._updates.check(manual)

    def _on_update_result(self, payload: object) -> None:
        if not isinstance(payload, UpdateResult):
            return
        if not payload.error:
            self._remember(last_update_check=time.time())
        release = payload.release
        if release is not None and (payload.manual or release.version != self._prefs.skipped_update):
            self.update_bar.offer(release)
            if payload.manual:
                self.update_bar.show_notes()
        elif payload.manual and payload.error:
            QMessageBox.information(self, "Check for updates", f"Couldn't check: {payload.error}.")
        elif payload.manual:
            QMessageBox.information(
                self,
                "Check for updates",
                f"You have the newest version, {PRODUCT_NAME} {__version__}.",
            )

    # ------------------------------------------------------- IPTV (0.12)
    def _apply_network_streams(self) -> None:
        enabled = self._prefs.network_streams
        self.iptv.set_enabled(enabled)
        self.nav_tv.setVisible(enabled)
        self.tv_action.setVisible(enabled)
        if enabled:
            self.iptv.refresh_due()
            self.tv.refresh()
        elif self.current_page() is self.tv:
            self.show_page(self.home)

    def play_channel(self, entry: ChannelEntry) -> None:
        if self._current_channel is not None and self._current_channel.url != entry.url:
            self._last_channel = self._current_channel
        self._current_channel = entry
        self.show_page(self.player)
        self.player.open_channel(entry.url, entry.name, entry.user_agent, entry.referrer)
        self.statusBar().showMessage(f"{entry.number}  {entry.name}" if entry.number else entry.name, 4000)

    def step_channel(self, step: int) -> None:
        """Channel up and down among the channels on the TV page (Page Up / Page Down on the player)."""
        if self.player.channel_url is None:
            return
        entry = self.tv.neighbour(self.player.channel_url, step)
        if entry is not None:
            self.play_channel(entry)

    def previous_channel(self) -> None:
        """Back to the channel watched before this one (Backspace on the player)."""
        if self._last_channel is not None and self.player.channel_url is not None:
            self.play_channel(self._last_channel)

    def open_from_another_start(self, path: str) -> None:
        """A second start of the app handed over its file (0.12): come to the front and play it."""
        if self.mini.isVisible():
            self.leave_mini_player()
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()
        if path:
            self.open_path(path)

    def open_path(self, path: str) -> None:
        self.show_page(self.player)
        self.player.open_path(path)

    def _fill_chapters_menu(self) -> None:
        menu = self.chapters_menu
        menu.clear()
        current = self.player.current_chapter()
        for chapter in self.player.chapters[:200]:
            label = f"{format_time(chapter.start_ms)}  {chapter.label}".replace("&", "&&")
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(current is not None and chapter.index == current.index)
            action.triggered.connect(lambda _=False, i=chapter.index: self.player.jump_to_chapter(i))

    def show_bookmarks(self) -> BookmarksDialog:
        if self._bookmarks_dialog is None:
            dialog = BookmarksDialog(self)
            dialog.jump_requested.connect(self.player.seek_to)
            dialog.add_requested.connect(lambda: self.player.add_bookmark())
            dialog.rename_requested.connect(self.player.rename_bookmark)
            dialog.delete_requested.connect(self.player.delete_bookmark)
            self._bookmarks_dialog = dialog
        self._refresh_bookmarks()
        self._bookmarks_dialog.show()
        self._bookmarks_dialog.raise_()
        return self._bookmarks_dialog

    def _refresh_bookmarks(self) -> None:
        if self._bookmarks_dialog is not None:
            p = self.player
            name = p.controls.title_label.toolTip() if p.has_media else ""
            self._bookmarks_dialog.set_bookmarks(name, p.bookmarks, can_add=p.can_bookmark)
        self._update_actions()

    # --------------------------------------------- data left by the removed AI feature
    def delete_old_ai_data(self) -> None:
        db = self.library_service.db
        size = legacy_ai.leftover_bytes(db)
        if not size:
            return
        answer = QMessageBox.question(
            self,
            "Delete old AI data",
            f"Delete the speech models and machine-generated subtitles left by earlier versions "
            f"({size / 1e6:.0f} MB)? Your media files and your own subtitles are not affected.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        legacy_ai.delete_leftovers(db)
        self.statusBar().showMessage("Old AI data deleted")
        self._refresh_old_ai_data()

    def _refresh_old_ai_data(self) -> None:
        self.settings.set_old_ai_data(legacy_ai.leftover_bytes(self.library_service.db))

    def show_report(self) -> ReportDialog:
        """Help → Report a problem (M11): text to copy into the issue form; nothing is sent."""

        def gather() -> tuple[dict[str, str], MediaInfo | None, str, str]:
            p = self.player
            if not p.engine_is_ready:
                return {"Engine": "not started"}, None, "", p.last_error
            diag = dict(p.controller.engine.diagnostics())
            diag.pop("log_errors", None)
            info = p.controller.media_info() if p.has_media else None
            return diag, info, p.media_name, p.last_error

        dialog = ReportDialog(gather, self)
        dialog.show()
        return dialog

    def show_media_info(self) -> MediaInfoDialog:
        if self._media_info_dialog is None:
            self._media_info_dialog = MediaInfoDialog(self)
        self._refresh_media_info()
        self._media_info_dialog.show()
        self._media_info_dialog.raise_()
        return self._media_info_dialog

    def _refresh_media_info(self) -> None:
        dialog = self._media_info_dialog
        if dialog is None:
            return
        p = self.player
        status = p.controller.status() if p.engine_is_ready else None
        uri = status.uri if status is not None and p.has_media and status.uri else ""
        dialog.set_media(p.controller.media_info() if uri else None, uri)

    def play_list(self, paths: list[str], start: int = 0) -> None:
        self.show_page(self.player)
        self.player.play_queue(paths, start)

    def choose_library_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Add a folder to the library")
        if path:
            self.add_library_folder(path)

    def add_library_folder(self, path: str) -> None:
        self.show_page(self.library)
        self.library.add_folder(path)

    # ------------------------------------------------------- history (M6)
    def refresh_home(self) -> None:
        self._home_dirty = False
        db = self.library_service.db
        self.home.refresh_greeting()
        newest = db.media(sort=SortOrder.DATE_ADDED, limit=ADDED_LIMIT)
        self.home.set_recently_added(
            [(e.path, e.display_title, self.library_service.thumbnail_path(e.thumbnail)) for e in newest]
        )
        if not self._prefs.remember_history:
            self.home.set_history([], [], lambda _e: None)
            return
        self.home.set_history(db.continue_watching(), db.recent(), self._thumbnail_for)

    def play_now(self) -> None:
        """The banner's Play now: carry on with what was playing; else the newest file in the library."""
        db = self.library_service.db
        if self._prefs.remember_history:
            for entry in (*db.continue_watching(1), *db.recent(1)):
                if entry.available:
                    self.open_path(entry.path)
                    return
        newest = db.media(sort=SortOrder.DATE_ADDED, limit=1)
        if newest:
            self.open_path(newest[0].path)
        else:
            self.choose_file()

    def _thumbnail_for(self, entry: HistoryEntry) -> Path | None:
        return self.library_service.thumbnail_path(entry.thumbnail)

    def _history_changed(self) -> None:
        self._home_dirty = True
        if self.current_page() is self.home:
            self.refresh_home()
        self._update_actions()

    def _forget(self, path: str) -> None:
        self.library_service.db.remove_history(path)
        self.refresh_home()
        self.statusBar().showMessage("Removed from history")

    def back_up(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Back up settings and playlists", "babarify-backup.json", "Backup (*.json)"
        )
        if not path:
            return
        try:
            backup.write_backup(Path(path), backup.build_backup(self._prefs, self.library_service.db))
        except OSError as exc:
            QMessageBox.warning(self, "Back up", f"The backup couldn't be saved.\n{exc}")
            return
        self._notify_status("Backup saved")

    def restore_from_backup(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Restore from a backup", "", "Backup (*.json)")
        if not path:
            return
        try:
            data = backup.read_backup(Path(path))
        except backup.BackupError as exc:
            QMessageBox.warning(self, "Restore", str(exc))
            return
        answer = QMessageBox.question(
            self,
            "Restore",
            "Your settings are replaced by the ones in the file. Playlists, favourites and hidden files are "
            "added to the ones you have.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        restored = backup.restore_lists(data, self.library_service.db)
        prefs = Preferences.from_dict(data.get("preferences", {}))
        self.settings.set_preferences(prefs)
        self._on_preferences_changed(prefs)
        self._prefs = replace(
            self._prefs,
            repeat_mode=prefs.repeat_mode,
            library_sort=prefs.library_sort,
            picture=prefs.picture,
            equalizer=prefs.equalizer,
            profiles=prefs.profiles,
        )
        self.player.set_preferences(self._prefs)
        self._store.save(self._prefs)
        self.library.playlists.refresh()
        self.library.refresh()
        self._notify_status(
            f"Restored. New playlists: {restored.playlists}. New favourites: {restored.favourites}."
        )

    def _notify_status(self, text: str) -> None:
        QMessageBox.information(self, "Backup", text)

    def show_lyrics(self) -> None:
        uri = self.player.current_uri
        if uri is None:
            return
        dialog = LyricsDialog(uri, lambda: self.player.position_ms, self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.show()

    def show_hidden_files(self) -> None:
        HiddenFilesDialog(self.library_service, self).exec()
        self.library.refresh()

    def clear_history(self) -> None:
        answer = QMessageBox.question(
            self,
            "Clear history",
            "Clear recently played files and all resume positions? Library folders, files and "
            "playlists are not affected.",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.library_service.db.clear_history()
            self._remember(last_queue=(), last_queue_index=-1)  # the saved queue is history too
            self.refresh_home()
            self.statusBar().showMessage("History cleared")

    # ------------------------------------------------- picture and sound (M7)
    def show_enhancements(self) -> EnhancementsDialog:
        if self._enhancements is None:
            dialog = EnhancementsDialog(self._preset_values, self)
            dialog.picture_changed.connect(self.player.set_picture)
            dialog.equalizer_changed.connect(self.player.set_equalizer)
            dialog.geometry_changed.connect(self.player.set_geometry)
            dialog.transform_changed.connect(self.player.set_transform)
            dialog.profiles_changed.connect(lambda profiles: self._remember(profiles=tuple(profiles)))
            self._enhancements = dialog
        self._enhancements.set_profiles(self._prefs.profiles)
        self._refresh_enhancements()
        self._enhancements.show()
        self._enhancements.raise_()
        return self._enhancements

    def _preset_values(self, name: str) -> EqualizerSettings:
        return self.player.controller.engine.equalizer_preset(name)

    def _refresh_enhancements(self) -> None:
        dialog = self._enhancements
        if dialog is None:
            return
        p = self.player
        info = p.controller.media_info() if p.engine_is_ready else None
        has_video = bool(info and info.video_codec)
        dialog.set_capabilities(p.capabilities_or_none(), has_video)
        dialog.set_picture(self._prefs.picture)
        dialog.set_equalizer(self._prefs.equalizer)
        dialog.set_video(p.video_geometry, p.transform)

    def _remember(self, **changes: object) -> None:
        self._prefs = replace(self._prefs, **changes)  # type: ignore[arg-type]
        self._store.save(self._prefs)

    def _on_library_sort(self, sort: str) -> None:
        self._prefs = replace(self._prefs, library_sort=sort)
        self._store.save(self._prefs)

    def choose_subtitle_file(self) -> None:
        """Explicit user action: the file is read locally by the engine, never uploaded."""
        if not self.player.can_load_subtitles:
            return
        status = self.player.controller.status()
        start = str(Path(status.uri).parent) if status.uri and "://" not in status.uri else ""
        path, _ = QFileDialog.getOpenFileName(self, "Load subtitle file", start, SUBTITLE_FILTER)
        if path:
            self.player.load_subtitle_file(path)

    def _set_media_title(self, name: str) -> None:
        self.setWindowTitle(f"{name} — {PRODUCT_NAME}" if name else PRODUCT_NAME)

    def _on_engine_ready(self, ok: bool) -> None:
        self.settings.set_audio_devices(self.player.audio_devices())
        # Songs waiting to be read, like an existing library's after an update, need no rescan.
        if ok and self.library_service.db.counts()[2]:
            self.library_service.fetch_metadata()
        if not ok:
            self.show_page(self.player)  # the player page explains what failed
        elif self._prefs.remember_history and self._prefs.last_queue and self.player.current_uri is None:
            # The queue of the last session, paused where it was: nothing plays until asked (M2).
            self.player.restore_queue(list(self._prefs.last_queue), self._prefs.last_queue_index)
        db = self.library_service.db
        notice = db.recovered or db.read_only_reason
        if notice:  # after the engine's own status line, so it is not overwritten
            self.statusBar().showMessage(notice)
            # Too important to leave on a bar that may be hidden: the library was replaced or not opened.
            box = QMessageBox(QMessageBox.Icon.Warning, "Library", notice, parent=self)
            box.setTextFormat(Qt.TextFormat.PlainText)
            box.open()
        self._update_actions()

    def _on_video_started(self) -> None:
        if self._prefs.start_fullscreen and not self.isFullScreen():
            self.toggle_fullscreen()

    # --------------------------------------------------------- fullscreen
    def toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.exit_fullscreen()
            return
        if self.current_page() is not self.player:
            self.show_page(self.player)
        self._was_maximized = self.isMaximized()
        for widget in (self._rail, self.menuBar(), self.statusBar(), self.update_bar):
            widget.hide()
        self.showFullScreen()
        self._update_chrome()
        self.player.set_fullscreen_mode(True)

    def exit_fullscreen(self) -> None:
        if not self.isFullScreen():
            return
        self.player.set_fullscreen_mode(False)
        if self._was_maximized:
            self.showMaximized()
        else:
            self.showNormal()
        for widget in (self._rail, self.menuBar()):
            widget.show()
        self.statusBar().setVisible(self._prefs.show_status_bar)
        self._update_chrome()

    # -------------------------------------------------------- preferences
    def _restore_geometry(self) -> None:
        geo = self._prefs.window
        self.resize(DEFAULT_SIZE)
        if geo is None:
            return
        rect = QRect(geo.x, geo.y, geo.width, geo.height)
        # Ignore saved positions that are no longer on any screen (monitor unplugged, DPI change).
        if any(screen.availableGeometry().intersects(rect) for screen in QGuiApplication.screens()):
            self.setGeometry(rect)
        if geo.maximized:
            self.setWindowState(self.windowState() | Qt.WindowState.WindowMaximized)

    def _on_preferences_changed(self, prefs: object) -> None:
        if not isinstance(prefs, Preferences):
            return
        history_toggled = prefs.remember_history != self._prefs.remember_history
        streams_toggled = prefs.network_streams != self._prefs.network_streams
        theme_changed = prefs.colour_theme != self._prefs.colour_theme
        background_changed = prefs.background_picture != self._prefs.background_picture
        self._prefs = replace(
            prefs,
            volume=self._prefs.volume,
            muted=self._prefs.muted,
            repeat_mode=self._prefs.repeat_mode,
            window=self._prefs.window,
            library_sort=self._prefs.library_sort,
            picture=self._prefs.picture,
            equalizer=self._prefs.equalizer,
            profiles=self._prefs.profiles,
        )
        self.player.set_preferences(self._prefs)
        self._store.save(self._prefs)
        if streams_toggled:
            self._apply_network_streams()
        self.status_bar_action.setChecked(self._prefs.show_status_bar)
        if not self.isFullScreen():
            self.statusBar().setVisible(self._prefs.show_status_bar)
        if background_changed and not theme_changed:
            self._apply_background()
        if theme_changed:
            self._apply_colour_theme(self._prefs.colour_theme)
            self._apply_background()
            self.player.refresh_theme()
            self.home.refresh_theme()
            self.player_bar.refresh_theme()
            self.now_panel.refresh_theme()
            self._draw_rail_brand()
            self._draw_rail_toggle()
            for button, glyph in self._nav_icons:
                nav_icon = glyph_icon(glyph, theme.TEXT, theme.TEXT_DISABLED, size=64, weight=0.03)
                if nav_icon is not None:
                    button.setIcon(nav_icon)
            self._home_dirty = True  # Its cards hold pictures drawn in the old colours.
        if history_toggled:
            self._home_dirty = True
        self._update_actions()

    def shuffle_list(self, paths: list[str]) -> None:
        self.show_page(self.player)
        self.player.play_queue(paths, random.randrange(len(paths)), shuffle=True)

    def build_theme_menu(self) -> QMenu:
        """Every theme, one click away. Choosing one goes through Settings, so both always agree."""
        menu = QMenu(self)
        for key, palette in THEMES.items():
            action = menu.addAction(theme_swatch(palette), palette.label)
            action.setCheckable(True)
            action.setChecked(key == self._prefs.colour_theme)
            action.triggered.connect(lambda _=False, chosen=key: self.choose_colour_theme(chosen))
        return menu

    def build_animation_menu(self) -> QMenu:
        menu = QMenu(self)
        for style, label in STYLE_LABELS.items():
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(self._prefs.visual_style == style.value)
            action.triggered.connect(lambda _=False, s=style: self._choose_animation(s))
        return menu

    # ------------------------------------------------------- mini-player and always on top (M3)
    def enter_mini_player(self) -> None:
        if self.isFullScreen():
            self.exit_fullscreen()
        self.mini.show()
        set_topmost(self.mini, self._prefs.always_on_top)
        self.hide()
        self.mini.raise_()
        self.mini.activateWindow()

    def leave_mini_player(self) -> None:
        self.mini.hide()
        self.show()
        set_topmost(self, self._prefs.always_on_top)
        self.raise_()
        self.activateWindow()

    def set_always_on_top(self, enabled: bool) -> None:
        self._remember(always_on_top=enabled)
        for window in (self, self.mini):
            if window.isVisible():
                set_topmost(window, enabled)

    def _keep_on_top(self, window: QWidget) -> None:
        """Windows ignores "on top" from a window that isn't the active one (measured: no error, no change),
        e.g. right after start-up or when the mini player opens behind another app. So it is asked again
        whenever one of our windows becomes active."""
        if self._prefs.always_on_top:
            set_topmost(window, True)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._keep_on_top(self)

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.ActivationChange and self.isActiveWindow():
            self._keep_on_top(self)

    def show_library(self, section: str, tab: str | None = None, automatic: str | None = None) -> None:
        """Music, Videos or Playlists (M3): one page, showing one part of the library at a time. Since the
        0.12 side bar, also straight to a tab (Albums, Artists) or an automatic playlist (Favourites)."""
        if self.library.section != section:
            self.library.set_section(section)
        if tab is not None:
            names = [self.library.tabs.tabText(i) for i in range(self.library.tabs.count())]
            if tab in names:
                self.library.tabs.setCurrentIndex(names.index(tab))
        if automatic is not None:
            self.library.playlists.show_automatic(automatic)
        self.show_page(self.library)

    def _sync_library_buttons(self, page: QWidget) -> None:
        """The side bar lights the button for what the library page shows now."""
        current = self.library.tabs.tabText(self.library.tabs.currentIndex())
        automatic = self.library.playlists.current_automatic
        best = None
        for button, section, tab, auto in self._library_buttons:
            if page is self.library and self.library.section == section:
                if section == "playlists":
                    if auto == automatic:
                        best = button
                elif tab is None or tab == current:
                    best = button
        for button, _section, _tab, _auto in self._library_buttons:
            button.setChecked(button is best)

    def _update_chrome(self, page: QWidget | None = None) -> None:
        """The player bar and Now Playing panel step aside on the Playing page, which has its own controls,
        and in full screen; the panel also when the user hid it or the window is narrow (0.12)."""
        page = page or self.current_page()
        full = self.isFullScreen()
        self.player_bar.setVisible(page is not self.player and not full)
        self.now_panel.setVisible(
            page is not self.player
            and not full
            and self._prefs.show_now_panel
            and self.width() >= PANEL_MIN_WIDTH
        )
        self._place_video(page)

    def _place_video(self, page: QWidget | None = None) -> None:
        """A video plays on, live, in the Now Playing panel while another page shows, and comes back to the
        Playing page and full screen as soon as they show (0.12)."""
        if not hasattr(self, "now_panel"):
            return  # still being built
        lend = (
            self.player.has_video
            and self.now_panel.isVisibleTo(self)
            and (page or self.current_page()) is not self.player
            and not self.isFullScreen()
        )
        if lend != self.player.video_lent:
            self.player.lend_video(self.now_panel.video_slot if lend else None)
            self.now_panel.follow_video()  # the cover makes way before the panel is drawn again

    def _on_video_clicked(self) -> None:
        if self.player.video_lent:
            self.show_page(self.player)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is getattr(self, "_rail", None) and event.type() == QEvent.Type.Resize:
            self._place_rail_toggle()  # the arrow stays halfway down the side bar's edge
        return super().eventFilter(watched, event)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if hasattr(self, "now_panel"):
            self._update_chrome()

    def set_now_panel(self, shown: bool) -> None:
        self._remember(show_now_panel=shown)
        self._update_chrome()

    def _fill_theme_menu(self) -> None:
        self.theme_menu.clear()
        for action in self.build_theme_menu().actions():
            action.setParent(self.theme_menu)
            self.theme_menu.addAction(action)

    def choose_colour_theme(self, key: str) -> None:
        combo = self.settings.colour_theme
        combo.setCurrentIndex(max(0, combo.findData(key)))

    def _on_repeat_changed(self, mode: object) -> None:
        self._prefs = replace(self._prefs, repeat_mode=str(mode))
        self.settings.set_preferences(self._prefs)
        self._store.save(self._prefs)

    def show_queue(self) -> None:
        queue, index = self.player.queue
        if len(queue) < 2:
            self.statusBar().showMessage("No playlist is playing")
            return
        names = [Path(path).stem if "://" not in path else path for path in queue]
        QueueDialog(names, index, self.player.play_queue_item, self).open()

    def _fill_sleep_menu(self) -> None:
        self.sleep_menu.clear()
        remaining = self.player.sleep_remaining_ms
        off = self.sleep_menu.addAction("Off")
        off.setCheckable(True)
        off.setChecked(remaining is None)
        off.triggered.connect(lambda: self.player.set_sleep_timer(None))
        if remaining is not None:
            left = self.sleep_menu.addAction(f"Pausing in {format_time(remaining)}")
            left.setEnabled(False)
        self.sleep_menu.addSeparator()
        for minutes in SLEEP_MINUTES:
            action = self.sleep_menu.addAction(f"{minutes} minutes")
            action.triggered.connect(lambda _=False, m=minutes: self.player.set_sleep_timer(m))

    def _fill_animation_menu(self) -> None:
        self.animation_menu.clear()
        for style, label in STYLE_LABELS.items():
            action = self.animation_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(self._prefs.visual_style == style.value)
            action.triggered.connect(lambda _=False, s=style: self._choose_animation(s))

    def _choose_status_bar(self, shown: bool) -> None:
        if shown == self._prefs.show_status_bar:
            return
        self._prefs = replace(self._prefs, show_status_bar=shown)
        self.settings.set_preferences(self._prefs)
        self._store.save(self._prefs)
        if not self.isFullScreen():
            self.statusBar().setVisible(shown)

    def _choose_animation(self, style: VisualStyle) -> None:
        self._prefs = replace(self._prefs, visual_style=style.value)
        self.player.set_preferences(self._prefs)
        self.settings.set_preferences(self._prefs)
        self._store.save(self._prefs)

    @staticmethod
    def _apply_colour_theme(key: str) -> None:
        if key == theme.current_theme:
            return
        theme.apply_theme(key)
        app = QGuiApplication.instance()
        if isinstance(app, QApplication):
            # Windows draws the title bar and some small parts of controls, and follows this for them.
            scheme = Qt.ColorScheme.Light if theme.is_light() else Qt.ColorScheme.Unknown
            app.styleHints().setColorScheme(scheme)
            app.setStyleSheet(theme.STYLESHEET)

    def _apply_background(self) -> None:
        """The person's picture behind the pages, dimmed with the theme's colour so text stays readable."""
        app = QGuiApplication.instance()
        prepared = ""
        source = self._prefs.background_picture
        image = QImage(source) if source else QImage()
        if not image.isNull():
            image = image.scaled(
                QSize(1920, 1920),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ).convertToFormat(QImage.Format.Format_RGB32)
            painter = QPainter(image)
            dim = QColor(theme.BG)
            dim.setAlpha(205)
            painter.fillRect(image.rect(), dim)
            painter.end()
            target = self._store.path.parent / "background.png"
            with contextlib.suppress(OSError):
                target.parent.mkdir(parents=True, exist_ok=True)
            if image.save(str(target)):
                prepared = str(target)
        theme.set_background(prepared)
        if isinstance(app, QApplication):
            app.setStyleSheet(theme.STYLESHEET)

    def _final_preferences(self) -> Preferences:
        normal = self.normalGeometry() if (self.isMaximized() or self.isFullScreen()) else self.geometry()
        maximized = self.isMaximized() or (self.isFullScreen() and self._was_maximized)
        prefs = replace(
            self._prefs,
            window=WindowGeometry(normal.x(), normal.y(), normal.width(), normal.height(), maximized),
        )
        if prefs.remember_volume:
            volume, muted = self.player.volume_state()
            prefs = replace(prefs, volume=volume, muted=muted)
        queue, index = self.player.queue
        if prefs.remember_history and queue:
            prefs = replace(prefs, last_queue=tuple(queue), last_queue_index=index)
        elif not prefs.remember_history:
            prefs = replace(prefs, last_queue=(), last_queue_index=-1)
        return prefs.normalized()

    # ------------------------------------------------------------ window
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        urls = event.mimeData().urls()
        dropped_stream = self._prefs.network_streams and bool(urls) and is_network_uri(urls[0].toString())
        if self.player.engine_is_ready and urls and (urls[0].isLocalFile() or dropped_stream):
            event.acceptProposedAction()
            self.home.set_drag_active(True)

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self.home.set_drag_active(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        self.home.set_drag_active(False)
        urls = event.mimeData().urls()
        if urls and not urls[0].isLocalFile() and is_network_uri(urls[0].toString()):
            if self._prefs.network_streams:  # a link dragged from a browser (as in 0.10)
                self.open_path(urls[0].toString())  # checked by the engine like a typed address
                event.acceptProposedAction()
            return
        if urls and urls[0].isLocalFile() and Path(urls[0].toLocalFile()).is_dir():
            self.add_library_folder(urls[0].toLocalFile())  # a dropped folder joins the library
            event.acceptProposedAction()
            return
        if urls and urls[0].isLocalFile():
            path = urls[0].toLocalFile()
            # A subtitle dropped onto a playing video is added to it; anything else is opened.
            if Path(path).suffix.lower() in SUBTITLE_EXTENSIONS and self.player.can_load_subtitles:
                self.show_page(self.player)
                self.player.load_subtitle_file(path)
            else:
                self.open_path(path)
            event.acceptProposedAction()

    def show_playback_info(self) -> PlaybackInfoDialog:
        if self._info_dialog is None:
            self._info_dialog = PlaybackInfoDialog(
                self.player.controller, lambda: self.player.last_error, self
            )
        self._info_dialog.show()
        self._info_dialog.raise_()
        return self._info_dialog

    def _show_shortcuts(self) -> None:
        rows = "".join(
            f"<tr><td><b>{keys}</b>&nbsp;&nbsp;</td><td>{what}</td></tr>" for keys, what in SHORTCUTS
        )
        extra = (
            "<tr><td><b>S</b></td><td>Stop</td></tr>"
            "<tr><td><b>Ctrl+N</b></td><td>Open network stream</td></tr>"
            "<tr><td><b>F11 / double-click</b>&nbsp;&nbsp;</td><td>Fullscreen</td></tr>"
            "<tr><td><b>Esc</b></td><td>Leave fullscreen</td></tr>"
            "<tr><td><b>Ctrl+1 / 2 / 3</b>&nbsp;&nbsp;</td><td>Home / Now Playing / Settings</td></tr>"
            "<tr><td><b>Ctrl+I</b></td><td>Playback info</td></tr>"
            "<tr><td><b>Ctrl+L</b></td><td>Library</td></tr>"
            "<tr><td><b>Z</b></td><td>Shuffle</td></tr>"
            "<tr><td><b>R</b></td><td>Repeat: off, this file, all</td></tr>"
            "<tr><td><b>Q</b></td><td>Queue</td></tr>"
            "<tr><td><b>U</b></td><td>Add to or remove from favourites</td></tr>"
            "<tr><td><b>N / P</b></td><td>Next / previous in playlist</td></tr>"
            "<tr><td><b>Home</b></td><td>Start over</td></tr>"
            "<tr><td><b>Ctrl+E</b></td><td>Picture &amp; Sound</td></tr>"
            "<tr><td><b>Shift+S</b></td><td>Snapshot (Pictures\\Babarify Media Player)</td></tr>"
            "<tr><td><b>. / ,</b></td><td>Next / previous frame</td></tr>"
            "<tr><td><b>L</b></td><td>A-B repeat (set A, set B, off)</td></tr>"
            "<tr><td><b>V / B</b></td><td>Next subtitle / audio track</td></tr>"
            "<tr><td><b>G / H</b></td><td>Subtitles 50 ms earlier / later</td></tr>"
            "<tr><td><b>J / K</b></td><td>Audio 50 ms earlier / later</td></tr>"
            "<tr><td><b>Ctrl+D</b></td><td>Sync and delay</td></tr>"
            "<tr><td><b>Ctrl+Shift+O</b>&nbsp;&nbsp;</td><td>Load subtitle file</td></tr>"
            "<tr><td><b>Ctrl+→ / Ctrl+←</b>&nbsp;&nbsp;</td><td>Next / previous chapter</td></tr>"
            "<tr><td><b>Ctrl+B</b></td><td>Add bookmark</td></tr>"
            "<tr><td><b>Ctrl+Shift+B</b>&nbsp;&nbsp;</td><td>Bookmarks</td></tr>"
            "<tr><td><b>Ctrl+Shift+I</b>&nbsp;&nbsp;</td><td>Media information</td></tr>"
            "<tr><td><b>F1</b></td><td>This list</td></tr>"
        )
        QMessageBox.information(
            self,
            "Keyboard shortcuts",
            f"<table>{rows}{extra}</table><br>Playback keys work on the Now Playing page.",
        )

    def _show_about(self) -> None:
        engine = ""
        if self.player.engine_is_ready:
            caps = self.player.controller.capabilities()
            engine = f"<br>Playback engine: {caps.engine_name} {caps.engine_version}"
        QMessageBox.about(
            self,
            f"About {PRODUCT_NAME}",
            f"<b>{PRODUCT_NAME}</b> {__version__}<br>{TAGLINE}<br><br>"
            f"Free, no ads, no account, no telemetry.{engine}",
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        self.mini.hide()
        self.mini.deleteLater()
        if self._info_dialog is not None:
            self._info_dialog.close()
        if self._enhancements is not None:
            self._enhancements.close()
        self._now.stop()  # the player bar and panel stop reading the library before it closes
        self.player.lend_video(None)
        self._store.save(self._final_preferences())
        # Rule: the engine must be closed while its host window still exists.
        self.player.shutdown()  # also saves the playback position
        self.tv.stop()
        self.iptv.shutdown()
        self.library.stop_listening()
        self.library_service.shutdown()
        self.library_service.db.close()
        super().closeEvent(event)
