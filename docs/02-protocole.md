# Phase 4, configuration protocol (REA)

Cross-checked sources:

1. ILSpy decompilation of the managed *Ultimate Software V2* app (`/tmp/dec/v2`), frames in clear text;
2. exports and strings of `8BitDoAdvance.dll` (native engine), see `docs/re/8BitDoAdvance_exports.txt`;
3. community work verified on hardware: `MiguelSanzBr/8bitdo-ultimate2-linux`
   (`docs/PROTOCOL.md`, `ULTIMATE_24G.md`, `ULTIMATE_BT.md`), `s8n/ultimatecontroller-rs`.

## 1. Why a mode switch is needed

In Xbox mode (XGIP `ff/47/d0`) the pad exposes **no configuration channel**: two
64 byte interrupt endpoints that only carry gamepad reports and Xbox LED/rumble
commands. The official software therefore starts by making it re-enumerate into
"configuration mode", where it exposes a HID interface with output report `0x81`
and input report `0x02`.

Sequence (identical on Ultimate BT / 2.4G, to be replayed on the 3-mode):

```
01 03 02                      Xbox LED init
02 08 03                      controller init
01 03 02                      Xbox LED init
01 03 06                      configuration mode trigger
00 08 00 01 00 00 00 00       left rumble
00 08 00 00 01 00 00 00       right rumble
00 08 00 01 01 00 00 00       both
00 08 00 05 01 00 00 00       strong
00 08 00 00 00 00 00 00       stop
```

About 15 ms between packets, sent on the interrupt OUT endpoint. Roughly one second
later the pad disconnects and comes back with another PID. To go back to Xbox mode:
unplug and replug, or `81 05 00 51 02` if the pad accepts it.

Known PIDs in the family:

| PID | Meaning |
|---|---|
| `0x3106` | pad in XInput mode (wired or receiver) |
| `0x3012` | pad in configuration mode (wired, switch on D, or after the knock) |
| `0x3013` | 2.4G receiver in configuration mode |
| `0x6007` | Ultimate BT in configuration mode |
| `0x6009` ... `0x6013` | internal PIDs reported in replies (`getRR`) |
| **`0x2030`** | **Ultimate 3-mode for Xbox, XInput (our pad)** |

## 2. Frames of the Ultimate family

Three framing variants exist depending on the model. All start with `0x81` (output
report), replies start with `0x02`.

**Ultimate 2 (wired, dedicated HID channel), with CRC:**

```
request  : 81 04 | u16 cmd | u16 sub | u16 len | u16 crc | u32 total | u32 offset | data[len <= 45]
response : 02 04 | u16 4   | u16 cmd | u16 len | u16 crc | u32 total | u32 offset | data
```

`crc` is CRC-16/MODBUS over `data` (reflected polynomial `0xA001`, init `0xFFFF`).

**Ultimate BT / 2.4G, length first, no CRC:**

```
request  : 81 | n | 04 | u16 cmd | u16 sub | u32 len | u32 total | u32 offset | data   (n = 17 + len)
response : 02 04 | u16 4 | u16 cmd | u32 len | u32 total | u32 offset | data
```

**Fixed short queries:**

```
81 05 00 21 01        version + edition       -> 02 22 | u16 fw*100 | u8 beta | ...
81 04 00 01 00        device info (= getRR)   -> 02 04 | ... | [18:20] fw*100, [20] beta, [22:24] PID
81 05 c1 00           PID                     -> 02 05 | ... | [4]=0xc1 | ... | [22:24] PID
81 05 08 00           current mode             -> 02 05 | [18] = 0/1
81 05 00 51 02        back to Xbox mode
81 05 01 36           calibration start
81 05 00 38           calibration end
81 05 02 36           read calibration state
```

Raw extract from the managed app (`AdvanceSuper.Hid/HIDManage.cs`):

```csharp
getRR_CMD               = 81 04 00 01 00 ...
getControllerVersion_CMD= 81 04 21 01 00 00 06 ...
getPID_CMD              = 81 05 c1 00 ...
getmode_CMD             = 81 04 05 01 ...
getmode_CMD1            = 81 05 08 00 ...
getSuperButton          = 81 05 21 00 ...
getUltimate2Color       = 81 05 00 21 01 ...
getPro3USBColor_CMD     = 81 04 0b 00 00 00 20 00 00 00 20 00 ...
Start_CMD               = 81 05 01 36 ...
End_CMD                 = 81 05 00 38 ...
```

## 3. Configuration record commands

| cmd | sub | Effect | Reply |
|---|---|---|---|
| `0x0001` | none | device info (`u16 fw*100`, `u8 beta`, `u16 pid`) | data |
| `0x0002` | 0 | read `len` bytes of the record at `offset` (`total` = record size) | the bytes |
| `0x0001` | 0 | write `data` at `offset` | header echo |
| `0x0006` | `0x123` | commit to flash (about 3 s) | header echo |
| `0x0007` | 0/1 | stop/restart input reports around writes | echo |

The software writes **one setting at a time** (the bytes of that section, without
recomputing the global CRC), then sends the commit.

## 4. Configuration record (Ultimate family)

Size varies by model (1592 bytes for the Ultimate 2, 1652 for BT/2.4G, **to be
measured for the 3-mode**). Common structure, offsets from the start:

| Offset | Size | Field |
|---|---|---|
| `0 + 4s` | 4 | slot flag: `0x20200911` enabled, `0x20190000` disabled, `0` deleted, `0xffffffff` erased |
| 12 | 4 | `crc_value` |
| 16 | 2 | `gamepad_mode`: 0 Switch, 1 Android/DInput, 3 Windows/XInput |
| 18 | 2 | `cur_slot`: active profile |
| `20 + 32s` | 32 | profile name, UTF-16 (BE or LE depending on model) |
| `116 + 12s` | 12 | rumble: flag, left `float`, right `float` |
| `152 + 8s` | 8 | **stick deadzone**: flag, left start/end, right start/end (0..128) |
| `176 + 8s` | 8 | **trigger deadzone**: flag, LT start/end, RT start/end (0..255) |
| `200 + 8s` | 8 | "special" bits (inversions, swap sticks/triggers, trigger rumble) |
| `224 + 92s` | 92 | **button mapping**: flag, 22 x u32 function codes |
| `500 + 216s` | 216 | macros: flag, count, 4 x 52 bytes |
| `1148 + 8s` | 8 | trigger rumble range |
| `1172 + 12s` | 12 | six-axis: flag, activation button, mode, sensitivity, dead compensation |
| `1208 + 12s` | 12 | dynamic LED |
| `1244 + 16s` | 16 | hotwheel LED |
| `1292 + 100s` | 100 | custom LED (24 colours) |

Each section carries its own `0x20200911` flag, which is what allows changing a
single setting without rewriting the whole record.

## 5. Measurements on the 3-mode (2dc8:2030)

### The Xbox 360 knock is ignored

The sequence `01 03 02 / 02 08 03 / 01 03 06 / rumble...` was sent:

| Target | Effect |
|---|---|
| 2.4G dock (5-1.1) | bus disconnect, back as `2030` after replug |
| wired pad (5-1.2) | **no effect**, the pad stays on the bus |

Conclusion: this pad does not speak the Xbox 360 protocol, it speaks **GIP**.

### The pad speaks GIP (confirmed)

`05 20 01 01 00` (`GIP_CMD_POWER`, mode ON) starts the stream:

```
<- INPUT    opt=0x00 seq=12 len=32  (pad state, 32 bytes)
<- STATUS   opt=0x20 seq=15 len=4  96 00 00 00
```

`04 20 02 00` (`GIP_CMD_IDENTIFY`) returns 58 bytes. However `GIP_CMD_HID_REPORT`
(`0x0b`) stays **silent**, even when splitting a 64 byte report following the
`xone` chunking rules (58 bytes max, `ACK|CHUNK_START|CHUNK` flags). The commands
tested (`0x04 0x05 0x09 0x0a 0x0b 0x0c 0x1e 0x30 0x40 0x50`) return nothing.

### The configuration channel is not over USB

The 8BitDo Android app configures this family ("Three/Gamesir", BLE `81HB-X/D/W`)
**over BLE only**; the USB cable only provides power. Same `0x04 / cmd / sub / chunk
/ crc / total / offset` protocol, without the HID encapsulation:

```
BLE request  : 04 | u16 cmd | u16 sub | u16 len | u16 crc | u32 total | u32 offset | data
BLE response : 04 | 00 | u16 cmd | u16 len | u16 crc | u32 total | u32 offset | data
```

GATT discovery: service `00010203-0405-0607-0809-0A0B0C0D1910`, characteristic
`00010203-0405-0607-0809-0A0B0C0D2B11`, MTU negotiated at 67.

### Third path: the D mode

The pad has an `X / D / S` selector on the back. In D mode the other Ultimate models
expose a **HID configuration channel** (`2dc8:3012`, report `0x81` out / `0x02` in).
That would be the simplest path if the 3-mode behaves the same, to be measured.

## 6. Still to determine

- Descriptors and PID in D mode.
- Record size and offsets (1652 expected?), deadzone / mapping / profile fields.
- The GIP message used by *Ultimate Software X* (only if the D and BLE paths fail).

## 7. The real configuration channel: GIP `0x13` (832 bytes)

Decisive find through the community project
[`AriesAlex/8bitdo-gyro`](https://github.com/AriesAlex/8bitdo-gyro) (Rust/Tauri,
targeting exactly this controller): configuration does **not** go through BLE in
Xbox/PC mode, it goes through **GIP**, with a 64 byte report as payload.

### Format

```
GIP payload (60 bytes):
  04 | u16 cmd | u16 sub | u16 len | u16 crc | u32 total | u32 offset | data

GIP frame    : [0x13][options][seq][len=60] + payload
GIP response : [0x12][options][seq][len]    + 04 00 | u16 cmd | u16 len | u16 crc
                                              | u32 total | u32 offset | data
```

- `total` is **832** (`0x340`) over GIP; in HID mode the app sends `total = len`.
- Read: `cmd 2`. Write: `cmd 1` (stage) then **`cmd 6 sub 0`** (apply to the input
  processor, the command we were missing).
- Session: `cmd 7 sub 0` to open, `cmd 7 sub 1` to close.

Verified on hardware: `cmd 7 sub 0` returns `12 00 ... 04 00 07 00 ...`;
`cmd 2` returns `04 00 02 00 20 00 00 00 40 03 00 00 00 00 00 00 <data>`.

### Record: 832 bytes, 3 profiles of 276

The community tool gives `CONFIG_SIZE = 0x340` and `motion_offset(i) = 0x10C +
i*0x114` (blocks of 276, consistent with `get3Xbox_Write*` in the Android library).
Layout found in the Android app (`S_Ultimate3XboxAdvance`):

| Section | Offset (profile relative) |
|---|---|
| name | `+0x08` |
| mapping | `+0x2C` (stride 8 in the Android library) |
| stick deadzone | `+0xDC` |
| triggers | `+0xF3` |
| vibration | `+0xFB` |
| special | `+0x104` |
| gyroscope / motion | `+0x108` (`0x10C` with a 4 byte base) |

### Test status

| Operation | Result |
|---|---|
| read the record over GIP | yes (832 bytes, header `crc16 + 0xFF + mode` read back) |
| `cmd 1` then `cmd 6 sub 0` | acknowledged (`12 00 ... 04 00 01 00 ...` then `04 00 06 00`) |
| persistence of a test write | no, the value read back stays `0xFF` |

The write is accepted but not kept: most likely the "configuration mode" message
that the Windows driver (`XboxGIP_Admin`) sends before opening the session
(`00 0F 00 00 00 00 FF 00 EB`) is missing, and that message has no obvious wire
equivalent.

## 8. Full profile plus `cmd 6 sub 0`, still nothing

Final test on the GIP channel: full record read (532 bytes served, the read stops
there even when announcing `total = 832`), profile rebuilt for **all three** blocks
(flag `0x20200911`, 20 mapping codes, calibration, deadzone `LS 0->66`, triggers),
written in 26 chunks of 32 bytes, then **`cmd 6 sub 0`** (the apply command from the
community project) and `sub 0x67`.

After a power cycle: `BTN_SOUTH` for A, stick at +/-32768. No effect.

Conclusion: on this model neither BLE nor the GIP `0x13` channel makes a
configuration apply to the XInput path. Reads work, writes are acknowledged, the
apply does nothing.

## 9. Upstream issue

The work was shared with the author of the only project targeting this family:
<https://github.com/AriesAlex/8bitdo-gyro/issues/1>

Question asked: the "configuration mode" message his Windows driver sends before
opening the session (`00 0F 00 00 00 00 FF 00 EB`) has no identified wire
equivalent, and the record served by our pad is 532 bytes, not 832.

## 10. Windows VM (reproducible)

Set up to observe the official software:

```bash
docker run -d --name win \
  --device=/dev/kvm --device=/dev/net/tun --device=/dev/bus/usb --cap-add NET_ADMIN \
  -p 8006:8006 \
  -e VERSION=11 -e RAM_SIZE=6G -e CPU_CORES=4 -e DISK_SIZE=40G \
  -e ARGUMENTS="-device usb-host,vendorid=0x2dc8,productid=0x2030" \
  -v ~/vms/windows:/storage -v ~/vms/shared:/shared \
  --stop-timeout 120 dockurr/windows
```

Windows installs itself, the UI is on <http://localhost:8006>, the shared folder
shows up as drive `Z:`.

**Blocker**: the USB passthrough fails because the pad **re-enumerates as soon as a
process opens its interface** (`libusb_release_interface: -4 [NO_DEVICE]`), so QEMU
loses the handle. Options: pass the whole PCI controller, a different USB port, or
an intermediate hub.

## 11. Full GIP write: it persists, but it does not apply

The GIP `0x13` channel accepts a write of **532 bytes** (not 832): 17 chunks of 32
bytes, then `cmd 6 sub 0`, then closing the session with `cmd 7 sub 1`. Reading back
after a power cycle confirms that **everything is kept in flash**:

```
0x000  89 c9 ff 02        recomputed CRC + mode
0x008  4c 00 49 00 ...    profile name "LINUX" (UTF-16LE)
0x004  11 09 20 20        profile flag 0x20200911
0x02c  00 10 00 00        mapping[0] = 0x1000 (A -> B)
0x094  00 64 00 64        stick deadzone = 100
0x0ae  55 aa              block marker
```

Measured result after a reboot: `BTN_SOUTH` for A, stick at +/-32768.

Variants tried without effect: 532 and 832 byte writes, `cmd 6 sub 0`, `sub 0x67`,
`sub 0x15`, `sub 0x123`, session closed with `cmd 7 sub 1`, markers `55 aa` /
`55 cc` / absent, profile name present or not, over BLE and over GIP, on the 2.4G
dock and wired.

**Conclusion**: on this firmware (2.00), software written profiles are stored
faithfully but never applied to the XInput path. The only links that could not be
measured are Bluetooth/DirectInput (BlueZ refuses to create the pad,
`input-hog profile accept failed`) and Tournament mode (`0x2051`, out of reach
without the Windows driver configuration message).

The real configuration therefore goes through the Windows software, and the VM was
blocked on USB passthrough (the pad re-enumerates on open, QEMU loses the handle).
Option: pass the whole PCI USB controller instead of the device.

## 12. Unblocking the VM: PCI controller passthrough

Device passthrough alone fails (the pad re-enumerates on open and QEMU loses the
handle). The clean solution is to hand the VM **the whole PCI controller**.

Survey of this machine:

| Item | Value |
|---|---|
| Bus 5 controller (the pad) | `0000:c8:00.3` (`1022:15c0`) |
| IOMMU group | **29**, containing only that controller |
| What it carries | pad, VIA hub, Terminus hub, billboard, microSD reader |
| Keyboard / mouse / Bluetooth | `0000:c6:00.3`, **not affected** |

`vfio-pci` only exists for kernels **7.3.0-3** and **6.18.55-lts**
(`/lib/modules/7.2.9-2-cachyos` is missing). A reboot on 7.3.0-3 is therefore
required, and it also unblocks `usbmon`, which is useful for captures.

```bash
sudo ./scripts/usb-passthrough.sh on     # controller -> vfio
docker run -d --name win \
  --device=/dev/kvm --device=/dev/net/tun --cap-add NET_ADMIN \
  --device=/dev/vfio/vfio --device=/dev/vfio/29 \
  -p 8006:8006 \
  -e VERSION=11 -e RAM_SIZE=6G -e CPU_CORES=4 -e DISK_SIZE=40G \
  -e ARGUMENTS="-device vfio-pci,host=0000:c8:00.3" \
  -v ~/vms/windows:/storage -v ~/vms/shared:/shared \
  --stop-timeout 120 dockurr/windows

sudo ./scripts/usb-passthrough.sh off    # give it back to the host afterwards
```

In Windows: `Z:\8bitdo-gyro.exe`, right click, Run as administrator.

## 13. Ultimate Software X works in the VM (PCI passthrough)

Device passthrough blocker worked around by passing **the whole PCI controller**
(`0000:c8:00.3`, IOMMU group 29, only the pad and a hub behind it):

```bash
sudo ./scripts/usb-passthrough.sh on
docker run -d --name win \
  --device=/dev/kvm --device=/dev/net/tun --cap-add NET_ADMIN \
  --device=/dev/vfio/vfio --device=/dev/vfio/29 --ulimit memlock=-1:-1 \
  -p 8006:8006 -e VERSION=11 -e RAM_SIZE=4G -e CPU_CORES=4 \
  -e ARGUMENTS="-device vfio-pci,host=0000:c8:00.3" \
  -v ~/vms/windows:/storage -v ~/vms/shared:/shared \
  --stop-timeout 120 dockurr/windows
```

Without `--ulimit memlock=-1:-1`, QEMU fails with
`vfio_container_dma_map(... ) = -12 (Cannot allocate memory)`.

Result inside Windows:

```
USB\VID_2DC8&PID_2030   Xbox Gaming Device   (class XboxComposite)
```

**Ultimate Software X** (fetched from the Store, sideloaded with its dependencies)
starts, **detects the pad** and shows the right model with its Profile / Mapping /
Sticks / Triggers / Vibration / Update tabs.

The community `8bitdo-gyro` tool, on the other hand, stays blocked: its access to
`\\.\XboxGIP_Admin` returns access denied even at High integrity, and its README
admits that this GIP path has never been verified on hardware.

Driving the VM from the host: `vncdo -s 172.17.0.4::5900 capture|key|type` (QEMU's
VNC server is reachable on the Docker network).

Next step: make the app write a setting, hand the controller back to the host
(`usb-passthrough.sh off`) and read the record again to derive the exact format.

## 14. Verdict: the official software does not write into that record

Test protocol, with the official app in the VM and the pad passed through over PCI:

1. read the 532 bytes of the record over GIP;
2. in *Ultimate Software X*, map **P1 to A** (the change shows in the UI, the app
   displays "A" on the selector);
3. close the app, hand the pad back to the host, read again.

Result: **no difference** at all, neither in the flags, nor in the mapping, nor in
the CRC. The record is identical byte for byte.

Previous test, same finding: ticking "Disable Deadzone" only changed six bytes (CRC
plus `55 bb` markers), without touching the sections.

**Conclusion**: the configuration applied by the official software does not travel
through the record exposed over GIP (nor presumably over BLE, which serves the same
buffer). It goes through a private channel of the Xbox GIP driver, the very one the
community tool cannot open (`\\.\XboxGIP_Admin`, access denied).

What this settles for good: on this model, neither BLE nor the 532 byte GIP record
carries the XInput configuration. Every conforming write we could do is therefore
stored without effect, and that was not a mistake on our side.

Remaining lead, if anyone wants to pick it up: capture USB traffic **inside Windows**
(USBPcap) while the official app applies a setting, to see the real frames. That is
the only missing observation.

## 15. USBPcap in the VM: environment limit

Silent install of USBPcap 1.5.4.0 (`/S`, exit 0, `USBPcapCMD.exe` present), then `-I`
(non standard HWID init, required for USB 3.0). After rebooting the VM,
`USBPcapCMD -d \\.\USBPcapN` returns `Couldn't open device - 2` for N = 1..4: the
filter driver does not attach to the xHCI controller as QEMU exposes it (vfio-pci on
`0000:c8:00.3`).

Conclusion: capturing the private channel of the Xbox GIP driver **inside this VM**
is not possible as is. It would need a native Windows host.

## 16. What the VM gives us anyway

The official **Ultimate Software X** works in the VM, detects the pad
(`USB\VID_2DC8&PID_2030`, class `XboxComposite`) and lets you set profiles, mapping,
sticks, triggers, vibration and update the firmware.

So it is, as of today, **the way to configure this pad from a Linux machine**: a
Windows VM with PCI passthrough of the USB controller. It is not a native tool, but
it is reproducible and documented (sections 12 and 13).
