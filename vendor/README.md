# Retrieved artifacts (official 8BitDo binaries)

These archives and binaries are **not versioned** (see `.gitignore`): they are
proprietary artifacts, only useful for reverse engineering. This file documents
how to fetch them again.

## Ultimate Software V2 (Win32 app, .NET + native DLL)

Official page: <https://app.8bitdo.com/Ultimate-Software-V2/>

```bash
cd vendor
curl -LO https://support.8bitdo.com/bd-uploads/files/ultimate_soft/8BitDo_Ultimate_Software_V2_Windows_V1.37.zip
unzip 8BitDo_Ultimate_Software_V2_Windows_V1.37.zip
```

Interesting content:

| File | Role |
|---|---|
| `8BitDo Ultimate Software V2.exe` | managed app, .NET single-file bundle, WPF UI |
| `8BitDoAdvance.dll` | **native x86 protocol engine**: 402 named exports (`Open_Hid`, `ReadHid`, `_ReadProfile`, `_WriteMapKey`, `_ANSI_CRC_16_Ultimate2_4`...) |
| `RTKHIDKit.dll` | low level HID layer |
| `GenericHid.pdb`, `8BitDo Ultimate Software V2.pdb` | symbols (managed method names) |
| `dfu4.exe` | DFU flashing utility |

Decompiling the managed part:

```bash
dotnet tool install -g ilspycmd
ilspycmd --bundle-entry "8BitDo Ultimate Software V2.dll" -p -o /tmp/dec/v2 \
  "8BitDo Ultimate Software V2.exe"
```

## Ultimate Software X (UWP app, for this controller)

Microsoft Store entry: <https://apps.microsoft.com/detail/9PMC9MN3ZZ85>

Store links can be fetched through the rg-adguard endpoint (see the issue thread
and `docs/02-protocole.md`):

- `WuCategoryId` = `6e30d7e5-607f-47e8-b138-c5e6ad92df6a`
- `..._1.5.0.0_..._up4wwata42ye0.appxbundle` (not encrypted, 62 MB)
- `..._1.5.0.70_..._up4wwata42ye0.eappxbundle` (encrypted, 72 MB)

The 1.5.0.0 `appxbundle` unpacks normally:

```
UWPAdvance_1.5.0.0_x64.appx
  |-- UWPAdvance.dll           15 MB  .NET Native (AOT, x64)
  |-- D4XGaming.Devices.dll  100 KB  WinRT component (GIP transport)
  `-- D4XGaming.Devices.winmd        metadata: SendMessageA / SendMessageId / GetMessageB
```

## Other artifacts

| File | Source |
|---|---|
| `8BitDo_Ultimate_Software_V2_Android_V2.01.apk` | `https://support.8bitdo.com/bd-uploads/files/ultimate_soft/8BitDo_Ultimate_Software_V2_Android_V2.01.apk` |
| `USBPcapSetup.exe` | <https://github.com/desowin/usbpcap/releases> |
| `8bitdo-gyro.exe` | <https://github.com/AriesAlex/8bitdo-gyro/releases> |
