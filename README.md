# Physiverse Motorized Mirror Mount — Client

Command-line client for the [mirror mount
firmware](https://github.com/physiverse/physiverse_monolithic_motorized_mirror_mount_firmware).
It talks to the mount over **USB serial** (first-time provisioning, and
control without WiFi) or over **WiFi TCP** with challenge-response
authentication.

## Install

```bash
pip install .          # or: pipx install .
```

Provides the `mount` command. You can also run it without installing:

```bash
python3 -m mount_client --help    # pyserial must be installed
```

macOS / Linux only (uses `select` on the serial fd).

## First-time setup (USB)

1. Connect the board by USB-C. The VIN screw terminal must also be powered
   (5–12 V) for the motors, but provisioning works from USB alone.
2. Provision WiFi credentials and set a command password:

   ```bash
   mount provision --ssid MyNetwork --wifi-password wifipass \
                   --device-password mountpass
   ```

   The client auto-detects the serial port (`--port` overrides), saves the
   credentials on the device, and waits until it joins the network. It then
   prints the `connect` line for future use.

The device advertises itself as `mirrormount-xxxx.local` on your network via
mDNS; the exact name is shown at provisioning time.

## Controlling the mount

Interactive session over WiFi (authenticated):

```bash
mount connect mirrormount-ac88.local mountpass
```

Or over USB (no password needed — physical access is trust):

```bash
mount connect --usb
```

Then type commands directly (`?` lists them). The day-to-day safe set:

| Command | Description |
|---------|-------------|
| `seekN <target> <speed>` | Closed-loop move axis N to sensor value `target` |
| `homeN [speed]` / `home` | Park one axis / both axes at their home positions |
| `tickN <±n> [spd] [ms]` | Fine adjustment: small continuous nudge of axis N (sign = direction) |
| `s` | Stop both motors immediately |
| `r` | Read both sensors |
| `status` | Report position/range/home for both axes |

Calibration and low-level motor commands exist in the firmware but are
intentionally not documented here — see the firmware repo's `PROTOCOL.md`
if you know you need them (USB recommended).

One-shot status check:

```bash
mount status mirrormount-ac88.local mountpass   # WiFi
mount status --usb                              # USB
```

## Other commands

```bash
mount factory-reset        # USB only: clears wifi + command password
                           # (axis calibration is kept)
```

## Troubleshooting

- **"no USB serial ports found"** — check the cable/port; on macOS the board
  shows up as `/dev/cu.usbmodem*`.
- **"multiple serial ports found"** — pass the one you want:
  `mount connect --usb /dev/cu.usbmodem3101`.
- **WiFi connect fails** — confirm the password with `mount status --usb`
  (it prints `cmd-password=set/UNSET`), or re-provision.
- **Motors don't move** — VIN must be powered (5–12 V); USB power alone runs
  the logic but not the motors.
