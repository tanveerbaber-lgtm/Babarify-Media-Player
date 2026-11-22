"""One running copy (0.12): a second start hands its file to the window that is already open.

Opening a file from Explorer while Babarify runs used to start another copy, with its own window and engine.
Now the new copy passes the file to the running one over a local named pipe and exits once the running copy
has confirmed. The pipe is private to the Windows user (``UserAccessOption``) and to the settings folder, so
a test profile or another account gets its own copy; nothing leaves the PC. Only one short JSON line is
accepted: ``{"open": "<path>"}``, where an empty path means "show the window". The answer is ``ok``.
"""

from __future__ import annotations

import getpass
import hashlib
import json
import logging
import os
import sys
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

log = logging.getLogger(__name__)

SERVER_PREFIX = "babarify-media-player-"
MAX_MESSAGE_BYTES = 70_000  # a Windows path is at most 32,767 characters
CONNECT_TIMEOUT_MS = 1500
NEWLINE = b"\n"
ACK = b"ok"


def server_name() -> str:
    """Per Windows user and per settings folder."""
    profile = os.environ.get("BABARIFY_CONFIG_DIR") or os.environ.get("APPDATA") or str(Path.home())
    digest = hashlib.sha256(f"{getpass.getuser()}|{profile}".casefold().encode()).hexdigest()[:16]
    return SERVER_PREFIX + digest


def hand_over(path: str | None, name: str | None = None) -> bool:
    """Give ``path`` (or nothing: just show the window) to a running copy. True only once it has confirmed,
    so a copy that doesn't answer (closing, or stuck) never leaves the file unopened: this one runs.
    Call it from the main thread of a starting copy (Windows pipes need it there, measured)."""
    socket = QLocalSocket()
    socket.connectToServer(name or server_name())
    if not socket.waitForConnected(CONNECT_TIMEOUT_MS):
        return False
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.user32.AllowSetForegroundWindow(-1)  # ASFW_ANY: the running copy may come to the front
    socket.write(json.dumps({"open": path or ""}).encode("utf-8") + NEWLINE)
    while socket.bytesToWrite() > 0:
        if not socket.waitForBytesWritten(CONNECT_TIMEOUT_MS):
            socket.abort()
            return False
    answer = b""
    while NEWLINE not in answer and socket.waitForReadyRead(CONNECT_TIMEOUT_MS):
        answer += bytes(socket.readAll().data())
    socket.abort()
    return answer.strip() == ACK


def parse_message(data: bytes) -> str | None:
    """The path asked for ("" = show the window), or None for anything else."""
    if len(data) > MAX_MESSAGE_BYTES:
        return None
    try:
        message = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    if not isinstance(message, dict) or not isinstance(message.get("open"), str):
        return None
    path: str = message["open"]
    return path if len(path) <= 32_767 and "\0" not in path else None


class InstanceServer(QObject):
    """Listens for later starts. ``open_requested`` carries the path ("" = just show the window)."""

    open_requested = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._server = QLocalServer(self)
        self._server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self._server.newConnection.connect(self._accept)

    def listen(self, name: str | None = None) -> bool:
        if self._server.listen(name or server_name()):
            return True
        log.warning("could not take the single-copy pipe: %s", self._server.errorString())
        return False

    def close(self) -> None:
        self._server.close()

    def _accept(self) -> None:
        while (socket := self._server.nextPendingConnection()) is not None:
            buffer = bytearray()

            def read(s: QLocalSocket = socket, b: bytearray = buffer) -> None:
                b += bytes(s.readAll().data())
                if NEWLINE not in b:
                    if len(b) > MAX_MESSAGE_BYTES:
                        s.abort()
                    return
                line = bytes(b[: b.index(NEWLINE)])
                b.clear()
                path = parse_message(line)
                if path is None:
                    log.warning("ignored a message on the single-copy pipe")
                    s.abort()
                    return
                s.write(ACK + NEWLINE)  # confirm first: the other copy waits for this, then exits
                s.flush()
                self.open_requested.emit(path)

            socket.readyRead.connect(read)
            socket.disconnected.connect(socket.deleteLater)
            if socket.bytesAvailable():
                read()
