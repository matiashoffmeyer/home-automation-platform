#!/usr/bin/env python3
"""otbr_rcp_stats.py — Thread-helbred som tal i HA (2026-10-14, B234).

User 14/10: "entre lys og stue spots skubber hinanden af thread. nu vil jeg
altså ha det stabiliseret!" + "vi skal aldrig belaste thread så meget som ild
flimmer gjorde!". Begge kræver et MÅL der lever i HA — før det fandtes kun
`grep -c "RCP failure"` i hånden (B232).

Kører fra otbr_selfheal.sh's daemon-loop (hvert 2. min). Læser OTBR-add-on'ets
log via supervisor og `ot-ctl uptime` (loggens tidsstempler er OTBR-uptime,
"[Nd.]HH:MM:SS.mmm", nulstillet ved hver add-on-start) og udgiver:

  sensor.otbr_rcp_resets_1t   (via eventet otbr_rcp_stats) RCP-resets den seneste time (én reset = linjen
                              "RCP failure detected"; ~5 s hvor HELE Thread står)
    attributter: resets_10m, seneste (min siden), split_peer, split_minutter,
                 offline_noder (Matter-noder matter-serveren ser som offline)
  sensor.thread_routere_vaek  (samme event, 15/10) antal netdrevne Thread-noder
                              (routere) der IKKE svarer, + `routere`/`sovende` =
                              status pr. enhed til Status-sidens Thread-kort.
                              Stue-spotsene er ude af recorderen (B227) — denne
                              sensor er deres eneste net-historik.

Status pr. router: Matter-serveren først (available = forbundet); ellers slås
dens extended MAC op i OTBR'ens router-tabel + meshdiag-topologien: står den
dér, lever radioen men Matter er døv (zombie, thread_zombie_kick.py); ellers
er den væk. Sovende batteri-enheder kan ikke pinges når de er koblet af — de
skal vækkes med et tryk/en åbning (15/10: MYGGSPRAY 27 + MYGGBETT 37 stod
hverken som barn under OTBR'en eller nogen router).

Split: "Different partition (peer:X, local:Y)" = OTBR'en hører routere fra en
ANDEN partition, som ikke vil smelte sammen (13-14/10: begge GRILLPLATS i
~14 t). split_minutter = sammenhængende varighed (huller < 6 min) i log-vinduet.

  python3 otbr_rcp_stats.py            # udgiv
  python3 otbr_rcp_stats.py --dry-run  # print kun
"""

import asyncio
import base64
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

SUP = "http://supervisor"
ADDON = "core_openthread_border_router"
MATTER_WS = "ws://172.30.32.1:5580/ws"
TS = re.compile(r"^(?:(\d+)d\.)?(\d+):(\d\d):(\d\d)\.(\d+)")
PEER = re.compile(r"Different partition \(peer:(\d+)")
# Matter-noder der er parret men BEVIDST strømløse — tæller aldrig som "faldet
# af". Tom siden 15/10: 498 (GRILLPLATS 0x1F2, nu "Stue Plug") stod her mens den
# lå i skuffen, var 14-15/10 Thread-router i depotet og driver fra 15/10 hyggelampen i stuen (B234)
# og var 15/10 netværkets LEDER — undtaget ville den aldrig blive meldt væk.
PASSIVE_NODER = set()


def sup(path, data=None):
    req = urllib.request.Request(
        SUP + path,
        data=None if data is None else json.dumps(data).encode(),
        headers={
            "Authorization": f"Bearer {os.environ.get('SUPERVISOR_TOKEN', '')}",
            "Content-Type": "application/json",
        },
        method="GET" if data is None else "POST",
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", "replace")


def secs(s):
    m = TS.match(s.strip())
    if not m:
        return None
    d, h, mi, se, ms = m.groups()
    return int(d or 0) * 86400 + int(h) * 3600 + int(mi) * 60 + int(se) + int(ms) / 10 ** len(ms)


def otbr_uptime():
    out = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True
    ).stdout
    c = next((n for n in out.split() if ADDON in n), None)
    if not c:
        return None
    out = subprocess.run(
        ["docker", "exec", c, "sh", "-c", "ot-ctl uptime"],
        capture_output=True,
        text=True,
        timeout=20,
    ).stdout
    return secs(out.splitlines()[0]) if out.strip() else None


async def matter_noder():
    import websockets

    async with websockets.connect(MATTER_WS, max_size=None, open_timeout=10) as ws:
        await ws.recv()
        await ws.send(json.dumps({"message_id": "s", "command": "get_nodes"}))
        while True:
            m = json.loads(await asyncio.wait_for(ws.recv(), 60))
            if m.get("message_id") == "s":
                return m.get("result") or []


def offline_noder(noder):
    ud = []
    for n in noder:
        if n.get("available") or n.get("node_id") in PASSIVE_NODER:
            continue
        a = n.get("attributes", {})
        ud.append((n.get("node_id"), a.get("0/40/5") or a.get("0/40/3") or "?"))
    return ud


def otbr_container():
    out = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True
    ).stdout
    return next((n for n in out.split() if ADDON in n), None)


def ot(cmd, timeout=20):
    c = otbr_container()
    if not c:
        return ""
    return subprocess.run(
        ["docker", "exec", c, "sh", "-c", f"ot-ctl {cmd}"],
        capture_output=True,
        text=True,
        timeout=timeout,
    ).stdout


def mesh_macs(fuld):
    """Extended MACs OTBR'en kan se i sin partition. Router-tabellen er billig
    men kender ikke altid MAC'en på routere uden direkte link (15/10: router 58
    stod med 0000000000000000) — derfor meshdiag-topologien når `fuld` (kun når
    en router faktisk mangler i Matter; den spørger hver router over luften)."""
    macs = set()
    for line in ot("router table").splitlines():
        f = [x.strip() for x in line.strip().strip("|").split("|")]
        if len(f) >= 8 and f[0].isdigit() and f[7].strip("0"):
            macs.add(f[7].lower())
    if fuld:
        try:
            macs |= set(re.findall(r"ext-addr:([0-9a-f]{16})", ot("meshdiag topology", 40)))
        except subprocess.TimeoutExpired:
            pass
    return macs


def mac_of(node):
    for i in node.get("attributes", {}).get("0/51/0") or []:
        if isinstance(i, dict) and i.get("4"):
            return base64.b64decode(i["4"]).hex().lower()
    return None


def enhed_status(noder, navne, luft=True):
    """(routere, sovende) til Thread-kortet. Router = netdrevet (har en On/Off-
    cluster på endpoint 1: pærer og plugs); resten er sovende batteri-enheder."""

    def navn(n):
        a = n.get("attributes", {})
        return navne.get(f"{n['node_id']:016X}", a.get("0/40/5") or a.get("0/40/3") or "?")

    routere = [n for n in noder if "1/6/0" in n.get("attributes", {})]
    sovende = [n for n in noder if "1/6/0" not in n.get("attributes", {})]
    mangler = [n for n in routere if not n.get("available") and n["node_id"] not in PASSIVE_NODER]
    macs = mesh_macs(fuld=bool(mangler) and luft) if mangler else set()
    r_ud = []
    for n in sorted(routere, key=navn):
        if n["node_id"] in PASSIVE_NODER:
            st = "ikke i brug"
        elif n.get("available"):
            st = "forbundet"
        elif mac_of(n) in macs:
            st = "i nettet, Matter svarer ikke"
        else:
            st = "væk"
        r_ud.append({"navn": navn(n), "node": n["node_id"], "status": st})
    s_ud = [
        {
            "navn": navn(n),
            "node": n["node_id"],
            "status": "forbundet" if n.get("available") else "væk",
        }
        for n in sorted(sovende, key=navn)
    ]
    return r_ud, s_ud


# HA-navnet (name_by_user) på en Matter-node: device-identifieren er
# 'deviceid_<fabric>-<node 16 hex>-MatterNodeDevice'. Pushen skal sige
# "Stue Plug", ikke "GRILLPLATS Plug (node 498)".
NAVNE_TPL = """{% set ns = namespace(m={}) %}
{% for e in integration_entities('matter') %}{% set d = device_id(e) %}
{% if d %}{% for i in device_attr(d, 'identifiers') or [] %}
{% if i[1].endswith('-MatterNodeDevice') %}{% set ns.m = dict(ns.m, **{i[1].split('-')[1] | upper: device_attr(d, 'name_by_user') or device_attr(d, 'name')}) %}{% endif %}
{% endfor %}{% endif %}{% endfor %}{{ ns.m | to_json }}"""


TOPO_ROUTER = re.compile(r"^id:(\d+) rloc16:(0x[0-9a-f]{4}) ext-addr:([0-9a-f]{16}) ver:(\d+)(.*)$")
TOPO_LINKS = re.compile(r"^\s+([123])-links:\{([^}]*)\}")
TOPO_CHILD = re.compile(r"^\s+rloc16:(0x[0-9a-f]{4}) lq:(\d)")
CHILD_MAC = re.compile(
    r"rloc16:(0x[0-9a-f]{4}) ext-addr:([0-9a-f]{16})[^\n]*\n\s+timeout:\d+ age:(\d+)"
)
DIAG_SVAR = re.compile(r"Ext Address: ([0-9a-f]{16})\s+Rloc16: (0x[0-9a-f]{4})")


DIAG_CACHE = "/tmp/otbr_child_macs.json"
# Luft-forespørgslerne (meshdiag topology/childtable/routerneighbortable) koster
# ~15-20 multi-hop-udvekslinger pr. måling. Hvert 2. min (15/10 13:30-16:15)
# faldt sammen med husets værste Matter-time (alle noder, stue-spot 1 væk fra
# 13:32) → højst hvert 30. min; imellem står kortet med sin målte alder og
# status læses fra OTBR'ens LOKALE router-tabel.
# 15/10 aften (user: "få kortet til at opdatere oftere ... burde ikke belaste
# særligt"): RCP-resets/t var ens med måling hvert 2. min (13:30-16:15, p50 3)
# og hvert 30. (16:30-19:15, p50 3), og stue-klyngen faldt ud 18:09-18:51 også
# med 30 min → intervallet er nu en slider, default 4 min (~250 udvekslinger/t
# i hele nettet, ~5 pr. måling gennem entré mod ildens ~120 kommandoer/t).
LUFT_ENTITY = "input_number.thread_kort_maaling_minutter"
LUFT_S = 1800  # fallback hvis slideren ikke kan læses
LUFT_STEMPEL = "/tmp/otbr_luft_sidst"


def luft_interval():
    try:
        return max(120, float(json.loads(sup(f"/core/api/states/{LUFT_ENTITY}"))["state"]) * 60)
    except Exception:
        return LUFT_S


def luft_tilladt():
    # -20 s: daemonens 2-min-tik har jitter — ellers bliver "4 min" til 6.
    try:
        return time.time() - os.path.getmtime(LUFT_STEMPEL) >= luft_interval() - 20
    except OSError:
        return True


def luft_brugt():
    try:
        open(LUFT_STEMPEL, "w").close()
    except OSError:
        pass


def gem_cache(cache):
    try:
        json.dump(cache, open(DIAG_CACHE, "w"))
    except OSError:
        pass


def diag_macs(rlocs, kendte=None, vent=15):
    """Spørg børn direkte om deres MAC (netdiag TLV 0). GRILLPLATS (ver 4)
    svarer ikke på `meshdiag childtable`, men barnet selv svarer når det
    poller sin forælder (15/10: depotets 0xd408/0xd409 = badets to PIR'er).
    Svarene kommer asynkront → én interaktiv ot-ctl der lytter `vent` s.
    Et barn poller sjældnere end det → sidste kendte svar for samme RLOC16
    (cache i /tmp, fodret af hver childtable der svarer; et RLOC16 skifter
    når barnet skifter forælder). Returnerer hele cachen rloc → MAC."""
    try:
        cache = json.load(open(DIAG_CACHE))
    except Exception:
        cache = {}
    cache.update(kendte or {})
    rlocs = [r for r in rlocs if r not in cache]
    c = otbr_container()
    if not c or not rlocs:
        gem_cache(cache)
        return cache
    m = re.search(r"^([0-9a-f:]+:ff:fe00:)[0-9a-f]+$", ot("ipaddr rloc"), re.M)
    if not m:
        return cache
    prefix = m.group(1)
    cmds = "".join(f'echo "networkdiagnostic get {prefix}{r[2:]} 0 1"; sleep 1; ' for r in rlocs)
    try:
        out = subprocess.run(
            ["docker", "exec", c, "sh", "-c", f"({cmds}sleep {vent}) | ot-ctl"],
            capture_output=True,
            text=True,
            timeout=vent + len(rlocs) + 15,
        ).stdout
    except subprocess.TimeoutExpired as e:
        out = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
    cache.update({rloc: mac for mac, rloc in DIAG_SVAR.findall(out)})
    gem_cache(cache)
    return cache


def router_tabel():
    """id → MAC for alle router-ID'er partitionen har tildelt — også dem der
    ikke svarer på meshdiag (15/10: stue-spotsene stod her med path cost 4-5
    og LQ 1 mens Matter og meshdiag var døve)."""
    ud = {}
    for line in ot("router table").splitlines():
        f = [x.strip() for x in line.strip().strip("|").split("|")]
        if len(f) >= 9 and f[0].isdigit() and f[7] != "0" * 16:
            ud[int(f[0])] = {"rloc": f[1], "mac": f[7].lower()}
    return ud


NB_FEJL = re.compile(
    r"rloc16:0x([0-9a-f]{2})00 ext-addr:[0-9a-f]{16}[^\n]*\n[^\n]*\n\s+err-rate - frame:([\d.]+)% msg:([\d.]+)%"
)
LQ_FEJL = re.compile(
    r"^\| 0x([0-9a-f]{2})00 \| [0-9a-f]{16} \|\s+([\d.]+) % \|\s+([\d.]+) % \|", re.M
)


def link_fejl(routere):
    """Tab pr. link i SENDERENS retning: {nabo-id: [frame-fejl %, msg-fejl %]}
    (15/10: stue spot 2 → entré-loft stod grønt — signal -70 — men 90 % af
    frames og 26 % af beskederne gik tabt; Matter-abonnementet nåede aldrig
    igennem). LQ måler kun signalstyrke. OTBR'en lokalt, ver-5-routere over
    luften (0,1 s hver); GRILLPLATS (ver 4) svarer ikke (5 s timeout) → sprunget over."""
    for r in routere:
        if r["mig"]:
            tekst, rx = ot("neighbor linkquality"), LQ_FEJL
        elif r["svarer"] and r["ver"] >= 5:
            try:
                tekst, rx = ot(f"meshdiag routerneighbortable {r['rloc']}", 15), NB_FEJL
            except subprocess.TimeoutExpired:
                continue
        else:
            continue
        r["fejl"] = {
            str(int(h, 16) >> 2): [round(float(f)), round(float(m), 1)]
            for h, f, m in rx.findall(tekst)
        }


def topologi(noder, navne):
    """Hele partitionen som OTBR'en ser den (15/10, Status-sidens net-tegning):
    routere med links (link-kvalitet 1-3 set fra routeren selv) og børn, plus
    Matter-noder der IKKE er i partitionen (en ø, eller strømløse). Ét
    `meshdiag topology` (~3 s, én forespørgsel pr. router) + én `childtable`
    pr. router med børn + netdiag til børn uden MAC — højst hvert LUFT_S."""
    out = ot("meshdiag topology children", 40)
    routere, cur = [], None
    for line in out.splitlines():
        m = TOPO_ROUTER.match(line)
        if m:
            rid, rloc, mac, ver, rest = m.groups()
            cur = {
                "id": int(rid),
                "rloc": rloc,
                "mac": mac,
                "ver": int(ver),
                "leder": "leader" in rest,
                "br": " br" in rest or "- me" in rest,
                "mig": "- me" in rest,
                "svarer": True,
                "links": {},
                "born": [],
            }
            routere.append(cur)
            continue
        if cur is None:
            continue
        m = TOPO_LINKS.match(line)
        if m:
            for x in m.group(2).split():
                cur["links"][str(int(x))] = int(m.group(1))
            continue
        m = TOPO_CHILD.match(line)
        if m:
            cur["born"].append({"rloc": m.group(1), "lq": int(m.group(2))})
    if not routere:
        return None
    # Tildelte router-ID'er der ikke svarede på meshdiag: tegnes med de links
    # naboerne melder (ensidige), så en halvdød router ikke ligner en ø.
    kendte = {r["id"] for r in routere}
    for rid, rt in router_tabel().items():
        if rid not in kendte:
            routere.append(
                {
                    "id": rid,
                    "rloc": rt["rloc"],
                    "mac": rt["mac"],
                    "ver": 0,
                    "leder": False,
                    "br": False,
                    "mig": False,
                    "svarer": False,
                    "links": {},
                    "born": [],
                }
            )
    # Lederen kan selv være en der ikke svarer (15/10: stue spot 2) → fra
    # leaderdata, ikke kun meshdiag-flaget.
    m = re.search(r"Leader Router ID: (\d+)", ot("leaderdata"))
    if m:
        for r in routere:
            r["leder"] = r["id"] == int(m.group(1))
    link_fejl(routere)
    # Børnenes MAC + alder (s siden forælderen sidst hørte dem): OTBR'ens egen
    # tabel lokalt, de andre over luften, resten spørges direkte.
    child = {}
    for r in routere:
        if not r["born"]:
            continue
        if r["mig"]:
            for line in ot("child table").splitlines():
                f = [x.strip() for x in line.strip().strip("|").split("|")]
                if len(f) >= 14 and f[0].isdigit():
                    child[f[1].lower()] = (f[13].lower(), int(f[3]))
        elif r["ver"] >= 5:  # GRILLPLATS (ver 4) svarer aldrig → spar 5 s
            try:
                for rloc, mac, age in CHILD_MAC.findall(ot(f"meshdiag childtable {r['rloc']}", 15)):
                    child[rloc] = (mac, int(age))
            except subprocess.TimeoutExpired:
                pass
    # Ukendte: sidste kendte MAC for samme RLOC16 (childtable kan time ud),
    # ellers spørges barnet selv. Alder ukendt → taber til en frisk post.
    ukendt = [b["rloc"] for r in routere for b in r["born"] if b["rloc"] not in child]
    cache = diag_macs(ukendt, {rloc: mac for rloc, (mac, _) in child.items()})
    for rloc in ukendt:
        if rloc in cache:
            child[rloc] = (cache[rloc], 10**6)
    mac_navn = {}
    for n in noder:
        mac = mac_of(n)
        if mac:
            a = n.get("attributes", {})
            mac_navn[mac] = (
                navne.get(f"{n['node_id']:016X}", a.get("0/40/5") or "?"),
                "1/6/0" in a,
                bool(n.get("available")),
            )
    # En batteri-enhed der skifter forælder står i den gamles tabel til dens
    # timeout (240 s) udløber → samme enhed under 2-3 routere (15/10: Entré
    # PIR'en, frame-fejl 90 %). Kun posten med lavest alder er den rigtige.
    bedst, poster = {}, {}
    for r in routere:
        for b in r["born"]:
            mac, age = child.get(b["rloc"], (None, None))
            b["mac"] = mac
            if mac:
                poster[mac] = poster.get(mac, 0) + 1
                if mac not in bedst or age < bedst[mac][1]:
                    bedst[mac] = (b["rloc"], age)
    set_macs = {r["mac"] for r in routere} | set(bedst)
    hjemlose = [
        mac for mac, (nv, rt, av) in mac_navn.items() if mac not in set_macs and not rt and av
    ]
    uden_mac = sum(1 for b in r2b(routere) if not b["mac"])
    for r in routere:
        r["navn"] = (
            "Border-router" if r["mig"] else mac_navn.get(r["mac"], (f"Router {r['id']}",))[0]
        )
        r["matter"] = mac_navn.get(r["mac"], (None, None, True))[2]
        born = []
        for b in r["born"]:
            mac = b.pop("mac")
            if mac:
                if bedst[mac][0] != b["rloc"]:
                    continue
                b["hop"] = poster[mac] - 1
                nv = mac_navn.get(mac)
                b["navn"] = nv[0] if nv else b["rloc"]
                b["matter"] = nv[2] if nv else True
            elif len(hjemlose) == 1 and uden_mac == 1:
                # Ét ukendt barn, én placeringsløs enhed Matter når → den.
                b["navn"], b["matter"], b["hop"] = mac_navn[hjemlose[0]][0], True, 0
            elif hjemlose:
                b["navn"], b["matter"], b["hop"] = "Ukendt", True, 0
            else:
                # Alle enheder Matter når er placeret → en forældet post fra
                # en enhed der har skiftet forælder. Ikke tegnet.
                continue
            born.append(b)
        r["born"] = born
        for k in ("mig", "ver"):
            r.pop(k)
    set_macs |= set(hjemlose)
    uden_for = [
        {"navn": nv, "router": rt, "matter": av}
        for mac, (nv, rt, av) in sorted(mac_navn.items(), key=lambda x: x[1][0])
        if mac not in set_macs
    ]
    return {"routere": routere, "uden_for": uden_for}


def r2b(routere):
    return [b for r in routere for b in r["born"]]


def ha_navne_map():
    try:
        return json.loads(sup("/core/api/template", {"template": NAVNE_TPL}))
    except Exception:
        return {}


def ha_navne(noder, m):
    return [f"{m.get(f'{nid:016X}', label)} (node {nid})" for nid, label in noder]


def main():
    dry = "--dry-run" in sys.argv
    up = otbr_uptime()
    if up is None:
        return 0
    log = sup(f"/addons/{ADDON}/logs?lines=4000")
    resets, peers = [], []
    for line in log.splitlines():
        t = secs(line)
        if t is None or t > up + 5:
            continue  # linje fra før seneste add-on-start (uptime ældre end nu)
        if "RCP failure detected" in line:
            resets.append(t)
        m = PEER.search(line)
        if m:
            peers.append((t, m.group(1)))
    r1 = sum(1 for t in resets if up - t <= 3600)
    r10 = sum(1 for t in resets if up - t <= 600)
    seneste = round((up - resets[-1]) / 60) if resets else None
    split_peer, split_min = "", 0
    if peers and up - peers[-1][0] <= 360:
        split_peer = peers[-1][1]
        start = slut = peers[-1][0]
        for t, p in reversed(peers):
            if p != split_peer or slut - t > 360:
                break
            start, slut = t, t
        split_min = round((up - start) / 60)
    offline = routere = sovende = None
    luft = luft_tilladt() and not dry
    if luft:
        luft_brugt()
    try:
        noder = asyncio.run(matter_noder())
        navne = ha_navne_map()
        offline = ha_navne(offline_noder(noder), navne)
        routere, sovende = enhed_status(noder, navne, luft)
    except Exception:
        pass
    try:
        topo = topologi(noder, navne) if routere is not None and luft else None
        if topo is not None:
            topo["maalt"] = round(time.time())
    except Exception:
        import traceback

        traceback.print_exc()
        topo = None
    attrs = {
        "resets": r1,
        "resets_10m": r10,
        "seneste": seneste,
        "otbr_uptime_t": round(up / 3600, 1),
        "split_peer": split_peer,
        "split_minutter": split_min,
    }
    if offline is not None:
        attrs["offline_noder"] = offline
    if routere is not None:
        attrs["routere"] = routere
        attrs["sovende"] = sovende
    if topo is not None:
        attrs["topologi"] = topo
    if dry:
        print(r1, json.dumps(attrs, ensure_ascii=False))
        return 0
    # Event → trigger-sensoren i packages/thread_otbr_watchdog.yaml (overlever
    # en HA-restart, modsat POST /api/states).
    sup("/core/api/events/otbr_rcp_stats", attrs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
