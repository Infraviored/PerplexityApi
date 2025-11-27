"""
Minimal systemd notify helper.

Allows the server to keep the systemd service in the "activating" state
until the browser is actually ready to accept questions.
"""

from __future__ import annotations

import os
import socket
from typing import Optional


class SdNotifier:
    """Thin wrapper around sd_notify(3) semantics."""

    def __init__(self) -> None:
        self._socket_path = os.environ.get("NOTIFY_SOCKET")
        self._address: Optional[bytes] = None
        if self._socket_path:
            path = self._socket_path
            # Abstract namespace sockets use a leading "@"
            if path.startswith("@"):
                path = "\0" + path[1:]
            self._address = path.encode("utf-8")

    def available(self) -> bool:
        """Return True if we can talk to systemd."""
        return self._address is not None

    def _send(self, payload: str) -> bool:
        """Send a raw payload, swallowing any socket errors."""
        if not self._address:
            return False

        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
                sock.connect(self._address)
                sock.sendall(payload.encode("utf-8"))
            return True
        except OSError:
            return False

    def notify(self, **items: str) -> bool:
        """Send arbitrary key=value pairs."""
        if not items:
            return False
        payload = "\n".join(f"{key.upper()}={value}" for key, value in items.items())
        return self._send(payload)

    def status(self, message: str) -> bool:
        """Update STATUS value shown by systemctl."""
        return self.notify(STATUS=message)

    def ready(self, message: Optional[str] = None) -> bool:
        """Signal READY=1 (optionally updating STATUS)."""
        data = {"READY": "1"}
        if message:
            data["STATUS"] = message
        return self.notify(**data)

    def extend_timeout(self, seconds: int) -> bool:
        """Request more startup time while still in activating state."""
        microseconds = max(0, int(seconds * 1_000_000))
        return self.notify(EXTEND_TIMEOUT_USEC=str(microseconds))

    def watchdog(self) -> bool:
        """Ping WATCHDOG=1 if WatchdogSec is enabled."""
        return self.notify(WATCHDOG="1")


