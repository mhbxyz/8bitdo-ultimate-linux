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

## 5. Résultats mesurés sur la 3-mode (2dc8:2030)

### Le knock Xbox 360 est ignoré

La séquence `01 03 02 / 02 08 03 / 01 03 06 / rumble…` a été envoyée :

| Cible | Effet |
|---|---|
| dock 2.4G (5-1.1) | déconnexion du bus, retour en `2030` après rebranchement |
| pad filaire (5-1.2) | **aucun effet**, la manette reste sur le bus |

Conclusion : ce pad ne parle pas le protocole Xbox 360, il parle **GIP**.

### Le pad parle GIP (confirmé)

`05 20 01 01 00` (= `GIP_CMD_POWER`, mode ON) fait démarrer le flux :

```
<- INPUT    opt=0x00 seq=12 len=32  (état manette, 32 o)
<- STATUS   opt=0x20 seq=15 len=4  96 00 00 00
```

`04 20 02 00` (`GIP_CMD_IDENTIFY`) renvoie 58 octets. En revanche, `GIP_CMD_HID_REPORT`
(`0x0b`) est **silencieux**, y compris en découpant un rapport de 64 octets selon les
règles de chunking de `xone` (58 o max, drapeaux `ACK|CHUNK_START|CHUNK`). Les commandes
testées (`0x04 0x05 0x09 0x0a 0x0b 0x0c 0x1e 0x30 0x40 0x50`) ne renvoient rien.

### Le canal de configuration n'est pas en USB

L'app Android de 8BitDo configure cette famille (« Three/Gamesir », BLE `81HB-X/D/W`)
**exclusivement en BLE** — le câble USB ne sert qu'à l'alimentation. Même protocole
`0x04 / cmd / sub / chunk / crc / total / offset`, mais sans encapsulation HID :

```
requête BLE : 04 | u16 cmd | u16 sub | u16 len | u16 crc | u32 total | u32 offset | data
réponse BLE : 04 | 00 | u16 cmd_echo | u16 len | u16 crc | u32 total | u32 offset | data
```

Découverte GATT : service `00010203-0405-0607-0809-0A0B0C0D1910`,
caractéristique `00010203-0405-0607-0809-0A0B0C0D2B11`, MTU négocié à 67.

### Troisième voie : le mode D

La manette a un sélecteur `X / D / S` au dos. En D, les autres Ultimate exposent un
**canal HID de configuration** (`2dc8:3012`, rapport `0x81` sortant / `0x02` entrant).
C'est la voie la plus simple si la 3-mode se comporte pareil — à mesurer.

## 6. Ce qui reste à déterminer

- Descripteurs et PID en mode D.
- Taille et offsets du record (1652 o attendus ?), champs deadzone / mapping / profils.
- Message GIP utilisé par *Ultimate Software X* (seulement si les voies D et BLE échouent).

## 7. Le vrai canal de configuration : GIP `0x13` (832 octets)

Découverte décisive via le projet communautaire
[`AriesAlex/8bitdo-gyro`](https://github.com/AriesAlex/8bitdo-gyro) (Rust/Tauri,
cible exactement cette manette) : la configuration ne passe **pas** par le BLE en
mode Xbox/PC, mais par **GIP**, avec un rapport de 64 octets en charge utile.

### Format

```
charge utile GIP (60 octets) :
  04 | u16 cmd | u16 sub | u16 len | u16 crc | u32 total | u32 offset | data

trame GIP : [0x13][options][seq][len=60] + charge utile
réponse   : [0x12][options][seq][len]    + 04 00 | u16 cmd | u16 len | u16 crc
                                            | u32 total | u32 offset | data
```

- `total` = **832** (`0x340`) en GIP ; l'app en mode HID envoie `total = len`.
- Lecture : `cmd 2`. Écriture : `cmd 1` (stage) puis **`cmd 6 sub 0`** (applique
  au processeur d'entrée — c'est la commande qui manquait).
- Session : `cmd 7 sub 0` à l'ouverture, `cmd 7 sub 1` à la fermeture.

Vérifié sur matériel : `cmd 7 sub 0` → `12 00 … 04 00 07 00 …` ;
`cmd 2` renvoie `04 00 02 00 20 00 00 00 40 03 00 00 00 00 00 00 <data>`.

### Record : 832 octets, 3 profils de 276

L'outil communautaire donne `CONFIG_SIZE = 0x340` et `motion_offset(i) =
0x10C + i·0x114` (blocs de 276, cohérent avec `get3Xbox_Write*` de la
bibliothèque Android). Disposition relevée dans l'app Android (`S_Ultimate3XboxAdvance`) :

| Section | Offset (relatif au profil) |
|---|---|
| nom | `+0x08` |
| mapping | `+0x2C` (pas de 8 dans la bibliothèque Android) |
| deadzone sticks | `+0xDC` |
| triggers | `+0xF3` |
| vibration | `+0xFB` |
| special | `+0x104` |
| gyroscope / motion | `+0x108` (`0x10C` avec base 4) |

### État des essais

| Opération | Résultat |
|---|---|
| lecture du record en GIP | ✅ (832 octets, en-tête `crc16 + 0xFF + mode` lu) |
| `cmd 1` puis `cmd 6 sub 0` | ✅ acquittés (`12 00 … 04 00 01 00 …` puis `04 00 06 00`) |
| persistance d'une écriture test | ❌ la valeur relue reste `0xFF` |

L'écriture est acceptée mais non conservée : il manque vraisemblablement le
message de « mode configuration » que le pilote Windows (`XboxGIP_Admin`) envoie
avant d'ouvrir la session (`00 0F 00 00 00 00 FF 00 EB`), message qui n'a pas
d'équivalent évident sur le fil.
