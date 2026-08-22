"""Transports for talking to the mirror mount: USB serial and WiFi TCP.

Both transports speak the same newline-terminated command protocol. USB
serial needs no authentication (physical access is trust); WiFi TCP does a
challenge-response handshake (NONCE / AUTH) against the password stored on
the device.
"""

import hashlib
import hmac
import re
import socket
import time

import serial
import serial.tools.list_ports


class TransportError(Exception):
    pass


class AuthError(TransportError):
    pass


class SerialTransport:
    def __init__(self, port, baud=115200):
        try:
            self.ser = serial.Serial(port, baud, timeout=0)
        except OSError as e:
            raise TransportError(f"cannot open {port}: {e}") from e

    def settle(self, seconds=2.0):
        """Wait out the ESP32-C3 boot/reset that port opening can trigger,
        then drop any boot banner so it doesn't pollute command output."""
        time.sleep(seconds)
        self.ser.reset_input_buffer()

    def send_line(self, text):
        self.ser.write((text + "\n").encode())
        self.ser.flush()

    def send_raw(self, data):
        self.ser.write(data)
        self.ser.flush()

    def recv(self):
        return self.ser.read(4096)

    def fileno(self):
        return self.ser.fileno()

    def close(self):
        self.ser.close()


class WifiTransport:
    DEFAULT_PORT = 3333

    def __init__(self, host, port=None, timeout=5):
        try:
            self.sock = socket.create_connection(
                (host, port or self.DEFAULT_PORT), timeout=timeout)
        except OSError as e:
            raise TransportError(f"cannot connect to {host}:{port or self.DEFAULT_PORT}: {e}") from e
        self.sock.settimeout(None)

    def handshake(self, password):
        greeting = self._read_line()
        if not greeting.startswith("NONCE "):
            raise TransportError(f"unexpected greeting: {greeting!r}")
        nonce = greeting.split()[1]
        key = hashlib.sha256(password.encode()).digest()
        resp = hmac.new(key, nonce.encode(), hashlib.sha256).hexdigest()
        self.send_line(f"AUTH {resp}")
        reply = self._read_line()
        if reply != "OK":
            raise AuthError("authentication failed (wrong password?)")

    def _read_line(self):
        buf = bytearray()
        while b"\n" not in buf:
            chunk = self.sock.recv(256)
            if not chunk:
                raise ConnectionError("connection closed during handshake")
            buf += chunk
        return bytes(buf).partition(b"\n")[0].decode(errors="replace").strip()

    def send_line(self, text):
        self.sock.sendall((text + "\n").encode())

    def send_raw(self, data):
        self.sock.sendall(data)

    def recv(self):
        return self.sock.recv(4096)

    def fileno(self):
        return self.sock.fileno()

    def close(self):
        self.sock.close()


_PORT_RE = re.compile(r"(cu\.usb(modem|serial)|ttyACM\d+|ttyUSB\d+)")


def find_serial_port(explicit=None):
    """Return a serial port path: the explicit one, or auto-detect the board."""
    if explicit:
        return explicit
    candidates = []
    for p in serial.tools.list_ports.comports():
        if _PORT_RE.search(p.device):
            candidates.append(p.device)
        elif p.device.startswith("COM") and p.description and any(
            w in p.description.lower() for w in ("usb", "serial", "esp32")
        ):
            candidates.append(p.device)
    candidates.sort()
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise TransportError(
            "no USB serial ports found (is the board plugged in via USB-C?)"
        )
    raise TransportError(
        "multiple serial ports found, pick one with --port:\n  "
        + "\n  ".join(candidates)
    )
