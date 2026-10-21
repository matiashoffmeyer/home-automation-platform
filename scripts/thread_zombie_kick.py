#!/usr/bin/env python3
"""thread_zombie_kick.py — genopliv en Thread-"zombie-router" (2026-10-09).

MÅLT 2026-10-09: light.badevaerelse_spot_2 (KAJPLATS, Matter-node 206) stod
unavailable i ~1 t efter at Thread-nettet var samlet igen. Den sendte MLE-
advertisements (OTBR'ens router-tabel: Age 0-15 s, RSSI -85) — men svarede
hverken på Matter-ping eller ICMP til sin egen RLOC. Pæren lyste, og intet
kunne slukke den. `ot-ctl releaserouterid <id>` på lederen (OTBR'en) tvang den
til at gen-attache: ny router-id 80 s senere, og HA så den igen med det samme.

Kører fra otbr_selfheal.sh's daemon-loop (hvert 2. min, deler kill-switchen
input_boolean.thread_watchdog_enabled). Rører INTET andet end `ot-ctl` i OTBR-
containeren — ingen serielport, ingen USB, ingen dataset-læsning.

Kriterier (alle skal holde):
  - OTBR'en er LEDER og ser ≥ 2 andre routere (raskt net — ellers ejer
    stigen i thread_otbr_watchdog.yaml problemet);
  - Matter-noden er unavailable i matter-serveren;
  - dens extended MAC står i router-tabellen med Age ≤ 30 s (radioen lever);
  - ICMP-ping til dens RLOC fejler (3 pakker);
  - tilstanden har holdt ≥ 6 min (3 polls) → ikke et flimmer under re-attach;
  - højst ét kick pr. node pr. 30 min;
  - aldrig en BRO-router (BRO_NODER: entré-loftet bærer hele stuen).

  python3 thread_zombie_kick.py            # tjek + kick
  python3 thread_zombie_kick.py --dry-run  # vis kun kandidaterne
"""

import asyncio
import base64
import json
import os
import re
import subprocess
import sys
import time

MATTER_WS = "ws://172.30.32.1:5580/ws"
STATE = "/data/otbr_selfheal/zombie.json"
LOG = "/data/otbr_selfheal/selfheal.log"
HOLD_S = 360
# BRO-routere kickes ALDRIG (15/10): entré-loftet (node 461) er stuens eneste vej
# til OTBR'en. Kicket 13/10 19:55 → stue-spotsene mistede broen med det samme.
# En døv bro er stigens problem (thread_otbr_watchdog.yaml), ikke et release.
BRO_NODER = {"461"}
KICK_COOLDOWN_S = 1800
MAX_AGE_S = 30
# Leder-vagt (15/10): OTBR'ens leader weight over alle andres (64-65) → en
# partition OTBR'en leder vinder ALTID en fletning (Mle::ComparePartitions
# sammenligner weighting FØR størrelse og partition-ID). 15/10 vandt stue-
# spotsenes ø i stedet, stue spot 2 blev leder og var døv: ingen kunne få
# router-ID (sove-lyskæden hang som barn) og releaserouterid herunder kræver
# OTBR'en som leder. Nulstilles ved hver add-on-start → holdes hvert tick.
LEDER_VAEGT = 128
LEDER_STATE = "/data/otbr_selfheal/leder.json"
LEDER_HOLD_POLLS = 3  # ≥ 6 min som router før overtagelse
LEDER_COOLDOWN_S = 6 * 3600  # højst én tvungen ny partition pr. 6 t
LEDER_MIN_LINKS = 2  # OTBR'en skal høre ≥ 2 routere med LQ 3 begge veje


def log(msg):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} zombie: {msg}"
    print(line)
    try:
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def otbr_container():
    out = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True
    ).stdout
    return next((n for n in out.split() if "core_openthread_border_router" in n), None)


def ot(c, cmd, timeout=30):
    return subprocess.run(
        ["docker", "exec", c, "sh", "-c", f"ot-ctl {cmd}"],
        capture_output=True,
        text=True,
        timeout=timeout,
    ).stdout


def router_table(c):
    """{ext_mac: (router_id, rloc16, age)} — kun rækker med link-info."""
    rows = {}
    for line in ot(c, "router table").splitlines():
        f = [x.strip() for x in line.strip().strip("|").split("|")]
        if len(f) >= 8 and f[0].isdigit():
            rows[f[7].lower()] = (int(f[0]), f[1].lower(), int(f[6]))
    return rows


def rloc_prefix(c):
    for a in ot(c, "ipaddr").split():
        m = re.match(r"^(.+):0:ff:fe00:[0-9a-f]{1,4}$", a)
        if m:
            return m.group(1)
    return None


def ping_ok(c, addr):
    out = ot(c, f"ping {addr} 16 3 1", timeout=20)
    m = re.search(r"(\d+) packets received", out)
    return bool(m and int(m.group(1)) > 0)


async def matter_nodes():
    import websockets

    async with websockets.connect(MATTER_WS, max_size=None, open_timeout=10) as ws:
        await ws.recv()
        await ws.send(json.dumps({"message_id": "z", "command": "get_nodes"}))
        while True:
            m = json.loads(await asyncio.wait_for(ws.recv(), 60))
            if m.get("message_id") == "z":
                return m.get("result") or []


def mac_of(node):
    for i in node.get("attributes", {}).get("0/51/0") or []:
        if isinstance(i, dict) and i.get("4"):
            return base64.b64decode(i["4"]).hex().lower()
    return None


def leder_hold(c, dry):
    """Hold leader weight og gør OTBR'en til leder når den ikke er det.
    `state leader` danner en NY partition med OTBR'ens vægt; de andre routere
    hører den som bedre og flytter over (~1 min blink på Thread-lys). Kun på
    et raskt net (≥ LEDER_MIN_LINKS stærke links), efter LEDER_HOLD_POLLS
    polls som router og med LEDER_COOLDOWN_S imellem — ellers risikerer vi en
    ensom partition (thread_matter.md)."""
    w = ot(c, "leaderweight").split()[:1]
    if w and w[0].isdigit() and int(w[0]) != LEDER_VAEGT and not dry:
        ot(c, f"leaderweight {LEDER_VAEGT}")
        log(f"leaderweight {w[0]} → {LEDER_VAEGT}")
    try:
        with open(LEDER_STATE) as f:
            st = json.load(f)
    except OSError, ValueError:
        st = {"polls": 0, "sidst": 0}
    rolle = ot(c, "state").split()[:1]
    if rolle != ["router"]:
        st["polls"] = 0
    else:
        st["polls"] += 1
        staerke = 0
        for line in ot(c, "router table").splitlines():
            f = [x.strip() for x in line.strip().strip("|").split("|")]
            if len(f) >= 9 and f[0].isdigit() and f[8] == "1" and f[4] == "3" and f[5] == "3":
                staerke += 1
        m = re.search(r"Leader Router ID: (\d+)", ot(c, "leaderdata"))
        if dry:
            print(
                f"leder-vagt: router i {st['polls']} polls, {staerke} stærke links, "
                f"leder id {m.group(1) if m else '?'}"
            )
        elif (
            st["polls"] >= LEDER_HOLD_POLLS
            and staerke >= LEDER_MIN_LINKS
            and time.time() - st["sidst"] >= LEDER_COOLDOWN_S
        ):
            ot(c, "state leader")
            st["sidst"], st["polls"] = time.time(), 0
            log(
                f"OTBR'en var router (leder id {m.group(1) if m else '?'}, "
                f"{staerke} stærke links) → state leader (vægt {LEDER_VAEGT})"
            )
    if not dry:
        tmp = LEDER_STATE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(st, f)
        os.replace(tmp, LEDER_STATE)


def main():
    dry = "--dry-run" in sys.argv
    c = otbr_container()
    if not c:
        return 0
    leder_hold(c, dry)
    if ot(c, "state").split()[:1] != ["leader"]:
        return 0  # releaserouterid kræver leder-rollen; ikke-leder = stigens problem
    routers = router_table(c)
    if len(routers) < 3:  # OTBR'en selv + ≥ 2 andre
        return 0
    try:
        nodes = asyncio.run(matter_nodes())
    except Exception as e:
        log(f"matter-server utilgængelig: {e}")
        return 0
    try:
        with open(STATE) as f:
            st = json.load(f)
    except OSError, ValueError:
        st = {}
    now = time.time()
    seen = set()
    prefix = None
    for n in nodes:
        if n.get("available"):
            continue
        mac = mac_of(n)
        if not mac or mac not in routers:
            continue
        rid, rloc, age = routers[mac]
        if age > MAX_AGE_S:
            continue
        prefix = prefix or rloc_prefix(c)
        if not prefix:
            return 0
        addr = f"{prefix}:0:ff:fe00:{rloc[2:]}"
        if ping_ok(c, addr):
            continue  # radio og IP lever — matter-laget må selv fange op
        key = str(n["node_id"])
        seen.add(key)
        e = st.setdefault(key, {"since": None, "kicked": 0})
        if e["since"] is None:
            e["since"] = now
        name = n.get("attributes", {}).get("0/40/5") or n.get("attributes", {}).get("0/40/3")
        held = now - e["since"]
        if dry:
            print(f"kandidat node {key} ({name}) router {rid} {rloc} age {age}s, holdt {held:.0f}s")
            continue
        if held >= HOLD_S and now - e["kicked"] >= KICK_COOLDOWN_S:
            if key in BRO_NODER:
                e["kicked"] = now  # cooldown = én log-linje pr. 30 min
                log(f"node {key} ({name}) døv i {held / 60:.0f} min — BRO-router, kickes ikke")
                continue
            ot(c, f"releaserouterid {rid}")
            e["kicked"] = now
            log(
                f"node {key} ({name}) MLE-levende men døv i {held / 60:.0f} min "
                f"→ releaserouterid {rid} ({rloc})"
            )
    for k in list(st):
        if k not in seen and now - st[k].get("kicked", 0) >= KICK_COOLDOWN_S:
            del st[k]
        elif k not in seen:
            st[k]["since"] = None  # ude af zombie-tilstand: nulstil hold-uret, behold cooldown
    if not dry:
        tmp = STATE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(st, f)
        os.replace(tmp, STATE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
