# Phase 1, hardware identification

Date: 2026-10-26, host: CachyOS, kernel 7.2.9-2-cachyos

## Detected device

```
Bus 005 Device 050: ID 2dc8:2030 8BitDo 8BitDo Ultimate 3mode Xbox
```

| Field | Value | Source |
|---|---|---|
| `idVendor` | `0x2dc8` (8BitDo) | sysfs |
| `idProduct` | `0x2030` | sysfs |
| `bcdDevice` | `0x0200` (firmware 2.00) | sysfs |
| iManufacturer | `8BitDo` | descriptor |
| iProduct | `8BitDo Ultimate 3mode Xbox` | descriptor |
| iSerial | `0000DA8814D072EB` | descriptor |
| `bDeviceClass` | `0xff` / `0x47` / `0xd0` | descriptor |
| Speed | Full Speed (12 Mbps) | `speed` = 12 |
| USB path | `5-1.1` (behind a VIA VL815 hub) | sysfs |

`ff/47/d0` is **XGIP** (*Xbox Game Input Protocol*). It is **not** HID: there is no
report descriptor in the enumeration and no `hidraw` node is created for this
device.

## Interfaces

```
Interface 0  alt 0   class 0xff/0x47/0xd0   driver = xpad
   EP 0x81  IN  interrupt  64 B  bInterval 4
   EP 0x01  OUT interrupt  64 B  bInterval 4

Interface 1  alt 0   (no endpoint)
Interface 1  alt 1   isochronous (headset audio)
   EP 0x03  OUT isoc 224 B  bInterval 1
   EP 0x83  IN  isoc 128 B  bInterval 1
```

Interface 0 carries the Xbox input and configuration traffic, interface 1 alt 1
carries headset audio. The kernel binds `xpad` to interface 0 and exposes
`/dev/input/js0` and `/dev/input/event16`.

## What this means for the project

1. No `hidraw`: the regular HID layer is unusable on this model in Xbox mode.
2. The official software (*Ultimate Software X*, Microsoft Store UWP) talks to the
   pad through `Windows.Gaming.Input.Custom` and `GipGameControllerProvider`, that
   is **GIP messages** over the interrupt endpoints 0x01/0x81.
3. On Linux the path is therefore: detach `xpad` from interface 0, take over with
   libusb, then send 64 byte GIP frames (4 byte header plus payload).

## The WinRT component on the Windows side (proof of the GIP transport)

`UltimateSoftwareX_1.5.0.0.appxbundle` ships `D4XGaming.Devices.winmd`, which
exposes:

```csharp
public sealed class D4XDevice : IGameController, IGameControllerBatteryInfo
{
    public void SendMessageA(byte[] pData);
    public void SendMessageId(byte[] pData, uint messageId);
    public void GetMessageB(byte[] pData, out uint dataSize);
    public void SendReceiveMessageC(MessageCRequest request, out MessageCResponse response);
}
```

Same contract as `GipGameControllerProvider` (WinRT GIP API): `messageId` is the GIP
command, `pData` the payload. The "3-mode" model has **no DInput mode**: the official
manual only documents Xbox, Windows 10-11 (2.4G and wired), Android, Apple and Steam
Deck. There is no classic HID mode on PC.

## Still to identify

- PIDs and descriptors with the **2.4G adapter** (the kit ships one).
- PIDs and descriptors in **Bluetooth** mode (Android and Apple hosts).
- The GIP command number 8BitDo uses for its configuration messages.
