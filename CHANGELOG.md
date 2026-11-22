# Changelog

Released versions are published on the
[releases page](https://github.com/tanveerbaber-lgtm/Babarify-Media-Player/releases). Details for Windows
releases are in [`docs/release-notes/`](docs/release-notes/).

## Windows 0.10.0 (2026-11-08, public beta)

Release notes: [0.10.0](docs/release-notes/0.10.0.md).

- Changed: the app is now called Babarify Media Player, and installs in a folder of that name. Upgrading moves it
  there and keeps your settings and library. A taskbar pin to the old copy has to be pinned again. New snapshots go to `Pictures\Babarify Media Player`; existing ones stay where they are.
- New: audio has its own screen, with the song's picture, title and artist, and colours taken from the picture.
  Songs with no picture get an animation: mirrored bars with a reflection, capsules, waves, a circle or lights.
  They change by themselves while a song plays, or you can choose one. They don't follow the sound.
- New: repeat off, this file or all, remembered between sessions.
- New: shuffle, and a queue you can jump around in, for playlists.
- New: a sleep timer that pauses playback.
- New: the Library has Songs, Albums and Artists tabs, from your folders' tags and pictures, with search, sorting,
  Play and Shuffle. Existing songs are read once more, in the background, the first time this version runs.
- New: seven colour themes in Settings, including Light, and Bass boost and Preamp dials on the equalizer. The
  bass dial turns up the four lowest equalizer bands.
- Changed: Settings, Theme and Animation now sit together at the bottom of the left bar, in place of About, which
  stays in the Help menu. Theme and Animation switch quickly from there.
- Changed: all text is Arial, bold for titles and headings. The home page shows the name once, in brand colours.
- New: favourites, with a heart on the player, and automatic Favourites, Recently played, Most played and
  Recently added lists.
- Changed: in full screen, audio keeps its controls until you hide them.
- Changed: the player's control buttons are larger, with bolder icons that are easier to see.
- Changed: clearer tabs, buttons and side bar icons; buttons lift with a soft shadow when you point at them.
- Changed: the status bar along the bottom is hidden unless you switch it on in Settings or the View menu.
- New: Play next and Add to queue from a song's menu.
- New: hide files from the library, and bring them back in Settings. The files aren't touched.
- New: delete from disk, which asks first and moves the file to the Recycle Bin.
- New: lyrics from an .lrc or text file, or typed in, that follow along when they have times.
- New: a For you tab: a recap of what you've played, top songs, artists and albums, and songs never played.
- New: edit a song's title, artist, album and cover. Saved in the app; the file isn't changed.
- New: your own picture as the background of the main pages.
- New: fade between songs in a playlist or queue, and a sound effect: room, wider stereo or both (Settings → Playback).
- New: back up settings, playlists, favourites and hidden files to a file, and restore them.
- New: import and export playlists as M3U.
- New: sort songs by folder, oldest first, most played or year. Songs are read once more for their year.
- New: volume from 1 to 100, with optional boost to 200.

## Android 0.2.0-beta (ready to publish, 7 November 2026)

Brings the Android app close to the Windows app. Release notes: [Android 0.2.0-beta](docs/release-notes/android-0.2.0-beta.md).

- Changed: the app is now called Babarify Media Player.
- New: library of folders you choose, with search, sorting and pictures; playlists; bookmarks.
- New: speed, volume number from 1 to 100 and optional boost to 200, chapters, A-B repeat, sync and delay.
- New: picture controls, equalizer with presets, profiles, aspect, zoom, rotate, flip, snapshots.
- New: subtitle look, preferred languages, media and playback information, pictures while seeking.
- New: a redesigned interface: full-screen video with overlay controls, icons, bottom tabs and grouped settings.
- New: repeat off, one or all; shuffle; add media to a playlist from the library, your files or the player.
- New: a Music tab listing every song on the phone by song, album, artist and folder, with search and sorting.
  It asks for a new, optional permission to read songs; you can still open files and add folders without it.
- New: songs have one row of controls: back 10 s, shuffle, previous, play, next, repeat and forward 10 s.
  Speed and volume are in the ⋮ menu.
- New: a now-playing screen with the song's picture filling the top, colours taken from it, or an animation
  if it has none: mirrored bars with a reflection, capsules, waves, a circle or lights. They change by
  themselves while a song plays, or you can choose one. Its controls stay until you hide them. The animations
  don't follow the sound.
- New: favourites, and automatic Recently played, Most played and Recently added lists.
- New: a queue you can jump around in, and shuffle that can be switched off again.
- New: an equalizer screen with preset chips, upright sliders, and bass boost and preamp dials.
- New: an opening animation in 3D with the icon and name when the app starts. Tap to skip it. Android 12 and later
  no longer show the icon twice at start-up.
- New: Play next and Add to queue, selecting several songs, and hiding songs (Settings brings them back).
- New: delete songs from the phone, always after a confirmation.
- New: lyrics from an .lrc or text file, or typed in, that follow along when they have times.
- New: a For you screen: a recap of what you've played, top songs, artists and albums, and songs never played.
- New: a home screen widget with play controls.
- New: edit a song's title, artist, album and cover. Saved in the app; the file isn't changed.
- New: set a song as the ringtone. This needs one new permission, which Android asks for.
- New: your own picture as the background of the main screens.
- New: fade between songs in a playlist or queue, and a sound effect: room, wider stereo or both (Settings → Playback).
- Changed: text uses Arimo, which matches Arial, and the name on Home has the brand colours.
- Changed: a new app icon, a blue "B" with a play button, green sound bars and a green swoosh on a glossy blue
  tile, on the home screen, in the opening animation and on the widget. The tagline is now "Play • Enjoy • Anytime".
- New: back up settings, playlists and favourites to a file, and restore them.
- New: import and export playlists as M3U. Songs are matched by file name.
- New: sort songs by folder, oldest first, most played or year.
- New: seven colour themes, a sleep timer and touch lock. In Light, the player stays dark so its controls can be
  read over video.
- New: a mini player on the main screens: a card coloured from the song's picture, with its progress, title and
  artist. Swipe it sideways to change song.
- New: the notification shows the song's title, artist and picture, with a favourite button.
- New: audio files keep playing with the app closed, in a mini player in the notifications, until you close
  it there. Video stops when you leave unless you choose otherwise. This needs three new permissions; still no
  internet permission.
- New: swipe gestures and a small floating window.
- Not included: network streams and local AI subtitles, by the owner's decision.

## Android 0.1.0-beta (not released)

First Android version, for Android 10 or later. Built and tested, never published
([M13 report](docs/milestones/M13/acceptance-report.md)).

- Opens files through the system picker or "open with"; no permissions, no internet.
- Play, pause, seek, audio and subtitle tracks, external subtitle files.
- Recent files and resume, kept on the phone.
- Known: the first video after installing can take about 30 seconds to start.

## iOS (not started)

A feasibility prototype only, with no version planned yet
([M14 report](docs/milestones/M14/acceptance-report.md)).

## Windows (next version, not released)

- Fixed: albums play in their own order, by disc and track number, instead of alphabetically. Songs are read
  once more, in the background, for their track and disc numbers and album artist.
- New: an album shows its album artist, so a compilation is listed under the name on its cover.
- New: Settings → Playback → Sound output: play through headphones or speakers without changing Windows'
  default. If the chosen device is unplugged, sound goes to the Windows default until it's back.
- New: Settings → Playback → Volume levelling (off by default): songs play at a steadier loudness, by song or
  by album, using the ReplayGain tags in MP3, Ogg and Opus files. Videos are never changed.
- Changed: opening a file while Babarify is open plays it in the open window, instead of starting a second
  copy of the app.
- New: the library and the Open dialog include AIFF, WavPack, TTA and CAF audio, and ASF, DivX, F4V and
  RealMedia video. The Open dialog also lists MKA files, which it was missing.
- New: network streams and IPTV, off until you switch them on (Settings → Network). *File → Open network
  stream* (Ctrl+N) plays web streams, HLS, internet radio, RTSP and your internet provider's multicast TV. A
  live stream that drops reconnects by itself for about a minute. Web streams go through Babarify's own
  safeguard, so a server can never make the player open a file on this PC.
- New: a TV page for IPTV channel lists (M3U) you add from your provider, by web address or as a file:
  groups, search, favourites, hidden groups, Now and Next from the TV guide (XMLTV), and each channel's
  schedule. Page Up and Page Down change channel on the player, and Backspace goes back to the last one.
  Lists and guides are read again daily. Babarify doesn't include or suggest channels.
- New: Babarify tells you when a new version is out (Settings → Privacy, on by default). It asks GitHub
  once a day and sends nothing about you; *Download* opens the release page, and you can skip a version.
  *Help → Check for updates* asks at any time.

## Windows 0.11.0 (2026-11-22, public beta)

Release notes: [0.11.0](docs/release-notes/0.11.0.md).

- Changed: Babarify Media Player is now a local player. It plays files on this PC and makes no network
  connections of its own. Network streams and internet radio (File → Open network stream, dropped links)
  are removed, and the bundled engine no longer includes its network plugins.
- Removed: the optional AI subtitles and spoken-word search. The program is about 255 MB smaller, with a
  third fewer files. If you used them, Settings → Privacy → Delete old AI data removes the speech models
  and generated subtitles they left; nothing is deleted unless you choose it.
- Changed: stream addresses in your history from earlier versions are no longer listed (they aren't deleted).
- Removed: the unused mpv engine prototype (developers only).
- Fixed: volume above 100 % no longer distorts. The boost now happens before a limiter, and 200 % means twice as
  loud (+6 dB). Before, 126 % already clipped 41 % of a loud song's samples (measured).
- Fixed: the Room and Wider stereo sound effects never actually played; now they do.
- Fixed: switching the equalizer on made everything about 12 dB quieter. The preamp is now shown relative to
  normal level (0 dB = no change). Preamp values you set are converted and sound as before; the untouched
  default now means normal level.
- New: a moved or renamed file keeps its history, resume point, favourite, edited details, bookmarks, lyrics and
  playlist entries, when the library finds it in its new place.
- New: the queue is kept when you close the app and comes back, paused where it was, next time (only while
  play history is switched on; Clear history forgets it, and backups don't include it).
- New: Settings → Fullscreen → "When a video ends, play the next video in its folder" (off by default).
- Changed: the left bar is now Home, Music, Videos, Playlists, Playing and Settings. Music has Songs, Albums,
  Artists and Genres; Videos shows all videos, Continue watching, Recently watched or Favourites. Theme and
  animation are chosen in Settings or the View menu instead of the left bar.
- New: eight colour themes: Ocean Blue, Forest Green, Royal Purple, Amber Gold, Teal Breeze, Rose Pink,
  Classic Dark and Light. Sunset is retired; if you used it, you get Amber Gold.
- New: genres, read from your songs' tags (songs are read once more, in the background, the first time).
- New: one search box on Home finds songs and videos by title, artist, album, genre or file name.
- New: drag songs to put a playlist in order (your own playlists; the automatic lists keep their own order).
- New: a mini player (View → Mini player, Ctrl+Shift+M), and View → Always on top, which is remembered.
- Changed: much quicker with large libraries. With 20,000 files, the Music tabs open in under 0.2 s (they took
  up to 4 s), and the window stays responsive while folders are scanned.
- Fixed: closing the app during a folder scan could write an error to the log.
- Fixed: at high display scaling (200 % on a 1920 × 1080 screen), the Playlists page's buttons were cut off and
  its "Your playlists" heading overlapped the lists.
- Fixed: a rare crash while a video's seek-bar previews were being prepared (seen once in about 60 test runs).
- New: before an update changes your library's format, a complete copy of it is kept next to it, named for
  example `library.before-v7.db`, so an update can always be undone.
- Changed: a new app icon, a blue "B" with a play button, green sound bars and a green swoosh on a glossy blue
  tile, for the program, the installer, the taskbar and the left bar. The tagline is now "Play • Enjoy • Anytime".
- Fixed: with a background picture, the Continue watching row on Home showed a second, squeezed copy of it.
- Fixed: in the Theme menu and Settings, the Light theme's colour square now looks light instead of blue.

## Windows 0.9.1 (2026-11-02, public beta)

- New: *Help → Report a problem* prepares technical details for you to copy; nothing is sent.
- Fixed: outlines of controls were too faint (WCAG non-text contrast).

Full notes: [0.9.1](docs/release-notes/0.9.1.md).

## Windows 0.9.0 (2026-11-01, not published)

First packaged build: installer, playback, audio and subtitles, library, enhancement, network streams,
chapters and bookmarks, and optional local AI. Full notes: [0.9.0](docs/release-notes/0.9.0.md).
