"""Bounded, authenticated loopback transport for the external Godot renderer.

The Qt thread polls nonblocking sockets. This module never accesses UART, physics
or Qt objects; malformed/stalled peers are discarded without blocking the GUI.
"""
import hmac
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import time

MAX_LINE = 65536
KEYS = {"w", "up", "s", "down", "a", "left", "d", "right"}
SETTINGS = {"mode", "accEnabled", "targetKmh", "headwayMs", "seed"}


def find_godot(root):
    """Locate an installed/runtime-local Godot without changing system settings."""
    explicit = os.environ.get("GODOT_BIN")
    if explicit:
        candidate = Path(explicit).expanduser()
        return candidate if candidate.is_file() and os.access(candidate, os.X_OK) else None
    root = Path(root)
    candidates = [root / ".tools/godot/Godot.app/Contents/MacOS/Godot",
                  root / "tools/godot/Godot.app/Contents/MacOS/Godot",
                  root / ".tools/godot/godot", root / ".tools/godot/godot.exe",
                  root / "tools/godot/godot", root / "tools/godot/godot.exe",
                  Path("/Applications/Godot.app/Contents/MacOS/Godot")]
    for folder in (root / '.tools/godot', root / 'tools/godot'):
        candidates.extend(sorted(folder.glob('Godot_v*-stable_win64.exe'), reverse=True))
        candidates.extend(sorted(folder.glob('Godot_v*-stable_linux.x86_64'), reverse=True))
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    for name in ("godot", "godot4", "Godot", "godot.exe"):
        candidate = shutil.which(name)
        if candidate:
            return Path(candidate)
    return None


class GodotBridge:
    """A single authenticated localhost renderer; poll only from one owner."""
    def __init__(self, *, clock=time.monotonic, token=None, heartbeat_timeout=.35):
        self.clock = clock
        self.token = token or secrets.token_urlsafe(32)
        self.heartbeat_timeout = heartbeat_timeout
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(2)
        self.listener.setblocking(False)
        self.port = self.listener.getsockname()[1]
        self.peer = None
        self.connected = False
        self.active = False
        self.closed = False
        self._accepted_at = 0.
        self._heartbeat_at = 0.
        self._input = bytearray()
        self._output = b""
        self._latest = b""
        self._events = []

    def _disconnect(self, reason):
        if self.peer is not None:
            try:
                self.peer.close()
            except OSError:
                pass
        self.peer = None
        was_connected = self.connected
        self.connected = self.active = False
        self._input.clear()
        self._output = self._latest = b""
        if was_connected:
            # Discard commands from the same batch when validation/liveness
            # fails. The owner must not apply a command before its disconnect.
            self._events = [e for e in self._events if e['type'] in ('connected', 'disconnected')]
            self._events.append(dict(type="disconnected", reason=reason))

    def _message(self, message):
        if not isinstance(message, dict):
            raise ValueError("Message must be an object")
        if not self.connected:
            if (message.get("type") != "hello" or type(message.get("protocol")) is not int
                    or message["protocol"] != 1 or not isinstance(message.get("token"), str)
                    or not hmac.compare_digest(message["token"], self.token)):
                raise ValueError("Authentication failed")
            self.connected = True
            self._heartbeat_at = self.clock()
            self._events.append(dict(type="connected"))
            return
        kind = message.get("type")
        if kind == "input":
            if (message.get("key") not in KEYS or type(message.get("pressed")) is not bool
                    or type(message.get("repeat", False)) is not bool):
                raise ValueError("Invalid input")
        elif kind == "heartbeat" or (kind == "action" and message.get("name") == "focus"):
            if type(message.get("active")) is not bool:
                raise ValueError("Invalid focus heartbeat")
            self.active = message["active"]
            self._heartbeat_at = self.clock()
        elif kind == "action":
            if message.get("name") not in ("start", "pause", "restart"):
                raise ValueError("Invalid action")
        elif kind == "setting":
            key, value = message.get("key"), message.get("value")
            if key not in SETTINGS:
                raise ValueError("Invalid setting")
            if key == "mode":
                valid = isinstance(value, str) and value in ("active", "warn", "off")
            elif key == "accEnabled":
                valid = type(value) is bool
            else:
                lo, hi = {"targetKmh": (0, 200), "headwayMs": (800, 4000), "seed": (1, 999999)}[key]
                valid = type(value) in (int, float) and lo <= value <= hi and int(value) == value
            if not valid:
                raise ValueError("Invalid setting value")
        else:
            raise ValueError("Unsupported message")
        self._events.append(message)

    def poll(self):
        if self.closed:
            return []
        # An extra client cannot replace the authenticated renderer.
        for _ in range(4):
            try:
                peer, address = self.listener.accept()
            except BlockingIOError:
                break
            except OSError:
                break
            if self.peer is not None or address[0] != "127.0.0.1":
                peer.close()
                continue
            peer.setblocking(False)
            peer.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.peer = peer
            self._accepted_at = self.clock()
        if self.peer is not None:
            try:
                for _ in range(8):
                    try:
                        data = self.peer.recv(8192)
                    except BlockingIOError:
                        break
                    if not data:
                        self._disconnect("closed")
                        break
                    self._input.extend(data)
                    if len(self._input) > MAX_LINE:
                        raise ValueError("Input buffer limit exceeded")
                # At most 64 input messages per GUI poll. Excess traffic is a
                # failed renderer, never an unbounded Qt event queue.
                for _ in range(64):
                    if b"\n" not in self._input:
                        break
                    line, _, rest = self._input.partition(b"\n")
                    self._input = bytearray(rest)
                    self._message(json.loads(line))
                if b"\n" in self._input:
                    raise ValueError("Message rate limit exceeded")
                now = self.clock()
                if self.connected and now - self._heartbeat_at > self.heartbeat_timeout:
                    self._disconnect("heartbeat_timeout")
                elif not self.connected and now - self._accepted_at > 3:
                    self._disconnect("authentication_timeout")
                if self.peer is not None:
                    if not self._output:
                        self._output, self._latest = self._latest, b""
                    if self._output:
                        try:
                            sent = self.peer.send(self._output)
                            self._output = self._output[sent:]
                        except BlockingIOError:
                            pass
            except (OSError, ValueError, UnicodeError, TypeError, OverflowError, RecursionError):
                self._disconnect("invalid_or_broken_peer")
        events, self._events = self._events, []
        return events

    def send_state(self, state, *, connected, backend):
        if self.connected:
            packet = json.dumps(dict(type="state", protocol=1, state=state,
                                     connected=connected, backend=backend),
                                ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode() + b"\n"
            if len(packet) > MAX_LINE:
                raise ValueError("State packet exceeds transport limit")
            # Keep the newest complete snapshot behind any partially sent one.
            self._latest = packet

    def close(self):
        if self.closed:
            return
        self._disconnect("server_closed")
        self.listener.close()
        self.closed = True
