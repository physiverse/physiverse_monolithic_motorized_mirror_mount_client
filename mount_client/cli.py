"""Command-line interface for the Physiverse mirror mount.

Subcommands:
  provision      first-time setup over USB: save WiFi credentials and
                 (optionally) the command password on the device
  connect        interactive session over WiFi (authenticated) or USB
  status         one-shot report of both axes + connectivity
  factory-reset  clear WiFi + command password over USB
"""

import argparse
import os
import re
import select
import sys
import time

from .transport import (
    AuthError,
    SerialTransport,
    TransportError,
    WifiTransport,
    find_serial_port,
)


def open_serial(args):
    port = find_serial_port(args.port)
    print(f"using serial port {port}")
    tr = SerialTransport(port, args.baud)
    tr.settle()
    return tr


def pump(tr, max_wait=2.0, quiet=0.5, capture=None):
    """Print device output until it goes quiet; returns False on disconnect."""
    end = time.time() + max_wait
    while True:
        remaining = end - time.time()
        if remaining <= 0:
            return True
        r, _, _ = select.select([tr], [], [], min(quiet, remaining))
        if not r:
            continue
        data = tr.recv()
        if not data:
            print("\n(device disconnected)")
            return False
        text = data.decode(errors="replace")
        if capture is not None:
            capture.append(text)
        sys.stdout.write(text)
        sys.stdout.flush()
        end = max(end, time.time() + quiet)


def interactive(tr):
    print("connected — type commands (? for help), Ctrl-C or Ctrl-D to quit")
    stdin_fd = sys.stdin.fileno()
    inbuf = bytearray()
    is_serial = isinstance(tr, SerialTransport)
    old_attrs = None
    if is_serial:
        # cbreak: per-keystroke forwarding, no local echo -- the firmware
        # echoes serial input itself, so line mode would double every char.
        import termios
        import tty

        old_attrs = termios.tcgetattr(stdin_fd)
        tty.setcbreak(stdin_fd)
    try:
        while True:
            readable, _, _ = select.select([stdin_fd, tr], [], [])
            if tr in readable:
                data = tr.recv()
                if not data:
                    print("\n(disconnected by device)")
                    return 0
                sys.stdout.write(data.decode(errors="replace"))
                sys.stdout.flush()
            if stdin_fd in readable:
                chunk = os.read(stdin_fd, 4096)
                if not chunk:  # EOF (Ctrl-D)
                    pump(tr, max_wait=1.0, quiet=0.3)
                    return 0
                if is_serial:
                    for byte in chunk:
                        if byte == 0x04:  # Ctrl-D
                            pump(tr, max_wait=1.0, quiet=0.3)
                            return 0
                        tr.send_raw(bytes([byte]))  # device echoes it back
                    continue
                inbuf += chunk
                while b"\n" in inbuf:
                    line, _, rest = inbuf.partition(b"\n")
                    inbuf = bytearray(rest)
                    text = line.strip().decode(errors="replace")
                    if text:
                        tr.send_line(text)
    except KeyboardInterrupt:
        pass
    finally:
        if old_attrs is not None:
            import termios

            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old_attrs)
        tr.close()
    return 0


def resolve_transport(args):
    """Build a transport from --usb/--port or <host> <password> [tcp_port]."""
    if args.usb is None and getattr(args, "port", None):
        args.usb = ""  # an explicit serial port implies USB mode
    if args.usb is None:
        if not args.host or not args.password:
            raise TransportError(
                "need <host> <password> for WiFi, or --usb for serial"
            )
        tr = WifiTransport(args.host, args.port_num)
        tr.handshake(args.password)
        return tr
    if args.host or args.password:
        raise TransportError("--usb takes no host/password")
    return open_serial(args)


def cmd_provision(args):
    tr = open_serial(args)
    try:
        tr.send_line(f"wifi {args.ssid} {args.wifi_password}")
        pump(tr)
        if args.device_password:
            tr.send_line(f"setpass {args.device_password}")
            pump(tr)

        print("waiting for the mount to join the network...")
        seen = []
        deadline = time.time() + 30
        connected = False
        name = None
        while time.time() < deadline and not connected:
            tr.send_line("wifi")
            del seen[:]
            pump(tr, max_wait=3.0, quiet=1.0, capture=seen)
            blob = "".join(seen)
            connected = "wifi: CONNECTED" in blob
            m = re.search(r"name=(\S+\.local)", blob)
            if m:
                name = m.group(1)
            if not connected:
                time.sleep(2)

        if connected:
            print("\nprovisioning complete.")
            if name:
                pw_hint = " <device-password>" if args.device_password else ""
                print(f"connect over WiFi with:\n  mount connect {name}{pw_hint}")
        else:
            print(
                "\nstill not connected after 30s — check SSID/password/signal.\n"
                "Run `mount status --usb` to retry."
            )
            return 1
    finally:
        tr.close()
    return 0


def cmd_connect(args):
    tr = resolve_transport(args)
    return interactive(tr)


def cmd_status(args):
    tr = resolve_transport(args)
    try:
        tr.send_line("status")
        pump(tr)
        tr.send_line("wifi")
        pump(tr)
    finally:
        tr.close()
    return 0


def cmd_factory_reset(args):
    tr = open_serial(args)
    try:
        tr.send_line("factory-reset")
        pump(tr)
    finally:
        tr.close()
    return 0


def add_transport_args(p):
    p.add_argument("host", nargs="?", help="mount hostname or IP (WiFi mode)")
    p.add_argument("password", nargs="?", help="command password (WiFi mode)")
    p.add_argument("port_num", nargs="?", type=int, default=None,
                   metavar="tcp_port", help=f"TCP port (default {WifiTransport.DEFAULT_PORT})")
    p.add_argument("--usb", nargs="?", const="", default=None, metavar="PORT",
                   help="use USB serial instead of WiFi (auto-detects PORT)")
    p.add_argument("--port", default=None, metavar="PORT",
                   help="serial port (same as --usb PORT)")


def build_parser():
    ap = argparse.ArgumentParser(
        prog="mount",
        description="Client for the Physiverse motorized mirror mount.",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("provision", help="first-time setup over USB")
    p.add_argument("--ssid", required=True, help="WiFi network name")
    p.add_argument("--wifi-password", required=True, help="WiFi password")
    p.add_argument("--device-password", default=None,
                   help="command password for WiFi clients (recommended)")
    p.add_argument("--port", default=None, help="serial port (auto-detected)")
    p.add_argument("--baud", type=int, default=115200)
    p.set_defaults(func=cmd_provision)

    p = sub.add_parser("connect", help="interactive session (WiFi or USB)")
    add_transport_args(p)
    p.add_argument("--baud", type=int, default=115200)
    p.set_defaults(func=cmd_connect)

    p = sub.add_parser("status", help="one-shot axis + wifi report")
    add_transport_args(p)
    p.add_argument("--baud", type=int, default=115200)
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("factory-reset", help="clear wifi + password over USB")
    p.add_argument("--port", default=None, help="serial port (auto-detected)")
    p.add_argument("--baud", type=int, default=115200)
    p.set_defaults(func=cmd_factory_reset)

    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.func(args) or 0
    except (AuthError, TransportError, ConnectionError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
