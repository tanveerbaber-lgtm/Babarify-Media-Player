# Babarify Media Player — offline player audit and proposed changes

Status: **for review, nothing implemented yet.** Prepared 21 November 2026 against `main` at `882f5ba`.

## 1. Summary

The Windows app already matches most of the specification: it is a local music and video player with a library,
playlists, queue, equalizer, lyrics, sleep timer, themes and backup, with no account, ads or telemetry. The work is
therefore **mostly removal, refinement and a handful of targeted additions**, not a rewrite.

Main proposals:

1. **Remove the two online/AI features** — network streams (incl. internet radio) and AI subtitles/spoken-word search.
   The AI part alone is **255 MB of the 445 MB install and 223 of its 701 files**; removing it should also shorten the
   slow first launch.
2. **Reorganise navigation** into Home · Music · Videos · Playlists · Now Playing · Settings, splitting today's single
   Library page into a Music page and a Videos page.
3. **Fix the documented playback issues that the engine allows**: clipping protection for boosted volume (libVLC's
   compressor), keeping history when files are moved or renamed (existing content keys), near-gapless and genuine
   overlapping crossfade (two engine players — to be proven by measurement before it ships).
4. **Add the missing local features**: genres, a Videos library (folders, recently watched, favourites, continue
   watching), drag-and-drop playlist reordering, saving/restoring the queue, auto-play next video, mini-player and
   always-on-top.
5. **Themes from your reference image**: eight themes with the given colours (adds Teal Breeze and Classic Dark).

No architecture change: Python 3.13 + Qt 6 (PySide6) + libVLC 3.0.24 stay.

## 2. Inspection

- **Project instructions:** there is no `AGENTS.md` or `CLAUDE.md`. Followed instead: `Babarify_Vision_Official_Architecture_and_Milestones.md`,
  `docs/architecture/overview.md`, ADR-0001 (playback engine), `README.md`, `docs/PRIVACY.md`, `docs/beta/KNOWN_ISSUES.md`.
- **Architecture:** `core/` (models, no UI/engine), `playback/` (contract, controller, libVLC adapter; mpv prototype and a
  mock for tests), `library/` (SQLite with versioned migrations, background scanner, history, M3U, lyrics, recap, backup),
  `configuration/` (settings.json), `ai/` (optional worker process), `ui/`. ~14,500 lines in ui/library/playback.
- **Engine:** libVLC 3.0.24, hardware decoding Automatic, `--no-lua`. Audio filters available in the bundle include
  `compressor`, `normvol`, `gain`, `equalizer`, `spatializer`, `stereo_widen`, `scaletempo`.
- **Data safety already in place:** schema versions with one transaction per migration; edits/lyrics/covers stored by the
  app, never written to media; delete asks and uses the Recycle Bin.

## 3. Feature audit

Key: **Keep** works and stays · **Improve** exists, needs work · **New** missing · **Remove** excluded by the spec.

### Music

| Spec item | Today | Action | Milestone |
|---|---|---|---|
| Play, pause, stop, next/previous, seek, volume | Yes | Keep | — |
| Shuffle, repeat (off/one/all, remembered) | Yes | Keep | — |
| Album artwork, title, artist, album | Yes (tags + pictures, colours from art) | Keep | — |
| **Genre** | Shown in Media information only; not stored or browsable | New: store genre, add Genres view | M3 |
| Songs / Albums / Artists | Yes | Keep (move to Music page) | M3 |
| Recently played, Most played, Recently added, Favourites | Yes (automatic lists, 50 each) | Keep; treat as the "smart playlists" | M3 |
| Smart playlists from local data | The four automatic lists | Improve slightly: add Never played and By year/genre only if cheap; no rule editor | M3 |
| Playlists: create, rename, delete, add, remove, reorder | Yes (Move up/down) | Improve: drag-and-drop reorder | M3 |
| M3U import/export | Yes | Keep | — |
| Queue, Play next, Add to queue | Yes | Improve: **save and restore the queue** between sessions | M2 |
| Equalizer, presets, bass boost, preamp | Yes (10 bands, 18 presets) | Keep | — |
| Lyrics from local files | Yes (.lrc/.txt, typed, auto-find same-name .lrc) | Keep | — |
| Lyrics from **embedded tags** | No | Optional: needs a tag reader (e.g. mutagen, GPL-compatible). Propose skipping unless you want it | — |
| History, sleep timer, playback speed | Yes | Keep | — |
| **Gapless** | No (~0.4 s gap measured) | Improve: pre-load the next song in a second player and start it at the end; ship only if measured gap < 50 ms | M2 |
| **Genuine crossfade** | Fade out, then in (no overlap) | Improve: overlap two players; ship only if it measures and sounds right | M2 |
| **Clipping protection** | None above 100% | Improve: enable libVLC compressor/limiter when volume > 100% | M2 |
| Large-library performance | Background scan exists; not tested at scale | Test with 20,000+ files, fix any freezes | M3/M4 |
| Artwork caching | Thumbnails cached on disk | Keep; verify album art reuse | M3 |
| Metadata editing (user-controlled, app-only) | Yes | Keep | — |
| Global search | Per tab (Songs/Albums/Artists/Media) | Improve: one search box across music and videos | M3 |
| Persistent playback position | Yes (any file played ≥ 10 s) | Keep | — |

### Video

| Spec item | Today | Action | Milestone |
|---|---|---|---|
| Play/pause/stop/seek, full screen, volume, speed | Yes | Keep | — |
| Local subtitle files, embedded subtitle and audio tracks, sync | Yes | Keep | — |
| Subtitle font, size, colour, background, position | Yes (plain-text subtitles) | Keep; document ASS/SSA keep own style | — |
| Brightness, contrast, saturation (+hue, gamma) | Yes | Keep | — |
| Frame capture (Shift+S), A-B repeat | Yes | Keep | — |
| Resume, recently watched, history, Continue watching | Yes | Keep (move to Videos page) | M3 |
| Hardware decoding, 4K | Yes (Automatic); 4K tested | Keep; re-test | M4 |
| **Rotation** | Works but restarts playback; 4K rotation stutters | Investigate: libVLC 3 can't change video filters live. Aim: seamless-looking restart (hold last frame, resume exact position). May remain a documented limit | M2 |
| Remember position per file | Yes | Keep | — |
| **Auto-play next video** | No | New: setting "Play the next video in the folder" | M2 |
| **Video library** (all, folders, recently watched, favourites, continue watching) | Partly (Media tab: all files) | New: Videos page with those five views; favourites already work for any file | M3 |
| Thumbnails | Yes (background) | Keep | — |
| Chapters | Yes (Ctrl+→/←) | Keep | — |

### Library, app and UX

| Spec item | Today | Action | Milestone |
|---|---|---|---|
| Multiple folders, rescan, manual refresh | Yes | Keep | — |
| Duplicate detection | Yes (content key: size + SHA-1 of first/last 64 KB; both kept) | Keep; show duplicates more clearly | M3 |
| **Persistent identity after rename/move** | No (history keyed by path) | New: on rescan, a missing file whose content key reappears at a new path takes its history, favourites, playlist entries, bookmarks, edits and lyrics with it (safe DB migration) | M2 |
| Navigation: Home, Music, Videos, Playlists, Now Playing, Settings | Home, Library (6 tabs), Playing; Settings, Theme, Animation at the bottom | Improve: the six-item layout; Theme and Animation move into Settings (theme also in the View menu) | M3 |
| Light and dark themes, accent colours | 7 themes | Improve: 8 themes from your image (section 6) | M3 |
| High-DPI | Works at 250% | Re-test at 100/150/250% | M4 |
| Keyboard shortcuts | Many (F1) | Keep | — |
| **Mini-player** | No | New: compact window with artwork, title, play/pause/next/previous, seek | M3 |
| **Always on top** | No | New: View menu option (also for mini-player) | M3 |
| Backup and restore (local) | Yes | Keep; include the saved queue | M2 |
| Report a problem | Prepares text locally; a button opens the GitHub issue page in the browser | Keep the local report; see decision D3 | M1 |

## 4. Removal inventory

| Feature | What goes | Consequences and data handling |
|---|---|---|
| **Network streams and internet radio** | `ui/network.py` dialog, Ctrl+N and menu item, `playback/stream_proxy.py`, `core/network.py` URL handling, the "network" capability, dropping URLs onto the window, libVLC `http`, `https` and `live555` (RTSP) access plugins from the bundle | Existing history entries for stream addresses are hidden and skipped on resume (left in the database, never deleted). Local file playback unaffected. Removes the app's only general network code |
| **AI subtitles and spoken-word search** | `ai/` package, `babarify-ai-worker.exe`, Settings → AI features, Generate subtitles (Ctrl+Shift+G), Search spoken words (Ctrl+Shift+F), model download | **−255 MB, −223 files.** Removes faster-whisper, CTranslate2, onnxruntime, numpy, PyAV, tokenizers, huggingface_hub, hf-xet, httpx2/httpcore2/h11/anyio and their helpers. Already-generated subtitle files and downloaded models stay on disk; Settings → Privacy shows "Delete old AI data (N MB)" only if any exist (decision D4). The `transcripts` table stays for database compatibility, unused |
| **mpv engine prototype** (not shipped) | `playback/adapters/mpv.py`, `mpv` optional dependency, its skipped tests | No user impact; simpler code and tests (decision D2) |
| Unused bundled libraries | Re-check after the removals (e.g. Pillow appears in the bundle without being imported by the app) | Smaller install. **Kept:** OpenSSL (`libcrypto`) is still needed for file hashing |
| Settings, shortcuts and help text for the removed features | All references | Old settings keys are ignored when read (existing behaviour) |

Not removed (local and useful): snapshots, chapters, bookmarks, media information, playback info, picture controls,
profiles, sound effects.

Out of scope: the Android app (spec covers the Windows app; Android is untouched).

## 5. Documented issues

| Issue | Plan | Can we promise it? |
|---|---|---|
| Slow first launch (9.2 s measured on a fresh copy; 2.9 s after) | Remove AI (a third fewer files), drop unused libraries, defer engine and library start-up work after the window shows | Measure after M1; target < 5 s cold |
| Clipping with volume boost | Compressor/limiter above 100% | Yes, testable with a loud test file |
| Gaps between songs | Pre-loaded second player | Only if measured < 50 ms |
| Crossfade limitations | Two overlapping players with volume ramps | Only if measured and listened to |
| Rotation restarts playback; 4K stutter | Smoother restart | Partly; may stay a limitation |
| History lost after move/rename | Content-key matching on rescan | Yes |
| Subtitle limitations (one track at a time) | libVLC 3 has no second-subtitle API | Stays a limitation |
| Accessibility (Windows contrast themes not followed), high-DPI | Keep the 3:1 / 4.5:1 contrast audit for all 8 themes; DPI tests | Contrast and DPI yes; following Windows contrast themes is a separate decision |
| Stability after sleep/wake | Add a manual test (sleep mid-playback, resume) | Test-only |

## 6. Themes from the reference image

| Image theme | Accent | Today | Proposal |
|---|---|---|---|
| Ocean Blue | #0B6EC7 | Ocean (#3B82F6) | Retune to #0B6EC7 |
| Forest Green | #00B894 | Forest (#10B981) | Retune |
| Royal Purple | #8A2BE2 | Violet (#A78BFA) | Rename and retune |
| Amber Gold | #F4A261 | Amber (#F59E0B) | Rename and retune |
| Teal Breeze | #00D9FF | — | **New** |
| Rose Pink | #E91E63 | Rose (#FB7185) | Rename and retune |
| Classic Dark | #2E3A46 | — | **New** (neutral grey) |
| Light Theme | #F4F7FC | Light (#F5F7FB) | Retune |
| — | — | Sunset (#F97316) | Not in the image (decision D1) |

Every theme keeps the contrast audit (text ≥ 4.5:1, outlines ≥ 3:1). If an exact hex fails as a button colour (e.g. dark
text on #0B6EC7), I'd keep the hex for highlights and use a lighter or darker shade for that one use, and say so.

## 7. Milestones

Each milestone ends with tests passing, a test build installed for your check, and a commit only on your OK.

1. **M1 — Cleanup (offline only).** Remove streams, AI, mpv prototype, unused libraries; update settings, menus, help,
   privacy text, installer and licences. Verify: full test suite, an **offline run with networking disabled**, install
   size and cold-start before/after.
2. **M2 — Playback.** Clipping protection; history kept on move/rename (migration with backup of the database first);
   queue save/restore; auto-play next video; gapless and crossfade prototypes with measurements (ship or report);
   smoother rotation; start-up deferral.
3. **M3 — Library and interface.** Music / Videos / Playlists pages; genres; global search; drag-and-drop playlists;
   eight themes; mini-player; always-on-top; large-library test with 20,000+ files.
4. **M4 — QA and release.** Offline, format, large-library, high-DPI, performance, sleep/wake and installer tests;
   upgrade from 0.10.0 with real data; release notes; new installer.

## 8. Decisions needed

- **D1 Sunset theme:** retire it (users on Sunset move to Amber Gold) or keep it as a ninth theme?
- **D2 mpv prototype:** remove (recommended) or keep for future engine work?
- **D3 Report a problem:** keep the button that opens the GitHub issue page in the browser (user-initiated, sends nothing), or show the address as text only?
- **D4 Old AI data:** offer a one-click "Delete old AI data" in Settings (recommended), or leave it untouched?
- **D5 Embedded lyrics:** skip (recommended), or add a small tag-reading library for them?

## 9. Baseline measurements (for later comparison)

Intel Core i7-8565U, 32 GB RAM, Windows 11 Home 26300; installed build 0.10.0.6.

| Measure | Value |
|---|---|
| Installed size | 445 MB, 701 files (AI 255 MB / 223 files; engine 73 MB / 267; app 99 MB / 148) |
| Installer | 117.6 MB (0.10.0) |
| Cold first start (fresh copy) | 9.2 s to window |
| Warm start | 2.9 s to window |
| Memory: idle / music / 1080p video | ~190 / ~210 / ~450–480 MB |
| CPU: idle / music / 1080p video | < 0.5% / < 0.5% / < 2% |
| Format test | 41 files, 57 libVLC engine tests passed |
| Full test suite | 718 passed, 72 skipped |

## 10. Milestone 1 results (21 November 2026, test build 0.10.0.7, not committed)

Decisions applied: D1 Sunset retires in M3; D2 mpv removed; D3 Report a problem kept; D4 "Delete old AI data"
offered in Settings → Privacy; D5 embedded lyrics skipped.

| Measure | Before (0.10.0.6) | After (0.10.0.7) |
|---|---|---|
| Installer | 117.6 MB | **46.3 MB** |
| Installed program | 445 MB, 701 files | **158 MB, 383 files** |
| Runtime Python packages | 27 | **3** (PySide6-Essentials, shiboken6, python-vlc) |
| libVLC plugins | 259 | **251**: no http, https, RTSP, stream-output or muxer plugins |
| Cold start (fresh copy, to window) | 9.2 s | **4.0 s** |
| Warm start | 2.9 s | **1.9–2.5 s** |
| Memory after start | ~186 MB | ~186 MB |
| Network connections (playing MP3, 1080p video, or given a web address) | 0 | **0** |

Tests: full suite 622 passed (0 skipped; previously 718 passed and 72 skipped, the difference being removed AI,
stream and mpv tests); all 139 real-engine tests pass against the trimmed release engine; contrast audit passes.

Still to verify by hand: a run with Wi-Fi switched off (changing the PC's network settings is left to the owner).

## 11. Milestone 2 results (21 November 2026, not committed)

| Item | Result | Evidence |
|---|---|---|
| Clipping with volume boost | **Fixed.** Boost is extra equalizer preamp before a limiter; libVLC's own gain (after every filter) is never used above 100 %. A -1 dBFS signal at 200 %: 60 % of samples clipped before, under 0.1 % after | `tools/clipping_check.py`; `tests/integration/test_audio_chain_engine.py` |
| Sound effects (Room, Wider stereo) | **Fixed: they never loaded in 0.10** (a per-media `:audio-filter` option is ignored by libVLC 3). Set through libvlccore's `var_SetChecked` on the player and the live audio output (`playback/adapters/libvlc_audio.py`) | verbose engine log; integration test |
| Equalizer 12 dB quieter | **Fixed.** libVLC's equalizer is unity at preamp +12 dB; the preamp is now relative (0 = no change) and older saved values are converted so the sound doesn't change | measured; unit tests |
| History after move or rename | **Done.** Unambiguous content-key matches carry history, favourite, hidden mark, edits, bookmarks, playlist entries and lyrics | `tests/unit/test_library_db.py` (rename, move between folders, copies and ambiguous moves left alone) |
| Queue save and restore | **Done.** Restored paused; only with history on; cleared by Clear history; never in backups | `tests/ui/test_queue_restore_ui.py` |
| Auto-play next video | **Done.** Off by default; natural name order; not during a queue | unit and UI tests |
| Gapless | **Not possible with libVLC 3.** Gap measured 110–130 ms (median 118 ms); a preloaded second player only reaches 109 ms | `tools/gapless_check.py`, 5 runs each |
| Genuine crossfade | **Feasible, not built yet.** Two players overlap (about 0.2 s when started 1.5 s early, 0.8 s at 2 s); a second player needs about 1.2 s to start, so it must be preloaded. Needs two engines in the player: proposed as its own step | `tools/gapless_check.py` |
| Rotation restart | Unchanged: libVLC 3 applies rotation only when playback starts | — |
| Start-up | Unchanged in M2 (M1 already: cold 9.2 s → 4.0 s) | — |

## 12. Milestone 3 results (22 November 2026, test build 0.10.0.10, not committed)

| Item | Result | Evidence |
|---|---|---|
| Eight themes | **Done**, in the image's order. Ocean, Royal Purple and Rose accents lightened 13 %, 21 % and 6 % to reach 4.5:1 for icons; Classic Dark has its own swatch so it doesn't look light. Sunset → Amber Gold for anyone who used it | `tests/unit/test_themes.py`; `tools/a11y_audit.py` |
| Genres | **Done.** Stored (schema 8), read again for existing songs, Genres tab grouped case-insensitively with Unknown genre last | `tests/unit/test_music_library.py`; a real tagged MP3 through libVLC |
| Navigation | **Done.** Home · Music · Videos · Playlists · Playing · Settings; Videos has All, Continue watching, Recently watched and Favourites | `tests/ui/test_themes_ui.py` |
| Global search | **Done** on Home: every word must match a title, artist, album, genre or file name; hidden and missing files are left out; about 40 ms at 20,000 files | `tests/ui/test_m3_ui.py` |
| Drag-and-drop playlists | **Done** for the person's own playlists; a stale or foreign order can't move or lose an item | unit and UI tests |
| Mini player, always on top | **Done.** Always on top uses `SetWindowPos`, so the window (and libVLC's video surface) is never rebuilt; checked on the real desktop | `tests/ui/test_m3_ui.py` |
| 20,000 files | Scan 394 s with the worst UI pause 115 ms. Before the fixes: Songs tab 4.1 s, Albums and Genres 2.4 s, Videos 2.9–4.8 s. After (blocked tab signals during section switches, the media grid loaded only when shown, the song list kept until the library visibly changes): Music page 0.2 s, tabs 27–164 ms, Videos 0.8 s, Playlists 23 ms, search 40 ms | `tools/large_library_check.py` |
| Closing during a scan | **Fixed:** a stopped scan's last report reached the page after the library was closed (an error in the log) | timing runs |
| Not done | Scan speed for many new files (6.5 min for 20,000) not investigated; the mini player has no artwork; crossfade still awaits a decision | — |
