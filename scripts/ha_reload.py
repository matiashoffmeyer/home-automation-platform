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

   EXCEPT a lasting consequence (2026-11-18): the deploy can make a template
   REALLY change (a new input to ``binary_sensor.projektor_aktiv``) and an
   automation acts on it inside the settle window. Dark Mode started 17:35:59
   and turned the living room off; the restore lit it again 16 s later and
   repainted the kitchen chain, which then read the restore's user_id as the
   user's hand (failure class #27: a handback replaying a pre-loan snapshot).
   A darkened light whose LAST change in the window was an automation/script
   acting on ``state of X``, where X ended in a different real state than it
   had before the reload, is reported, not restored. A flicker (X back where it
   started, the 2026-11-02 price factor) or a change with no automation behind
   it (template unavailable cascade) is restored as before. Attribution reads
   the recorder via ``hq.who_db``; lights outside the recorder inherit the
   cause of a recorded light changed in the same context. Without the DB it
   falls back to restoring.

Usage::

    python3 scripts/ha_reload.py templates [--settle 45] [--no-restore]

Exit 0 = nothing changed or everything was restored, 1 = b103 failed,
2 = there were changes that were reported but not restored.
"""

import argparse
import os
import re
import sqlite3
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hq import DB_PATH, HA, HQError, who_db  # noqa: E402

DIM_TOLERANCE = 8  # brightness 0-254; ~3 %, above rounding and transition noise
COLOUR_ATTRS = ("color_temp_kelvin", "hs_color", "color_mode")
CAUSE_RE = re.compile(r"state of ([a-z_]+\.\w+)")
VOID = (None, "unavailable", "unknown")


def snapshot(ha):
    lights, modes, every, ctx = {}, {}, {}, {}
    for s in ha.req("/states"):
        eid = s["entity_id"]
        every[eid] = s["state"]
        ctx[eid] = (s.get("context") or {}).get("id")
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
    return lights, modes, every, ctx


def lasting_cause(conn, eid, start, end, every_before, every_after):
    """(who, cause, before, after) when the light's last change in the window
    was an automation/script acting on ``state of <cause>`` and <cause> ended in
    a different real state than before the reload — a consequence of the deploy,
    not reload damage. Otherwise None (restore as before)."""
    if conn is None:
        return None
    try:
        rows = who_db(conn, eid, start, end, attr_changes=True)
    except HQError, sqlite3.Error:
        return None
    if not rows:
        return None
    _ts, _fra, _til, who, det = rows[-1]
    m = CAUSE_RE.search(det or "")
    if not who.startswith(("automation.", "script.")) or not m:
        return None
    cause = m.group(1)
    b, a = every_before.get(cause), every_after.get(cause)
    if b in VOID or a in VOID or b == a:
        return None
    return who, cause, b, a


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
    before, modes_before, every_before, _ = snapshot(ha)
    print(f"snapshot: {len(before)} lys, {len(modes_before)} room_modes")
    t0 = datetime.now(UTC) - timedelta(seconds=1)
    ha.req("/services/template/reload", body={})
    print(f"template.reload sendt — venter {args.settle} s")
    time.sleep(args.settle)
    after, modes_after, every_after, ctx_after = snapshot(ha)

    harm = harmed(before, after)
    conn = (
        sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=15)
        if os.path.exists(DB_PATH)
        else None
    )
    kept = {}
    for eid in list(harm):
        c = lasting_cause(conn, eid, t0, datetime.now(UTC), every_before, every_after)
        if c:
            kept[eid] = c
            del harm[eid]
    # Lights outside the recorder (the sofa spots, B227) cannot be attributed
    # themselves, but one service call stamps every light it touches with the
    # SAME context id → they share the cause of a recorded sibling.
    by_ctx = {ctx_after.get(e): c for e, c in kept.items() if ctx_after.get(e)}
    for eid in list(harm):
        if ctx_after.get(eid) in by_ctx:
            kept[eid] = by_ctx[ctx_after[eid]]
            del harm[eid]
    other = [
        f"{e}: {before[e]['state']}/{before[e].get('brightness')} → "
        f"{after[e]['state']}/{after[e].get('brightness')}"
        for e in before
        if e in after
        and e not in harm
        and e not in kept
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
    for eid, (who, cause, b, a) in kept.items():
        print(
            f"  IKKE gendannet — varig følge: {eid} {before[eid]['state']}/"
            f"{before[eid].get('brightness')} → {after[eid]['state']}/"
            f"{after[eid].get('brightness')} af {who} ← {cause} {b}→{a}"
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
    if not (harm or kept or other or modes):
        print("ingen lys eller room_modes ændret af reloaden ✓")
        return 0
    return 2 if (kept or other or modes or (harm and args.no_restore)) else 0


if __name__ == "__main__":
    sys.exit(main())
