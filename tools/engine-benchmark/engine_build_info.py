"""Print build/version information reported by libVLC itself (evidence for the licensing report).

Usage:  python tools/engine-benchmark/engine_build_info.py
"""

from __future__ import annotations

from babarify_frame.playback.adapters.libvlc import _load_vlc


def main() -> None:
    vlc = _load_vlc()
    print("libvlc version :", vlc.libvlc_get_version().decode())
    print("libvlc compiler:", vlc.libvlc_get_compiler().decode())
    print("libvlc changeset:", vlc.libvlc_get_changeset().decode())


if __name__ == "__main__":
    main()
