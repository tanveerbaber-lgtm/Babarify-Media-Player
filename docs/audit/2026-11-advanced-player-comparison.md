# Babarify Media Player 0.11.0 compared with advanced offline players

22 November 2026. Babarify facts are from the code and the M1–M4 measurements in
[the offline-player audit](2026-11-offline-player-audit.md). Other players are described from their documented
features. Cells marked † come from a single third-party source and should be checked before being quoted publicly.

Compared with: **VLC 3.0.24** (the current stable VLC; VLC 4 is still in development and uses the same engine as
Babarify), **MPC-HC** (clsid2), **PotPlayer**, **mpv**, and for music **foobar2000** and **MusicBee**.

Key: ✓ yes · ~ partly · ✗ no · — not that kind of player.

## 1. Summary

Babarify is already ahead of most of these players in four areas:

- **Privacy:** it makes no network connection at all. VLC offers online metadata, PotPlayer shows ads and online
  content, and several others have update checks.
- **A modern, accessible library:** Music, Videos, Playlists, Continue watching, eight themes, and contrast
  checked against WCAG.
- **Remembering your files:** history, favourites and edits follow a file when it's moved or renamed.
- **Ease of use:** one search box, seek-bar previews, synced lyrics, local backup and restore, and quick
  large-library browsing.

It falls behind in two places:

1. **Music basics a music player is expected to get right.**
   - Albums play in alphabetical order, because track and disc numbers are not read.
   - There is no album artist.
   - There is no volume levelling (ReplayGain).
   - Several lossless formats are not added to the library.
2. **Windows integration.**
   - Media keys and Bluetooth headset buttons work only while Babarify is the active window.
   - Babarify doesn't appear in Windows' media controls.
   - Opening a file from Explorer starts a second copy of the app instead of using the one already running.
   - The sound always goes to the default output device; there's no way to choose another.

These are all fixable without new dependencies or network access, and most are small. The remaining gaps are
mostly limits of the engine (libVLC 3): gapless playback, two subtitles at once, and live rotation. These are
for a later engine decision (section 5), not a quick fix.

## 2. Comparison

### Music

| Feature | Babarify | VLC | MPC-HC | PotPlayer | mpv | foobar2000 | MusicBee |
|---|---|---|---|---|---|---|---|
| Albums in **track / disc order** | ✗ alphabetical | ~ | — | ~ | — | ✓ | ✓ |
| Album artist, compilations | ~ ("Various artists" guessed) | ✗ | — | ✗ | — | ✓ | ✓ |
| Library by album / artist / genre | ✓ | ~ | ✗ | ✗ | ✗ | ✓ | ✓ |
| Automatic lists (recent, most played, favourites) | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ | ✓ |
| Rule-based smart playlists | ✗ (fixed lists, by design) | ✗ | ✗ | ✗ | ✗ | ✓ | ✓ |
| **Gapless** | ✗ (110–130 ms gap; engine limit) | ✗ | ~ | ✓† | ✓ | ✓ | ✓ |
| Crossfade with overlap | ✗ (fade out, then in) | ✗ | ✗ | ~ | ✗ | ~ (add-on) | ✓ |
| **Volume levelling (ReplayGain)** | ✗ | ✓ | ~ | ✓ | ✓ | ✓ | ✓ |
| Equalizer | ✓ 10 bands, presets, bass, preamp | ✓ | ~ | ✓ | ~ | ✓ | ✓ |
| Boost above 100 % without distortion | ✓ (limiter) | ~ | ~ | ✓ | ~ | ~ | ~ |
| Choose the output device | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Exclusive / bit-perfect output | ✗ | ~ | ✓ | ✓† | ✓ | ✓ | ✓ |
| Synced lyrics from local files | ✓ | ✗ | ✗ | ✓ | ✗ | ~ (add-on) | ✓ |
| Edit tags | ~ (kept in the app; files never changed, by design) | ✗ | ✗ | ✗ | ✗ | ✓ | ✓ |
| CUE sheets (one file, many tracks) | ✗ | ~ | ✗ | ✓ | ~ | ✓ | ✓ |
| Library formats: AIFF, APE, WavPack, DSD, Musepack, TTA | ✗ (not added to the library; most would play) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Listening recap ("For you") | ✓ | ✗ | ✗ | ✗ | ✗ | ~ | ~ |

### Video

| Feature | Babarify | VLC | MPC-HC | PotPlayer | mpv |
|---|---|---|---|---|---|
| Plays almost any format | ✓ (VLC's engine) | ✓ | ✓ | ✓ | ✓ |
| Video library, Continue watching | ✓ | ~ | ✗ | ~ | ✗ |
| Seek-bar previews | ✓ | ✗ | ✗ (MPC-BE ✓) | ✓ | ~ (script) |
| Resume, bookmarks, chapters, A-B repeat, frame step | ✓ | ✓ | ✓ | ✓ | ✓ |
| Subtitle style, delay, audio delay | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Two subtitles at once** | ✗ (engine limit) | ✗ (VLC 4) | ✗ | ✓† | ✓ |
| Aspect, crop, zoom, rotation | ✓ (rotation restarts playback) | ✓ | ✓ | ✓ | ✓ |
| Deinterlacing choice | ~ (automatic only) | ✓ | ✓ | ✓ | ✓ |
| HDR to SDR | ~ (engine does it; not tested or exposed) | ✓ | ✓ | ✓ | ✓ |
| Surround passthrough to an AV receiver | ✗ | ✓ | ✓ | ✓ | ✓ |
| Upscaling shaders, frame interpolation | ✗ (not planned) | ✗ | ✓ | ✓ | ✓ |
| Auto-play next video in the folder | ✓ | ✓ | ✓ | ✓ | ~ |

### Windows and the app

| Feature | Babarify | VLC | MPC-HC | PotPlayer | mpv | foobar2000 | MusicBee |
|---|---|---|---|---|---|---|---|
| **Windows media controls** (volume flyout, lock screen, Bluetooth buttons) | ✗ | ✗ | ✓ (1.9.17+) | ~ | ✓ (0.41) | ✓ | ✓ |
| Media keys while in the background | ✗ (active window only) | ~ (global hotkeys) | ✓ | ✓ | ✓ | ✓ | ✓ |
| **One copy**: a file opened from Explorer goes to the running app | ✗ (a new copy starts) | ~ (option) | ✓ | ✓ | ~ | ✓ | ✓ |
| Taskbar buttons (play, next) | ✗ | ✗ | ✓ | ✓ | ✗ | ~ | ✓ |
| Mini player, always on top | ✓ | ~ | ✓ | ✓ | ~ | ~ | ✓ |
| Themes, high-contrast checked | ✓ 8 themes, WCAG-checked | ~ | ~ | ✓ skins | ✗ | ✓ | ✓ skins |
| Works with large libraries | ✓ (20,000 files tested) | ~ | — | — | — | ✓ | ✓ |
| Files keep history after a move or rename | ✓ | ✗ | ✗ | ✗ | ✗ | ~ | ~ |
| Local backup and restore | ✓ | ✗ | ~ (settings) | ~ (settings) | ✗ | ~ | ✓ |
| **No network at all** | ✓ | ✗ (metadata, update check) | ~ (update check) | ✗ (ads, online content) | ✓ | ~ (update check) | ~ (online features) |

## 3. Recommendations

Ordered by value for the effort. Everything stays offline and needs no new dependency unless stated.

### Next version: fix the basics (small, high value)

| # | Change | Why | Effort |
|---|---|---|---|
| 1 | **Track and disc numbers, album artist** read from tags. Albums play in order, and compilations group under their album artist | The most visible music bug: every album currently plays in the wrong order | Small: libVLC already reads TrackNumber and AlbumArtist (shown in Media information). Needs a schema 9 migration and one more re-read of songs |
| 2 | **One running copy:** a file opened from Explorer, or a second launch, goes to the app that's already open (play it, or add it to the queue) | Today each double-click opens another window and another engine | Small: a local named pipe (`QLocalServer`), nothing leaves the PC |
| 3 | **Choose the output device** (Settings → Playback), remembered | Headphones and speakers are switched without changing Windows' default | Small: libVLC lists the devices and can switch them |
| 4 | **More file types in the library:** AIFF, APE, WavPack, Musepack, TTA, DSD (DSF/DFF); M2V, ASF, F4V, RM/RMVB, DivX | They play already, but scanning skips them | Small: a list change, checked against the bundled engine's plugins |
| 5 | **Volume levelling (ReplayGain)**: off, by track or by album, using the tags the files already have | Songs from different albums play at very different loudness | Small to medium: a libVLC option, then a test with tagged files |

### Following version: Windows integration (medium)

| # | Change | Why | Effort |
|---|---|---|---|
| 6 | **Windows media controls**: Babarify in the volume flyout and on the lock screen; media keys and Bluetooth headset buttons work in the background | Expected of any media app on Windows 10/11 | Medium: needs a small WinRT binding package (Python `winrt`) or a ctypes layer. Purely local |
| 7 | **Taskbar buttons:** previous, play/pause, next on the taskbar preview | Control without opening the window | Medium: Windows' taskbar API through ctypes (Qt 6 dropped its helper) |
| 8 | **Crossfade with overlap** (already measured as feasible in M2) | The one music feature users notice that the engine allows | Medium: a second preloaded player |
| 9 | **An off switch for the audio animation**, or a lower frame rate on battery | About 5 % CPU while it's on screen | Small |
| 10 | Deinterlacing choice; HDR test files in the test set | Older TV recordings; HDR films | Small (deinterlace); test only (HDR) |

### Not recommended (against the simplification goal or the "never change files" rule)

- Upscaling shaders, frame interpolation, skins and DSP chains: enthusiast features that add complexity.
- Writing tags into files: Babarify promises never to change your files. Edits stay in the app.
- Online lyrics, artwork or metadata: the app is offline only.
- A rule editor for smart playlists: already decided against. The automatic lists cover most needs.
- Exclusive and bit-perfect output: niche, and libVLC 3's support for it is weak.

## 4. Engine limits

These gaps can't be closed with libVLC 3.0.24:

- **Gapless playback:** the gap between songs measured 110–130 ms.
- **Two subtitles at once.**
- **Live rotation:** rotating restarts playback.
- **Exact frame-stepping backwards.**

Options, when these matter enough:

1. **libVLC 4:** gapless, two subtitles and live filters are expected. It isn't stable yet (only betas, on Apple
   devices); stay on 3.0.x until it is.
2. **libmpv:** gapless, two subtitles, shaders, and Windows media controls in the player itself. Babarify removed
   its mpv prototype in M1 (decision D2), so this means rebuilding an engine adapter. It's a large change, and
   only worth it if gapless and two subtitles become top requests.

Recommendation: stay on libVLC 3 for the next two versions (items 1–10 don't depend on the engine), and look at
libVLC 4 again when a stable Windows release ships.

## 5. Sources for other players

- VLC status: [VLC 3.0.23](https://jbkempf.com/blog/2026/vlc-3.0.23/),
  [VLC security update, September 2026](https://www.omgubuntu.co.uk/2026/09/vlc-major-security-update),
  [VLC 4.0 news](https://mailman.videolan.org/pipermail/vlc-commits/2026-June/073422.html)
- MPC-HC media controls:
  [MPC-HC 1.9.17 changelog](https://www.neowin.net/amp/media-player-classic---home-cinema-1917/),
  [clsid2/mpc-hc](https://github.com/clsid2/mpc-hc)
- mpv media controls: [mpv 0.41 `osdep/win32/smtc.cpp`](https://sources.debian.org/src/mpv/0.41.0-2/osdep/win32/smtc.cpp)
- PotPlayer: [AlternativeTo](https://alternativeto.net/software/daum-potplayer/about),
  [TechSpot](https://www.techspot.com/downloads/5543-daum-potplayer.html),
  [WASAPI exclusive note](https://contentbase.com/blog/potplayer/audio-device-switching-fix) (†)
- foobar2000 and MusicBee: their documented features. Not separately checked in this pass.

## 6. Status (22 November 2026, branch m5-music-basics, not committed)

Items 1–5 are built and tested:

1. **Track and disc order, album artist:** schema 9; read by the real engine from MP3, FLAC and M4A tags.
2. **One running copy:** a later start hands its file over a local named pipe and exits only once the open
   window confirms. Tested between two real processes.
3. **Output device:** a device that isn't connected is never asked for; the Windows default plays instead.
4. **More file types:** AIFF, WavPack, TTA, CAF, ASF, DivX, F4V and RealMedia, each played through the
   bundled engine first. Raw M2V was left out: it plays with no running time. APE, Musepack and DSD were left
   out because they couldn't be tested.
5. **Volume levelling:** set on the live audio output for each file, so it applies to songs only (libVLC
   would otherwise turn every untagged video down 7 dB). Measured: a song tagged −12 dB plays at a quarter of
   its level; a video is unchanged. Limit: libVLC 3 reads the tags from MP3, Ogg and Opus, but not FLAC or
   M4A.
