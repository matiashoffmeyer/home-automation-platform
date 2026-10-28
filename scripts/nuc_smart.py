#!/usr/bin/env python3
"""SMART for NUC'ens systemdisk — kun læsende ATA-kommandoer, ingen smartctl (B272).

Køres af HA's command_line-sensor (`sensor.nuc_smart`, packages/nuc_helbred.yaml)
og printer ÉN linje JSON. Hvorfor ikke smartctl: HA Core-imaget har det ikke,
SSH-add-on'et har det men må ikke åbne /dev/sda, og Supervisor nægter ethvert
add-on adgang til systemdisken ("tried to access blocked device sda", målt
28/10). HA Core-containeren er derimod privilegeret og kan åbne disken, så
scriptet taler selv ATA gennem SG_IO (ATA PASS-THROUGH 16) og sender kun:

  SMART READ DATA (B0h/D0h) · READ THRESHOLDS (D1h) · READ LOG 01h (D5h) ·
  RETURN STATUS (DAh)

Attribut-numrene følger smartmontools' "Phison Driven SSDs" (drivedb.h), der
dækker denne Kingston SM2280S3 (firmware S8FM06.A = Phison S8, samme som
SS200S3): 5 retired blocks · 170 bad blocks senere/fra fabrik · 187
uncorrectable · 192 usikre nedlukninger · 199 + 218 CRC · 233 NAND-skrivninger
(GiB) · 241 host-skrivninger (GiB) · 242 host-læsninger (GiB) · 244/245
gennemsnitlig/max slettecyklus. Disken har ingen 231 (liv tilbage), så HA
regner sliddet ud fra 244. Facit 28/10: identisk med `smartctl -x`.

  python3 scripts/nuc_smart.py [/dev/sda]
"""

import ctypes
import fcntl
import json
import os
import sys
from datetime import datetime

SG_IO = 0x2285
SG_DXFER_NONE = -1
SG_DXFER_FROM_DEV = -3


class SgIoHdr(ctypes.Structure):
    _fields_ = [
        ("interface_id", ctypes.c_int),
        ("dxfer_direction", ctypes.c_int),
        ("cmd_len", ctypes.c_ubyte),
        ("mx_sb_len", ctypes.c_ubyte),
        ("iovec_count", ctypes.c_ushort),
        ("dxfer_len", ctypes.c_uint),
        ("dxferp", ctypes.c_void_p),
        ("cmdp", ctypes.c_void_p),
        ("sbp", ctypes.c_void_p),
        ("timeout", ctypes.c_uint),
        ("flags", ctypes.c_uint),
        ("pack_id", ctypes.c_int),
        ("usr_ptr", ctypes.c_void_p),
        ("status", ctypes.c_ubyte),
        ("masked_status", ctypes.c_ubyte),
        ("msg_status", ctypes.c_ubyte),
        ("sb_len_wr", ctypes.c_ubyte),
        ("host_status", ctypes.c_ushort),
        ("driver_status", ctypes.c_ushort),
        ("resid", ctypes.c_int),
        ("duration", ctypes.c_uint),
        ("info", ctypes.c_uint),
    ]


def smart_cmd(fd, feature, lba_low=0, data_in=True):
    """Én SMART-kommando (B0h). data_in: PIO ind, 1 sektor. Ellers non-data
    med CK_COND, så disken sender sine registre tilbage i sense-data."""
    if data_in:
        # protokol 4 = PIO Data-In · T_DIR=1, BYT_BLOK=1, T_LENGTH=2 (sector count)
        proto, flags, direction, length = 4 << 1, 0x0E, SG_DXFER_FROM_DEV, 512
    else:
        # protokol 3 = Non-data · CK_COND=1
        proto, flags, direction, length = 3 << 1, 0x20, SG_DXFER_NONE, 0
    cdb = bytes([0x85, proto, flags, 0, feature, 0, 1, 0, lba_low, 0, 0x4F, 0, 0xC2, 0, 0xB0, 0])
    cdb_buf = ctypes.create_string_buffer(cdb, len(cdb))
    data = ctypes.create_string_buffer(max(length, 1))
    sense = ctypes.create_string_buffer(32)
    hdr = SgIoHdr(
        interface_id=ord("S"),
        dxfer_direction=direction,
        cmd_len=len(cdb),
        mx_sb_len=len(sense),
        dxfer_len=length,
        dxferp=ctypes.cast(data, ctypes.c_void_p) if length else None,
        cmdp=ctypes.cast(cdb_buf, ctypes.c_void_p),
        sbp=ctypes.cast(sense, ctypes.c_void_p),
        timeout=10000,
    )
    fcntl.ioctl(fd, SG_IO, hdr)
    if data_in:
        if hdr.status or hdr.host_status or (hdr.driver_status & 0x0F):
            raise OSError(
                f"SMART {feature:#04x} fejlede (status {hdr.status}, host {hdr.host_status})"
            )
        raw = data.raw[:512]
        if sum(raw) % 256:
            raise ValueError(f"SMART {feature:#04x}: checksum passer ikke")
        return raw
    return sense.raw[: hdr.sb_len_wr]


def health(sense):
    """RETURN STATUS: LBA mid/high = 4Fh/C2h er sund, F4h/2Ch svigter.
    libata svarer i fast eller descriptor-format afhængigt af D_SENSE."""
    if len(sense) < 12:
        return None
    if (sense[0] & 0x7F) in (0x72, 0x73):
        i = 8
        while i + 1 < len(sense):
            if sense[i] == 0x09 and i + 13 < len(sense):
                mid, high = sense[i + 9], sense[i + 11]
                break
            i += 2 + sense[i + 1]
        else:
            return None
    elif (sense[0] & 0x7F) in (0x70, 0x71):
        mid, high = sense[10], sense[11]
    else:
        return None
    if (mid, high) == (0x4F, 0xC2):
        return True
    if (mid, high) == (0xF4, 0x2C):
        return False
    return None


def main():
    dev = sys.argv[1] if len(sys.argv) > 1 else "/dev/sda"
    fd = os.open(dev, os.O_RDONLY | os.O_NONBLOCK)
    try:
        data = smart_cmd(fd, 0xD0)
        thresh = smart_cmd(fd, 0xD1)
        try:
            errlog = smart_cmd(fd, 0xD5, lba_low=0x01)
        except OSError, ValueError:
            errlog = None
        passed = health(smart_cmd(fd, 0xDA, data_in=False))
    finally:
        os.close(fd)

    attrs, limits = {}, {}
    for off in range(2, 2 + 30 * 12, 12):
        aid = data[off]
        if aid:
            attrs[aid] = {
                "flags": int.from_bytes(data[off + 1 : off + 3], "little"),
                "value": data[off + 3],
                "raw": int.from_bytes(data[off + 5 : off + 11], "little"),
            }
        if thresh[off]:
            limits[thresh[off]] = thresh[off + 1]
    # En prefail-attribut (flag-bit 0) på eller under sin tærskel = disken
    # melder selv svigt, også hvis RETURN STATUS ikke kunne læses.
    failing = sorted(
        aid
        for aid, a in attrs.items()
        if a["flags"] & 1 and limits.get(aid, 0) and a["value"] <= limits[aid]
    )

    def raw(aid):
        return attrs[aid]["raw"] if aid in attrs else None

    bad = raw(170)
    print(
        json.dumps(
            {
                "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
                "passed": passed if passed is not None else (not failing if attrs else None),
                "failing_attrs": failing,
                "power_on_hours": raw(9),
                "power_cycles": raw(12),
                "unsafe_shutdowns": raw(192),
                "retired_blocks": raw(5),
                # 170 = to 16-bit tællere: byte 5-4 senere (voksede), byte 1-0 fra fabrik
                "bad_blocks_later": None if bad is None else (bad >> 32) & 0xFFFF,
                "bad_blocks_early": None if bad is None else bad & 0xFFFF,
                "uncorrectable": raw(187),
                "pending": raw(197),
                "crc_errors": (raw(199) or 0) + (raw(218) or 0),
                "error_log": None if errlog is None else int.from_bytes(errlog[452:454], "little"),
                "host_writes_gib": raw(241),
                "nand_writes_gib": raw(233),
                "host_reads_gib": raw(242),
                "avg_erase": raw(244),
                "max_erase": raw(245),
            },
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    main()
