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
| `0x0006` | **`0x67`** | commit en flash — validé sur matériel (voir §5) |
| `0x0006` | `0x15` / `0x123` | sous-codes des autres générations |
| `0x0007` | 0 | `report_state` (non nécessaire ici) |

## 3. Record : 532 octets

**Pas 1652** : la 3-mode ne gère ni turbo ni macro (FAQ officiel), la section
macros de 1176 octets de l'Ultimate 2 n'existe donc pas. La structure fait
500 octets, suivis de 28 octets de sections non décodées : 4 + 500 + 28 = 532.

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
| `0x1F4` | 28 | sections supplémentaires (gyro/LED), non décodées |

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

## 5. Limite connue : le commit du record PC ne persiste pas

Mesures sur le record **PC/Windows** (`81HB-W`, `record id 1`) :

| Action | Résultat |
|---|---|
| lecture | ✅ 532 octets cohérents, CRC recalculé identique |
| écriture (tranches de 45 o) | ✅ acquittée, relue dans la session |
| relecture après reconnexion BLE | ✅ la modification est toujours là |
| relecture après **extinction/rallumage** | ❌ retour à l'état d'origine (`0xc323`) |

Essais infructueux pour faire persister : `commit sub 0x15`, `commit sub 0x123`,
les deux à la suite, `report_state 0/1` autour de l'écriture, attente de 3 s avant
déconnexion, avec et sans le dock branché (liaison 2.4G active ou non).

À l'inverse, sur le record **D/Bluetooth** (`record id 3`), un `commit sub 0x15`
avait bien survécu à un cycle d'alimentation — la voie d'écriture flash existe donc.

Hypothèses restantes :

1. le profil PC est stocké (ou validé) côté **dock/récepteur 2.4G**, pas dans la
   manette — le logiciel officiel passerait par le canal de configuration du dock ;
2. le commit exige un sous-code propre à ce mode, non déterminé ;
3. un champ d'en-tête du bloc (les 28 octets à `bloc+0x0C`) doit être rempli pour
   que le profil soit jugé valide et écrit.

Trancher demande une capture du logiciel officiel sur Windows (VM + USBPcap).

## 6. Ce que dit l'application Android officielle

APK récupéré : `8BitDo Ultimate Software V2 Android V2.01`
(`com.bbitdo.advanceandroidv2`), décompilé avec jadx ; `libadvancelib.so` n'est
pas strippé, ce qui donne les symboles JNI et les constantes de protocole.

### Notre manette dans l'app

`utils/BLEUtils.java` reconnaît les noms `81HB-X`, `81HB-D`, `81HB-W` et les
associe au service `…1910` / caractéristique `…2B11` — exactement le canal qu'on
utilise. Côté modèle, ils sont rangés dans la famille **« Three »**, qui emprunte
le chemin générique « Ultimate Wired » (20 boutons : A B X Y LB RB LT RT L3 R3
Select Start Share/Logo + croix + P1/P2), et non la classe `Ultimate3Xbox`.

### Constantes de protocole extraites de la bibliothèque native

```
read channel : offset 0, longueur 832 (0x340), cmd 2
write channel: offset 0, longueur 832, cmd 1
CRC          : ANSI_CRC_16_sh(record, 0x364)
```

Les fonctions `get3Xbox_Write*` donnent la disposition d'un record de **276
octets par profil** (`0x114`), avec :

| Section | Offset dans le bloc | Taille |
|---|---|---|
| nom | `+0x08` | 32 |
| mapping | `+0x2C` | 4 o par entrée, pas de 8 |
| sticks | `+0xDC` | 23 |
| triggers | `+0xF3` | 8 |
| vibration | `+0xFB` | 9 |
| special | `+0x104` | 8 |

Soit 3 × 276 + 4 = **832 octets** — à comparer aux **532 octets** que la manette
sert réellement sur la caractéristique `2B11`, quelle que soit la valeur de
`total` demandée (testé 532, 832, 868, 1652 : la lecture s'arrête toujours à
`offset 532`, et au-delà la manette ne répond plus).

### Point ouvert

Deux dispositions coexistent donc : celle du logiciel (blocs de 276, mapping à
pas de 8, 832 octets) et celle observée sur la manette (blocs de 176 terminés par
`55 AA`, mapping à pas de 4, 532 octets). La seconde est un sous-ensemble cohérent
(les 3 profils et les sections sticks/triggers/options y sont), mais écrire dedans
ne survit pas à un cycle d'alimentation en mode PC.

Prochaine étape logique : identifier le **PID interne** que la manette renvoie à
l'app (commande de version) pour savoir sous quelle classe elle est réellement
traitée, puis rejouer la trame exacte de `write3ECustomConfig`/`write3XboxCustomConfig`
(avec son `total` de 832) sur la caractéristique `2B11`.


## 7. Résolution du commit : `sub 0x67`

Le sous-code de sauvegarde a été retrouvé dans `libadvancelib.so`, fonction
`getSaveCustomConfigChannel`, qui construit la commande :

```
cmd = 0x0006, sub = 0x0067, offset = 0, longueur = 0
```

Testé sur la manette en mode PC : après `write` complet puis `commit sub 0x67`,
le record **survit à un cycle d'alimentation** (CRC `0xc781` conservé, `a→b`
toujours présent). Les sous-codes `0x15` et `0x123` ne faisaient que modifier la
copie en RAM.

Ce qui reste : le mapping écrit à `bloc+0x2C` est bien persisté mais **n'agit pas**
sur les rapports XInput. Le chemin natif du modèle « Three » reste à identifier
(celui de `Ultimate3Xbox` écrit des entrées de 8 octets à `+0x2C`, alors que le
record de 532 octets observé les espace de 4 octets).

## 8. `cur_slot` et limite d'application en mode PC

`S_Ultimate3XboxAdvance_setCurslot` écrit dans **`record[3]`** : l'octet que
j'avais pris pour un « identifiant de record » est en réalité le **profil actif**.
Valeurs observées : `1` en mode PC/W, `2` en mode Xbox, `3` en mode D.

La manette **refuse** qu'on le modifie : écrit `0`, relu `1` après commit. Elle
garde la main sur ce champ.

Test d'application, avec `deadzone sticks = 100/128` écrit successivement :

| Bloc écrit | Amplitude mesurée du stick gauche |
|---|---|
| bloc 0 | ±32768 (pleine course) |
| bloc 1 (= `cur_slot`) | ±32768 (pleine course) |

Conclusion : le record accessible sur la caractéristique `2B11` (532 octets,
blocs de 176) **n'est pas celui que le firmware applique au chemin XInput/2.4G**.
Les écritures y sont persistées (commit `0x67`) mais restent sans effet sur les
rapports de manette.

Cohérent avec le §6 : le logiciel officiel manipule un record de **832 octets**
(blocs de 276), que la manette ne sert pas sur ce canal dans les modes testés.

Prochaine piste : trouver comment l'app atteint ce record de 832 octets — soit un
canal/mode de configuration distinct (déclenché par une commande, comme le
« knock » des autres modèles), soit une négociation préalable sur `2B11`.

## 9. Conclusion sur l'application des réglages

Test final, avec la séquence complète du logiciel officiel reproduite
(lecture de l'en-tête de 116 octets, écriture du record entier, `commit 0x67`,
cycle d'alimentation) et `deadzone sticks = 100/128` :

| Essai | Amplitude du stick gauche |
|---|---|
| bloc 0, commit `0x15` | ±32768 |
| bloc 1 (= `cur_slot`), commit `0x67` | ±32768 |
| après lecture d'en-tête + commit `0x67` | ±32768 |

Le firmware **n'applique pas** ce record au chemin XInput/2.4G : les écritures
sont persistées en flash (vérifié après cycle d'alimentation) mais restent sans
effet sur les rapports de manette.

Bilan : le canal BLE `2B11` est un canal de configuration fonctionnel (lecture,
écriture, sauvegarde), mais il ne porte pas la configuration que la manette
utilise en mode XInput. Le logiciel officiel manipule un record de 832 octets que
ce canal ne sert pas.

Le record a été restauré dans son état d'usine (CRC `0xc323`, deadzone pleine
course, remaps par défaut) à l'issue des essais.

## 10. Oracle par l'application iOS — et verdict

L'app iOS officielle *Ultimate Software* (la V2 refuse de s'appairer sur ce
modèle) se connecte en **mode Bluetooth** (`81HB-D`) et configure la manette.
Elle a servi d'oracle : un seul réglage changé (deadzone stick gauche = 50), puis
comparaison des relevés avec `tools/record-diff.py`.

### Ce que l'app écrit — notre disposition était la bonne

| Octet modifié | Contenu |
|---|---|
| `0x000` | CRC d'en-tête (recalculé) |
| `bloc+0x00` | flag de profil `0x20200911` |
| `bloc+0x28` | flag de section mapping |
| `bloc+0x2C..0x7B` | 20 codes de fonction, **4 octets chacun** |
| `bloc+0x7C` | flag calibration, puis 4 flottants |
| `bloc+0x90` / `+0x94` | deadzone : `00 42 00 80` → **LS 0→66** (l'app convertit 50 en 66) |
| `bloc+0x98` / `+0x9C` | triggers `00 ff 00 ff` |
| `bloc+0xA0` / `+0xA4` | options |
| `bloc+0xAE` | marqueur `55 cc` (au lieu de `55 aa` à l'usine) |

### Verdict

Un profil **cloné octet pour octet** depuis celui produit par l'app (marqueur
`55 cc` inclus), écrit dans le record PC puis commité, **ne s'applique toujours
pas** : le stick sort à ±32768.

Le canal BLE `2B11` est donc un canal de configuration réel (l'app s'en sert),
mais le record qu'il expose en mode PC n'est pas celui que le firmware applique
au chemin XInput/2.4G. Piste restante : la configuration XInput est probablement
portée par le **dock**, poussée dans la manette à l'établissement du lien 2.4G —
ce qui expliquerait qu'aucune écriture, même valide, ne survive à la
reconnexion.

## 11. Test décisif : l'application officielle elle-même

L'app iOS connectée **en mode PC** (sélecteur sur « PC ») modifie deux réglages :
deadzone stick gauche = 50 et A → B.

Diff des records relevés avant/après (`tools/record-diff.py`) :

```
0x000..0x001  CRC d'en-tête                     0xc323 → 0x9f4b
0x031         bloc 0 +0x2d  mapping A → B       0x20   → 0x10
0x099         bloc 0 +0x95  deadzone LS fin     0x80   → 0x42  (66)
```

Deux écritures **partielles**, marqueurs de bloc inchangés (`55 aa`).

Après extinction/rallumage :

| Vérification | Résultat |
|---|---|
| record conservé | ✅ CRC `0x9f4b`, deadzone `0→66`, `a→b` |
| A appuyé sur la manette | ❌ sort en `BTN_SOUTH` (A) |
| stick gauche à fond | ❌ ±32768, deadzone non appliquée |

**Conclusion** : même le logiciel officiel ne modifie pas le comportement
XInput par ce canal. Le record exposé sur `2B11` décrit donc le profil de la
liaison **Bluetooth**, pas celui du lien 2.4G/dock — ce qui explique d'un coup
pourquoi aucune de nos écritures, même parfaitement conformes, n'a jamais eu
d'effet sur la manette utilisée via le dock.

Corollaire : le canal BLE fait bien ce qu'il annonce (lecture, écriture
partielle, sauvegarde), et notre outillage est correct ; c'est simplement le
mauvais profil qui est éditable depuis Linux.

## 12. Test en filaire : le dock est innocenté

Le sélecteur sur **Xbox** et un câble USB-C font apparaître la manette en `2dc8:2030`
(mode filaire). La manette reste joignable en BLE sous `81HB-X`, ce qui a permis de
lui écrire une configuration puis de la mesurer sur son nœud `evdev` filaire.

Configuration écrite dans **les trois profils** du record Xbox (deadzone
`LS 0→66`, mapping `A→B`), commit `0x67`, en flash (CRC `0x3796`), puis
débranchement/rebranchement.

Résultat : `BTN_SOUTH` pour A, stick à ±32768. **Aucun effet.**

| Liaison testée | Configuration stockée | Appliquée |
|---|---|---|
| dock 2.4G (mode PC) | ✅ | ❌ |
| filaire USB (mode Xbox) | ✅ | ❌ |
| écriture par l'app officielle (mode PC) | ✅ | ❌ |

Le dock est donc hors de cause : le même silence s'observe en filaire. Trois
liaisons, trois échecs, y compris quand c'est le logiciel officiel qui écrit.

`setConfigState` (`cmd 0x11`) existe dans la bibliothèque mais n'est utilisé que
pour les modèles `UT2`/`lashen`, pas pour celui-ci.

État final : records remis à zéro, manette rendue à son comportement d'usine.
