#!/usr/bin/env python3
"""Map every light and cover to the automations that switch it on or off, change its colour, or move it.

This is the ground truth for the Triggers dashboard.

  python3 scripts/triggers_scan.py          human-readable report
  python3 scripts/triggers_scan.py --json   raw JSON

The heuristic is deliberately simple; check by hand when in doubt:
  - It walks each automation block (alias) in automations/*.yaml and packages/*.yaml.
  - It finds ``light.turn_on``/``light.turn_off`` and ``cover.*`` calls in the action tree.
  - It classifies them as ON, OFF, COLOUR (rgb/hs/color_temp/xy/effect) or cover.
  - Targets are a direct entity_id or a light group (light_groups.yaml), which
    is expanded to the physical bulbs. Templated targets (``{{ ... }}``) are
    reported as DYNAMIC.
"""

import glob
import json
import os
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rosters  # noqa: E402  roster-!include → entity-listen


# --- permissiv YAML-loader (ignorér HA's !include/!secret/!input tags) ---------
class _Loader(yaml.SafeLoader):
    pass


def _ignore(loader, tag_suffix, node):
    # En roster-!include (rosters/<navn>.yaml, konsolidering P2) er en entity-
    # liste — uden dette så scanneren sti-strengen i stedet for lamperne.
    roster = rosters.yaml_tag(loader, tag_suffix, node)
    if roster is not None:
        return roster
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    return loader.construct_mapping(node)


_Loader.add_multi_constructor("!", _ignore)


def load_yaml(path):
    with open(path, encoding="utf-8") as f:
        try:
            return yaml.load(f, Loader=_Loader)  # noqa: S506 - a SafeLoader subclass
        except Exception as e:  # noqa
            print(f"  ! kunne ikke parse {path}: {e}", file=sys.stderr)
            return None


# --- lys-grupper: gruppe-slug → medlemmer (rekursivt) --------------------------
def load_groups():
    data = load_yaml(os.path.join(ROOT, "packages", "light_groups.yaml")) or {}
    raw = {}
    for item in data.get("light", []) or []:
        if isinstance(item, dict) and item.get("platform") == "group":
            uid = item.get("unique_id")
            if uid:
                raw["light." + uid] = [e for e in (item.get("entities") or [])]

    # rekursiv ekspansion (grupper kan indeholde grupper)
    def expand(ent, seen):
        if ent in seen:
            return set()
        seen = seen | {ent}
        if ent in raw:
            out = set()
            for m in raw[ent]:
                out |= expand(m, seen)
            return out
        return {ent}

    return {g: sorted(expand(g, set())) for g in raw}, raw


GROUPS, GROUPS_RAW = load_groups()


def resolve_targets(entity_ids):
    """entity_id-liste → (fysiske pærer/covers, dynamisk?)."""
    physical, dynamic = set(), False
    for e in entity_ids:
        if not isinstance(e, str):
            dynamic = True
            continue
        if "{{" in e or "{%" in e:
            dynamic = True
            continue
        if e in GROUPS:
            physical |= set(GROUPS[e])
        else:
            physical.add(e)
    return physical, dynamic


# --- walk action-træet og saml service-kald ------------------------------------
COLOR_KEYS = {
    "rgb_color",
    "hs_color",
    "color_temp",
    "color_temp_kelvin",
    "xy_color",
    "rgbw_color",
    "color_name",
    "effect",
}


def collect_entity_ids(data):
    """træk entity_id ud af target: / data: / top-level."""
    ids = []
    for holder in (
        data,
        data.get("target") if isinstance(data, dict) else None,
        data.get("data") if isinstance(data, dict) else None,
    ):
        if isinstance(holder, dict):
            eid = holder.get("entity_id")
            if isinstance(eid, str):
                ids.append(eid)
            elif isinstance(eid, list):
                ids += [x for x in eid]
    return ids


def has_color(data):
    def scan(d):
        if isinstance(d, dict):
            for k, v in d.items():
                if k in COLOR_KEYS:
                    return True
                if scan(v):
                    return True
        elif isinstance(d, list):
            return any(scan(x) for x in d)
        return False

    return scan(data)


def walk_actions(node, out):
    """rekursivt find alle service/action-kald."""
    if isinstance(node, dict):
        svc = node.get("service") or node.get("action")
        if isinstance(svc, str):
            ids = collect_entity_ids(node)
            if svc in ("light.turn_on", "homeassistant.turn_on"):
                out.append(("FARVE" if has_color(node) else "ON", ids, svc))
            elif svc in ("light.turn_off", "homeassistant.turn_off"):
                out.append(("OFF", ids, svc))
            elif svc == "light.toggle":
                out.append(("TOGGLE", ids, svc))
            elif svc.startswith("cover."):
                kind = {"cover.open_cover": "GARDIN-OP", "cover.close_cover": "GARDIN-NED"}.get(
                    svc, "GARDIN"
                )
                out.append((kind, ids, svc))
        for v in node.values():
            walk_actions(v, out)
    elif isinstance(node, list):
        for v in node:
            walk_actions(v, out)


# --- gå gennem alle automations ------------------------------------------------
def iter_automations():
    files = sorted(glob.glob(os.path.join(ROOT, "automations", "*.yaml")))
    files += sorted(glob.glob(os.path.join(ROOT, "packages", "*.yaml")))
    for path in files:
        rel = os.path.relpath(path, ROOT)
        data = load_yaml(path)
        if data is None:
            continue
        blocks = []
        if isinstance(data, list):
            blocks = data
        elif isinstance(data, dict):
            a = data.get("automation")
            if isinstance(a, list):
                blocks += a
            elif isinstance(a, dict):
                blocks.append(a)
        for b in blocks:
            if isinstance(b, dict) and (
                "trigger" in b or "triggers" in b or "action" in b or "actions" in b
            ):
                yield rel, b


def main():
    # entity → {ON/OFF/FARVE/...: set(alias)}, + dynamiske pr. fil
    entity_map = {}
    dynamic_hits = []  # (rel, alias, kind)
    for rel, block in iter_automations():
        alias = block.get("alias") or block.get("id") or "(uden alias)"
        calls = []
        walk_actions(block.get("action") or block.get("actions") or [], calls)
        for kind, ids, _svc in calls:
            physical, dyn = resolve_targets(ids)
            for ent in physical:
                entity_map.setdefault(ent, {}).setdefault(kind, set()).add(f"{alias}  [{rel}]")
            if dyn or not ids:
                dynamic_hits.append((rel, alias, kind))

    out = {
        "entities": {
            e: {k: sorted(v) for k, v in kinds.items()} for e, kinds in sorted(entity_map.items())
        },
        "dynamic": sorted(set(dynamic_hits)),
    }

    if "--json" in sys.argv:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    for ent, kinds in out["entities"].items():
        print(f"\n=== {ent} ===")
        for kind in ("ON", "FARVE", "OFF", "TOGGLE", "GARDIN-OP", "GARDIN-NED", "GARDIN"):
            if kind in kinds:
                print(f"  {kind}:")
                for a in kinds[kind]:
                    print(f"    - {a}")
    print(
        f"\n\n### DYNAMISKE targets ({len(out['dynamic'])}) — templated entity_id, tjek manuelt ###"
    )
    for rel, alias, kind in out["dynamic"]:
        print(f"  [{kind}] {alias}  ({rel})")


if __name__ == "__main__":
    main()
