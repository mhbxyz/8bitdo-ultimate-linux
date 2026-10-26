# ultim8do, 8BitDo Ultimate 3-mode controller on Linux

Configuring the **8BitDo Ultimate 3-mode Controller for Xbox** (`2dc8:2030`) from
Linux: profiles, stick and trigger deadzones, button remapping, options, without
going through *Ultimate Software X* (Windows UWP app).

## How it works

The pad exposes **no configuration channel over USB**. It speaks GIP on its XGIP
interface (`ff/47/d0`), ignores the "Xbox 360" frames used by other Ultimate
models, and ignores `GIP_CMD_HID_REPORT`. Its Bluetooth identity `81HB-*` does
expose a GATT configuration service, and that is the path the official Android app
uses.

```
BLE service 00010203-0405-0607-0809-0A0B0C0D1910
    char    00010203-0405-0607-0809-0A0B0C0D2B11   (write + notify)

request  : 04 | u16 cmd | u16 sub | u16 len | u16 crc | u32 total | u32 offset | data
response : 04 | 00      | u16 cmd | u16 len | u16 crc | u32 total | u32 offset | data
```

Configuration record: **532 bytes**, CRC-16/KERMIT header over `record[2:]`, then
the Ultimate family structure (without macros), with 3 profiles.

Full details, measurements and evidence: [`docs/03-protocole-ble.md`](docs/03-protocole-ble.md).

## Getting started

On the pad: set the selector to the **Bluetooth** position (first symbol), then
hold **X + Start for 3 s** to pair. The pad then advertises as `81HB-D`.

```bash
uv sync
sudo ./scripts/setup-permissions.sh     # udev (USB/hidraw access) + usbmon

uv run ultim8do dump                    # read and print the record
```

## Usage

```bash
uv run ultim8do dump --json --save capture/record.bin
uv run ultim8do set --slot 0 --map a=b --map b=a
uv run ultim8do set --slot 0 --stick-deadzone 12 --trigger-deadzone 8
uv run ultim8do set --slot 1 --enable
```

`set` writes in 45 byte chunks, sends the commit and reads the record back to
verify.

Available function codes: `none start l3 r3 select x y right left down up lb rb b
a lt rt menu home p1 p2 p3 p4`.

## Status

| Phase | State |
|---|---|
| 1. USB identification (`lsusb`, descriptors) | done, [`docs/01-device-identification.md`](docs/01-device-identification.md) |
| 2. Traffic capture | done over BLE (this model has no USB configuration channel) |
| 3. Setting comparison | done, read/write/commit verified on hardware |
| 4. REA of the 8BitDo binaries | done, [`docs/02-protocole.md`](docs/02-protocole.md), [`docs/re/`](docs/re/) |
| 5. Python reimplementation | done, `src/ultim8do/` (BLE transport, record, CLI) |
| 6. Native Linux interface | not started |

**Important limitation.** Read, write and commit all work, and the record is stored
in flash, but the firmware **never applies it** to the XInput path. Even the
official software does not change that record when it applies a mapping, so the
real settings travel through a private driver channel. Details and evidence in
[`docs/03-protocole-ble.md`](docs/03-protocole-ble.md) sections 5 to 14.

The configuration is also **per mode**: the record read in Bluetooth mode has a
different `record id` from the PC/2.4G one.

## What actually works today

**Ultimate Software X running in a Windows VM**, with the USB controller passed
through over vfio. That is the only known way to configure this pad from a Linux
host, and it is fully documented in `docs/02-protocole.md` section 13, with the
helper script `scripts/usb-passthrough.sh`.

## Diagnostic tools

```bash
./tools/dump-device.sh             # USB state: descriptors, interfaces, hidraw
./tools/usbwatch.sh                # watch 2dc8:* (re)enumerations
uv run tools/gip-probe.py listen   # speak GIP: power-on, identify, frame dump
uv run tools/ble-probe.py scan     # scan for 81HB-* pads
uv run tools/record-diff.py a.bin b.bin   # diff two record dumps
```

## Tests

```bash
uv run pytest -q
```
