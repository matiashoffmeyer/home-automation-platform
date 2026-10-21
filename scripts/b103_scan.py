#!/usr/bin/env python3
"""Find state triggers that fire falsely on a ``template.reload``.

A template reload sends every template entity through ``unavailable``. A state
trigger without an explicit ``from:`` reads both ``unavailable -> off`` and
``unavailable -> on`` as a real edge. Both directions are dangerous: templates
re-render immediately after the reload, so a sensor that *is* on goes
``unavailable -> on``. (B103 is the backlog item where this was first traced.)

Run before any template reload; the pre-commit hook runs it as well::

    python3 scripts/b103_scan.py

Exit 1 if vulnerable triggers remain. A trigger whose edge is itself the
evidence is listed in ``ALLOWLIST``, with the reason.
"""

import glob
import os
import sys
from functools import cache

import yaml

DOMAINS = ("sensor", "binary_sensor", "switch", "number", "select", "button", "image")

# Automations der BEVIDST skal fyre på `unavailable -> X`, fordi det er hele
# deres formål. Et mekanisk indsat `from:` gør dem til en garanteret no-op —
# derfor står de her frem for at blive "rettet" af næste sweep.
# Tilføjer du en: skriv HVORFOR flanken er beviset, ikke artefaktet.
ALLOWLIST = {
    # Freder et rum hvis occupancy-kanal er blind, og skal netop sweepe igen NÅR
    # kanalen kommer tilbage og melder tomt. 2026-09-09 fik den `from: "on"` af
    # dette sweep, hvilket gjorde dens egen "kom kanalen tilbage fra blind?"-
    # condition usand for evigt = fredningen blev permanent.
    "airbnb_dormant_resweep_efter_blind_kanal": (
        "lever af flanken `unavailable -> off`; et from: dræber den"
    ),
    # Retur-grenen (`sove_retur_til_seng` to: on) RYDDER kun afgangs-stemplet,
    # og det er den sikre retning (et tabt stempel koster minutter, et holdt
    # stempel rydder godnat under en nat-tur). Sensoren er trigger-baseret og
    # står `unknown` til første sample, så et `from: "off"` ville sluge den
    # allerførste ægte retur efter en restart. Vurderet 2026-10-07 (P9).
    "sove_voksen_afgang_sweep": (
        "falsk retur rydder kun et stempel (sikker retning); from: sluger første ægte retur"
    ),
}


# Én HA-kompatibel slugify for alle scripts (konsolidering 2026-10-04): den
# lokale version her lavede å → "aa", men HA laver å → "a".
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ha_slug import slugify as slug  # noqa: E402


class _Loader(getattr(yaml, "CSafeLoader", yaml.SafeLoader)):
    """safe_load der tåler HA-tags (!include, !include_dir_named, !secret …).

    Ren yaml.safe_load kaster på dem, og scanneren sprang så filen TAVST over
    (init_user_preferences fik !include_dir_named i P1 2026-10-04).
    CSafeLoader (libyaml) når den findes: 11 s → ~1 s, så scanneren kan køre i
    pre-commit."""


_Loader.add_multi_constructor("!", lambda loader, suffix, node: None)


@cache
def _load(path):
    with open(path, encoding="utf-8") as f:
        return yaml.load(f, Loader=_Loader)  # noqa: S506 - a SafeLoader subclass


def collect_template_entities() -> set:
    found = set()

    def walk(block):
        if isinstance(block, list):
            for item in block:
                walk(item)
        elif isinstance(block, dict):
            for dom in DOMAINS:
                entries = block.get(dom)
                if isinstance(entries, list):
                    for e in entries:
                        if isinstance(e, dict) and e.get("name"):
                            found.add(f"{dom}.{slug(str(e['name']))}")

    for path in glob.glob("packages/*.yaml") + glob.glob("*.yaml"):
        try:
            doc = _load(path)
        except Exception:
            continue
        if isinstance(doc, dict) and "template" in doc:
            walk(doc["template"])
    return found


def scan(template_entities: set) -> list:
    hits = []
    for path in glob.glob("automations/*.yaml") + glob.glob("packages/*.yaml"):
        try:
            doc = _load(path)
        except Exception:
            continue
        autos = (
            doc
            if isinstance(doc, list)
            else (doc.get("automation") if isinstance(doc, dict) else None)
        )
        if not isinstance(autos, list):
            continue
        for auto in autos:
            if not isinstance(auto, dict):
                continue
            if auto.get("id") in ALLOWLIST:
                continue
            for trig in auto.get("trigger") or auto.get("triggers") or []:
                if not isinstance(trig, dict):
                    continue
                if (trig.get("platform") or trig.get("trigger")) != "state":
                    continue
                if trig.get("to") is None:
                    continue
                # `not_from` er svaret naar `to:` ikke er on/off (enum-sensorer
                # som sensor.activity_state): den udelukker artefakterne uden at
                # skulle liste alle gyldige fra-tilstande. Kun en liste der
                # daekker BEGGE sentinels er en gyldig guard.
                nf = trig.get("not_from")
                nf = [nf] if isinstance(nf, str) else (nf or [])
                if "from" in trig or {"unknown", "unavailable"} <= set(nf):
                    continue
                eids = trig.get("entity_id") or []
                if isinstance(eids, str):
                    eids = [eids]
                bad = [e for e in eids if e in template_entities]
                if bad:
                    hits.append((path, auto.get("id"), trig["to"], bad))
    return hits


def main() -> int:
    tmpl = collect_template_entities()
    hits = scan(tmpl)
    print(f"template-entities: {len(tmpl)}")
    print(f"SÅRBARE triggers (to: uden from: på en template-entity): {len(hits)}")
    off = [h for h in hits if h[2] in ("off", ["off"])]
    print(f"  heraf sluk-veje (to: 'off'): {len(off)}")
    for path, aid, to, ents in hits:
        print(f"  {path}  {aid}  to={to!r}  {ents}")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
