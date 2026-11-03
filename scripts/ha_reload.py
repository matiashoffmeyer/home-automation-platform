#!/usr/bin/env python3
"""Reload template entities without letting the reload change the house.

A ``template.reload`` sends every template entity through ``unavailable`` and
then through intermediate values. Triggers read those as real edges. On
2026-11-02, four bare reloads made the price factor flicker
0.768 -> 1.0 -> 0.64 -> 0.768, and each step rescaled every light that was on.
The steps did not cancel out, so open plan got darker with every reload (the
reading lamp ended on 17 % instead of 61 %). The rule in CLAUDE.md was text
only. ``scripts/reload_guard.py`` now rejects a bare reload, and this script is
the only way to do one:

1. ``b103_scan`` must pass (no ``to:`` without ``from:`` on a template entity).
2. Snapshot every light (state, brightness, colour) and every ``room_mode``.
3. Reload.
4. Wait ``--settle`` seconds (default 45; the price rescale needs 30 s of hold).
5. Diff. A light that was ON and is now off or more than 3 % dimmer is damage
   from the reload. It is put back with a ``scene.create`` + ``scene.turn_on``
   of ``scene.reload_restore``. That scene is allowlisted in
   ``automations/manual_override.yaml``, so the restore does not put the room
   in Manual (failure class #11). A light that turned ON, a brighter light and a
   changed room_mode are reported only: those can be a person who walked in
   during the window.

Usage::

    python3 scripts/ha_reload.py templates [--settle 45] [--no-restore]

Exit 0 = nothing changed or everything was restored, 1 = b103 failed,
2 = there were changes that were reported but not restored.
"""

import argparse
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hq import HA  # noqa: E402

DIM_TOLERANCE = 8  # brightness 0-254; ~3 %, above rounding and transition noise
COLOUR_ATTRS = ("color_temp_kelvin", "hs_color", "color_mode")


def snapshot(ha):
    lights, modes = {}, {}
    for s in ha.req("/states"):
        eid = s["entity_id"]
        if eid.startswith("light."):
            a = s["attributes"]
            if a.get("entity_id"):  # groups follow their members
                continue
            lights[eid] = {"state": s["state"], "brightness": a.get("brightness")}
            for k in COLOUR_ATTRS:
                if a.get(k) is not None:
                    lights[eid][k] = a[k]
        elif eid.startswith("input_select.room_mode_"):
            modes[eid] = s["state"]
    return lights, modes


def harmed(before, after):
    """Lights the reload darkened: on -> off, or on and dimmer."""
    out = {}
    for eid, b in before.items():
        a = after.get(eid)
        if b["state"] != "on" or a is None or a["state"] == "unavailable":
            continue
        if a["state"] == "off":
            out[eid] = b
        elif (b.get("brightness") or 0) - (a.get("brightness") or 0) > DIM_TOLERANCE:
            out[eid] = b
    return out


def scene_entities(harm):
    ents = {}
    for eid, b in harm.items():
        e = {"state": "on"}
        if b.get("brightness") is not None:
            e["brightness"] = b["brightness"]
        if b.get("color_mode") == "color_temp" and b.get("color_temp_kelvin"):
            e["color_temp_kelvin"] = b["color_temp_kelvin"]
        elif b.get("hs_color"):
            e["hs_color"] = b["hs_color"]
        ents[eid] = e
    return ents


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("what", choices=["templates"])
    p.add_argument("--settle", type=int, default=45)
    p.add_argument("--no-restore", action="store_true")
    args = p.parse_args()

    here = os.path.dirname(os.path.abspath(__file__))
    if subprocess.run([sys.executable, os.path.join(here, "b103_scan.py")]).returncode:
        print("ha_reload: b103_scan fejlede — ret triggerne før reload.", file=sys.stderr)
        return 1

    ha = HA()
    before, modes_before = snapshot(ha)
    print(f"snapshot: {len(before)} lys, {len(modes_before)} room_modes")
    ha.req("/services/template/reload", body={})
    print(f"template.reload sendt — venter {args.settle} s")
    time.sleep(args.settle)
    after, modes_after = snapshot(ha)

    harm = harmed(before, after)
    other = [
        f"{e}: {before[e]['state']}/{before[e].get('brightness')} → "
        f"{after[e]['state']}/{after[e].get('brightness')}"
        for e in before
        if e in after
        and e not in harm
        and (
            before[e]["state"] != after[e]["state"]
            or abs((before[e].get("brightness") or 0) - (after[e].get("brightness") or 0))
            > DIM_TOLERANCE
        )
        and after[e]["state"] != "unavailable"
    ]
    modes = [
        f"{e}: {modes_before[e]} → {v}"
        for e, v in modes_after.items()
        if modes_before.get(e) not in (None, v)
    ]

    for eid, b in harm.items():
        a = after[eid]
        print(
            f"  MØRKLAGT af reload: {eid} {b['state']}/{b.get('brightness')} → "
            f"{a['state']}/{a.get('brightness')}"
        )
    for line in other:
        print(f"  ændret (kun rapporteret): {line}")
    for line in modes:
        print(f"  room_mode ændret (kun rapporteret): {line}")

    if harm and not args.no_restore:
        ha.req(
            "/services/scene/create",
            body={"scene_id": "reload_restore", "entities": scene_entities(harm)},
        )
        ha.req(
            "/services/scene/turn_on", body={"entity_id": "scene.reload_restore", "transition": 2}
        )
        print(f"gendannet {len(harm)} lys via scene.reload_restore")
    if not (harm or other or modes):
        print("ingen lys eller room_modes ændret af reloaden ✓")
        return 0
    return 2 if (other or modes or (harm and args.no_restore)) else 0


if __name__ == "__main__":
    sys.exit(main())
