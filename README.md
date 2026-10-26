# ultim8do — 8BitDo Ultimate 3-mode Controller sous Linux

Configuration de la manette **8BitDo Ultimate 3-mode Controller for Xbox**
(`2dc8:2030`) depuis Linux : profils, deadzones sticks/triggers, remapping des
boutons, options — sans passer par *Ultimate Software X* (UWP Windows).

## Comment ça marche

La manette n'expose **aucun canal de configuration en USB**. Elle parle GIP sur son
interface XGIP (`ff/47/d0`), refuse les trames « Xbox 360 » des autres Ultimate, et
ignore `GIP_CMD_HID_REPORT`. En revanche, son identité Bluetooth `81HB-*` expose un
service GATT de configuration, et c'est par là que passe l'app Android officielle.

```
BLE service 00010203-0405-0607-0809-0A0B0C0D1910
    char    00010203-0405-0607-0809-0A0B0C0D2B11   (write + notify)

requête : 04 | u16 cmd | u16 sub | u16 len | u16 crc | u32 total | u32 offset | data
réponse : 04 | 00      | u16 cmd | u16 len | u16 crc | u32 total | u32 offset | data
```

Record de configuration : **532 octets**, en-tête CRC-16/KERMIT sur `record[2:]`,
puis la structure de la famille Ultimate (sans macros), avec 3 profils.

Détails complets, mesures et preuves : [`docs/03-protocole-ble.md`](docs/03-protocole-ble.md).

## Mise en route

Côté manette : sélecteur sur la position **Bluetooth** (le premier symbole), puis
**X + Start 3 s** pour l'appairage. La manette annonce alors `81HB-D`.

```bash
uv sync
sudo ./scripts/setup-permissions.sh     # udev (accès USB/hidraw) + usbmon

uv run ultim8do dump                    # lit et affiche le record
```

## Utilisation

```bash
uv run ultim8do dump --json --save capture/record.bin
uv run ultim8do set --slot 0 --name SALON
uv run ultim8do set --slot 0 --stick-deadzone 12 --trigger-deadzone 8
uv run ultim8do set --slot 0 --map a=b --map b=a
uv run ultim8do profile 1
```

`set` écrit par tranches de 45 octets, envoie le commit (`cmd 6 sub 0x15`) puis
relit le record pour vérifier.

Codes de fonction disponibles : `none start l3 r3 select x y right left down up
lb rb b a lt rt menu home p1 p2 p3 p4`.

## État

| Phase | État |
|---|---|
| 1. Identification USB (`lsusb`, descripteurs) | ✅ [`docs/01-device-identification.md`](docs/01-device-identification.md) |
| 2. Capture du trafic | ✅ via BLE (le canal USB n'existe pas sur ce modèle) |
| 3. Comparaison des réglages | ✅ lecture/écriture/commit vérifiés sur matériel |
| 4. REA des binaires 8BitDo | ✅ [`docs/02-protocole.md`](docs/02-protocole.md), [`docs/re/`](docs/re/) |
| 5. Réimplémentation Python | ✅ `src/ultim8do/` (transport BLE, record, CLI) — lecture/écriture/commit fonctionnels, mais le firmware n'applique pas ce record au mode XInput (voir §9 de la doc) |
| 6. Interface Linux native | ⏳ |

Limite connue : le `commit` **persiste en mode Bluetooth/D** (vérifié après cycle
d'alimentation) mais **pas encore en mode PC/W** — voir
[`docs/03-protocole-ble.md`](docs/03-protocole-ble.md#5-limite-connue--le-commit-du-record-pc-ne-persiste-pas).

La configuration est aussi **par mode**. Le record lu en mode Bluetooth
(`record id 3`, `gamepad_mode 1`) est distinct de celui du mode PC/2.4G
(`gamepad_mode 3`) : pour configurer ce dernier, basculer le sélecteur sur « PC »
et relancer les mêmes commandes.

## Outils de diagnostic

```bash
./tools/dump-device.sh          # état USB : descripteurs, interfaces, hidraw
./tools/usbwatch.sh             # surveille les (re)énumérations 2dc8:*
uv run tools/gip-probe.py listen   # parle GIP : power-on, identify, dump des trames
uv run tools/ble-probe.py scan     # scanne les manettes 81HB-*
```

## Tests

```bash
uv run pytest -q
```
