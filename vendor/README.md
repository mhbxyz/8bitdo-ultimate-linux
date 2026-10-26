# Éléments récupérés (binaires officiels 8BitDo)

Ces archives/binaires **ne sont pas versionnés** (voir `.gitignore`) : ce sont des
artefacts propriétaires, uniquement utiles pour le reverse engineering. Ce fichier
documente comment les reproduire.

## Ultimate Software V2 (application Win32, .NET + DLL native)

Page officielle : <https://app.8bitdo.com/Ultimate-Software-V2/>

```bash
cd vendor
curl -LO https://support.8bitdo.com/bd-uploads/files/ultimate_soft/8BitDo_Ultimate_Software_V2_Windows_V1.37.zip
unzip 8BitDo_Ultimate_Software_V2_Windows_V1.37.zip
```

Contenu intéressant :

| Fichier | Rôle |
|---|---|
| `8BitDo Ultimate Software V2.exe` | app managée en *single-file bundle* (.NET), UI WPF |
| `8BitDoAdvance.dll` | **moteur protocole natif x86** : 402 exports nommés (`Open_Hid`, `ReadHid`, `_ReadProfile`, `_WriteMapKey`, `_ANSI_CRC_16_Ultimate2_4`…) |
| `RTKHIDKit.dll` | couche HID bas niveau |
| `GenericHid.pdb`, `8BitDo Ultimate Software V2.pdb` | symboles (noms de méthodes managées) |
| `dfu4.exe` | utilitaire de flash DFU |

Décompilation de la partie managée :

```bash
dotnet tool install -g ilspycmd
ilspycmd --bundle-entry "8BitDo Ultimate Software V2.dll" -p -o /tmp/dec/v2 \
  "8BitDo Ultimate Software V2.exe"
```

## Ultimate Software X (application UWP, pour ce contrôleur)

Fiche Microsoft Store : <https://apps.microsoft.com/detail/9PMC9MN3ZZ85>

Récupération des liens depuis l'API Store (cf. `tools/fetch-store-package.sh`) :

- `WuCategoryId` = `6e30d7e5-607f-47e8-b138-c5e6ad92df6a`
- `..._1.5.0.0_..._up4wwata42ye0.appxbundle` (non chiffré, 62 Mo)
- `..._1.5.0.70_..._up4wwata42ye0.eappxbundle` (chiffré, 72 Mo)

L'`appxbundle` 1.5.0.0 se dézippe normalement :

```
UWPAdvance_1.5.0.0_x64.appx
  ├── UWPAdvance.dll           15 Mo  .NET Native (AOT, x64)
  ├── D4XGaming.Devices.dll   100 Ko  composant WinRT (transport GIP)
  └── D4XGaming.Devices.winmd          métadonnées : SendMessageA / SendMessageId / GetMessageB
```
