# Plan: IPTV and update notifications (milestone M6, 0.12)

22 November 2026. Your decisions:

- **IPTV scope:** live TV and a TV guide.
- **Network features:** off until switched on.
- **Updates:** users are told when a new version is published, and the notice opens the download page.

## 1. Principles

- **Off by default.** Babarify stays fully offline until the user switches on *Settings → Network → Network
  streams and IPTV*. Switched off, it makes no stream, playlist, guide or logo connections.
- **The update check is separate.** It's on by default and can be switched off in *Settings → Privacy*. It
  asks GitHub at most once a day for the list of releases. It sends no user data: the request carries only a
  generic "Babarify Media Player/<version>" client name, and GitHub sees the PC's internet address, as for
  any web request.
- **Everything from the internet is untrusted:** stream addresses, M3U playlists, XMLTV guides, channel logos
  and release notes. Each has size, time and content limits, and is shown as plain text.
- **No bundled or suggested sources.** Babarify never includes or recommends channel lists. Xtream Codes and
  Stalker logins are not supported.
- **The stream proxy comes back (from M8).** libVLC 3 follows web redirects to *any* address, including
  `file:` and `\\server\share`. So web streams go through Babarify's loopback proxy:
  - it listens on 127.0.0.1 only and needs a random token;
  - it follows redirects only to http/https;
  - it rewrites HLS playlists.

## 2. Stages

### A. Network streams (restored from 0.10, then extended)

- *File → Open network stream* (Ctrl+N), with an address box and recent streams. Dropped links open too.
- Supported addresses:
  - http and https, through the proxy: files, HLS `.m3u8`, MPEG-TS over HTTP and internet radio;
  - rtsp;
  - multicast `udp://@` and `rtp://@`, for internet providers' own TV. These are new, and only multicast or
    private addresses are allowed.
- **Reconnect:** a live stream that drops is retried, with increasing waits, for up to a minute.
- **Engine:** the release engine gets its http, https and live555 (RTSP) plugins back, plus udp/rtp.

### B. IPTV live TV

- **Playlists:** add one or more by link or file, with automatic refresh (daily, or on demand). The extended
  M3U attributes are read: `tvg-id`, `tvg-name`, `tvg-logo`, `tvg-chno`, `group-title` and `url-tvg`.
- **A "TV" page** in the left bar, shown only while network features are on:
  - channel groups, numbers, logos, search, favourites and recently watched;
  - hidden groups;
  - channel up and down (also Page Up / Page Down), and back to the last channel.
- **Library:** channels are stored in the library database as schema 10, and never mixed into Music or Videos.

### C. TV guide (XMLTV)

- **Sources:** the guide link from the playlist (`url-tvg`) or one entered by hand. `.xml` and `.xml.gz` are
  both accepted.
- **Updating:** refreshed daily, read piece by piece, with limits on size and age, keeping 7 days.
- **Display:**
  - *Now / Next* on each channel and in the player;
  - a guide grid by channel and hour;
  - programme details on selection.

### D. Update notifications

- **When:** once a day, about a minute after start, unless switched off. Also *Help → Check for updates*.
- **How:** reads the recent releases of the project's GitHub repository and compares the newest version with
  the running one.
- **Notice:** a quiet strip on Home ("Babarify 0.12.1 is available") and, when chosen, a dialog with the
  release notes as plain text. The buttons:
  - **Download**, which opens the release page on github.com in the browser;
  - **Skip this version**;
  - **Later**.
- **Never:** it doesn't download, install or run anything by itself.

## 3. Not in this milestone

- Movies and series from playlists, and a parental PIN.
- Catch-up and archives.
- Recording, pausing live TV, and multi-view.
- Xtream Codes or Stalker logins.
- Automatic installing of updates.

## 4. Testing

- **Unit tests:** the address rules, the M3U and XMLTV readers (including malformed, huge and hostile files),
  and version comparison.
- **Proxy tests:** redirects to `file:`, `\\server` and non-web schemes are refused, HLS is rewritten, and the
  token is required.
- **Real-engine tests:** a local test server provides HLS, MPEG-TS over HTTP and a dropping stream for
  reconnect. Nothing goes to the internet in tests.
- **Interface tests:** the switch off means no TV page and no connections; then playlists, zapping, the guide
  and the update notice.
- **Release engine:** the format checks run again on the rebuilt engine, which now includes network plugins.

## 5. Status (22 November 2026, branch m6-iptv-updates, not committed)

| Stage | State |
|---|---|
| A. Network streams | **Done.** M8's dialog and its stream proxy are restored, and network streams are off until switched on; the engine itself refuses streams while off. New: multicast udp/rtp, live-stream reconnect after 2, 4, 8, 15 and 30 s, and titles that never show the query. The release engine keeps http, https, live555, udp and rtp. |
| B. IPTV live TV | **Done.** The M3U reader, downloads (size limits, redirects to web addresses only), library schema 10, a background service with daily refresh, the TV page (lists, groups, search, favourites, hidden groups), and channel up/down/last on the player. A channel's own user agent and referrer reach only its streams, HLS pieces included. |
| C. TV guide | **Partly.** The XMLTV reader is built: gzip handled, entity declarations refused, an unpacking limit, and 6 h back to 7 days ahead. Now/Next and each channel's schedule are shown. **Not built:** the grid of all channels by hour, and channel logos. |
| D. Update notices | **Done.** A daily check of the GitHub release list (pre-releases included; only this repository's release pages). The notice strip has What's new (plain text), Download (opens the browser), Later and Skip. Help → Check for updates. The Settings → Privacy switch is on by default. Tests and smoke runs never check. |

The redesign (new logo, dashboard layout, 7 themes) comes after this milestone is committed.
