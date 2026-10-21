#!/usr/bin/env python3
"""Doubt gate for the trainers: ask the household only when a guess is uncertain.

A trainer asks, through an actionable notification, whether the house guessed
right. Measured over 14 days, the activity trainer was still asking about a
guess that had been right eight times out of eight. This script reads
``ai_feedback/<slug>_feedback.jsonl``, joins answers to questions on the ask
id, and gives each guess its recent track record. A guess is *certain* when
its latest ``min_svar`` answers within ``dage`` days are at least ``min_pct``
percent "rigtig" (right). "delvist" (partly) and "forkert" (wrong) count as not
right; "afvist" (dismissed) and "vedikke" (don't know) do not count at all.

Why the latest N answers rather than all of them: an old error from an outage
that has since been fixed must be able to age out. The day window means that a
certain guess, never asked about again, eventually loses its answers and is
validated again.

Called by the command_line sensors ``sensor.traener_aktivitet_sikre_gaet`` and
``sensor.traener_dormant_sikre_gaet`` (packages/ai_trainer.yaml). Output is one
JSON line on stdout; the exit code is always 0::

    {"antal_sikre": 3, "sikre": [...], "record": {"cooking": "4/8", ...}}

Usage (slug, min_svar, min_pct, dage)::

    python3 scripts/trainer_tvivl.py aktivitet 8 90 120
"""

import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta

LOG_DIR = os.environ.get("AI_FEEDBACK_DIR", "/config/ai_feedback")


def main() -> int:
    slug = sys.argv[1] if len(sys.argv) > 1 else "aktivitet"
    try:
        min_svar = max(1, int(float(sys.argv[2]))) if len(sys.argv) > 2 else 8
        min_pct = float(sys.argv[3]) if len(sys.argv) > 3 else 90.0
        dage = float(sys.argv[4]) if len(sys.argv) > 4 else 120.0
    except ValueError:
        min_svar, min_pct, dage = 8, 90.0, 120.0
    out = {"antal_sikre": 0, "sikre": [], "record": {}}
    if not re.fullmatch(r"[a-z_]{1,40}", slug):
        print(json.dumps(out))
        return 0
    path = os.path.join(LOG_DIR, f"{slug}_feedback.jsonl")
    asks, svar = {}, []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r.get("type") == "ask":
                    asks[str(r.get("id"))] = r
                elif r.get("type") == "answer":
                    svar.append(r)
    except OSError:
        print(json.dumps(out))
        return 0
    graense = datetime.now().astimezone() - timedelta(days=dage)
    pr_gaet = defaultdict(list)
    for r in svar:
        a = asks.get(str(r.get("id")))
        if a is None or r.get("answer") in (None, "afvist", "vedikke"):
            continue
        try:
            ts = datetime.fromisoformat(a["ts"])
        except KeyError, ValueError:
            continue
        if ts < graense:
            continue
        pr_gaet[a.get("guess")].append((ts, r.get("answer") == "rigtig"))
    for gaet, liste in pr_gaet.items():
        if not gaet:
            continue
        liste.sort()
        seneste = liste[-min_svar:]
        rigtige = sum(1 for _, ok in seneste if ok)
        out["record"][gaet] = f"{rigtige}/{len(seneste)}"
        if len(seneste) >= min_svar and 100.0 * rigtige / len(seneste) >= min_pct:
            out["sikre"].append(gaet)
    out["sikre"].sort()
    out["antal_sikre"] = len(out["sikre"])
    print(json.dumps(out, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
