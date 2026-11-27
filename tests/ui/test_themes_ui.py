"""Changing the colour theme while the app runs, and the equalizer's dials."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QDial, QLabel, QPushButton
from pytestqt.qtbot import QtBot

from babarify_frame.configuration.preferences import PreferencesStore
from babarify_frame.core.themes import DEFAULT_THEME, THEMES
from babarify_frame.playback.adapters.mock import MockEngine
from babarify_frame.playback.factory import EngineDescriptor, EngineFactory, EngineProbe
from babarify_frame.ui import controls, theme
from babarify_frame.ui.app import load_icon
from babarify_frame.ui.audio_view import colour_from
from babarify_frame.ui.main_window import MainWindow
from babarify_frame.ui.pages.library import SECTION_TABS
from babarify_frame.ui.pages.settings import theme_swatch

pytestmark = pytest.mark.ui


def make_window(qtbot: QtBot, tmp_path: Path) -> MainWindow:
    factory = EngineFactory()
    factory.register(EngineDescriptor("mock", "Mock", MockEngine, lambda: EngineProbe("mock", True, "1.0")))
    win = MainWindow(
        factory, load_icon(), engine_name="mock", store=PreferencesStore(tmp_path / "settings.json")
    )
    qtbot.addWidget(win)
    win.show()
    win.start_engine()
    qtbot.waitUntil(lambda: win.player.engine_is_ready, timeout=5000)
    return win


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    win = make_window(qtbot, tmp_path)
    yield win
    win.close()
    theme.apply_theme(DEFAULT_THEME)
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    app.setStyleSheet(theme.STYLESHEET)


def real_display() -> bool:
    return QApplication.platformName() != "offscreen"


def choose(window: MainWindow, key: str) -> None:
    combo = window.settings.colour_theme
    combo.setCurrentIndex(combo.findData(key))


def test_settings_offer_every_theme(window: MainWindow) -> None:
    combo = window.settings.colour_theme
    assert [combo.itemData(i) for i in range(combo.count())] == list(THEMES)
    assert combo.currentData() == DEFAULT_THEME
    assert not combo.itemIcon(1).isNull(), "each shows its colours"


def test_choosing_a_theme_applies_at_once_and_is_remembered(window: MainWindow, tmp_path: Path) -> None:
    choose(window, "aurora")
    assert theme.current_theme == "aurora"
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    assert THEMES["aurora"].bg in app.styleSheet()
    pixel = window.settings.grab().toImage().pixelColor(2, 2)
    assert pixel.name().upper() == THEMES["aurora"].bg
    assert PreferencesStore(tmp_path / "settings.json").load().colour_theme == "aurora"


def test_a_saved_theme_applies_when_the_app_starts(qtbot: QtBot, tmp_path: Path) -> None:
    store = PreferencesStore(tmp_path / "settings.json")
    store.save(store.load().__class__(colour_theme="violet"))
    win = make_window(qtbot, tmp_path)
    try:
        assert theme.current_theme == "violet"
        assert win.settings.colour_theme.currentData() == "violet"
    finally:
        win.close()
        theme.apply_theme(DEFAULT_THEME)
        app = QApplication.instance()
        assert isinstance(app, QApplication)
        app.setStyleSheet(theme.STYLESHEET)


def test_lit_buttons_take_the_new_colour(
    qtbot: QtBot, window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Checks the colour asked for, not the picture: a machine without the icon font draws plain icons.
    asked: list[str] = []
    real_icon = controls.icon

    def recording_icon(widget, name, color=None):  # type: ignore[no-untyped-def]
        asked.append(color or theme.TEXT)
        return real_icon(widget, name, color)

    monkeypatch.setattr(controls, "icon", recording_icon)
    window.player.cycle_repeat()
    assert THEMES[DEFAULT_THEME].accent2 in asked
    asked.clear()
    choose(window, "neon")
    assert THEMES["neon"].accent2 in asked


def test_light_redraws_every_button_and_the_rail_in_its_colours(
    qtbot: QtBot, window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[str] = []
    real_icon = controls.icon

    def recording_icon(widget, name, color=None):  # type: ignore[no-untyped-def]
        asked.append(color or theme.TEXT)
        return real_icon(widget, name, color)

    monkeypatch.setattr(controls, "icon", recording_icon)
    choose(window, "light")
    assert THEMES["light"].text in asked, "ordinary buttons"
    assert "#FFFFFF" in asked, "the play button"
    assert THEMES[DEFAULT_THEME].text not in asked
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    if real_display():  # with no display, Qt ignores the request
        assert app.styleHints().colorScheme() == Qt.ColorScheme.Light
    pixel = window.settings.grab().toImage().pixelColor(2, 2)
    assert pixel.name().upper() == THEMES["light"].bg
    choose(window, DEFAULT_THEME)


def test_the_colour_theme_is_one_click_away_in_the_view_menu(window: MainWindow, tmp_path: Path) -> None:
    window.theme_menu.aboutToShow.emit()  # as when the menu opens
    actions = window.theme_menu.actions()
    assert [action.text() for action in actions] == [palette.label for palette in THEMES.values()]
    assert [action.text() for action in actions if action.isChecked()] == ["Ocean Glow"]
    next(action for action in actions if action.text() == "Aurora Dream").trigger()
    assert theme.current_theme == "aurora"
    assert window.settings.colour_theme.currentData() == "aurora", "Settings agrees"
    assert PreferencesStore(tmp_path / "settings.json").load().colour_theme == "aurora"
    window.theme_menu.aboutToShow.emit()
    assert [a.text() for a in window.theme_menu.actions() if a.isChecked()] == ["Aurora Dream"]
    choose(window, DEFAULT_THEME)


def test_the_animation_is_chosen_in_the_view_menu(window: MainWindow, tmp_path: Path) -> None:
    actions = window.build_animation_menu().actions()
    assert [a.text() for a in actions if a.isChecked()] == ["Change automatically"]
    next(a for a in actions if a.text() == "Circle").trigger()
    assert window.player.audio_view.visualizer.style_choice.value == "circle"
    assert window.settings.visual_style.currentData() == "circle", "Settings agrees"
    assert PreferencesStore(tmp_path / "settings.json").load().visual_style == "circle"
    assert [a.text() for a in window.build_animation_menu().actions() if a.isChecked()] == ["Circle"]


def side_bar(window: MainWindow) -> list[str]:
    buttons = (b for b in window.findChildren(QPushButton) if b.objectName() == "navButton" and b.isVisible())
    return [b.text() for b in sorted(buttons, key=lambda b: b.y())]


def test_the_rail_follows_the_design(window: MainWindow) -> None:
    """The side bar of the 0.12 redesign: the pages, then Your library and Tools, the theme at the foot."""
    assert side_bar(window) == [
        "Home", "Music", "Videos", "Now Playing",
        "Albums", "Artists", "Playlists", "Favourites", "Recently Played",
        "Equalizer", "Settings", "Theme",
    ]  # fmt: skip
    sections = [label.text() for label in window.findChildren(QLabel) if label.objectName() == "railSection"]
    assert sections == ["Tools"] and window.library_toggle.text() == "Your Library"  # a drop-down (0.12)
    buttons = [b for b in window.findChildren(QPushButton) if b.objectName() == "navButton" and b.isVisible()]
    assert {b.width() for b in buttons} == {window.nav_home.width()}, "lined up"
    if real_display():  # with no display there is no Arial or icon font, so the sizes mean nothing
        for button in buttons:
            assert button.sizeHint().width() <= button.width(), f"{button.text()} would be cut off"
    assert window.nav_theme.y() > window.nav_settings.geometry().bottom(), "the theme sits at the foot"
    window.nav_settings.click()
    assert window.current_page() is window.settings


@pytest.mark.parametrize(
    ("button", "section", "title"),
    [
        ("nav_music", "music", "Music"),
        ("nav_videos", "videos", "Videos"),
        ("nav_playlists", "playlists", "Playlists"),
    ],
)
def test_music_videos_and_playlists_show_their_part_of_the_library(
    window: MainWindow, button: str, section: str, title: str
) -> None:
    getattr(window, button).click()
    library = window.library
    assert window.current_page() is library and library.section == section and library.title.text() == title
    assert getattr(window, button).isChecked()
    shown = [library.tabs.tabText(i) for i in range(library.tabs.count()) if library.tabs.isTabVisible(i)]
    assert shown == list(SECTION_TABS[section])
    assert library.video_view.isVisibleTo(library) is (section == "videos")


def test_the_name_and_logo_lead_the_side_bar(window: MainWindow) -> None:
    """0.12 branding: the neon mark with "BABARIFY MEDIA PLAYER" leads the side bar; Home greets."""
    assert window._rail_wordmark.accessibleName() == "Babarify Media Player"
    assert window._rail_wordmark.pixmap() is not None and not window._rail_wordmark.pixmap().isNull()
    assert window.windowTitle() == "Babarify Media Player"
    window.show_page(window.home)
    assert window.home.greeting.text() in ("Good Morning", "Good Afternoon", "Good Evening")
    assert window.home.banner_logo.pixmap() is not None and not window.home.banner_logo.pixmap().isNull()


def test_light_themes_get_the_light_logos(window: MainWindow) -> None:
    from babarify_frame.ui import widgets

    choose(window, "light")
    assert widgets._brand_file("babarify-wordmark").endswith("babarify-wordmark-light.png")
    choose(window, "ocean")
    assert widgets._brand_file("babarify-wordmark").endswith("babarify-wordmark.png")


def test_your_library_opens_and_closes(window: MainWindow, tmp_path: Path) -> None:
    """0.12: Your Library is a drop-down; closed, its entries hide; the choice is remembered."""
    window.library_toggle.click()
    assert not window.nav_albums.isVisible() and not window.nav_recent.isVisible()
    assert not PreferencesStore(tmp_path / "settings.json").load().library_open
    window.set_rail_folded(True)
    assert window.nav_albums.isVisible()  # folded, every icon shows
    window.set_rail_folded(False)
    assert not window.nav_albums.isVisible()
    window.library_toggle.click()
    assert window.nav_albums.isVisible() and PreferencesStore(tmp_path / "settings.json").load().library_open


def test_a_background_picture_goes_behind_the_pages_until_removed(window: MainWindow, tmp_path: Path) -> None:
    picture = tmp_path / "mine.png"
    image = QImage(8, 8, QImage.Format.Format_RGB32)
    image.fill(QColor("#FF0000"))
    assert image.save(str(picture))
    window.settings.set_background(str(picture))
    assert "border-image" in theme.STYLESHEET
    assert PreferencesStore(tmp_path / "settings.json").load().background_picture == str(picture)
    prepared = QImage(theme.BACKGROUND_FILE)
    assert prepared.pixelColor(0, 0).red() < 255, "dimmed so text stays readable"
    assert window.player.objectName() == "playerPage", "the player keeps its plain background"
    window.settings.set_background("")
    assert theme.BACKGROUND_FILE == "" and "border-image" not in theme.STYLESHEET


def test_the_light_theme_swatch_looks_light_and_dark_themes_show_their_accents(window: MainWindow) -> None:
    def middle(key: str) -> QColor:
        return theme_swatch(THEMES[key]).pixmap(16, 16).toImage().pixelColor(8, 8)

    light = middle("light")
    assert light.lightness() > 200, "Light shows its pale page colours, not its dark blue accents"
    edge = theme_swatch(THEMES["light"]).pixmap(16, 16).toImage().pixelColor(0, 8)
    assert edge.alpha() > 0 and edge.lightness() < light.lightness(), (
        "an outline keeps it visible on a light menu"
    )
    for key, palette in THEMES.items():
        if not palette.light:
            assert middle(key).lightness() < 200, f"{key} shows its accent colours"


def test_the_continue_watching_row_shows_the_page_behind_it(window: MainWindow) -> None:
    """The picture goes on every widget named "page". The row would draw a second, squeezed copy."""
    row = window.home.continue_row
    scroll = window.home._continue_scroll
    for widget in (row, scroll, scroll.viewport()):
        assert widget.objectName() == "seeThrough"
    assert "QWidget#seeThrough { background: transparent; }" in theme.STYLESHEET


def test_the_speed_button_is_the_same_square_as_the_others(window: MainWindow) -> None:
    controls = window.player.controls
    assert controls.speed_button.size() == controls.stop_button.size()
    assert controls.speed_button.width() == controls.speed_button.height()
    metrics = controls.speed_button.fontMetrics()
    if real_display():  # with no display there is no Arial, so the widths mean nothing
        for action in controls.speed_button.menu().actions():
            if action.text():
                assert metrics.horizontalAdvance(action.text()) <= controls.speed_button.width() - 4, (
                    action.text()
                )


def test_a_songs_colours_stay_readable_in_light(window: MainWindow) -> None:
    image = QImage(4, 4, QImage.Format.Format_RGB32)
    image.fill(QColor("#102040"))
    choose(window, "light")
    colour = colour_from(image)
    assert colour.valueF() > 0.9, "pale, for dark text"
    choose(window, DEFAULT_THEME)
    assert colour_from(image).valueF() <= 0.31


def dialog_of(window: MainWindow):  # type: ignore[no-untyped-def]
    window.show_page(window.player)
    window.show_enhancements()
    dialog = window._enhancements
    assert dialog is not None
    return dialog


def test_the_dials_can_be_named_and_used_from_the_keyboard(qtbot: QtBot, window: MainWindow) -> None:
    dialog = dialog_of(window)
    for dial, name in ((dialog.bass, "Bass boost"), (dialog.preamp, "Preamp")):
        assert isinstance(dial, QDial)
        assert dial.accessibleName().startswith(name)
        assert dial.focusPolicy() & Qt.FocusPolicy.TabFocus
    dialog.close()


def test_the_bass_dial_turns_up_the_low_bands(qtbot: QtBot, window: MainWindow) -> None:
    dialog = dialog_of(window)
    dialog.eq_enabled.setChecked(True)
    dialog.bass.setValue(100)
    settings = dialog.equalizer()
    assert settings.bass_pct == 100
    assert settings.bands_db[0] == 12
    assert settings.bands_db[4:] == (0.0,) * 6
    assert dialog.eq_sliders[0].value() == 12, "the sliders show it"
    assert window.player.controller.engine is not None
    dialog.bass.setValue(0)
    assert dialog.equalizer().bands_db == (0.0,) * 10
    dialog.close()


def test_the_preamp_dial_sets_the_preamp(qtbot: QtBot, window: MainWindow) -> None:
    dialog = dialog_of(window)
    dialog.eq_enabled.setChecked(True)
    dialog.preamp.setValue(-6)
    assert dialog.equalizer().preamp_db == -6
    dialog.close()


def test_dials_are_off_with_the_equalizer(qtbot: QtBot, window: MainWindow) -> None:
    dialog = dialog_of(window)
    dialog.eq_enabled.setChecked(False)
    assert not dialog.bass.isEnabled() and not dialog.preamp.isEnabled()
    dialog.eq_enabled.setChecked(True)
    assert dialog.bass.isEnabled() and dialog.preamp.isEnabled()
    dialog.close()


def test_reset_clears_the_bass_dial(qtbot: QtBot, window: MainWindow) -> None:
    dialog = dialog_of(window)
    dialog.eq_enabled.setChecked(True)
    dialog.bass.setValue(60)
    dialog.reset_eq_button.click()
    assert dialog.bass.value() == 0
    assert dialog.equalizer().bands_db == (0.0,) * 10
    dialog.close()


def test_the_status_bar_is_hidden_unless_chosen(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    bar = window.statusBar()
    assert bar.isHidden()
    window.player.status_changed.emit("A message")
    assert bar.isHidden(), "a message doesn't bring it back"
    window.settings.show_status_bar.setChecked(True)
    assert not bar.isHidden()
    assert window.status_bar_action.isChecked()
    assert PreferencesStore(tmp_path / "settings.json").load().show_status_bar
    window.status_bar_action.setChecked(False)
    assert bar.isHidden()
    assert not window.settings.show_status_bar.isChecked()
    assert not PreferencesStore(tmp_path / "settings.json").load().show_status_bar


def test_leaving_full_screen_keeps_the_status_bar_as_chosen(qtbot: QtBot, window: MainWindow) -> None:
    window.show_page(window.player)
    window.toggle_fullscreen()
    window.exit_fullscreen()
    assert window.statusBar().isHidden()
    window.status_bar_action.setChecked(True)
    window.toggle_fullscreen()
    assert window.statusBar().isHidden(), "full screen hides it either way"
    window.exit_fullscreen()
    assert not window.statusBar().isHidden()


def test_tv_joins_the_rail_only_while_streams_are_on(window: MainWindow, qtbot: QtBot) -> None:
    """0.12: IPTV stays out of sight until network streams are switched on."""
    assert "TV" not in side_bar(window) and not window.tv_action.isVisible()
    window.settings.network_streams.setChecked(True)
    qtbot.waitUntil(lambda: "TV" in side_bar(window))
    assert side_bar(window)[:5] == ["Home", "Music", "Videos", "TV", "Now Playing"]
    window.nav_tv.click()
    assert window.current_page() is window.tv
    window.settings.network_streams.setChecked(False)
    assert "TV" not in side_bar(window) and window.current_page() is window.home


def test_library_entries_open_their_tab_or_list(window: MainWindow) -> None:
    """Albums and Artists open their tab of Music; Favourites and Recently played their automatic list."""
    window.nav_albums.click()
    assert window.library.section == "music" and window.nav_albums.isChecked()
    assert window.library.tabs.tabText(window.library.tabs.currentIndex()) == "Albums"
    window.nav_favourites.click()
    assert window.library.section == "playlists" and window.nav_favourites.isChecked()
    assert window.library.playlists.current_automatic == "Favourites"
    window.nav_recent.click()
    assert window.library.playlists.current_automatic == "Recently played" and window.nav_recent.isChecked()


def test_a_short_window_scrolls_the_side_bar(window: MainWindow, qtbot: QtBot) -> None:
    """At the smallest window size the side bar scrolls; its entries keep their height (0.12 redesign)."""
    from PySide6.QtWidgets import QScrollArea

    window.resize(window.minimumSize())
    qtbot.wait(50)
    scroll = window._rail.findChild(QScrollArea)
    assert scroll is not None and scroll.verticalScrollBar().maximum() > 0
    assert {b.height() for b in window.findChildren(QPushButton) if b.objectName() == "navButton"} == {34}


def test_the_side_bar_folds_to_its_icons_and_remembers(window: MainWindow, tmp_path: Path) -> None:
    """0.12: the side bar's names can be hidden (its button, View → Side bar names, Ctrl+Shift+B)."""
    from babarify_frame.ui.main_window import RAIL_FOLDED

    window.rail_toggle.click()
    assert window._rail.width() == RAIL_FOLDED and window.nav_home.text() == ""
    assert window.nav_home.toolTip() and window.nav_home.accessibleName() == "Home"  # still named for readers
    assert PreferencesStore(tmp_path / "settings.json").load().rail_folded
    assert not window.rail_action.isChecked()
    window.rail_action.setChecked(True)
    assert (
        window.nav_home.text() == "Home"
        and not PreferencesStore(tmp_path / "settings.json").load().rail_folded
    )


def test_the_fold_arrow_sits_halfway_down_the_side_bar_edge(window: MainWindow, qtbot: QtBot) -> None:
    """0.12, the owner's choice: an arrow on the side bar's edge, halfway down, instead of a menu button."""
    from babarify_frame.ui.main_window import RAIL_FOLDED, RAIL_WIDTH

    tab = window.rail_toggle
    assert tab.parentWidget() is window._rail and tab.isVisible()

    def centred() -> bool:
        middle = window._rail.height() // 2
        box = tab.geometry()
        return box.right() == window._rail.width() - 1 and abs(box.center().y() - middle) <= 1

    assert centred()
    tab.click()
    qtbot.waitUntil(lambda: window._rail.width() == RAIL_FOLDED and centred())
    assert tab.accessibleName() == "Show the side bar"
    tab.click()
    qtbot.waitUntil(lambda: window._rail.width() == RAIL_WIDTH and centred())
    window.resize(window.width(), window.height() - 120)
    qtbot.waitUntil(centred)


def test_the_theme_entry_lines_up_with_the_others(window: MainWindow) -> None:
    assert window.nav_theme.menu() is None  # a menu attached to the button would shift its icon and text
    assert (
        window.nav_theme.x() == window.nav_settings.x()
        and window.nav_theme.width() == window.nav_settings.width()
    )
