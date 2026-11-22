# Known issues — Babarify Media Player beta

Last updated: 2026-11-07 (0.10.0). Please do not report these again, but do add details to the
linked issue if you have new information.

| Area | Issue | Workaround | Since |
|---|---|---|---|
| Install | The installer is not code-signed: SmartScreen shows "Windows protected your PC" | Check the SHA-256 against `SHA256SUMS.txt`, then *More info → Run anyway* | 0.9.0 |
| Start-up | The first start after installing or updating takes about 15 s ("Starting playback engine…") while Windows scans the new files; later starts are quick | Wait for it once | 0.9.0 |
| Playback | DVD and Blu-ray discs are not supported (legal reasons) | — | 0.9.0 |
| Playback | Previous frame (,) is not available with the libVLC engine | Seek back a little | M7 |
| Playback | The time display does not move during frame stepping | It updates on play | M7 |
| Playback | Rotation restarts playback at the same position; 4K rotation stutters | — | M7 |
| Picture | Gamma is only available with hardware decoding switched off | Settings → Hardware decoding: Off | M7 |
| Sound | Volume above 100 % goes up to +6 dB (twice as loud), less when the equalizer's preamp is already high; a limiter stops it clipping | — | 0.11 |
| Subtitles | One subtitle track is shown at a time | — | M5 |
| Previews | Some AV1 files show no preview picture for some positions; 4K previews are slow | — | M8 |
| Library | A moved or renamed file keeps its history only if it is still in a library folder and no identical copy exists | Keep files inside your library folders | 0.11 |
| Music | There is a short gap between songs (measured 110–130 ms); gapless playback isn't possible with this engine | Fade between songs makes the change smooth | 0.10.0 |
| Music | Fade between songs fades out and in; the songs don't overlap | — | 0.10.0 |
| Sound | The Room effect makes music noticeably quieter (it spreads the sound out) | Raise the volume, or use Wider stereo | 0.11 |
| Library | Adding a folder of 20,000 new files takes several minutes (about 6.5 measured); the app stays usable meanwhile | Add large collections one folder at a time | 0.11 |
| Library | With 10,000 videos, opening the Videos page takes about a second | — | 0.11 |
| Mini player | The mini player shows the title and controls, not the song's picture | — | 0.11 |
| Sound | Volume levelling reads ReplayGain tags from MP3, Ogg and Opus files only; the engine ignores them in FLAC and M4A files, which are turned down 7 dB like untagged songs | — | 0.12 |
| Library | APE, Musepack and DSD files aren't added to the library (they couldn't be tested); open them with File → Open | File → Open | 0.12 |
| IPTV | The TV guide is shown per channel (Now and Next, and a channel's schedule); there is no grid of all channels yet | — | 0.12 |
| IPTV | Channel logos aren't shown yet | — | 0.12 |
| IPTV | Logins to Xtream Codes or Stalker portals aren't supported: use your provider's M3U list | — | 0.12 |
| IPTV | Channels protected with DRM (as in most paid TV apps) can't play in any IPTV player | Use the provider's own app | 0.12 |
| Streams | Only one stream plays at a time; recording and pausing live TV aren't available | — | 0.12 |
| Music | The animation for songs with no picture uses about 5 % of the processor while it's on screen (0.2 % with the window minimised or on another page) | Minimise the window, or switch off animations in Windows (Settings → Accessibility → Visual effects) | 0.10.0 |
| Sleep | The app has no special handling for sleep and wake; playing through sleep and wake is checked by hand before each release | — | 0.11 |
| Library | Edited details and covers are kept by the app, not written into the files, so other apps don't see them | — | 0.10.0 |
| Update | Going back to 0.9.1 after 0.10.0 starts 0.9.1 with an empty library (it can't read the newer one); your data stays for the next update | Keep using 0.10.0 | 0.10.0 |
| Accessibility | Windows contrast themes are not followed: the app keeps its own dark theme (all text at least 5.6:1 contrast, control outlines at least 3:1) | — | 0.9.0 |

Fixed in 0.9.1: control outlines were hard to see (low contrast). 0.10.0 renames the app to Babarify Media Player; see the release notes.
