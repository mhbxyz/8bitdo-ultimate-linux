# Protocole de configuration — 8BitDo Ultimate 3-mode (BLE)

Tout ce qui suit a été **mesuré sur matériel** (firmware 2.00, pad `2dc8:2030`,
identité BLE `81HB-D` / `81HB-X`), pas seulement déduit des binaires.

## 1. Pourquoi BLE et pas USB

| Interface | Constat |
|---|---|
| USB `2dc8:2030` (XGIP `ff/47/d0`) | la manette **parle GIP** : `05 20 01 01 00` déclenche le flux `INPUT`/`STATUS`, `04 20 02 00` répond à l'identify. Mais `GIP_CMD_HID_REPORT` (0x0b) reste muet, même avec le chunking de `xone`. Aucun canal de configuration. |
| Knock « Xbox 360 » (`01 03 02` + rumble) | ignoré en filaire ; sur le dock il provoque une déconnexion sans bascule de mode |
| BLE `81HB-*` | ✅ service `00010203-…-1910`, caractéristique `…-2B11`, notifications |

Le câble USB ne sert qu'à l'alimentation ; l'app Android officielle configure
elle aussi **exclusivement en BLE**.

La manette annonce deux identités BLE :

- `81HB-D` / `81HB-X` → celle qui porte le service de configuration ;
- `8BitDo Ultimate 3mode Xbox` → identité HID « manette », **sans** la caractéristique de config.

## 2. Trame

```
requête : 04 | u16 cmd | u16 sub | u16 len | u16 crc | u32 total | u32 offset | data
réponse : 04 | 00      | u16 cmd | u16 len | u16 crc | u32 total | u32 offset | data
```

- en-tête de requête : 17 octets ; en-tête de réponse : 16 octets (le `sub` disparaît,
  un `00` s'insère après le type) ;
- réponses parfois **fragmentées** sur plusieurs notifications, et parfois plus
  courtes que 45 octets (fin de zone) → réassembler avant de parser ;
- un périphérique connecté n'annonce plus : toujours `disconnect` avant un scan.

| cmd | sub | Effet |
|---|---|---|
| `0x0002` | 0 | lit `len` octets du record à `offset` (`total` = taille du record) |
| `0x0001` | 0 | écrit `data` à `offset` |
| `0x0006` | `0x15` ou `0x123` | commit en flash |
| `0x0007` | 0 | `report_state` (non nécessaire ici) |

## 3. Record : 532 octets

**Pas 1652** : la 3-mode ne gère ni turbo ni macro (FAQ officiel), la section
macros de 1176 octets de l'Ultimate 2 n'existe donc pas.

```
0x000  2   CRC-16/KERMIT de record[2:532], little-endian — recalculé par la manette
0x002  1   réservé (0xFF)
0x003  1   identifiant du record : 0x03 en mode D, 0x02 en mode X/PC
0x004  …   structure de configuration (famille Ultimate, sans macros)
```

Offsets **dans la structure** (ajouter `0x004` pour le record brut) :

| Offset | Taille | Champ |
|---|---|---|
| `0x000` | 12 | flags des 3 profils : `0x20200911` actif, `0x20190000` désactivé, `0xffffffff` effacé |
| `0x00C` | 4 | `crc_value` (non validé par le firmware) |
| `0x010` | 2 | `gamepad_mode` (1 en mode D, 3 en X d'après la famille) |
| `0x012` | 2 | `cur_slot` (profil actif, 0..2) |
| `0x014` | 96 | noms, 3 × 32 o UTF-16LE |
| `0x074` | 36 | rumble, 3 × (flag u32, float gauche, float droite) |
| `0x098` | 24 | **deadzone sticks**, 3 × (flag, LS début/fin, RS début/fin ; 0..128) |
| `0x0B0` | 24 | **deadzone triggers**, 3 × (flag, LT début/fin, RT début/fin ; 0..255) |
| `0x0C8` | 24 | options, 3 × (flag, bits) — inversions, swap sticks/triggers, trigger rumble |
| `0x0E0` | 276 | **mapping**, 3 × (flag + 22 × u32 codes de fonction) |
| `0x1DC` | 56 | sections supplémentaires (gyro/LED), non décodées |

### Codes de fonction (mapping)

Ordre des boutons :

```
A B X Y LB RB LT RT L3 R3 Select Start Star Home Up Down Left Right P1 P2 P3 P4
```

| Code | Fonction | Code | Fonction |
|---|---|---|---|
| `0x1` | Start | `0x400` | LB |
| `0x2` | L3 | `0x800` | RB |
| `0x4` | R3 | `0x1000` | B |
| `0x8` | Select | `0x2000` | A |
| `0x10` | X | `0x4000` | LT |
| `0x20` | Y | `0x8000` | RT |
| `0x40` | Droite | `0x10000` | Menu |
| `0x80` | Gauche | `0x20000` | Home |
| `0x100` | Bas | `0x2000000` | P1 |
| `0x200` | Haut | `0x4000000` | P2 |
| `0` | désactivé | `0xFFFFFFFF` | effacé |

## 4. Vérifications faites

- écriture/lecture d'un motif `00 01 02 … 2c` à l'offset 0 : relu à l'identique ;
- écriture d'un nom `TEST` à `0x018` : relu `54 00 45 00 53 00 54 00` ;
- création du profil 0 (`flags = 0x20200911`, `mode = 1`, `cur_slot = 0`, nom) :
  conservé après commit ;
- `CRC` recalculé par la manette **identique** au nôtre (`0x5258`, puis `0x986d`
  après ajout des deadzones) → disposition et algorithme confirmés ;
- octet `record[3]` (id de record) réécrit par la manette si on tente de le modifier.
