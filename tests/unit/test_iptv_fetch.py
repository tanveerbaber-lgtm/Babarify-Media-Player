"""IPTV downloads (0.12): channel lists, guides and logos, with the proxy's safeguards and size limits."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from urllib.parse import quote

import pytest

import babarify_frame.playback.stream_proxy as stream_proxy
from babarify_frame.iptv.fetch import USER_AGENT, FetchError, fetch_bytes, fetch_to_file, read_local
from netserver import LocalServer


@pytest.fixture
def server(tmp_path: Path) -> Iterator[LocalServer]:
    (tmp_path / "list.m3u").write_text("#EXTM3U\n#EXTINF:-1,A\nhttps://tv.example.com/a\n", encoding="utf-8")
    (tmp_path / "big.bin").write_bytes(b"x" * 300_000)
    srv = LocalServer(tmp_path)
    yield srv
    srv.close()


def test_a_list_downloads(server: LocalServer) -> None:
    assert fetch_bytes(server.url("/list.m3u"), 1_000_000).startswith(b"#EXTM3U")


def test_a_redirect_to_another_web_address_is_followed(server: LocalServer) -> None:
    target = quote(server.url("/list.m3u"), safe="")
    assert fetch_bytes(server.url(f"/redirect?to={target}"), 1_000_000).startswith(b"#EXTM3U")


@pytest.mark.parametrize("to", ["file:///C:/Windows/win.ini", "vlc://quit"])
def test_a_redirect_elsewhere_is_refused(server: LocalServer, to: str) -> None:
    with pytest.raises(FetchError, match="redirect"):
        fetch_bytes(server.url(f"/redirect?to={quote(to, safe='')}"), 1_000_000)


def test_a_redirect_to_a_network_share_stays_on_the_web_server(server: LocalServer) -> None:
    """A Windows share path is read as a path on the same web server, so nothing connects to a share."""
    with pytest.raises(FetchError, match="404"):
        fetch_bytes(server.url("/redirect?to=" + quote("\\\\server\\share\\x", safe="")), 1_000_000)


def test_endless_redirects_stop(server: LocalServer) -> None:
    with pytest.raises(FetchError, match="redirects"):
        fetch_bytes(server.url("/loop"), 1_000_000)


def test_the_size_limit_stops_a_download(server: LocalServer, tmp_path: Path) -> None:
    with pytest.raises(FetchError, match="larger"):
        fetch_bytes(server.url("/big.bin"), 100_000)
    target = tmp_path / "out.bin"
    with pytest.raises(FetchError):
        fetch_to_file(server.url("/big.bin"), target, 100_000)
    assert not target.exists() and not (tmp_path / "out.bin.partial").exists()  # nothing half-written


def test_a_server_that_never_answers_times_out(server: LocalServer, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stream_proxy, "READ_TIMEOUT_S", 0.5)
    with pytest.raises(FetchError):
        fetch_bytes(server.url("/stall"), 1_000_000)


@pytest.mark.parametrize("url", ["file:///C:/Windows/win.ini", "rtsp://example.com/a", "C:\\list.m3u"])
def test_only_web_addresses_are_downloaded(url: str) -> None:
    with pytest.raises(FetchError):
        fetch_bytes(url, 1_000_000)


def test_a_local_file_is_read_with_its_limit(tmp_path: Path) -> None:
    small, big = tmp_path / "a.m3u", tmp_path / "b.m3u"
    small.write_bytes(b"#EXTM3U\n")
    big.write_bytes(b"x" * 2000)
    assert read_local(str(small), 1000) == b"#EXTM3U\n"
    with pytest.raises(FetchError):
        read_local(str(big), 1000)
    with pytest.raises(FetchError):
        read_local(str(tmp_path / "missing.m3u"), 1000)


def test_only_a_generic_client_name_is_sent() -> None:
    assert USER_AGENT.startswith("Babarify Media Player/")
