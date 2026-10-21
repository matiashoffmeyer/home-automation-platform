#!/usr/bin/env python3
"""Copied entity lists ("rosters") and where they have drifted apart.

Drifting rosters (failure class #16) and one rule coded in two places (#2)
are the most cited failure classes in the project's history. Measured on
2026-10-04: 305 lists with at least 3 entities, 25 of them copied verbatim
into several files (152 copies), and 92 near-duplicate pairs (Jaccard >= 0.6),
some deliberate and many drift.

Usage::

  python3 scripts/roster_drift.py            report: identical and drifted pairs
  python3 scripts/roster_drift.py --staged   pre-commit: did you edit a list that has
                                             twins? They are listed, with the OLD version
  python3 scripts/roster_drift.py --json     machine-readable

A deliberately different pair (for example "living room" against "living room
plus dining room") is approved in ``scripts/roster_drift_allow.txt`` with both
lists' fingerprints and a reason. If either list changes, its fingerprint
changes and the pair must be judged again: an approval applies to the content
it was given for.

To consolidate a roster, move the list to ``rosters/<name>.yaml``, use
``entity_id: !include ../rosters/<name>.yaml`` everywhere, and prove with
``python3 scripts/ha_offline.py equiv HEAD`` that Home Assistant sees exactly
the same configuration. Standard library only (runs in pre-commit without a
venv).
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ALLOW = REPO / "scripts" / "roster_drift_allow.txt"
# rosters/ (P2): den fælles liste sammenlignes med de kopier der er tilbage.
SCAN_DIRS = ("automations", "packages", "script_pkg", "rosters")
DOM = (
    r"(?:light|switch|binary_sensor|sensor|input_boolean|input_number|input_select|"
    r"input_text|input_datetime|cover|media_player|script|automation|scene|timer|person|"
    r"device_tracker|fan|climate|number|select|button|event|lock|vacuum|camera)"
)
ENT = re.compile(rf"\b({DOM}\.[a-z0-9_]+)\b")
BLOCK_ITEM = re.compile(r"^(\s*)- ([a-z_]+\.[a-z0-9_]+)\s*(#.*)?$")
FLOW = re.compile(r"\[\s*((?:['\"]" + DOM + r"\.[a-z0-9_]+['\"]\s*,?\s*(?:#[^\n]*)?\s*){3,})\]")
MIN_LEN = 3
NEAR = 0.6


def fingerprint(members: frozenset) -> str:
    return hashlib.sha1(",".join(sorted(members)).encode()).hexdigest()[:8]


def extract(text: str, rel: str) -> list[dict]:
    """Alle lister med ≥ 3 entities: YAML-blokke og Jinja/flow-lister."""
    lines = text.split("\n")
    out = []
    i = 0
    while i < len(lines):
        m = BLOCK_ITEM.match(lines[i])
        if m and ENT.fullmatch(m.group(2)):
            ind, j, items = m.group(1), i, []
            while j < len(lines):
                mm = BLOCK_ITEM.match(lines[j])
                if mm and mm.group(1) == ind and ENT.fullmatch(mm.group(2)):
                    items.append(mm.group(2))
                    j += 1
                elif lines[j].strip() == "" or lines[j].lstrip().startswith("#"):
                    j += 1
                else:
                    break
            if len(items) >= MIN_LEN:
                out.append({"file": rel, "line": i + 1, "end": j, "members": frozenset(items)})
            i = max(j, i + 1)
            continue
        i += 1
    for m in FLOW.finditer(text):
        members = frozenset(ENT.findall(m.group(1)))
        if len(members) >= MIN_LEN:
            start = text[: m.start()].count("\n") + 1
            out.append(
                {
                    "file": rel,
                    "line": start,
                    "end": start + m.group(0).count("\n") + 1,
                    "members": members,
                }
            )
    return out


def scan_tree() -> list[dict]:
    lists = []
    for d in SCAN_DIRS:
        for f in sorted((REPO / d).glob("*.yaml")):
            lists += extract(f.read_text(encoding="utf-8", errors="ignore"), f"{d}/{f.name}")
    return lists


def load_allow() -> set[frozenset]:
    pairs = set()
    if ALLOW.exists():
        for line in ALLOW.read_text(encoding="utf-8").splitlines():
            code = line.split("#", 1)[0].split()
            if len(code) >= 2:
                pairs.add(frozenset(code[:2]))
    return pairs


def jaccard(a: frozenset, b: frozenset) -> float:
    return len(a & b) / len(a | b)


def where(lst: dict) -> str:
    return f"{lst['file']}:{lst['line']}"


def report(lists: list[dict], as_json: bool) -> int:
    allow = load_allow()
    by_set = defaultdict(list)
    for lst in lists:
        by_set[lst["members"]].append(lst)
    identical = [v for v in by_set.values() if len({x["file"] for x in v}) > 1]
    near = []
    for a, b in itertools.combinations(by_set, 2):
        if len(a & b) < MIN_LEN:
            continue
        j = jaccard(a, b)
        if j >= NEAR and frozenset((fingerprint(a), fingerprint(b))) not in allow:
            near.append((j, a, b))
    near.sort(key=lambda x: (-x[0], where(by_set[x[1]][0])))
    if as_json:
        print(
            json.dumps(
                {
                    "lists": len(lists),
                    "identical": [[where(x) for x in v] for v in identical],
                    "near": [
                        {
                            "jaccard": round(j, 2),
                            "a": where(by_set[a][0]),
                            "b": where(by_set[b][0]),
                            "fp": [fingerprint(a), fingerprint(b)],
                            "only_a": sorted(a - b),
                            "only_b": sorted(b - a),
                        }
                        for j, a, b in near
                    ],
                },
                ensure_ascii=False,
                indent=1,
            )
        )
        return 0
    print(f"🔎 {len(lists)} entity-lister (≥ {MIN_LEN}) i {', '.join(SCAN_DIRS)}\n")
    print(
        f"== Identiske lister i flere filer: {len(identical)} "
        f"({sum(len(v) for v in identical)} kopier) — konsoliderings-kandidater =="
    )
    for v in sorted(identical, key=lambda v: -len(v)):
        sample = sorted(v[0]["members"])
        print(
            f"  {len(v)}× [{fingerprint(v[0]['members'])}] {len(sample)} entities "
            f"({', '.join(sample[:3])}{', …' if len(sample) > 3 else ''})"
        )
        print("     " + "  ".join(where(x) for x in v[:8]) + ("  …" if len(v) > 8 else ""))
    print(
        f"\n== Nær-dubletter (J ≥ {NEAR}, ikke godkendt i roster_drift_allow.txt): {len(near)} =="
    )
    for j, a, b in near:
        print(
            f"  J={j:.2f} {where(by_set[a][0])} [{fingerprint(a)}]  vs  "
            f"{where(by_set[b][0])} [{fingerprint(b)}]"
        )
        if a - b:
            print(f"     kun venstre: {', '.join(sorted(a - b))}")
        if b - a:
            print(f"     kun højre:   {', '.join(sorted(b - a))}")
    print("\nBevidst forskel? Tilføj '<fp_a> <fp_b>  # grund' til scripts/roster_drift_allow.txt.")
    return 0


def _git(*args: str) -> str:
    r = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def staged(lists: list[dict]) -> int:
    """JIT: hvilke tvillinger skal med i den commit du er ved at lave?"""
    files = [
        f
        for f in _git("diff", "--cached", "--name-only", "--diff-filter=AM").split()
        if f.endswith(".yaml") and f.split("/", 1)[0] in SCAN_DIRS
    ]
    if not files:
        return 0
    warnings = []
    for rel in files:
        old_lists = extract(_git("show", f"HEAD:{rel}"), rel)
        new_lists = extract(_git("show", f":{rel}"), rel)
        new_sets = {x["members"] for x in new_lists}
        # En liste der fandtes før commit'en, men ikke længere findes ordret =
        # en roster du har rettet. Hvem andre har stadig den GAMLE version?
        for old in old_lists:
            if old["members"] in new_sets:
                continue
            # Også tvillinger i SAMME fil — den rettede liste selv har jo det
            # nye indhold nu og matcher derfor ikke den gamle mængde.
            twins = [x for x in lists if x["members"] == old["members"]]
            if twins:
                new = min(new_lists, key=lambda n: abs(n["line"] - old["line"]), default=None)
                added = sorted(new["members"] - old["members"]) if new else []
                removed = sorted(old["members"] - new["members"]) if new else []
                delta = (
                    (f" (+{', '.join(added)}" if added else " (")
                    + (f" −{', '.join(removed)}" if removed else "")
                    + ")"
                )
                warnings.append(
                    f"{rel}:{old['line']} rettet{delta if new else ''} — "
                    f"{len(twins)} tvilling(er) har stadig den gamle liste: "
                    + ", ".join(where(t) for t in twins[:6])
                )
    if warnings:
        print(
            "⚠️  roster-drift (fejlklasse #16): du rettede en liste der står andre steder.",
            file=sys.stderr,
        )
        for w in warnings:
            print(f"   {w}", file=sys.stderr)
        print(
            "   Ret tvillingerne i samme commit — eller konsolidér til rosters/ (se --help).",
            file=sys.stderr,
        )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--staged", action="store_true", help="JIT-tjek af staged ændringer")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    lists = scan_tree()
    return staged(lists) if args.staged else report(lists, args.json)


if __name__ == "__main__":
    sys.exit(main())
