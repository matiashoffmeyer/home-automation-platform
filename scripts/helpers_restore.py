#!/usr/bin/env python3
"""Restore helper values from the git snapshot.

Reads ``config_snapshots/helper_values.yaml`` (written by ``helpers_export.py``)
and sets the values through the Home Assistant REST API. Intended for a fresh
install or a lost ``.storage``, where sliders would otherwise fall back to
their defaults.

Usage::

  python3 scripts/helpers_restore.py            dry run: show the differences only
  python3 scripts/helpers_restore.py --apply    apply them

Policy (an old snapshot must never overwrite runtime state). What counts as
configuration is decided by ``helpers_export.is_config``, the same definition
the snapshot was written with, so the two scripts cannot drift apart:

  input_number    configuration values, except learning state and cursors
                  (``adaptive_*``, ``*_idx*``, ``*cursor*``, ``scene_spread_level``,
                  ``user_prefs_version``) and runtime values such as counters,
                  timestamps and the people-count floors
  input_boolean   configuration switches only (kill switches and preferences)
  input_datetime  configuration times only
  input_select    configuration selects only; runtime state machines
                  (``room_mode``, ``visit_stage``, ``house_mode`` and so on) are skipped

Only values that differ from the live state are written; there are no no-op
writes.
"""

import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAP = os.path.join(ROOT, "config_snapshots", "helper_values.yaml")
HA_URL = "http://homeassistant.local:8123"

NUMBER_SKIP = ("adaptive_",)
NUMBER_SKIP_CONTAINS = ("_idx", "cursor")
NUMBER_SKIP_EXACT = ("scene_spread_level", "user_prefs_version")
DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Samme definition som snapshot'et blev skrevet med (ingen anden kopi).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from helpers_export import is_config as _is_config

    # ÉN parser for det format export skriver (JSON-citerede strenge) — før
    # 2026-10-04 havde restore sin egen kopi, der kun forstod `\"`.
    from helpers_export import parse_snapshot as _shared_parse
except ImportError:  # scriptet kørt uden for scripts/ — konservativ fallback
    _shared_parse = None

    def _is_config(domain, name):
        return domain == "input_datetime" and name in {
            "puttelys_start",
            "natlys_start",
            "putning_vindue_start",
        }


def load_token():
    # HA_TOKEN (PC/.env) foretrækkes; on-HAOS-sessioner har kun
    # SUPERVISOR_TOKEN → skift base-URL til Supervisor-proxyen.
    global HA_URL
    if os.environ.get("HA_TOKEN"):
        return os.environ["HA_TOKEN"]
    for p in (os.path.join(ROOT, ".env"), "/config/.env"):
        if os.path.isfile(p):
            for line in open(p, encoding="utf-8"):
                line = line.strip()
                if line.startswith("HA_TOKEN"):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    if os.environ.get("SUPERVISOR_TOKEN"):
        HA_URL = "http://supervisor/core"
        return os.environ["SUPERVISOR_TOKEN"]
    raise SystemExit("HA_TOKEN/SUPERVISOR_TOKEN ikke fundet (env eller .env)")


def parse_snapshot(path):
    """Flad parser (ingen pyyaml): 'domain:' headers + '  name: value' linjer."""
    if _shared_parse is not None:
        return _shared_parse(path)
    data = {}
    dom = None
    for raw in open(path, encoding="utf-8"):
        line = raw.rstrip("\n")
        if not line or line.lstrip().startswith("#"):
            continue
        m = re.match(r"^(\w+):\s*$", line)
        if m:
            dom = m.group(1)
            data[dom] = {}
            continue
        m = re.match(r"^  (\S+):\s*(.*)$", line)
        if m and dom:
            val = m.group(2).strip()
            if len(val) >= 2 and val[0] == '"' and val[-1] == '"':
                val = val[1:-1].replace('\\"', '"')
            data[dom][m.group(1)] = val
    return data


def want_number(name):
    # Runtime-tællere (helpers_export.RUNTIME_NUMBERS) står kun i is_config —
    # spørg den, så restore aldrig gendanner det export bevidst udelader.
    if _shared_parse is not None and not _is_config("input_number", name):
        return False
    if name.startswith(NUMBER_SKIP):
        return False
    if name in NUMBER_SKIP_EXACT:
        return False
    return not any(s in name for s in NUMBER_SKIP_CONTAINS)


def call(tok, domain, service, payload, apply):
    if not apply:
        return
    req = urllib.request.Request(
        f"{HA_URL}/api/services/{domain}/{service}",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"},
    )
    urllib.request.urlopen(req, timeout=20)


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(SNAP):
        raise SystemExit(f"Snapshot mangler: {SNAP} (kør helpers_export.py + commit)")
    tok = load_token()
    snap = parse_snapshot(SNAP)
    req = urllib.request.Request(f"{HA_URL}/api/states", headers={"Authorization": "Bearer " + tok})
    live = {s["entity_id"]: s["state"] for s in json.load(urllib.request.urlopen(req, timeout=30))}

    planned = []
    for name, val in snap.get("input_number", {}).items():
        if not want_number(name) or not _isnum(val):
            continue
        eid = f"input_number.{name}"
        cur = live.get(eid)
        if _isnum(cur) and float(cur) == float(val):
            continue  # uændret → ingen no-op write
        planned.append(
            (eid, "input_number", "set_value", {"entity_id": eid, "value": float(val)}, cur, val)
        )
    for name, val in snap.get("input_boolean", {}).items():
        # Samme autoritet som exporten (notif_*, voice_cmd_*, nemlig_foretraek_*,
        # roborock_styrbar_* + *_enabled). Før 2026-10-04 stod her kun
        # `endswith('_enabled')`, så 162 af 283 snapshottede booleans aldrig
        # blev gendannet (review af P1-hærdningen).
        if not (
            _is_config("input_boolean", name)
            if _shared_parse is not None
            else name.endswith("_enabled")
        ):
            continue
        eid = f"input_boolean.{name}"
        if live.get(eid) != val and val in ("on", "off"):
            planned.append(
                (
                    eid,
                    "input_boolean",
                    "turn_on" if val == "on" else "turn_off",
                    {"entity_id": eid},
                    live.get(eid),
                    val,
                )
            )
    for name, val in snap.get("input_datetime", {}).items():
        if not _is_config("input_datetime", name):
            continue
        eid = f"input_datetime.{name}"
        if live.get(eid) != val:
            if DATE_ONLY_RE.match(val):
                key = "date"  # dato-only helper (fx indkøbs-ankeret)
            elif len(val) <= 8:
                key = "time"
            else:
                key = "datetime"
            planned.append(
                (
                    eid,
                    "input_datetime",
                    "set_datetime",
                    {"entity_id": eid, key: val},
                    live.get(eid),
                    val,
                )
            )
    for name, val in snap.get("input_select", {}).items():
        if not _is_config("input_select", name):
            continue
        eid = f"input_select.{name}"
        if live.get(eid) != val:
            planned.append(
                (
                    eid,
                    "input_select",
                    "select_option",
                    {"entity_id": eid, "option": val},
                    live.get(eid),
                    val,
                )
            )
    for name, val in snap.get("input_text", {}).items():
        if not _is_config("input_text", name):
            continue
        eid = f"input_text.{name}"
        if live.get(eid) != val:
            planned.append(
                (
                    eid,
                    "input_text",
                    "set_value",
                    {"entity_id": eid, "value": val},
                    live.get(eid),
                    val,
                )
            )

    mode = "APPLY" if apply else "DRY-RUN"
    print(f"[{mode}] {len(planned)} helper(s) afviger fra snapshot:")
    for eid, dom, svc, payload, old, new in planned:
        print(f"  {eid}: {old} -> {new}")
        call(tok, dom, svc, payload, apply)
    if not apply and planned:
        print("\nKør med --apply for at anvende.")
    elif apply:
        print("Anvendt.")


def _isnum(s):
    try:
        float(s)
        return True
    except ValueError, TypeError:
        return False


if __name__ == "__main__":
    main()
