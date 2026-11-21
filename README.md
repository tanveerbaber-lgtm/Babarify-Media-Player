# Babarify Media Player

**Play • Enjoy • Anytime.** A free, privacy-focused media player by Babarify.

> Status: **Milestone 4 — Playback Reliability and Performance** (awaiting acceptance). The app
> plays local video and audio in a branded interface, reports honestly whether the GPU or the
> CPU is decoding, offers a Playback info panel (Ctrl+I), and is tested against a 42-file corpus,
> long sessions, seek storms and shutdown in every state. See
> [the plan](Babarify_Vision_Official_Architecture_and_Milestones.md) and the milestone
> reports for [M1](docs/milestones/M1/), [M2](docs/milestones/M2/) and [M3](docs/milestones/M3/).

- A local player: it opens files on this PC and needs no internet connection. No ads, no account, no
  telemetry.
- First platform: Windows 10/11 64-bit. An Android version (10 or later) is built in `android/player` but not yet released. iOS comes after a dedicated feasibility milestone.
- Playback engine: **libVLC** ([ADR-0001](docs/decisions/ADR-0001-playback-engine.md)). The mpv prototype
  was removed in 0.11.

## Development setup (Windows)

Requirements: Windows 10/11 x64, Python 3.13 (x64), Git. FFmpeg on `PATH` is only
needed to regenerate benchmark media.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

### Engine libraries (development only)

libVLC is a native library and is not installed by pip. Put a 64-bit build in the git-ignored
`.engines/` folder (or point `BABARIFY_VLC_DIR` at it):

| Engine | Source used in M1 | Expected layout |
|---|---|---|
| libVLC 3.0.24 x64 | `vlc-3.0.24-win64.zip` from download.videolan.org (SHA-256 verified) | `.engines/vlc/vlc-3.0.24/libvlc.dll` + `plugins/` |

A 32-bit VLC installation cannot be used from 64-bit Python.

## Run

```powershell
.\.venv\Scripts\python.exe -m babarify_frame [FILE]
```

Open files with **Ctrl+O**, by dragging them onto the window, or as a command-line argument.
Drop a folder (or use *File → Add folder to library…*) to add it to the **Library**: only the
folders you choose are scanned, in the background, and files are never modified. A file is deleted only
when you choose to and confirm.
Files continue where you stopped; *Home* lists *Continue watching* and *Recently played*.
History stays on this PC and can be turned off or cleared in *Settings → Privacy*.
Point at the seek bar for a preview picture. Network streams, internet radio and the optional
AI subtitles of earlier versions were removed in 0.11: the player is local only.

| Key | Action |
|---|---|
| Space | Play / pause |
| ← / → | Seek back / forward (step set in Settings, default 10 s) |
| ↑ / ↓ | Volume up / down |
| M | Mute |
| S | Stop |
| F, F11, double-click video | Fullscreen (Esc to leave) |
| Ctrl+1 / 2 / 3 | Home / Now Playing / Settings |
| Ctrl+O / Ctrl+Q | Open / exit |
| Ctrl+→ / Ctrl+← | Next / previous chapter (also *Playback → Chapters*) |
| Ctrl+B / Ctrl+Shift+B | Add a bookmark / list bookmarks |
| Ctrl+Shift+I | Media information (tracks, tags, chapters) |
| Ctrl+I | Playback info (decoder, frames, engine log) |
| Ctrl+L | Library |
| N / P | Next / previous in playlist |
| Home | Start over (after an automatic resume) |
| Ctrl+E | Picture & Sound: brightness, contrast, colour, aspect, crop, zoom, rotation, equalizer, profiles |
| Shift+S | Snapshot to Pictures\Babarify Media Player |
| . / , | Next / previous frame |
| L | A-B repeat (set A, set B, off) |
| V / B | Next subtitle track / next audio track |
| G / H | Subtitles 50 ms earlier / later |
| J / K | Audio 50 ms earlier / later |
| Ctrl+D | Sync and delay dialog |
| Ctrl+Shift+O | Load a subtitle file (or drop one onto a playing video) |
| F1 | Keyboard shortcuts |

Playback keys act on the Now Playing page. The subtitles button in the control bar lists audio
and subtitle tracks. Preferences (volume, window size, seek step, hardware decoding
Automatic/Off, fullscreen behaviour, subtitle look and preferred languages) are stored only on this PC in `%APPDATA%\Babarify\Frame\settings.json`
(override the folder with `BABARIFY_CONFIG_DIR`).

`--smoke-test [MS]` opens the window (and FILE), then exits after MS milliseconds (used by tests).

## Checks

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy
```

Integration tests skip automatically when an engine library or the generated media is
missing (generate it with `tools\engine-benchmark\make_media.py`). Resource stress tests run separately:

```powershell
.\.venv\Scripts\python.exe -m pytest -m stress -s
```

The test corpus and the regression catalog are documented in
[docs/testing/](docs/testing/).

## Engine benchmark

```powershell
.\.venv\Scripts\python.exe tools\engine-benchmark\make_media.py
.\.venv\Scripts\python.exe tools\engine-benchmark\bench.py --trials 5
```

See [tools/engine-benchmark/README.md](tools/engine-benchmark/README.md).

## Layout

```text
src/babarify_frame/
  core/        typed models, errors, events (no engine or UI imports)
  playback/    contract, lifecycle rules, factory, controller
    adapters/  mock, libvlc — the only place the engine binding is imported
  configuration/ typed preferences + local JSON store
  ui/          PySide6 shell (main_window), pages (home, player, settings), controls, theme tokens
tests/         unit, integration, ui, stress
tools/         engine-benchmark, player_screenshot, ui_responsiveness, real_input_check
branding/      icon source and generator
docs/          architecture, decisions (ADRs), milestone reports
```

## License

Babarify Media Player is free software, licensed under the **GNU General Public License v3 or later**
([LICENSE](LICENSE)). Releases bundle libVLC, Qt/PySide6 and other components under their own
licences; see `THIRD_PARTY_NOTICES.txt` in the program folder and [RELEASING.md](docs/RELEASING.md).
Privacy: [docs/PRIVACY.md](docs/PRIVACY.md).
