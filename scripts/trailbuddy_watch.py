#!/usr/bin/env python3
"""Trail Buddy-vagten for dem derhjemme: bevæger gruppen sig, og holder den planen?

Køres af HA's command_line-sensor `sensor.trail_buddy_status`
(packages/trailbuddy_status.yaml) hvert 5. min og printer ÉN linje JSON.

User-spec 2026-11-06: "en side i HA med en portal ind til Trail Buddy, så
Parent B kan se om vi bevæger os, hvornår vi sidst gjorde det, om vi holder
tidsplanen, og som sender en alarm til Parent B efter 24 t uden GPS-signal eller
med stillestående GPS-signal" — alarmen kun når HELE gruppen er stille.

Bevægelse: hver vandrer har et ANKER (position + tid). En fix mere end RADIUS
fra ankeret flytter det; ankerets tid er "sidst bevæget". Et manglende signal
og et stillestående signal ender derfor i samme tal: ingen ny anker-tid. Kun
gruppe-serverens SENESTE position pr. vandrer findes, så ankrene huskes i
state-filen mellem kørslerne. Indsatte pins (`manual`) og fixes > 100 m
unøjagtige er ikke bevis for bevægelse.

Hvem tæller: kun vandrere der er på ruten (`offRoute` < 50 km). Derhjemme
(Parent B med appen åben, test-positioner fra før turen) tæller ikke, ellers
ville hendes bevægelse i byen holde alarmen tilbage.

Tidsplan: appen sender `day` ud fra KALENDEREN på turens datoer (app.js
myProgress), så den siger intet om fremdrift. I stedet: gruppens km på ruten
(`along`, den forreste) mod dagens strækning i plan.csv (km ved dagens lejr),
skaleret til rutens faktiske længde (along + toGo). Datoerne er tyrkisk tid.

  python3 scripts/trailbuddy_watch.py [--timer 24] [--radius 250] [--dry-run]
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import ha_secrets

TRIP_TZ = ZoneInfo("Europe/Istanbul")
HOME_TZ = ZoneInfo("Europe/Copenhagen")
BASE = "http://local-trailbuddy:8080"
INTERNAL = "http://local-trailbuddy:8081"
PLAN_FILE = "/config/addons/trailbuddy/app/data/plan.csv"
STATE_FILE = "/config/.trailbuddy_watch_state.json"
CODE_KEY = "trailbuddy_trip_code"
MOVING_MS = 20 * 60_000  # anker flyttet + fix inden for 20 min = går nu
MAX_ACC_M = 100
MAX_OFF_ROUTE_M = 50_000


def dist_m(a: dict, b: dict) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    h = (
        math.sin((la2 - la1) / 2) ** 2
        + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    )
    return 6_371_000 * 2 * math.asin(math.sqrt(h))


def get_json(url: str, timeout: float = 10):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.load(r)


def load_plan(path: str = PLAN_FILE) -> list[dict]:
    """[{day, date, km_end}] — km ved dagens sidste række (lejren), stigende."""
    days: dict[int, dict] = {}
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            d = int(row["day"])
            km = float(row["km"])
            cur = days.setdefault(
                d, {"day": d, "date": date.fromisoformat(row["date"]), "km_end": km}
            )
            cur["km_end"] = max(cur["km_end"], km)
    return [days[k] for k in sorted(days)]


def load_state() -> dict:
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except OSError, ValueError:
        return {"members": {}}


def save_state(state: dict) -> None:
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, sort_keys=True)
    os.replace(tmp, STATE_FILE)


def iso(ms: float | None) -> str | None:
    if not ms:
        return None
    return datetime.fromtimestamp(ms / 1000, HOME_TZ).isoformat(timespec="seconds")


def update_members(state: dict, fetched: list[dict], radius: float) -> None:
    """Flyt ankre og husk sidste kendte km/rute-afstand pr. vandrer."""
    mem = state.setdefault("members", {})
    for e in fetched:
        name = str(e.get("name") or "").strip()
        lat, lon, t = e.get("lat"), e.get("lon"), e.get("time") or e.get("received")
        if not name or lat is None or lon is None or not t:
            continue
        m = mem.setdefault(name.lower(), {"name": name})
        m["name"] = name
        if t <= m.get("fix", 0):
            continue
        m["fix"] = t
        for k in ("along", "toGo", "offRoute", "battery"):
            if e.get(k) is not None:  # companion-fixes fra HA har ingen rute-felter
                m[k] = e[k]
        m["source"] = e.get("source") or "app"
        if e.get("manual") or (e.get("accuracy") or 0) > MAX_ACC_M:
            continue
        here = {"lat": lat, "lon": lon}
        anchor = m.get("anchor")
        if anchor is None or dist_m(anchor, here) > radius:
            m["anchor"] = {**here, "t": t}


def schedule(plan: list[dict], km: float | None, route_km: float | None, today: date) -> dict:
    if not plan:
        return {"tidsplan": "Ingen plan", "dag": None}
    if today < plan[0]["date"]:
        return {
            "tidsplan": f"Turen starter {plan[0]['date'].day}/{plan[0]['date'].month}",
            "dag": None,
        }
    if today > plan[-1]["date"]:
        return {"tidsplan": "Turen er slut", "dag": None}
    i = next((n for n, d in enumerate(plan) if d["date"] == today), None)
    if i is None:
        return {"tidsplan": "Hviledag", "dag": None}
    scale = 1.0
    if route_km and 0.7 < route_km / plan[-1]["km_end"] < 1.3:
        scale = route_km / plan[-1]["km_end"]
    start = (plan[i - 1]["km_end"] if i else 0.0) * scale
    end = plan[i]["km_end"] * scale
    out = {"dag": plan[i]["day"], "plan_km_start": round(start, 1), "plan_km_slut": round(end, 1)}
    if km is None:
        out["tidsplan"] = "Ukendt (ingen position på ruten)"
    elif km > end + 1:
        out["tidsplan"] = f"Foran planen ({km - end:.1f} km)"
    elif km >= end - 0.5:
        out["tidsplan"] = "Dagens etape er gået"
    elif km >= start - 1:
        out["tidsplan"] = f"Følger planen ({end - km:.1f} km til lejren)"
    else:
        out["tidsplan"] = f"Bagud ({start - km:.1f} km)"
    return out


def evaluate(state: dict, plan: list[dict], now_ms: float, timer_h: float, hentet: bool) -> dict:
    today = datetime.fromtimestamp(now_ms / 1000, TRIP_TZ).date()
    hikers = [
        m for m in state.get("members", {}).values() if (m.get("offRoute") or 0) < MAX_OFF_ROUTE_M
    ]
    if plan:
        start_ms = (
            datetime.combine(plan[0]["date"], datetime.min.time(), TRIP_TZ).timestamp() * 1000
        )
        end_ms = (
            datetime.combine(
                plan[-1]["date"] + timedelta(days=2), datetime.min.time(), TRIP_TZ
            ).timestamp()
            * 1000
        )
        aktiv = start_ms <= now_ms < end_ms
    else:
        start_ms, aktiv = now_ms, False
    moved = [m["anchor"]["t"] for m in hikers if m.get("anchor")]
    fixes = [m["fix"] for m in hikers if m.get("fix")]
    sidst_bevaeget = max(moved) if moved else None
    sidst_signal = max(fixes) if fixes else None
    # Før turen tæller ingen stilhed: ankre fra test-dagene derhjemme er ikke turen.
    stille_siden = max(sidst_bevaeget or 0, start_ms)
    stille = aktiv and now_ms - stille_siden >= timer_h * 3600_000
    grund = None
    if stille:
        grund = (
            "intet signal"
            if not sidst_signal or now_ms - sidst_signal >= timer_h * 3600_000
            else "stillestående"
        )
    bevaeger = any(
        m.get("anchor")
        and now_ms - m["anchor"]["t"] < MOVING_MS
        and now_ms - m.get("fix", 0) < MOVING_MS
        for m in hikers
    )
    alongs = [m["along"] for m in hikers if m.get("along") is not None]
    km = max(alongs) / 1000 if alongs else None
    lengths = [
        (m["along"] + m["toGo"]) / 1000
        for m in hikers
        if m.get("along") is not None and m.get("toGo") is not None
    ]
    sched = schedule(plan, km, max(lengths) if lengths else None, today)

    if not aktiv:
        status = (
            sched["tidsplan"] if sched["tidsplan"].startswith(("Turen", "Ingen")) else "Ikke aktiv"
        )
    elif stille:
        status = f"Stille i over {timer_h:g} t"
    elif bevaeger:
        status = "Går"
    elif sidst_bevaeget:
        status = "Pause"
    else:
        status = "Ingen position endnu"
    return {
        "state": status,
        "aktiv": aktiv,
        "bevaeger_sig": bevaeger,
        "stille": stille,
        "stille_grund": grund,
        "sidst_bevaeget": iso(sidst_bevaeget),
        "sidst_signal": iso(sidst_signal),
        "km": round(km, 1) if km is not None else None,
        "hentet_ok": hentet,
        "timer": timer_h,
        **sched,
        "vandrere": [
            {
                "navn": m["name"],
                "km": round(m["along"] / 1000, 1) if m.get("along") is not None else None,
                "sidst_signal": iso(m.get("fix")),
                "sidst_bevaeget": iso(m["anchor"]["t"]) if m.get("anchor") else None,
                "batteri": m.get("battery"),
                "kilde": m.get("source"),
            }
            for m in sorted(hikers, key=lambda m: m["name"].lower())
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--timer", type=float, default=24, help="timer uden bevægelse før alarm")
    ap.add_argument("--radius", type=float, default=250, help="meter et anker skal flyttes")
    ap.add_argument("--dry-run", action="store_true", help="skriv ikke state-filen")
    a = ap.parse_args()

    state = load_state()
    hentet = False
    try:
        code = urllib.parse.quote(ha_secrets.get(CODE_KEY), safe="")
        fetched = get_json(f"{BASE}/api/group/{code}").get("members", [])
        update_members(state, fetched, a.radius)
        hentet = True
    except Exception as e:  # add-on nede/forkert kode: ankrene står stille, og det ER signalet
        print(f"trailbuddy_watch: {type(e).__name__}", file=sys.stderr)
    try:
        url = get_json(f"{INTERNAL}/health", 5).get("public_url", "")
        state["public_url"] = url if url.startswith("https://") else state.get("public_url")
    except Exception:
        pass
    try:
        plan = load_plan()
    except OSError, ValueError, KeyError:
        plan = []
    out = evaluate(state, plan, time.time() * 1000, a.timer, hentet)
    out["public_url"] = state.get("public_url")
    if not a.dry_run and hentet:
        save_state(state)
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
