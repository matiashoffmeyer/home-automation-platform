#!/usr/bin/env python3
"""NUC'en skal tænde selv når strømmen kommer tilbage efter et svigt.

NUC5i5RYB (Broadwell-U PCH-LP, LPC 8086:9cc3). Chipsættets GEN_PMCON_3
(LPC D31:F0, offset 0xA4) bit 0 = AFTERG3_EN: 0 = boot når strømmen kommer
tilbage, 1 = bliv slukket (S5). Målt 2026-11-01: 0x3809, dvs. BIOS står på
"Stay Off" og huset var uden HA efter hvert strømsvigt (ingen UPS).

Bitten ligger i RTC-brønden (CMOS-batteriet holder den gennem svigtet), men
BIOS skriver sin egen værdi ved hver boot → sensoren kører ved HA-start og
hver time og retter den kun når den står forkert (value-compare). Bit 1-2 er
write-1-to-clear statusbits og skrives som 0 (= rør ikke). Fortryd: skriv
bit 0 = 1 eller genstart værten. Den permanente løsning er BIOS (F2 → Power →
After Power Failure = Power On); så skriver scriptet aldrig.

Udskrift (JSON): {"tilstand": "taender"|"slukket"|"ukendt", "rettet": bool, ...}
"""

import json
import sys

CONFIG = "/sys/bus/pci/devices/0000:00:1f.0/config"
LPC_ID = (0x8086, 0x9CC3)
OFFSET = 0xA4
AFTERG3_EN = 0x0001
RWC_BITS = 0x0006  # PWR_FLR + RTC_PWR_STS: write-1-to-clear


def main() -> int:
    ud = {"tilstand": "ukendt", "rettet": False}
    try:
        with open(CONFIG, "rb") as f:
            cfg = f.read(256)
        vendor = int.from_bytes(cfg[0:2], "little")
        device = int.from_bytes(cfg[2:4], "little")
        if (vendor, device) != LPC_ID:
            ud["fejl"] = f"ukendt LPC {vendor:04x}:{device:04x}"
            print(json.dumps(ud))
            return 0
        val = int.from_bytes(cfg[OFFSET : OFFSET + 2], "little")
        ud["register_foer"] = f"0x{val:04x}"
        ud["stroemsvigt_flag"] = bool(val & 0x0002)
        ud["cmos_doed_flag"] = bool(val & 0x0004)
        if val & AFTERG3_EN:
            ny = val & ~AFTERG3_EN & ~RWC_BITS & 0xFFFF
            with open(CONFIG, "r+b") as f:
                f.seek(OFFSET)
                f.write(ny.to_bytes(2, "little"))
            with open(CONFIG, "rb") as f:
                f.seek(OFFSET)
                val = int.from_bytes(f.read(2), "little")
            ud["rettet"] = True
        ud["register"] = f"0x{val:04x}"
        ud["tilstand"] = "slukket" if val & AFTERG3_EN else "taender"
    except OSError as e:
        ud["fejl"] = str(e)
    print(json.dumps(ud))
    return 0


if __name__ == "__main__":
    sys.exit(main())
