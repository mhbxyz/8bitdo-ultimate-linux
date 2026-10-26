# Configuration protocol, 8BitDo Ultimate 3-mode (BLE)

Everything below was **measured on hardware** (firmware 2.00, pad `2dc8:2030`, BLE
identity `81HB-D` / `81HB-X`), not merely inferred from the binaries.

## 1. Why BLE and not USB

| Interface | Finding |
|---|---|
| USB `2dc8:2030` (XGIP `ff/47/d0`) | the pad **speaks GIP**: `05 20 01 01 00` starts the `INPUT`/`STATUS` stream, `04 20 02 00` answers an identify. But `GIP_CMD_HID_REPORT` (0x0b) stays silent, even with `xone` chunking. No configuration channel. |
| "Xbox 360" knock (`01 03 02` + rumble) | ignored when wired; on the dock it causes a disconnect without a mode change |
| BLE `81HB-*` | yes: service `00010203-...-1910`, characteristic `...-2B11`, notifications |

The USB cable only provides power; the official Android app also configures
**over BLE only**.

The pad advertises two BLE identities:

- `81HB-D` / `81HB-X`, the one carrying the configuration service;
- `8BitDo Ultimate 3mode Xbox`, a "gamepad" HID identity, **without** the config
  characteristic.

## 2. Frame

```
request  : 04 | u16 cmd | u16 sub | u16 len | u16 crc | u32 total | u32 offset | data
response : 04 | 00      | u16 cmd | u16 len | u16 crc | u32 total | u32 offset | data
```

- request header: 17 bytes, response header: 16 bytes (the `sub` field disappears,
  a `00` byte is inserted after the type);
- replies are sometimes **fragmented** over several notifications, and sometimes
  shorter than 45 bytes (end of area), so reassemble before parsing;
- a connected peripheral stops advertising: always `disconnect` before scanning.

| cmd | sub | Effect |
|---|---|---|
| `0x0002` | 0 | read `len` bytes of the record at `offset` (`total` = record size) |
| `0x0001` | 0 | write `data` at `offset` |
| `0x0006` | **`0x67`** | commit to flash, verified on hardware (see section 7) |
| `0x0006` | `0x15` / `0x123` | sub-codes used by other generations |
| `0x0007` | 0 | `report_state` (not needed here) |

## 3. Record: 532 bytes

**Not 1652**: the 3-mode has neither turbo nor macro (official FAQ), so the 1176
byte macro section of the Ultimate 2 does not exist. The structure is 500 bytes,
followed by 28 bytes of undecoded sections: 4 + 500 + 28 = 532.

```
0x000  2   CRC-16/KERMIT over record[2:532], little-endian, recomputed by the pad
0x002  1   reserved (0xFF)
0x003  1   record id: 0x03 in D mode, 0x02 in X/PC mode
0x004  ..  configuration structure (Ultimate family, without macros)
```

Offsets **inside the structure** (add `0x004` for the raw record):

| Offset | Size | Field |
|---|---|---|
| `0x000` | 12 | flags of the 3 profiles: `0x20200911` enabled, `0x20190000` disabled, `0xffffffff` erased |
| `0x00C` | 4 | `crc_value` (not checked by the firmware) |
| `0x010` | 2 | `gamepad_mode` (1 in D mode, 3 in X mode per the family) |
| `0x012` | 2 | `cur_slot` (active profile, 0..2) |
| `0x014` | 96 | names, 3 x 32 bytes UTF-16LE |
| `0x074` | 36 | rumble, 3 x (flag u32, left float, right float) |
| `0x098` | 24 | **stick deadzone**, 3 x (flag, LS start/end, RS start/end, 0..128) |
| `0x0B0` | 24 | **trigger deadzone**, 3 x (flag, LT start/end, RT start/end, 0..255) |
| `0x0C8` | 24 | options, 3 x (flag, bits): inversions, swap sticks/triggers, trigger rumble |
| `0x0E0` | 276 | **mapping**, 3 x (flag + 22 x u32 function codes) |
| `0x1F4` | 28 | additional sections (gyro/LED), undecoded |

### Function codes (mapping)

Button order:

```
A B X Y LB RB LT RT L3 R3 Select Start Star Home Up Down Left Right P1 P2 P3 P4
```

| Code | Function | Code | Function |
|---|---|---|---|
| `0x1` | Start | `0x400` | LB |
| `0x2` | L3 | `0x800` | RB |
| `0x4` | R3 | `0x1000` | B |
| `0x8` | Select | `0x2000` | A |
| `0x10` | X | `0x4000` | LT |
| `0x20` | Y | `0x8000` | RT |
| `0x40` | Right | `0x10000` | Menu |
| `0x80` | Left | `0x20000` | Home |
| `0x100` | Down | `0x2000000` | P1 |
| `0x200` | Up | `0x4000000` | P2 |
| `0` | disabled | `0xFFFFFFFF` | erased |

## 4. Checks performed

- write then read a `00 01 02 ... 2c` pattern at offset 0: read back identically;
- write a `TEST` name at `0x018`: read back `54 00 45 00 53 00 54 00`;
- create profile 0 (`flags = 0x20200911`, `mode = 1`, `cur_slot = 0`, name): kept
  after the commit;
- CRC recomputed by the pad **identical** to ours (`0x5258`, then `0x986d` after
  adding the deadzones), so the layout and the algorithm are confirmed;
- byte `record[3]` (record id) is rewritten by the pad if you try to change it.

## 5. Known limit: the PC record commit does not persist

Measurements on the **PC/Windows** record (`81HB-W`, `record id 1`):

| Action | Result |
|---|---|
| read | yes, 532 consistent bytes, recomputed CRC matches |
| write (45 byte chunks) | acknowledged and read back within the session |
| read back after a BLE reconnect | the change is still there |
| read back after **power off/on** | back to the original state (`0xc323`) |

Attempts that did not help: `commit sub 0x15`, `commit sub 0x123`, both in a row,
`report_state 0/1` around the write, a 3 s wait before disconnecting, with and
without the dock plugged in (2.4G link active or not).

Conversely, on the **D/Bluetooth** record (`record id 3`), a `commit sub 0x15` did
survive a power cycle, so the flash write path does exist.

Remaining hypotheses:

1. the PC profile is stored or validated on the **dock/2.4G receiver** side, not in
   the pad, and the official software goes through the dock configuration channel;
2. the commit needs a sub-code specific to this mode, not identified yet;
3. a header field of the block (the 28 bytes at `block+0x0C`) must be filled in for
   the profile to be considered valid and written.

Settling this requires a capture of the official software on Windows (VM + USBPcap).

## 6. What the official Android app says

APK retrieved: `8BitDo Ultimate Software V2 Android V2.01`
(`com.bbitdo.advanceandroidv2`), decompiled with jadx; `libadvancelib.so` is not
stripped, which gives the JNI symbols and the protocol constants.

### Our pad in the app

`utils/BLEUtils.java` recognises the names `81HB-X`, `81HB-D`, `81HB-W` and maps
them to service `...1910` / characteristic `...2B11`, exactly the channel we use.
On the model side they are filed under the **"Three"** family, which takes the
generic "Ultimate Wired" path (20 buttons: A B X Y LB RB LT RT L3 R3 Select Start
Share/Logo plus the d-pad and P1/P2), not the `Ultimate3Xbox` class.

### Protocol constants extracted from the native library

```
read channel : offset 0, length 832 (0x340), cmd 2
write channel: offset 0, length 832, cmd 1
CRC          : ANSI_CRC_16_sh(record, 0x364)
```

The `get3Xbox_Write*` functions describe a record of **276 bytes per profile**
(`0x114`), with:

| Section | Offset in the block | Size |
|---|---|---|
| name | `+0x08` | 32 |
| mapping | `+0x2C` | 4 bytes per entry, stride 8 |
| sticks | `+0xDC` | 23 |
| triggers | `+0xF3` | 8 |
| vibration | `+0xFB` | 9 |
| special | `+0x104` | 8 |

That is 3 x 276 + 4 = **832 bytes**, to compare with the **532 bytes** the pad
actually serves on characteristic `2B11`, whatever `total` is requested (tested
532, 832, 868, 1652: the read always stops at `offset 532`, and beyond that the pad
stops answering).

### Open point

Two layouts coexist: the software one (blocks of 276, mapping with stride 8, 832
bytes) and the one observed on the pad (blocks of 176 ending with `55 AA`, mapping
with stride 4, 532 bytes). The second is a consistent subset (the 3 profiles and
the sticks/triggers/options sections are there), but writing into it does not
survive a power cycle in PC mode.

Logical next step: identify the **internal PID** the pad reports to the app
(version command) to know which class it is really handled by, then replay the exact
`write3ECustomConfig` / `write3XboxCustomConfig` frame (with its `total` of 832) on
characteristic `2B11`.

## 7. Solving the commit: `sub 0x67`

The save sub-code was found in `libadvancelib.so`, function
`getSaveCustomConfigChannel`, which builds the command:

```
cmd = 0x0006, sub = 0x0067, offset = 0, length = 0
```

Tested on the pad in PC mode: after a full `write` then `commit sub 0x67`, the
record **survives a power cycle** (CRC `0xc781` kept, `a->b` still present). The
`0x15` and `0x123` sub-codes only changed the RAM copy.

What remains: the mapping written at `block+0x2C` is persisted but **does not act**
on XInput reports. The native path of the "Three" model is still to be identified
(the `Ultimate3Xbox` one writes 8 byte entries at `+0x2C`, while the observed 532
byte record spaces them by 4 bytes).

## 8. `cur_slot` and the application limit in PC mode

`S_Ultimate3XboxAdvance_setCurslot` writes into **`record[3]`**: the byte I took
for a "record id" is actually the **active profile**. Observed values: `1` in PC/W
mode, `2` in Xbox mode, `3` in D mode.

The pad **refuses** to let it change: write `0`, read back `1` after the commit. It
keeps control of that field.

Application test, with `stick deadzone = 100/128` written in turn:

| Block written | Measured left stick amplitude |
|---|---|
| block 0 | +/-32768 (full range) |
| block 1 (= `cur_slot`) | +/-32768 (full range) |

Conclusion: the record reachable on characteristic `2B11` (532 bytes, 176 byte
blocks) **is not the one the firmware applies to the XInput/2.4G path**. Writes
there are persisted (commit `0x67`) but have no effect on gamepad reports.

Consistent with section 6: the official software manipulates an **832 byte**
record (276 byte blocks) that the pad does not serve on this channel in the modes
tested.

Next lead: find how the app reaches that 832 byte record, either a distinct
configuration channel/mode (triggered by a command, like the "knock" of other
models), or a prior negotiation on `2B11`.

## 9. Conclusion on applying settings

Final test, with the complete official software sequence reproduced (116 byte
header read, whole record written, `commit 0x67`, power cycle) and
`stick deadzone = 100/128`:

| Attempt | Left stick amplitude |
|---|---|
| block 0, commit `0x15` | +/-32768 |
| block 1 (= `cur_slot`), commit `0x67` | +/-32768 |
| after header read + commit `0x67` | +/-32768 |

The firmware **does not apply** this record to the XInput/2.4G path: writes are
persisted in flash (verified after a power cycle) but have no effect on gamepad
reports.

Summary: the BLE `2B11` channel is a working configuration channel (read, write,
save), but it does not carry the configuration the pad uses in XInput mode. The
official software manipulates an 832 byte record that this channel does not serve.

The record was restored to its factory state (CRC `0xc323`, full deadzone, default
remaps) at the end of the tests.

## 10. iOS app as an oracle, and verdict

The official iOS app *Ultimate Software* (V2 refuses to pair with this model)
connects in **Bluetooth mode** (`81HB-D`) and configures the pad. It served as an
oracle: one single setting changed (left stick deadzone = 50), then the dumps were
compared with `tools/record-diff.py`.

### What the app writes, our layout was right

| Byte changed | Content |
|---|---|
| `0x000` | header CRC (recomputed) |
| `block+0x00` | profile flag `0x20200911` |
| `block+0x28` | mapping section flag |
| `block+0x2C..0x7B` | 20 function codes, **4 bytes each** |
| `block+0x7C` | calibration flag, then 4 floats |
| `block+0x90` / `+0x94` | deadzone: `00 42 00 80`, **LS 0->66** (the app maps 50 to 66) |
| `block+0x98` / `+0x9C` | triggers `00 ff 00 ff` |
| `block+0xA0` / `+0xA4` | options |
| `block+0xAE` | marker `55 cc` instead of the factory `55 aa` |

### Verdict

A profile **cloned byte for byte** from the app output (marker `55 cc` included),
written into the PC record and committed, **still does not apply**: the stick goes
to +/-32768.

So the BLE `2B11` channel is a real configuration channel (the app uses it), but the
record it exposes in PC mode is not the one the firmware applies to the XInput/2.4G
path. Remaining lead: the XInput configuration is probably held by the **dock** and
pushed into the pad when the 2.4G link is established, which would explain why no
write, even a valid one, survives the reconnection.

## 11. Decisive test: the official application itself

The iOS app connected **in PC mode** (selector on "PC") changes two settings: left
stick deadzone = 50 and A -> B.

Diff of the records dumped before and after (`tools/record-diff.py`):

```
0x000..0x001  header CRC                     0xc323 -> 0x9f4b
0x031         block 0 +0x2d  mapping A -> B  0x20   -> 0x10
0x099         block 0 +0x95  deadzone LS end 0x80   -> 0x42  (66)
```

Two **partial** writes, block markers untouched (`55 aa`).

After power off/on:

| Check | Result |
|---|---|
| record kept | yes, CRC `0x9f4b`, deadzone `0->66`, `a->b` |
| A pressed on the pad | no, still `BTN_SOUTH` (A) |
| left stick pushed to the stop | no, +/-32768, deadzone not applied |

**Conclusion**: even the official software does not change XInput behaviour through
this channel. The record exposed on `2B11` therefore describes the **Bluetooth**
link profile, not the 2.4G/dock one, which explains in one go why none of our
writes, however conforming, ever had an effect on the pad used through the dock.

Corollary: the BLE channel does what it says (read, partial write, save) and our
tooling is correct; it is simply the wrong profile that is editable from Linux.

## 12. Wired test: the dock is cleared

Selector on **Xbox** plus a USB-C cable makes the pad appear as `2dc8:2030` (wired
mode). The pad is still reachable over BLE as `81HB-X`, which allowed writing a
configuration and then measuring it on its wired `evdev` node.

Configuration written into **all three profiles** of the Xbox record (deadzone
`LS 0->66`, mapping `A->B`), commit `0x67`, in flash (CRC `0x3796`), then unplug and
replug.

Result: `BTN_SOUTH` for A, stick at +/-32768. **No effect.**

| Link tested | Configuration stored | Applied |
|---|---|---|
| 2.4G dock (PC mode) | yes | no |
| wired USB (Xbox mode) | yes | no |
| written by the official app (PC mode) | yes | no |

The dock is therefore cleared: the same silence is observed when wired. Three
links, three failures, including when the official software does the writing.

`setConfigState` (`cmd 0x11`) exists in the library but is only used for the
`UT2`/`lashen` models, not this one.

Final state: records wiped, pad back to its factory behaviour.
