# Phase 4 — Protocole de configuration (REA)

Sources croisées :

1. décompilation ILSpy de l'app managée *Ultimate Software V2* (`/tmp/dec/v2`) — trames en clair ;
2. exports et chaînes de `8BitDoAdvance.dll` (moteur natif) — cf. `docs/re/8BitDoAdvance_exports.txt` ;
3. travaux communautaires vérifiés sur matériel : `MiguelSanzBr/8bitdo-ultimate2-linux`
   (`docs/PROTOCOL.md`, `ULTIMATE_24G.md`, `ULTIMATE_BT.md`), `s8n/ultimatecontroller-rs`.

## 1. Pourquoi une bascule de mode

En mode Xbox (XGIP `ff/47/d0`), la manette n'expose **aucun canal de configuration** :
deux endpoints interrupt 64 o qui ne transportent que les rapports de manette et les
commandes LED/rumble Xbox. Le logiciel officiel commence donc par la faire
ré-énumérer en « mode configuration », où elle expose une interface HID avec le
rapport de sortie `0x81` et le rapport d'entrée `0x02`.

Suite (identique pour Ultimate BT / 2.4G, à rejouer sur la 3-mode) :

```
01 03 02                      init LED Xbox
02 08 03                      init contrôleur
01 03 02                      init LED Xbox
01 03 06                      déclencheur du mode config
00 08 00 01 00 00 00 00       rumble gauche
00 08 00 00 01 00 00 00       rumble droit
00 08 00 01 01 00 00 00       les deux
00 08 00 05 01 00 00 00       fort
00 08 00 00 00 00 00 00       arrêt
```

≈15 ms entre paquets, envoyés sur l'endpoint interrupt OUT. Environ 1 s après, la
manette se déconnecte et revient avec un autre PID. Pour revenir en Xbox :
débrancher/rebrancher, ou `81 05 00 51 02` si la manette l'accepte.

PIDs connus dans la famille :

| PID | Sens |
|---|---|
| `0x3106` | pad en XInput (filaire ou récepteur) |
| `0x3012` | pad en mode config (filaire, switch sur D, ou après knock) |
| `0x3013` | récepteur 2.4G en mode config |
| `0x6007` | Ultimate BT en mode config |
| `0x6009` … `0x6013` | PID internes rapportés dans les réponses (`getRR`) |
| **`0x2030`** | **Ultimate 3-mode for Xbox, XInput (notre manette)** |

## 2. Trames de la famille Ultimate

Trois variantes de framing circulent selon le modèle. Toutes commencent par
`0x81` (rapport de sortie) et les réponses par `0x02`.

**Ultimate 2 (filaire, canal HID dédié) — avec CRC :**

```
requête : 81 04 | u16 cmd | u16 sub | u16 len | u16 crc | u32 total | u32 offset | data[len ≤ 45]
réponse : 02 04 | u16 4   | u16 cmd | u16 len | u16 crc | u32 total | u32 offset | data
```

`crc` = CRC-16/MODBUS sur `data` (poly réfléchi `0xA001`, init `0xFFFF`).

**Ultimate BT / 2.4G — longueur en tête, pas de CRC :**

```
requête : 81 | n | 04 | u16 cmd | u16 sub | u32 len | u32 total | u32 offset | data   (n = 17 + len)
réponse : 02 04 | u16 4 | u16 cmd | u32 len | u32 total | u32 offset | data
```

**Requêtes courtes fixes :**

```
81 05 00 21 01        version + édition          → 02 22 | u16 fw×100 | u8 beta | ... 
81 04 00 01 00        infos appareil (= getRR)   → 02 04 | ... | [18:20] fw×100, [20] beta, [22:24] PID
81 05 c1 00           PID                        → 02 05 | ... | [4]=0xc1 | ... | [22:24] PID
81 05 08 00           mode courant               → 02 05 | [18] = 0/1
81 05 00 51 02        retour en mode Xbox
81 05 01 36           début calibration
81 05 00 38           fin calibration
81 05 02 36           lecture état calibration
```

Extrait brut de l'app managée (`AdvanceSuper.Hid/HIDManage.cs`) :

```csharp
getRR_CMD               = 81 04 00 01 00 …
getControllerVersion_CMD= 81 04 21 01 00 00 06 …
getPID_CMD              = 81 05 c1 00 …
getmode_CMD             = 81 04 05 01 …
getmode_CMD1            = 81 05 08 00 …
getSuperButton          = 81 05 21 00 …
getUltimate2Color       = 81 05 00 21 01 …
getPro3USBColor_CMD     = 81 04 0b 00 00 00 20 00 00 00 20 00 …
Start_CMD               = 81 05 01 36 …
End_CMD                 = 81 05 00 38 …
```

## 3. Commandes du record de configuration

| cmd | sub | Effet | Réponse |
|---|---|---|---|
| `0x0001` | — | infos appareil (`u16 fw×100`, `u8 beta`, `u16 pid`) | données |
| `0x0002` | 0 | lit `len` octets du record à `offset` (`total` = taille du record) | les octets |
| `0x0001` | 0 | écrit `data` à `offset` | écho d'en-tête |
| `0x0006` | `0x123` | commit en flash (≈3 s) | écho d'en-tête |
| `0x0007` | 0/1 | coupe/relance les rapports d'entrée pendant les écritures | écho |

Le logiciel écrit **un réglage à la fois** (les octets de la section, sans recalculer
le CRC global), puis envoie le commit.

## 4. Record de configuration (famille Ultimate)

Taille variable selon le modèle (1592 o pour l'Ultimate 2, 1652 o pour BT/2.4G ;
**à mesurer pour la 3-mode**). Structure commune, offsets relatifs au début :

| Offset | Taille | Champ |
|---|---|---|
| `0 + 4s` | 4 | flag de slot : `0x20200911` actif, `0x20190000` désactivé, `0` supprimé, `0xffffffff` effacé |
| 12 | 4 | `crc_value` |
| 16 | 2 | `gamepad_mode` : 0 Switch, 1 Android/DInput, 3 Windows/XInput |
| 18 | 2 | `cur_slot` : profil actif |
| `20 + 32s` | 32 | nom du profil, UTF-16 (BE ou LE selon modèle) |
| `116 + 12s` | 12 | rumble : flag, `float` gauche, `float` droite |
| `152 + 8s` | 8 | **deadzone sticks** : flag, début/fin gauche, début/fin droite (0..128) |
| `176 + 8s` | 8 | **deadzone triggers** : flag, LT début/fin, RT début/fin (0..255) |
| `200 + 8s` | 8 | bits « special » (inversions, swap sticks/triggers, trigger rumble) |
| `224 + 92s` | 92 | **mapping boutons** : flag, 22 × u32 codes de fonction |
| `500 + 216s` | 216 | macros : flag, count, 4 × 52 o |
| `1148 + 8s` | 8 | plage de rumble des triggers |
| `1172 + 12s` | 12 | six-axis : flag, touche d'activation, mode, sensibilité, dead compensation |
| `1208 + 12s` | 12 | LED dynamique |
| `1244 + 16s` | 16 | LED hotwheel |
| `1292 + 100s` | 100 | LED custom (24 couleurs) |

Chaque section porte son propre flag `0x20200911` : c'est ce qui permet de modifier
un seul réglage sans réécrire tout le record.

## 5. Ce qui reste à déterminer sur la 3-mode

- PID exact du mode configuration (le knock est-il seulement accepté ?).
- Taille et offsets du record (probablement proches de l'Ultimate 2/2.4G).
- Endpoint de sortie à utiliser pour le knock (`0x01` observé ici, 64 o).
