#!/usr/bin/env python3
"""Apollo MSR-2: hvilke chips svarer på I2C-bussen? (B282, 2026-11-01)

Når en Apollo-sensor står `unknown` (eller på en gendannet værdi efter en
genstart), siger HA intet om HVORFOR. Noden ved det: ved boot scanner den
I2C-bussen, og en chip der ikke svarer markeres FAILED. Huset har intet
ESPHome-add-on, så den log var usynlig — B282 stod fast på netop det.

Scriptet kobler på nodens native API (plaintext, som HA-integrationen) og
abonnerer på loggen med dump_config=True: noden udskriver så hver komponents
config igen, inkl. bus-scanningen og "marked FAILED". KUN LÆSNING — ingen
number/select/switch-skrivning, ingen reboot (🔥 chip-wear,
.claude/rules/presence_radar.md).

Brug:
  python3 scripts/apollo_diag.py                # alle Apolloer
  python3 scripts/apollo_diag.py boernevaerelse # kun ét rum (entity-prefix)
  python3 scripts/apollo_diag.py --raw stue     # hele config-dumpet

Kræver aioesphomeapi (requirements-dev.txt → bash scripts/dev_setup.sh):
  .cache/dev-venv/bin/python scripts/apollo_diag.py
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

STORAGE = Path("/config/.storage")
# Kendte I2C-adresser på MSR-2 (factory-firmwaren).
CHIPS = {0x53: "LTR390 (lux/UV)", 0x62: "SCD40 (CO2)", 0x77: "DPS310 (temp/tryk)"}
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def apolloer() -> list[tuple[str, str]]:
    """[(rum-prefix, host)] fra HA's registre — rummet = entity-prefixet før _apollo_."""
    entries = json.loads((STORAGE / "core.config_entries").read_text())["data"]["entries"]
    hosts = {
        e["entry_id"]: e["data"].get("host")
        for e in entries
        if e["domain"] == "esphome" and "apollo" in e.get("title", "").lower()
    }
    rum: dict[str, str] = {}
    for e in json.loads((STORAGE / "core.entity_registry").read_text())["data"]["entities"]:
        m = re.match(r"\w+\.(\w+?)_apollo_", e["entity_id"])
        if m and e.get("config_entry_id") in hosts:
            rum.setdefault(hosts[e["config_entry_id"]], m.group(1))
    return sorted((r, h) for h, r in rum.items())


async def dump(host: str, sekunder: float) -> tuple[str, list[str]]:
    from aioesphomeapi import APIClient, LogLevel

    cli = APIClient(host, 6053, None)
    await cli.connect(login=True)
    info = await cli.device_info()
    linjer: list[str] = []

    def on_log(msg) -> None:
        t = (
            msg.message.decode("utf-8", "replace")
            if isinstance(msg.message, bytes)
            else msg.message
        )
        linjer.append(ANSI.sub("", t))

    cli.subscribe_logs(on_log, log_level=LogLevel.LOG_LEVEL_CONFIG, dump_config=True)
    await asyncio.sleep(sekunder)
    await cli.disconnect()
    return f"{info.name} · ESPHome {info.esphome_version} · {info.project_version}", linjer


def rapport(rum: str, host: str, hoved: str, linjer: list[str], raw: bool) -> None:
    print(f"== {rum} ({host}) — {hoved}")
    if raw:
        print("\n".join(linjer))
        return
    fundet = {
        int(a, 16)
        for a in re.findall(r"Found device at address (0x[0-9a-fA-F]+)", "\n".join(linjer))
    }
    for adr, navn in CHIPS.items():
        print(f"   {'✅' if adr in fundet else '❌'} 0x{adr:02x} {navn}")
    for a in sorted(fundet - CHIPS.keys()):
        print(f"   ❔ 0x{a:02x} ukendt chip på bussen")
    for linje in linjer:
        if "marked FAILED" in linje or "Communication failed" in linje:
            print(f"   {linje.strip()}")
    if not any("Results from bus scan" in linje for linje in linjer):
        print("   (ingen bus-scanning i dumpet — kør igen med længere tid eller --raw)")


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    raw = "--raw" in sys.argv
    try:
        import aioesphomeapi  # noqa: F401
    except ImportError:
        print(
            "aioesphomeapi mangler — bash scripts/dev_setup.sh --no-hooks, og kør med "
            ".cache/dev-venv/bin/python",
            file=sys.stderr,
        )
        return 2
    valgt = [(r, h) for r, h in apolloer() if not args or r in args]
    if not valgt:
        print(f"ingen Apollo matcher {args}", file=sys.stderr)
        return 1
    for rum, host in valgt:
        try:
            hoved, linjer = asyncio.run(dump(host, 20))
        except Exception as e:  # noqa: BLE001 — én død node må ikke stoppe resten
            print(f"== {rum} ({host}) — ingen forbindelse: {e}")
            continue
        rapport(rum, host, hoved, linjer, raw)
    return 0


if __name__ == "__main__":
    sys.exit(main())
