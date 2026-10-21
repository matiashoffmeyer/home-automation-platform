#!/usr/bin/env python3
"""otbr_usb_replug.py — "digital genplug" af Sonoff Thread-donglen (2026-10-09).

Kører i HA-core-containeren (privilegeret, /sys rw) via
shell_command.otbr_usb_replug. Slår dongle-portens `disable` til i 3 s og fra
igen → kernen kobler USB-enheden fra og genopregner den (ny devnum, CP2102N-
broen nulstilles). Dét er det tætteste software kommer på at trække stikket.

HÅRDT FAKTUM (målt 2026-10-09 med hub-deskriptoren): NUC'ens xHCI-root-hub har
`wHubCharacteristics=0x000a` = INGEN port-strømstyring → VBUS forbliver tændt,
så EFR32-chippen får IKKE et power-on-reset herfra. Sidder donglen en dag i en
hub MED per-port power switching, bliver det samme `disable`-skriv en ægte
strøm-afbrydelse (kernen slukker selv VBUS) — scriptet melder hvilken slags.

Sikkerhed: rører KUN en enhed med VID:PID 10c4:ea60 fundet via by-id-navnet
"Itead_Sonoff" — aldrig ZBT-2 (303a:831a, Zigbee) eller BLE-adapteren. Addon'et
skal være stoppet af kalderen (porten skal være fri). Exit 0 = enheden kom
tilbage; exit 1 = noget fejlede (teksten siger hvad).

  python3 otbr_usb_replug.py            # gør det
  python3 otbr_usb_replug.py --dry-run  # vis kun hvad der ville ske
"""

import glob
import os
import sys
import time

BYID_GLOB = "/dev/serial/by-id/*Itead*Sonoff*if00-port0"
VID, PID = "10c4", "ea60"
FORBUDT = {("303a", "831a")}  # ZBT-2 — Zigbee-koordinatoren


def laes(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return ""


def find_usb_enhed():
    links = glob.glob(BYID_GLOB)
    if len(links) != 1:
        sys.exit(f"FEJL: forventede præcis én Sonoff by-id, fandt {links}")
    tty = os.path.basename(os.path.realpath(links[0]))  # ttyUSB0
    intf = os.path.realpath(f"/sys/class/tty/{tty}/device")  # .../1-1/1-1:1.0/ttyUSB0
    dev = os.path.dirname(os.path.dirname(intf))  # .../1-1
    vid, pid = laes(f"{dev}/idVendor"), laes(f"{dev}/idProduct")
    if (vid, pid) in FORBUDT or (vid, pid) != (VID, PID):
        sys.exit(f"FEJL: {dev} er {vid}:{pid}, ikke Sonoff {VID}:{PID} — afbryder")
    return links[0], dev, laes(f"{dev}/serial")


def hub_har_strømstyring(port):
    """Læs hubbens wHubCharacteristics via usbfs (bits 1:0 = 00 ganged / 01 per-port)."""
    try:
        import ctypes
        import fcntl

        hubdev = os.path.realpath(os.path.join(port, "..", ".."))  # usbN eller N-M
        busnum, devnum = int(laes(f"{hubdev}/busnum")), int(laes(f"{hubdev}/devnum"))
        speed = laes(f"{hubdev}/speed")
        dtype = 0x2A if speed and float(speed) >= 5000 else 0x29

        class Ctrl(ctypes.Structure):
            _fields_ = [
                ("bRequestType", ctypes.c_uint8),
                ("bRequest", ctypes.c_uint8),
                ("wValue", ctypes.c_uint16),
                ("wIndex", ctypes.c_uint16),
                ("wLength", ctypes.c_uint16),
                ("timeout", ctypes.c_uint32),
                ("data", ctypes.c_void_p),
            ]

        buf = ctypes.create_string_buffer(16)
        req = Ctrl(0xA0, 6, dtype << 8, 0, 16, 1000, ctypes.cast(buf, ctypes.c_void_p))
        with open(f"/dev/bus/usb/{busnum:03d}/{devnum:03d}", "wb") as f:
            fcntl.ioctl(f, 0xC0185500, req)
        chars = buf.raw[3] | (buf.raw[4] << 8)
        return (chars & 0x3) in (0, 1), chars
    except Exception as e:  # kun informativt — replug virker uanset
        return None, str(e)


def main():
    dry = "--dry-run" in sys.argv
    byid, dev, serial = find_usb_enhed()
    port = os.path.realpath(f"{dev}/port")
    disable = f"{port}/disable"
    if not os.path.exists(disable):
        sys.exit(f"FEJL: {disable} findes ikke (kernen for gammel?)")
    strom, chars = hub_har_strømstyring(port)
    art = {
        True: "ÆGTE strøm-afbrydelse (hub har power switching)",
        False: "logisk frakobling (hub uden power switching — VBUS bliver tændt)",
        None: "ukendt hub-type",
    }[strom]
    print(
        f"Sonoff {serial[:8]}… på {os.path.basename(dev)}, port {os.path.basename(port)}: {art} [{chars}]"
    )
    if dry:
        print(f"dry-run: ville skrive 1 → {disable}, vente 3 s, skrive 0")
        return 0
    with open(disable, "w") as f:
        f.write("1")
    time.sleep(3 if strom is not True else 6)  # strømløs: lad kondensatorerne tømme
    with open(disable, "w") as f:
        f.write("0")
    for _ in range(30):
        time.sleep(1)
        if os.path.exists(byid) and laes(f"{dev}/idVendor") == VID:
            print(f"OK: donglen genopregnet efter {art.split(' (')[0]}")
            return 0
    print("FEJL: donglen kom ikke tilbage inden 30 s")
    return 1


if __name__ == "__main__":
    sys.exit(main())
