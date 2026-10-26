# ultim8do — 8BitDo Ultimate 3-mode Controller sous Linux

Objectif : comprendre et reproduire le protocole de configuration de la manette
**8BitDo Ultimate 3-mode Controller for Xbox** (`2dc8:2030`) pour pouvoir régler
deadzones, boutons et profils depuis Linux, sans passer par *Ultimate Software X*
(application UWP Microsoft Store, Windows uniquement).

## État des lieux

| Phase | État | Détail |
|---|---|---|
| 1. Identification (`lsusb`, descripteurs) | ✅ | [`docs/01-device-identification.md`](docs/01-device-identification.md) — XGIP `ff/47/d0`, 2 interfaces, 64 o interrupt |
| 2. Capture du trafic officiel | ⏳ | dépend du basculement en mode config (voir plus bas) |
| 3. Comparaison des captures | ⏳ | nécessite la phase 2 |
| 4. REA des binaires 8BitDo | 🟡 | exports de `8BitDoAdvance.dll`, trames protocolaires extraites, cf. [`docs/02-protocole.md`](docs/02-protocole.md) |
| 5. Réimplémentation Python | 🟡 | `src/ultim8do/` : transport GIP + jeu de trames |
| 6. Interface Linux native | ⏳ | |

## Installation

```bash
uv sync
sudo ./scripts/setup-permissions.sh     # règle udev (uaccess) + usbmon
```

Sans la règle udev, tout accès à `/dev/bus/usb/...` exige `sudo`.

## Outils

```bash
./tools/dump-device.sh          # lsusb, sysfs, descripteurs, nœuds hidraw/input
./tools/usbwatch.sh             # surveille les (re)énumérations 2dc8:*
uv run tools/mode-switch.py     # bascule la manette en mode configuration
```

## Le point clé : le « knock »

Les manettes Ultimate ne parlent pas de protocole de configuration tant qu'elles sont
en mode Xbox/GIP. Le logiciel officiel les fait **ré-énumérer** en mode configuration
en leur envoyant une séquence d'initialisation Xbox suivie d'une rafale de *rumble* sur
l'endpoint interrupt OUT, puis envoie ses trames `0x81` sur le canal HID ainsi exposé.

```
01 03 02                            init LED Xbox
02 08 03                            init contrôleur
01 03 02                            init LED Xbox
01 03 06                            déclencheur du mode config
00 08 00 01 00 00 00 00             rumble moteur gauche
00 08 00 00 01 00 00 00             rumble moteur droit
00 08 00 01 01 00 00 00             les deux
00 08 00 05 01 00 00 00             fort
00 08 00 00 00 00 00 00             arrêt
```

Après ~1 s la manette se déconnecte et réapparaît avec un autre PID, exposant un
`/dev/hidrawN`. Sur l'Ultimate 2.4G c'est `2dc8:3013` (récepteur) / `2dc8:3012`
(filaire) ; sur l'Ultimate BT, `2dc8:6007`. **Le PID de la 3-mode reste à mesurer.**

## Protocole de configuration (famille Ultimate)

```
requête : 81 | [n] | 04 | u16 cmd | u16 sub | u16 len | u16 crc | u32 total | u32 offset | data
réponse : 02 | 04 | u16 4 | u16 cmd | u16 len | u16 crc | u32 total | u32 offset | data
```

- `cmd 0x0001` : infos appareil (`u16 firmware×100`, `u8 beta`, `u16 pid`)
- `cmd 0x0002` : lecture de `len` octets du record à `offset`
- `cmd 0x0001 sub 0` : écriture, puis `cmd 6 sub 0x123` pour commiter en flash
- requêtes fixes : `81 05 00 21 01` (version), `81 05 00 51 02` (retour en mode Xbox)

Le record de configuration contient des flags par section (`0x20200911` = activé),
les noms de profils (UTF-16), les deadzones sticks/triggers, le mapping boutons et
les réglages LED/macro.

## Sources

- `vendor/README.md` — comment récupérer les binaires officiels (Ultimate Software V2 et X)
- `docs/re/8BitDoAdvance_exports.txt` — 402 exports nommés de la DLL native
- travaux communautaires : `MiguelSanzBr/8bitdo-ultimate2-linux` (protocole Ultimate 2/2.4G/BT),
  `s8n/ultimatecontroller-rs`, `BoredNewCoder/8bitdo-xbox-bridge` (GIP)
