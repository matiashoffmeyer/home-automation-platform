#!/usr/bin/env python3
"""Evaluér Apollo-spøgelser (B179): recorder-KPI'er + de to måle-JSONL'er.

    python3 scripts/apollo_spoegelse_eval.py [--dage 14]

1. SPØGELSES-RATE i bevist tomt hus (binary_sensor.hus_bevist_tomt on), pr. rum:
   rå udslag minus robot/gardin (apollo_flap_suppress + vacuum ± 5 min) og minus
   hjemkomst (de sidste 5 min før tomt → off = familien på vej ind). Pr. tomt-time.
2. STUE-HAK (falsk negativ): aften 17-23 — udslag og korte huller (< 60 s) pr.
   OPTAGET time, stue mod spisestue som kontrol. Delt før/efter flytningen bag
   radiatorskjuleren (2026-10-02 16:52). Målt 22/9-1/10: stue 11-61 udslag/t,
   4-34 korte huller/t — hakkede aftener fandtes også før; sammenlign med kontrollen.
3. RADIATOR: stue-Apolloens rum- og ESP-temperatur, døgn-max (canary 52 °C).
4. ai_feedback/apollo_udslag_feedback.jsonl: tomt-hus-udslag mod resten —
   still-energi/-afstand ved start, moving_target i spil, flap-jagtens gate.
5. ai_feedback/apollo_kalib_feedback.jsonl: seneste baseline pr. rum — aktive
   gates med margin (tærskel − støj-max) under 5.

Læser en KOPI af recorder-DB'en (HA skriver i den).
"""

import collections
import json
import shutil
import sqlite3
import sys
import tempfile
import time
from datetime import datetime

DB = "/config/home-assistant_v2.db"
ROOMS = ["koekken", "spisestue", "stue", "boernevaerelse", "sovevaerelse"]
FLYTNING = datetime(2026, 10, 2, 16, 52).timestamp()
UDSLAG = "/config/ai_feedback/apollo_udslag_feedback.jsonl"
KALIB = "/config/ai_feedback/apollo_kalib_feedback.jsonl"


def open_db():
    tmp = tempfile.mkdtemp()
    for suf in ("", "-wal", "-shm"):
        try:
            shutil.copy(DB + suf, f"{tmp}/db{suf}")
        except FileNotFoundError:
            pass
    return sqlite3.connect(f"{tmp}/db")


def episodes(con, eid, since, until):
    rows = con.execute(
        """SELECT s.state, s.last_updated_ts FROM states s JOIN states_meta m
           ON m.metadata_id = s.metadata_id WHERE m.entity_id = ?
           AND s.last_updated_ts >= ? AND s.last_updated_ts < ? ORDER BY 2""",
        (eid, since, until),
    ).fetchall()
    prev = con.execute(
        """SELECT s.state FROM states s JOIN states_meta m ON m.metadata_id = s.metadata_id
           WHERE m.entity_id = ? AND s.last_updated_ts < ? ORDER BY s.last_updated_ts DESC LIMIT 1""",
        (eid, since),
    ).fetchone()
    seq = [(prev[0], since)] if prev else []
    for st, t in rows:
        if not seq or seq[-1][0] != st:
            seq.append((st, t))
    return [
        (st, t, (seq[i + 1][1] if i + 1 < len(seq) else until) - t) for i, (st, t) in enumerate(seq)
    ]


def windows(con, eid, states, since, until, pad=0.0):
    return [(t - pad, t + d + pad) for st, t, d in episodes(con, eid, since, until) if st in states]


def inside(t, wins):
    return any(a <= t <= b for a, b in wins)


def pct(v, p):
    v = sorted(v)
    return v[min(len(v) - 1, int(p / 100 * len(v)))] if v else None


def fmt(v):
    return "–" if v is None else (f"{v:.0f}" if abs(v) >= 10 else f"{v:.1f}")


def main():
    dage = int(sys.argv[sys.argv.index("--dage") + 1]) if "--dage" in sys.argv else 14
    now = time.time()
    since = now - dage * 86400
    con = open_db()
    tomt = windows(con, "binary_sensor.hus_bevist_tomt", {"on"}, since, now)
    # Hjemkomst: de sidste 5 min af et tomt-vindue er familien på vej ind.
    tomt = [(a, b - 300) for a, b in tomt if b - 300 > a]
    stoej = windows(con, "binary_sensor.apollo_flap_suppress", {"on"}, since, now) + windows(
        con, "vacuum.s8_maxv_ultra", {"cleaning", "returning"}, since, now, 300
    )
    timer_tomt = sum(b - a for a, b in tomt) / 3600

    print(f"=== 1. Spøgelser i bevist tomt hus ({dage} døgn, {timer_tomt:.1f} tomt-timer) ===")
    for r in ROOMS:
        eps = [
            (t, d)
            for st, t, d in episodes(con, f"binary_sensor.{r}_apollo_occupancy", since, now)
            if st == "on" and inside(t, tomt) and not inside(t, stoej)
        ]
        pr_dag = collections.Counter(datetime.fromtimestamp(t).strftime("%m-%d") for t, _ in eps)
        print(
            f"  {r:15s} {len(eps):4d} udslag = {len(eps) / max(timer_tomt, 0.01):5.2f}/t  "
            f"varighed p50 {fmt(pct([d for _, d in eps], 50))} s  pr. dag: {dict(sorted(pr_dag.items()))}"
        )
        if r == "stue":
            efter = [t for t, _ in eps if t >= FLYTNING]
            t_efter = sum(max(0, b - max(a, FLYTNING)) for a, b in tomt) / 3600
            print(f"  {'':15s} heraf efter flytningen: {len(efter)} på {t_efter:.1f} tomt-timer")

    print("\n=== 2. Stue-hak om aftenen (17-23): udslag og huller < 60 s pr. optaget time ===")
    for r in ("stue", "spisestue"):
        pr_dag = collections.defaultdict(lambda: [0, 0, 0.0])
        for st, t, d in episodes(con, f"binary_sensor.{r}_apollo_occupancy", since, now):
            h = datetime.fromtimestamp(t).hour
            if not 17 <= h < 23:
                continue
            k = datetime.fromtimestamp(t).strftime("%m-%d") + ("*" if t >= FLYTNING else "")
            if st == "on":
                pr_dag[k][0] += 1
                pr_dag[k][2] += d
            elif st == "off" and d < 60:
                pr_dag[k][1] += 1
        print(
            f"  {r}: "
            + "  ".join(
                f"{k} {n / max(on / 3600, 0.1):.0f}/{g / max(on / 3600, 0.1):.0f}"
                for k, (n, g, on) in sorted(pr_dag.items())
            )
        )
    print("  (dato* = efter flytningen; tal = udslag/t · korte huller/t)")

    # Rå Apollo-temperaturer er recorder-ekskluderede; snapshot-kopien er ikke.
    # ESP-temperaturen findes kun i udslags-loggen (afsnit 4 læser den).
    print(
        "\n=== 3. Stue-Apollo temperatur, døgn-max (radiator: snapshot / ESP fra udslags-loggen) ==="
    )
    for eid in ("sensor.stue_temperatur",):
        rows = con.execute(
            """SELECT s.state, s.last_updated_ts FROM states s JOIN states_meta m
               ON m.metadata_id = s.metadata_id WHERE m.entity_id = ? AND s.last_updated_ts > ?""",
            (eid, since),
        ).fetchall()
        mx = collections.defaultdict(float)
        for st, t in rows:
            try:
                k = datetime.fromtimestamp(t).strftime("%m-%d")
                mx[k] = max(mx[k], float(st))
            except ValueError:
                pass
        print(
            f"  {eid.split('.')[1]:24s} " + " ".join(f"{k}:{v:.1f}" for k, v in sorted(mx.items()))
        )
    esp = collections.defaultdict(float)
    try:
        for line in open(UDSLAG, encoding="utf-8"):
            x = json.loads(line)
            if x.get("rum") == "stue" and x.get("esp", -1) > 0:
                esp[x["ts"][5:10]] = max(esp[x["ts"][5:10]], x["esp"])
    except FileNotFoundError:
        pass
    print(
        f"  {'stue ESP (canary 52)':24s} "
        + (" ".join(f"{k}:{v:.1f}" for k, v in sorted(esp.items())) or "(ingen data endnu)")
    )

    print("\n=== 4. Udslags-loggen (≤ 120 s) ===")
    try:
        rows = [json.loads(line) for line in open(UDSLAG, encoding="utf-8")]
    except FileNotFoundError:
        rows = []
    if not rows:
        print("  (ingen data endnu)")
    for r in ROOMS:
        rr = [x for x in rows if x.get("rum") == r]
        if not rr:
            continue
        sp = [x for x in rr if x.get("tomt") and not x.get("sup") and not x.get("andre")]
        print(f"  {r}: {len(rr)} udslag, {len(sp)} i tomt hus uden robot/nabo")
        for lab, grp in (("tomt", sp), ("resten", [x for x in rr if x not in sp])):
            if not grp:
                continue
            se = [x["s0"]["se"] for x in grp if x["s0"]["se"] >= 0]
            sd = [x["s0"]["sd"] for x in grp if x["s0"]["sd"] >= 0]
            mt = sum(1 for x in grp if x.get("mt_under"))
            gates = collections.Counter(
                x.get("gate", "").split(" · ")[0].split(": ", 1)[-1] for x in grp
            )
            print(
                f"    {lab:6s} n={len(grp):4d}  still-energi p10/p50/p90 {fmt(pct(se, 10))}/{fmt(pct(se, 50))}/"
                f"{fmt(pct(se, 90))}  afstand p50 {fmt(pct(sd, 50))} cm  moving_target {mt}/{len(grp)}  "
                f"gates {gates.most_common(3)}"
            )

    print("\n=== 5. Tomt-rum-baseline (seneste pr. rum) ===")
    try:
        kal = [json.loads(line) for line in open(KALIB, encoding="utf-8")]
    except FileNotFoundError:
        kal = []
    seneste = {}
    for k in kal:
        seneste[k["rum"]] = k
    if not seneste:
        print(
            "  (ingen baseline endnu — bestil: input_text.apollo_kalib_bestilling = 'stue,koekken')"
        )
    for r, k in seneste.items():
        aktive = {
            g: v
            for g, v in k["gates"].items()
            if v["taerskel"] is not None and 0 <= v["taerskel"] < 100
        }
        lav = {g: v for g, v in aktive.items() if v["margin"] is not None and v["margin"] < 5}
        print(
            f"  {r} {k['ts'][:16]} n={k['n']} (beskidt {k['n_beskidt']}) temp {k['temp']} esp {k['esp']}"
        )
        for g, v in sorted(aktive.items()):
            flag = "  ⚠ margin < 5" if g in lav else ""
            print(
                f"    {g:9s} støj p50 {fmt(v['p50'])} p95 {fmt(v['p95'])} max {fmt(v['max'])}"
                f"  tærskel {fmt(v['taerskel'])}  margin {fmt(v['margin'])}{flag}"
            )


if __name__ == "__main__":
    main()
