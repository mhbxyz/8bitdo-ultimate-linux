# Phase 1 — Identification du matériel

Date : 2026-10-26 · Hôte : CachyOS, kernel 7.2.9-2-cachyos

## Périphérique détecté

```
Bus 005 Device 050: ID 2dc8:2030 8BitDo 8BitDo Ultimate 3mode Xbox
```

| Champ | Valeur | Source |
|---|---|---|
| `idVendor` | `0x2dc8` (8BitDo) | sysfs |
| `idProduct` | `0x2030` | sysfs |
| `bcdDevice` | `0x0200` (firmware 2.00) | sysfs |
| iManufacturer | `8BitDo` | descipteur |
| iProduct | `8BitDo Ultimate 3mode Xbox` | descripteur |
| iSerial | `0000DA8814D072EB` | descripteur |
| `bDeviceClass` | `0xff` / `0x47` / `0xd0` | descripteur |
| Vitesse | Full Speed (12 Mbps) | `speed` = 12 |
| Chemin USB | `5-1.1` (derrière hub VIA VL815) | sysfs |

**`ff/47/d0` = XGIP** (*Xbox Game Input Protocol*). Ce n'est **pas** du HID :
il n'y a aucun descripteur de rapport dans l'énumération, et aucun nœud `hidraw`
n'est créé pour ce périphérique.

## Interfaces

```
Interface 0  alt 0   class 0xff/0x47/0xd0   driver = xpad
   EP 0x81  IN  interrupt  64 B  bInterval 4
   EP 0x01  OUT interrupt  64 B  bInterval 4

Interface 1  alt 0   (sans endpoint)
Interface 1  alt 1   isochrone (audio casque)
   EP 0x03  OUT isoc 224 B  bInterval 1
   EP 0x83  IN  isoc 128 B  bInterval 1
```

L'interface 0 est le canal de configuration/entrées Xbox ; l'interface 1 alt 1 est le
canal audio du casque. Le noyau lie `xpad` à l'interface 0 et expose `/dev/input/js0`
+ `/dev/input/event16`.

## Conséquences pour le projet

1. Pas de `hidraw` : la couche HID classique est inutilisable sur ce modèle en mode Xbox.
2. Le logiciel officiel (*Ultimate Software X*, UWP Microsoft Store) parle au pad via
   `Windows.Gaming.Input.Custom` → `GipGameControllerProvider`, c'est-à-dire des
   **messages GIP** sur les endpoints interrupt 0x01/0x81.
3. Côté Linux, la voie est donc : détacher `xpad` de l'interface 0, prendre la main en
   libusb, puis émettre des trames GIP de 64 octets (header 4 octets + payload).

## Le composant WinRT côté Windows (preuve du transport GIP)

`UltimateSoftwareX_1.5.0.0.appxbundle` contient `D4XGaming.Devices.winmd` qui expose :

```csharp
public sealed class D4XDevice : IGameController, IGameControllerBatteryInfo
{
    public void SendMessageA(byte[] pData);
    public void SendMessageId(byte[] pData, uint messageId);
    public void GetMessageB(byte[] pData, out uint dataSize);
    public void SendReceiveMessageC(MessageCRequest request, out MessageCResponse response);
}
```

C'est le même contrat que `GipGameControllerProvider` (API WinRT GIP) : `messageId`
= commande GIP, `pData` = payload. Le modèle « 3-mode » **n'a pas de mode DInput** :
le manuel officiel ne documente que Xbox / Windows 10-11 (2.4G et filaire), Android,
Apple et Steam Deck. Il n'existe donc pas de mode HID classique sur PC.

## Ce qui reste à identifier

- PID/descripteurs avec l'**adaptateur 2.4G** (le kit en fournit un).
- PID/descripteurs en **Bluetooth** (mode Android/Apple).
- Numéro de commande GIP utilisé par 8BitDo pour ses messages de configuration.
