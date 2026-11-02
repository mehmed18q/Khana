"""One desktop application per user, with file opens forwarded over local IPC."""

import json
import time
from hashlib import sha256
from pathlib import Path

from PySide6.QtCore import QLockFile, QObject, QStandardPaths, QTimer, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from reader import APP_ID


class SingleInstance(QObject):
    openRequested = Signal(list)

    def __init__(self, parent=None, directory=None, name=None):
        super().__init__(parent)
        identity = sha256(str(Path.home()).encode()).hexdigest()[:16]
        base = Path(
            directory
            or QStandardPaths.writableLocation(QStandardPaths.StandardLocation.TempLocation)
        )
        self.address = str(base / (name or f"{APP_ID}-{identity}"))
        self.lock = QLockFile(self.address + ".lock")
        self.lock.setStaleLockTime(0)
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.newConnection.connect(self._accept)
        self.clients = {}

    def start_or_forward(self, paths):
        """Return True for the owner, False only after the owner acknowledges."""
        payload = (
            json.dumps([str(Path(path).expanduser().resolve()) for path in paths]).encode() + b"\n"
        )
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if self.lock.tryLock(100):
                QLocalServer.removeServer(
                    self.address
                )  # Only the lock owner removes a stale socket.
                if not self.server.listen(self.address):
                    self.lock.unlock()
                    raise RuntimeError(self.server.errorString())
                return True
            client = QLocalSocket()
            client.connectToServer(self.address)
            if not client.waitForConnected(200):
                continue
            client.write(payload)
            client.waitForBytesWritten(1000)
            if client.waitForReadyRead(3000) and bytes(client.readAll()) == b"OK\n":
                client.disconnectFromServer()
                return False
            client.abort()
            # Do not resend an unacknowledged request or open a competing window.
            raise RuntimeError("The open Khana window did not respond. Please try again.")
        raise RuntimeError("Khana is still starting. Please try opening the file again.")

    def _accept(self):
        while self.server.hasPendingConnections():
            client = self.server.nextPendingConnection()
            self.clients[client] = bytearray()
            client.readyRead.connect(lambda c=client: self._read(c))
            client.disconnected.connect(lambda c=client: self._discard(c))
            QTimer.singleShot(5000, client, client.disconnectFromServer)
            self._read(client)

    def _discard(self, client):
        self.clients.pop(client, None)
        client.deleteLater()

    def _read(self, client):
        data = self.clients.get(client)
        if data is None:
            return
        data.extend(bytes(client.readAll()))
        if len(data) > 1024 * 1024:
            client.disconnectFromServer()
            return
        if b"\n" not in data:
            return
        try:
            paths = json.loads(data.split(b"\n", 1)[0])
            if not isinstance(paths, list) or any(
                not isinstance(p, str) or not Path(p).is_absolute() for p in paths
            ):
                raise ValueError("Invalid file paths")
            self.openRequested.emit(paths)
            client.write(b"OK\n")
            client.flush()
        except (ValueError, UnicodeError):
            pass
        client.disconnectFromServer()

    def close(self):
        self.server.close()
        self.lock.unlock()
