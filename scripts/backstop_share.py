#!/usr/bin/env python3
"""backstop_share.py: lamps whose backstop does the primary exit's job.

Failure class 25: an exit that waits for a radar to say ONE thing inherits the
radar's lie the other way. "Empty" never comes under a still ghost, "someone is
here" never comes while the radar is blind, "off for N min" is erased by a
blip. Nothing errors: the watchdog behind the exit quietly takes over, half an
hour late. 2026-11-02 (B290): the bedroom pre-light's fast clear needed the raw
occupancy off, and the ghost-still watchdog switched the ceiling off 29 times
in 14 days against 13 for the primary "room empty" exit.

This counts, per light and switch, who wrote each on->off over the last days
(`hq.py who`, recorder attribution) and lists those where writers named like a
backstop (watchdog, safety, sanity, vagt, ...) did a large share. A hit is a
question, not a verdict: which radar state does the primary exit wait for, and
what lands when the radar lies the other way? A backstop that is the ONLY
writer is a frequency question instead (B291: the radar hang probe).

    python3 scripts/backstop_share.py            # last 7 days
    python3 scripts/backstop_share.py --dage 14  # longer look-back

Read-only. Times are local.
"""

import argparse
import re
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hq  # noqa: E402

HQ = str(Path(__file__).resolve().parent / "hq.py")
BACKSTOP = re.compile(
    r"watchdog|backstop|safety|sikkerhed|sanity|max_on|spogelse|glemt|stuck|failsafe|vagt",
    re.IGNORECASE,
)


def off_writers(entity, days):
    """Counter of writer -> number of on->off flanks it caused."""
    p = subprocess.run(
        [sys.executable, HQ, "who", entity, "--since", f"{days}d", "--all"],
        capture_output=True,
        text=True,
        timeout=300,
    )
    c = Counter()
    for line in p.stdout.splitlines():
        f = line.split("\t")
        if len(f) >= 3 and f[1] == "on→off":
            c[f[2].lstrip("≈")] += 1
    return c


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dage", type=int, default=7)
    ap.add_argument("--min-andel", type=float, default=0.15, help="backstop-andel af slukkene")
    ap.add_argument("--min-n", type=int, default=4, help="mindst så mange backstop-sluk")
    a = ap.parse_args()

    ents = [
        s["entity_id"]
        for s in hq.HA().states()
        if s["entity_id"].split(".")[0] in ("light", "switch")
        and "entity_id" not in s.get("attributes", {})  # grupper: medlemmerne tæller
    ]
    with ThreadPoolExecutor(max_workers=2) as pool:
        counts = dict(zip(ents, pool.map(lambda e: off_writers(e, a.dage), ents)))

    hits = []
    for e, c in counts.items():
        total = sum(c.values())
        bs = Counter({w: n for w, n in c.items() if BACKSTOP.search(w)})
        nb = sum(bs.values())
        if total and nb >= a.min_n and nb / total >= a.min_andel:
            hits.append((nb / total, nb, total, e, bs.most_common(1)[0], c.most_common(1)[0]))

    for share, nb, total, e, (bw, bn), (tw, tn) in sorted(hits, reverse=True):
        alone = "  (eneste skriver → et frekvens-spørgsmål)" if len(counts[e]) == 1 else ""
        print(f"  {share:4.0%} {nb:3}/{total:<4} {e}{alone}")
        print(f"        backstop: {bw.removeprefix('automation.')} ×{bn}")
        if tw != bw:
            print(f"        flest:    {tw.removeprefix('automation.')} ×{tn}")
    print(
        f"  {len(hits)} hit af {len(ents)} lamper/switches"
        + (" — hvilken radar-tilstand venter den primære udgang på? (#25)" if hits else " — rent")
    )


if __name__ == "__main__":
    main()
