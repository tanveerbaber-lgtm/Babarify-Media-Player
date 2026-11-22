# Babarify Media Player — Privacy notice

Babarify Media Player is a media player for your own files. It has **no account, no advertising, no
telemetry and no crash upload**. Nothing about you, your files or what you watch is sent to
the developer or anyone else.

## What stays on this PC

| What | Where | Why | How to remove |
|---|---|---|---|
| Settings | `%APPDATA%\Babarify\Frame\settings.json` | Your choices (volume, subtitles, picture…) | *Settings → Reset to defaults*, or delete the file |
| Library, songs' tags and pictures, history and play counts, bookmarks, playlists, favourites | `%APPDATA%\Babarify\Frame\library.db` and `thumbnails\` | Library page, *Continue watching*, resume, bookmarks, automatic playlists | *Settings → Privacy → Clear history*; remove folders and entries in the Library; history can be switched off |
| Machine-generated subtitles left by 0.9–0.10 (AI feature, removed in 0.11) | `%APPDATA%\Babarify\Frame\subtitles\` and the library database | Only if you used them then | *Settings → Privacy → Delete old AI data* |
| Speech models left by 0.9–0.10 | `%LOCALAPPDATA%\Babarify\Frame\models\` | Only if you downloaded one then | *Settings → Privacy → Delete old AI data* |
| Logs and crash records | `%LOCALAPPDATA%\Babarify\Frame\logs\` | To help you (or someone you choose to share them with) understand a problem | Delete the folder at any time; old entries are trimmed automatically |
| Snapshots | `Pictures\Babarify Media Player` | Pictures you take with Shift+S | Delete them like any picture |

Logs can contain the names and folders of files you played. They are never uploaded; you decide whether to share them.

When you uninstall, you can choose to delete all of the above (except snapshots, which are your
pictures). Your media files are never changed by Babarify Media Player. One is deleted only when you choose
*Delete from disk* for it and confirm, and then it goes to the Recycle Bin. Edited song details, covers,
lyrics and a background picture are kept by the app, not written into your files.

## Network use

None. Since 0.11 Babarify Media Player is a local player: it plays files on this PC and makes no network
connections of its own. There are no network streams, no downloads and no automatic update check. To update,
download a newer installer yourself. (*Help → Report a problem* can open the project's issue page in your
browser when you click it; the report itself is text you copy, and nothing is sent by the app.)

Since 0.12, when you open a file while Babarify is already open, the new start passes the file to the open
window through a local named pipe and closes. The pipe is private to your Windows account, exists only on
this PC and carries nothing but the file's path.

Versions 0.9 and 0.10 could play network streams and download a speech model for optional AI subtitles. If
you used them, *Settings → Privacy → Delete old AI data* removes what they left.

## Contact

Questions about privacy: open an issue in the project's repository.

## Android

The Android app has no internet permission, so it cannot send anything anywhere. It reads the files you
open and the folders you add to the library, and it never changes them. A song is deleted only when you
choose *Delete from device* and confirm in Android's own prompt. If you tap *Find my music* and allow
it, the app also reads the list of songs on the phone, with their names, artists, albums and pictures, and
plays them. Android's permission for this is `READ_MEDIA_AUDIO` (`READ_EXTERNAL_STORAGE` on Android 12 and
earlier, where it can also see other files). The app works without it, and you can take it back in Android's
settings. The library, playlists, favourites, bookmarks, settings, recent files, how often you played each
song and your place in them stay on the phone, are excluded from backup and device transfer, and can be
cleared or removed in the app. *Settings → Privacy* switches off play history and clears it. A
subtitle file you add is copied into the app's private cache so the player can read it. Uninstalling
removes all of this, except snapshots you chose to take, which are saved in `Pictures/Babarify Media Player`
for you to keep.

Its other permissions are for sound that keeps playing after you leave: `FOREGROUND_SERVICE`,
`FOREGROUND_SERVICE_MEDIA_PLAYBACK` and `WAKE_LOCK`. Audio files always keep playing, even after closing
the app, until you close them from the notification. Video does so only if you choose that in *Settings →
When you leave a video*; otherwise leaving stops it. While sound plays on, the notification shows the file's
name, and the name also shows on the lock screen.

`WRITE_SETTINGS` is only for *Set as ringtone*. Android doesn't grant it until you turn on "Allow modifying
system settings" for the app in its settings, and the app uses it for nothing else.
