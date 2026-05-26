# Supported Devices

## Tested Host

- Distribution: `CachyOS`
- Kernel: `7.0.9-1-cachyos`
- Capture date: `2026-05-26`
- Controller observed on this host: `8BitDo Ultimate 3mode Xbox`

## Input Stack Note

Linux historically exposes gamepads through two different APIs:

- `evdev` through `/dev/input/eventX`, which is the modern event interface used by most tooling.
- `joystick` through `/dev/input/jsX`, which is the older joystick interface still required by some games and utilities.

A mode is only fully validated when the expected interface exists and produces usable events for the target client.

## Tested Device Matrix

`eventX`, `jsX`, and `hidrawX` are dynamic node numbers. Prefer `/dev/input/by-id/` and `/dev/input/by-path/` for stable references.

| Mode | Transport | Vendor ID | Product ID | eventX | jsX | hidraw | Etat |
| --- | --- | --- | --- | --- | --- | --- | --- |
| XInput | USB filaire | `0x2dc8` | `0x2030` | oui (`event17`) | oui (`js0`) | non | OK |
| DInput | USB filaire | - | - | - | - | - | Non teste |
| Switch | USB filaire | - | - | - | - | - | Non teste |
| Android | USB filaire | - | - | - | - | - | Non teste |
| XInput | Dongle 2.4G | - | - | - | - | - | Non teste |
| DInput | Dongle 2.4G | - | - | - | - | - | Non teste |
| Switch | Dongle 2.4G | - | - | - | - | - | Non teste |
| Android | Dongle 2.4G | - | - | - | - | - | Non teste |
| XInput | Bluetooth | - | - | - | - | - | Non teste |
| DInput | Bluetooth | - | - | - | - | - | Non teste |
| Switch | Bluetooth | - | - | - | - | - | Non teste |
| Android | Bluetooth | - | - | - | - | - | Non teste |

## Observed XInput USB Mode

The currently connected controller enumerates as:

- `lsusb`: `Bus 001 Device 019: ID 2dc8:2030 8BitDo 8BitDo Ultimate 3mode Xbox`
- `/proc/bus/input/devices` name: `Generic X-Box pad`
- Kernel driver: `xpad`
- Stable by-id symlinks:
  - `/dev/input/by-id/usb-8BitDo_8BitDo_Ultimate_3mode_Xbox_0000DA8814D072EB-event-joystick -> ../event17`
  - `/dev/input/by-id/usb-8BitDo_8BitDo_Ultimate_3mode_Xbox_0000DA8814D072EB-joystick -> ../js0`
- Stable by-path symlinks:
  - `/dev/input/by-path/pci-0000:c6:00.3-usb-0:3:1.0-event-joystick -> ../event17`
  - `/dev/input/by-path/pci-0000:c6:00.3-usb-0:3:1.0-joystick -> ../js0`

No matching `/dev/hidraw*` device was exposed for `2dc8:2030` on this host. Existing `hidraw` nodes belonged to other peripherals.

## Raw Capture Summary

### `lsusb -v -d 2dc8:2030`

- `idVendor`: `0x2dc8`
- `idProduct`: `0x2030`
- `iManufacturer`: `8BitDo`
- `iProduct`: `8BitDo Ultimate 3mode Xbox`
- `iSerial`: `0000DA8814D072EB`
- `bDeviceClass`: `255` vendor specific
- `bNumInterfaces`: `2`

### `cat /proc/bus/input/devices`

Relevant block:

```text
I: Bus=0003 Vendor=2dc8 Product=2030 Version=0200
N: Name="Generic X-Box pad"
P: Phys=usb-0000:c6:00.3-3/input0
H: Handlers=event17 js0
```

### `udevadm info --attribute-walk --name=/dev/input/event17`

Relevant attributes:

```text
ATTRS{id/vendor}=="2dc8"
ATTRS{id/product}=="2030"
ATTRS{name}=="Generic X-Box pad"
ATTRS{phys}=="usb-0000:c6:00.3-3/input0"
DRIVERS=="xpad"
ATTRS{manufacturer}=="8BitDo"
ATTRS{product}=="8BitDo Ultimate 3mode Xbox"
ATTRS{serial}=="0000DA8814D072EB"
```

### `evtest /dev/input/event17`

`evtest` successfully opened the device and reported:

- face buttons on `EV_KEY`
- sticks and triggers on `EV_ABS`
- force feedback support on `EV_FF`

This confirms that the `evdev` path is functional in the observed USB/XInput mode.

### `jstest /dev/input/js0`

The host exposes `/dev/input/js0`, so the legacy joystick node exists. The `jstest` binary was not installed on the capture machine, so event traffic for the legacy interface was not exercised during this pass.

## Raw Capture Commands

Run these commands once per transport and mode, replacing `eventX` and `jsX` with the actual nodes for that session:

```bash
lsusb
lsusb -v
cat /proc/bus/input/devices
ls -l /dev/input/by-id/
ls -l /dev/input/by-path/
ls -l /dev/hidraw*
udevadm info --attribute-walk --name=/dev/input/eventX
evtest /dev/input/eventX
jstest /dev/input/jsX
```

The project helper commands are also useful while collecting identifiers:

```bash
uv run ultim8do list --verbose
uv run ultim8do report --json
```

## Remaining Modes To Capture

The following combinations still need real hardware captures on this exact controller before they can be marked supported here:

- USB in `DInput`, `Switch`, and `Android` modes if the hardware/firmware exposes them.
- Dongle `2.4G` mode in each available controller mode.
- Bluetooth mode in each available controller mode.

Do not reuse the `0x2dc8:0x2030` identifiers for those rows unless the exact same identifiers are observed again. 8BitDo controllers frequently change product IDs, names, driver bindings, and interface exposure across transport and mode combinations.
