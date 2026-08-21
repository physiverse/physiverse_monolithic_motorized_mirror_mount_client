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

Then type firmware commands directly (`?` lists them). Highlights:

| Command | Description |
|---------|-------------|
| `seekN <target> <speed>` | Closed-loop move axis N to sensor value `target` |
| `home` | Home both axes |
| `mN <speed> [ms]` | Raw drive motor N |
| `s` | Stop both motors |
| `r` | Read both sensors |

See the firmware repo's `PROTOCOL.md` for the full command reference,
including calibration commands (`setrangeN`, `sethomeN`, `setpolN`, `probeN`)
— all of which work through this client on either transport.

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
