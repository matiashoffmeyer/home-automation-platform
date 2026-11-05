#!/usr/bin/env python3
"""Demokratisk forberedelse — dine svar på Folketingets forslag mod partiernes stemmer.

User-spec 2026-11-04: "forberede mig til næste folketingsvalg så jeg stemmer på
dem jeg har været mest enig med i valgperioden". Valg (samme dag): 1a spørg FØR
Folketinget stemmer, 2a Neutral tæller ikke med, 3b lovforslag OG
beslutningsforslag, 4a AI via HA's ai_task — skåret ned samme dag ("hold øje
med costs!"): AI skriver KUN one-lineren til den sag der pushes (scripts/
ai_forbrug.py fører regnskab og loft); siden viser Folketingets eget resumé.

Datakilde: Folketingets Åbne Data, https://oda.ft.dk/api (OData v3, ingen nøgle,
100 rækker pr. side — `$skip` pager; der kommer INTET nextLink). Kæden er
Sag (forslaget, med Folketingets eget `resume` i almindeligt sprog) → Sagstrin
(fremsættelse, behandlinger) → Afstemning (typeid 1 = endelig vedtagelse; dens
`konklusion` lister partierne pr. side) → Stemme (hvert medlem: 1 For, 2 Imod,
3 Fravær, 4 Hverken for eller imod) → Aktør (navn; partiet står i `biografi`).

Kommandoer (packages/folketing.yaml):
  status            command_line-sensoren sensor.folketing — skriver JSON fra
                    cachen på et øjeblik og starter en detached `scan`, hvis den
                    sidste er ældre end SCAN_HVER_MIN.
  scan              henter nye sager + afstemninger, sender højst
                    ÉN push pr. kørsel (kvote: input_number.folketing_pr_dag) og
                    beder HA genlæse sensoren.
  svar <sag> <FOR|IMOD|NEUTRAL> [kilde]
                    skriver ét svar (push-knap eller Folketing-siden).
  vaegt <sag> <VIGTIG|NORMAL|UVIGTIG> [kilde]
                    vægter et svar i enigheden (Vægtning-fanen på siden).
  scan --dry-run    henter og viser, skriver/sender intet.
  scan --uden-push  henter og gemmer, sender ingen push.
  opdater           starter `scan --uden-push` detached (Opdater-knappen på siden).

Filer:
  /config/.folketing_cache.json      sager, afstemninger, medlemmer (gitignored;
                                     kan genopbygges)
  /config/ai_feedback/folketing_feedback.jsonl
                                     DINE svar — git, privat data (ai_feedback/).
  /config/.folketing.log             scan-loggen (detached barn, ellers tavst).

Push går gennem script.push_notify (notif_id folketing): hjemkomst-køen
(`notif_folketing_hjemme`) holder pushen til du er hjemme, fordi et KNAPSVAR er
et HTTP-kald tilbage til HA og tabes stille på mobildata (mad-spørgsmålene,
2026-08-06). deliverable() SPEJLER push_notify's gate — ret BEGGE (fejlklasse #2).
Der er bevidst ingen `_parent_b`- og `_airbnb`-toggle: svarene er Parent A's egne,
og i AirBnB venter køen bare.

Ny valgperiode: ret PERIODE_FRA til den første samling efter valget. De gamle
svar bliver i filen, men tæller kun med for sager i de valgte samlinger.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

import ai_forbrug
import ha_secrets
import notif_queue

TZ = ZoneInfo("Europe/Copenhagen")
ODA = "https://oda.ft.dk/api"
HA_URL = "http://127.0.0.1:8123"
NOTIF_ID = "folketing"
SENSOR = "sensor.folketing"
E_PR_DAG = "input_number.folketing_pr_dag"

CACHE = "/config/.folketing_cache.json"
LOCK = "/config/.folketing.lock"
LOGFILE = "/config/.folketing.log"
SVAR_FIL = "/config/ai_feedback/folketing_feedback.jsonl"

# Periode 167 = 2025-26 (2. samling), den første efter valget i marts 2026.
PERIODE_FRA = 167
SAGSTYPER = {3: "Lovforslag", 5: "Beslutningsforslag"}
# Tilbagetaget, Udgået, Bortfaldet: der kommer ingen afstemning → ingen push.
DOEDE_STATUS = {4, 9, 13}
SVAR = ("FOR", "IMOD", "NEUTRAL")
# Dit svars vægt i enighed-procenten (user-spec 2026-11-05: "markere mine svar
# som vigtige eller uvigtige ... vægte udfaldet af stemmeanbefalingen").
# Sager-tallet på siden er stadig ét pr. svar; kun procenten vægtes.
VAEGTE = {"VIGTIG": 3.0, "NORMAL": 1.0, "UVIGTIG": 0.25}
SCAN_HVER_MIN = 55
PR_DAG_DEFAULT = 3
# Et forslag vises/pushes først når Folketingets resumé er så langt (tegn):
# nyfremsatte har 0-3 sætninger, og ft.dk udbygger resuméet løbende (user-spec
# 2026-11-05: "skal kun komme ind hvis der er nok info"). Målt 5/11 på 184 sager:
# p20 178, p30 279, p50 551 tegn; alle 20 under 400 var uafgjorte. Besvarede
# vises altid. Slider input_number.folketing_min_resume_tegn (læses ved scan).
E_MIN_RESUME = "input_number.folketing_min_resume_tegn"
MIN_RESUME_DEFAULT = 400
MIN_FAELLES = 5  # et medlem skal have stemt om mindst så mange af dine sager
PARTI_NAVNE = {
    "S": "Socialdemokratiet",
    "V": "Venstre",
    "DD": "Danmarksdemokraterne",
    "SF": "SF",
    "LA": "Liberal Alliance",
    "M": "Moderaterne",
    "KF": "Konservative",
    "EL": "Enhedslisten",
    "DF": "Dansk Folkeparti",
    "RV": "Radikale Venstre",
    "ALT": "Alternativet",
    "BP": "Borgernes Parti",
    "N": "Naleraq",
    "IA": "Inuit Ataqatigiit",
    "SIU": "Siumut",
    "JF": "Javnaðarflokkurin",
    "SP": "Sambandsflokkurin",
    "T": "Tjóðveldi",
}


def log(msg):
    print(f"{datetime.now(TZ):%Y-%m-%d %H:%M:%S} {msg}", file=sys.stderr, flush=True)


def now_iso():
    return datetime.now(TZ).isoformat(timespec="seconds")


# --- Folketingets API ---------------------------------------------------------


def oda_get(path, params):
    q = "&".join(f"{k}={urllib.parse.quote(str(v), safe='(),/')}" for k, v in params.items())
    url = f"{ODA}/{path}?{q}&$format=json"
    for forsoeg in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "homeassistant-folketing/1"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception as ex:
            if forsoeg == 2:
                raise
            log(f"ODA fejl ({ex}) — prøver igen")
            time.sleep(5)


def oda_alle(path, params):
    """Alle rækker: ODA pager med 100 og sender intet nextLink."""
    rows, skip = [], 0
    while True:
        side = oda_get(path, {**params, "$top": 100, "$skip": skip}).get("value", [])
        rows.extend(side)
        if len(side) < 100:
            return rows
        skip += 100


def hent_sager():
    typer = " or ".join(f"typeid eq {t}" for t in SAGSTYPER)
    return oda_alle(
        "Sag",
        {
            "$filter": f"periodeid ge {PERIODE_FRA} and ({typer})",
            "$expand": "Sagstrin/Afstemning",
        },
    )


def hent_perioder():
    rows = oda_get("Periode", {"$filter": f"id ge {PERIODE_FRA}"}).get("value", [])
    return {str(p["id"]): {"kode": p["kode"], "titel": p["titel"]} for p in rows}


def hent_stemmer(afstemning_id):
    rows = oda_alle("Stemme", {"$filter": f"afstemningid eq {afstemning_id}"})
    return {str(r["aktørid"]): r["typeid"] for r in rows}


def hent_aktoerer(ids):
    ud = {}
    ids = sorted(ids)
    for i in range(0, len(ids), 15):
        f = " or ".join(f"id eq {a}" for a in ids[i : i + 15])
        for a in oda_get("Akt%C3%B8r", {"$filter": f}).get("value", []):
            m = re.search(r"<partyShortname>(.*?)</partyShortname>", a.get("biografi") or "")
            ud[str(a["id"])] = {"navn": a.get("navn") or "", "parti": m.group(1) if m else ""}
    return ud


def parse_konklusion(tekst):
    """'For stemte 69 (S, SF, …), imod stemte 44 (V, …, Nadja … (UFG))' → partier pr. side.

    Kun parti-forkortelser tæller; navngivne løsgængere (UFG) står i medlems-
    opgørelsen. Et parti på BEGGE sider stemte splittet og tæller ikke som parti.
    """
    sider = {}
    for side, noegle in (
        ("for", r"for stemte"),
        ("imod", r"imod stemte"),
        ("hverken", r"hverken for eller imod stemte"),
    ):
        m = re.search(noegle + r"\s+\d+\s*\(", tekst or "", re.I)
        if not m:
            sider[side] = []
            continue
        i, dybde, start = m.end(), 1, m.end()
        while i < len(tekst) and dybde:
            dybde += {"(": 1, ")": -1}.get(tekst[i], 0)
            i += 1
        indhold = re.sub(r"\([^()]*\)", "", tekst[start : i - 1])
        dele = re.split(r",|\bog\b", indhold)
        sider[side] = [d.strip() for d in dele if re.fullmatch(r"[A-ZÆØÅ]{1,4}", d.strip())]
    splittet = set(sider["for"]) & set(sider["imod"])
    return {k: [p for p in v if p not in splittet] for k, v in sider.items()}


# --- Home Assistant -----------------------------------------------------------


def ha(method, path, payload=None, timeout=30):
    token = ha_secrets.get(ha_secrets.HA_API_TOKEN)
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        f"{HA_URL}{path}",
        data=data,
        method=method,
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def ha_states():
    return {s["entity_id"]: s for s in ha("GET", "/api/states")}


def _min(st, eid):
    a = (st.get(eid) or {}).get("attributes", {})
    if a.get("hour") is None:
        return None
    return a["hour"] * 60 + a.get("minute", 0)


def deliverable(st):
    """SPEJL af script.push_notify's gate_ok + targets for notif_id=folketing.

    Uden `_airbnb`-toggle gater AirBnB altid; uden `_parent_b` er Parent A eneste
    modtager. Ret BEGGE steder (packages/notifikationer.yaml).
    """
    on = lambda e: (st.get(e) or {}).get("state") == "on"  # noqa: E731
    if not on("input_boolean.notifikationer_master_enabled") or not on(
        f"input_boolean.notif_{NOTIF_ID}_enabled"
    ):
        return False
    if (st.get("input_select.house_mode") or {}).get("state") == "AirBnB" and not on(
        f"input_boolean.notif_{NOTIF_ID}_airbnb"
    ):
        return False
    if not on(f"input_boolean.notif_{NOTIF_ID}_parent_a"):
        return False
    s, e = (
        _min(st, f"input_datetime.notif_{NOTIF_ID}_start"),
        _min(st, f"input_datetime.notif_{NOTIF_ID}_slut"),
    )
    if s is None or e is None or s == e:
        return True
    n = datetime.now(TZ).hour * 60 + datetime.now(TZ).minute
    return (s <= n < e) if s < e else (n >= s or n < e)


# --- Cache og svar ------------------------------------------------------------


def load_cache():
    try:
        with open(CACHE, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError, json.JSONDecodeError:
        return {"sager": {}, "aktoerer": {}, "perioder": {}, "pushes": {}, "sidst_scannet": None}


def save_cache(c):
    tmp = CACHE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False)
    os.replace(tmp, CACHE)


def load_svar():
    """Seneste svar pr. sag (et nyt svar på samme sag erstatter det gamle).

    Vægt-rækker ({"vaegt": ...}, uden "svar") ligger i samme fil; den seneste
    pr. sag hænges på svaret som r["vaegt"] — også hvis svaret ændres bagefter.
    """
    ud, vaegt = {}, {}
    try:
        with open(SVAR_FIL, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if r.get("svar") in SVAR:
                    ud[str(r.get("sag"))] = r
                elif r.get("vaegt") in VAEGTE:
                    vaegt[str(r.get("sag"))] = r["vaegt"]
    except FileNotFoundError:
        pass
    for sid, v in vaegt.items():
        if sid in ud:
            ud[sid] = {**ud[sid], "vaegt": v}
    return ud


AI_PROMPT = """Skriv ÉN neutral sætning på højst 90 tegn på let dansk om hvad dette
forslag i Folketinget går ud på, så den kan stå alene i en notifikation (fx
"Hæver SU-fribeløbet for elever på ungdomsuddannelser"). Ingen partier, ingen
holdning, intet "Forslaget …". Svar KUN med sætningen.{bf}

{type} {nummer}: {titel}
{resume}"""
AI_RESUME_TEGN = 1200  # resten af resuméet ændrer sjældent one-lineren


def ai_kort(sag):
    """One-lineren til pushen — kun for den sag der SKAL pushes (≤ pr_dag kald
    om dagen, ~0,01 kr stykket). Detaljen er Folketingets eget resumé: AI-
    afsnittene var 90 % af den første udgift (user 2026-11-04: "hold øje med
    costs"). Fejl eller nået loft → Folketingets titelkort, som før."""
    prompt = AI_PROMPT.format(
        bf=" Det er et beslutningsforslag: det pålægger regeringen at gøre noget."
        if sag["typeid"] == 5
        else "",
        type=SAGSTYPER[sag["typeid"]],
        nummer=sag["nummer"],
        titel=sag["titel"],
        resume=(sag.get("resume") or "")[:AI_RESUME_TEGN],
    )
    svar = ai_forbrug.generer(f"folketing {sag['nummer']}", prompt)
    kort = str(svar or "").strip().strip('"').splitlines()[0].strip() if svar else ""
    if not kort:
        raise ValueError("tomt AI-svar")
    return {"kort": kort[:120], "model": ai_forbrug.MODEL, "tid": now_iso()}


def tekst(sag):
    """AI-one-lineren hvis sagen er pushet (ellers Folketingets titelkort) +
    Folketingets eget resumé. De 15 første sager har også et AI-afsnit (betalt)."""
    ai = sag.get("ai") or {}
    kort = ai.get("kort") or sag.get("titelkort") or sag["titel"][:110]
    detalje = ai.get("detalje") or sag.get("resume") or sag["titel"]
    return kort, detalje


def moden(c, s):
    """Resuméet er langt nok til at du kan tage stilling (MIN_RESUME_DEFAULT)."""
    return len(s.get("resume") or "") >= c.get("min_resume", MIN_RESUME_DEFAULT)


def koe(c, svar):
    """Sager der skal spørges om: ubesvarede, ikke pushet, ikke døde, modne.

    Uafgjorte først (1a: spørg FØR Folketinget stemmer), nyeste først; derefter
    de allerede afgjorte fra valgperioden, også nyeste først.
    """
    kand = [
        (sid, s)
        for sid, s in c["sager"].items()
        if sid not in svar
        and not s.get("pushet")
        and s.get("statusid") not in DOEDE_STATUS
        and moden(c, s)
    ]
    uafgjort = sorted(
        [k for k in kand if k[1].get("afst") is None],
        key=lambda x: x[1].get("fremsat") or "",
        reverse=True,
    )
    afgjort = sorted(
        [k for k in kand if k[1].get("afst") is not None],
        key=lambda x: x[1].get("fremsat") or "",
        reverse=True,
    )
    return uafgjort + afgjort


def ft_url(c, sag):
    kode = (c["perioder"].get(str(sag["periodeid"])) or {}).get("kode")
    if not kode:
        return ""
    slags = "lovforslag" if sag["typeid"] == 3 else "beslutningsforslag"
    return f"https://www.ft.dk/samling/{kode}/{slags}/{sag['nummer'].replace(' ', '')}/index.htm"


# --- Scan ---------------------------------------------------------------------


def opdater_sager(c, dry):
    nye = 0
    for s in hent_sager():
        sid = str(s["id"])
        trin = s.get("Sagstrin") or []
        fremsat = min(
            (t["dato"][:10] for t in trin if t.get("titel") == "Fremsættelse" and t.get("dato")),
            default=min((t["dato"][:10] for t in trin if t.get("dato")), default=None),
        )
        finale = sorted(
            (
                (t.get("dato") or "", a)
                for t in trin
                for a in t.get("Afstemning") or []
                if a.get("typeid") == 1
            ),
            key=lambda x: x[0],
        )
        gammel = c["sager"].get(sid) or {}
        if not gammel:
            nye += 1
        ny = {
            **gammel,
            "nummer": s["nummer"],
            "typeid": s["typeid"],
            "periodeid": s["periodeid"],
            "titel": s["titel"],
            "titelkort": s.get("titelkort") or "",
            "resume": (s.get("resume") or "").strip(),
            "statusid": s.get("statusid"),
            "fremsat": fremsat,
        }
        if finale:
            dato, a = finale[-1]
            if (gammel.get("afst") or {}).get("id") != a["id"]:
                k = parse_konklusion(a.get("konklusion") or "")
                ny["afst"] = {
                    "id": a["id"],
                    "dato": dato[:10],
                    "vedtaget": a.get("vedtaget"),
                    "konklusion": a.get("konklusion") or "",
                    "for": k["for"],
                    "imod": k["imod"],
                    "hverken": k["hverken"],
                    "stemmer": {} if dry else hent_stemmer(a["id"]),
                }
                log(f"afstemning {s['nummer']}: {'vedtaget' if a.get('vedtaget') else 'forkastet'}")
        c["sager"][sid] = ny
    return nye


def scan(dry=False, push=True):
    lock = open(LOCK, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("en scan kører allerede")
        return 0
    c = load_cache()
    c["perioder"] = hent_perioder() or c.get("perioder", {})
    nye = opdater_sager(c, dry)
    mangler = {
        a for s in c["sager"].values() for a in ((s.get("afst") or {}).get("stemmer") or {})
    } - set(c["aktoerer"])
    if mangler and not dry:
        c["aktoerer"].update(hent_aktoerer(mangler))
    log(f"{len(c['sager'])} sager ({nye} nye), {len(c['aktoerer'])} medlemmer")

    try:
        st = ha_states()
    except Exception as ex:
        log(f"HA svarer ikke ({ex}) — gemmer uden push")
        st = {}
    svar = load_svar()
    q = koe(c, svar)

    dag = datetime.now(TZ).date().isoformat()
    c["pushes"] = {dag: c.get("pushes", {}).get(dag, 0)}
    try:
        forrige = c.get("min_resume", MIN_RESUME_DEFAULT)
        c["min_resume"] = int(float((st.get(E_MIN_RESUME) or {}).get("state", forrige)))
    except ValueError:
        pass  # unavailable → behold den sidst læste
    try:
        pr_dag = int(float((st.get(E_PR_DAG) or {}).get("state", PR_DAG_DEFAULT)))
    except ValueError:
        pr_dag = PR_DAG_DEFAULT
    # Opdater-knappen på siden (push=False) må ikke sende dagens push midt i
    # at man sidder og svarer — den henter kun afstemningerne.
    if push and q and st and c["pushes"][dag] < pr_dag and deliverable(st):
        sid, s = q[0]
        if not s.get("ai") and not dry:
            try:
                s["ai"] = ai_kort(s)
                log(f"AI {s['nummer']}: {s['ai']['kort']}")
            except Exception as ex:  # AiLoft, timeout, tomt svar → titelkortet
                log(f"AI sprunget over for {s['nummer']}: {ex}")
        kort, _ = tekst(s)
        payload = {
            "tag": f"folketing_{sid}",
            "clickAction": "/folketing-dash/forslag",
            "url": "/folketing-dash/forslag",
            "actions": [
                {"action": f"FT_FOR_{sid}", "title": "👍 For"},
                {"action": f"FT_IMOD_{sid}", "title": "👎 Imod"},
                {"action": f"FT_NEUTRAL_{sid}", "title": "🤷 Neutral"},
            ],
        }
        titel = f"🏛️ {s['nummer']} · {SAGSTYPER[s['typeid']]}"
        if dry:
            log(f"DRY push: {titel} — {kort}")
        else:
            try:
                ha(
                    "POST",
                    "/api/services/script/push_notify",
                    {"notif_id": NOTIF_ID, "title": titel, "message": kort, "payload": payload},
                )
                s["pushet"] = now_iso()
                c["pushes"][dag] += 1
                log(f"push {s['nummer']}: {kort}")
            except Exception as ex:
                log(f"push fejlede: {ex}")

    c["sidst_scannet"] = now_iso()
    if dry:
        print(json.dumps(status_doc(c, svar), ensure_ascii=False, indent=1)[:4000])
        return 0
    save_cache(c)
    try:
        ha("POST", "/api/services/homeassistant/update_entity", {"entity_id": SENSOR})
    except Exception as ex:
        log(f"update_entity fejlede: {ex}")
    return 0


# --- Status (sensor.folketing) ------------------------------------------------


def pct(e, u):
    return round(100 * e / (e + u)) if e + u else None


def parti_sider(c, a):
    """Partierne pr. side: konklusionen, ellers medlemmernes stemmer.

    Konklusionen kan være tom (L 23, 2025-26); så tæller et parti på den side
    ALLE dets fremmødte medlemmer stemte — et splittet parti tæller ikke.
    """
    if a.get("for") or a.get("imod"):
        return {"for": a.get("for", []), "imod": a.get("imod", [])}
    sider = {}
    for aid, t in (a.get("stemmer") or {}).items():
        p = (c["aktoerer"].get(aid) or {}).get("parti")
        if p and p != "UFG" and t in (1, 2):
            sider.setdefault(p, set()).add(t)
    return {
        "for": sorted(p for p, t in sider.items() if t == {1}),
        "imod": sorted(p for p, t in sider.items() if t == {2}),
    }


def status_doc(c, svar):
    partier, medlemmer = {}, {}
    sammenlignet = 0
    for sid, r in svar.items():
        s = c["sager"].get(sid)
        if not s or r["svar"] == "NEUTRAL" or not s.get("afst"):
            continue
        sammenlignet += 1
        a, mit = s["afst"], r["svar"]
        w = VAEGTE[r.get("vaegt", "NORMAL")]
        sider = parti_sider(c, a)
        # [enig, uenig, vægtet enig, vægtet uenig]
        for side, kode in (("for", "FOR"), ("imod", "IMOD")):
            for p in sider[side]:
                d = partier.setdefault(p, [0, 0, 0.0, 0.0])
                i = 0 if mit == kode else 1
                d[i] += 1
                d[i + 2] += w
        for aid, t in (a.get("stemmer") or {}).items():
            if t not in (1, 2):
                continue  # fravær og "hverken" tæller ikke — som dit Neutral
            d = medlemmer.setdefault(aid, [0, 0, 0.0, 0.0])
            i = 0 if (t == 1) == (mit == "FOR") else 1
            d[i] += 1
            d[i + 2] += w

    pl = [
        {"parti": p, "navn": PARTI_NAVNE.get(p, p), "enig": e, "uenig": u, "pct": pct(we, wu)}
        for p, (e, u, we, wu) in partier.items()
    ]
    # Et parti med 1 af 1 (de nordatlantiske mandater stemmer sjældent) må ikke
    # stå øverst: under MIN_FAELLES fælles sager rangerer det efter de andre.
    pl.sort(
        key=lambda x: (
            x["enig"] + x["uenig"] < MIN_FAELLES,
            -(x["pct"] or 0),
            -(x["enig"] + x["uenig"]),
        )
    )
    maks = max((d[0] + d[1] for d in medlemmer.values()), default=0)
    # Medlemmer er fraværende ved mange afstemninger (pardannelse) → kræv en
    # tredjedel af dine sammenlignede sager, mindst MIN_FAELLES.
    graense = min(max(MIN_FAELLES, sammenlignet // 3), maks)
    ml = [
        {
            "navn": c["aktoerer"].get(aid, {}).get("navn", aid),
            "parti": c["aktoerer"].get(aid, {}).get("parti", ""),
            "enig": e,
            "uenig": u,
            "pct": pct(we, wu),
        }
        for aid, (e, u, we, wu) in medlemmer.items()
        if e + u >= graense and graense > 0
    ]
    ml.sort(key=lambda x: (-(x["pct"] or 0), -(x["enig"] + x["uenig"]), x["navn"]))

    ubesvarede = [
        (sid, s)
        for sid, s in c["sager"].items()
        if sid not in svar and s.get("statusid") not in DOEDE_STATUS and moden(c, s)
    ]
    pushet = sorted(
        (x for x in ubesvarede if x[1].get("pushet")), key=lambda x: x[1]["pushet"], reverse=True
    )
    q = koe(c, svar)
    aktuel = None
    if pushet or q:
        sid, s = (pushet or q)[0]
        kort, detalje = tekst(s)
        aktuel = {
            "id": sid,
            "nummer": s["nummer"],
            "type": SAGSTYPER[s["typeid"]],
            "titel": s.get("titelkort") or s["titel"][:150],
            "kort": kort,
            "detalje": detalje,
            "fremsat": s.get("fremsat"),
            "afgjort": s.get("afst") is not None,
            "url": ft_url(c, s),
        }
    seneste = []
    for sid, r in sorted(svar.items(), key=lambda x: x[1].get("tid", ""), reverse=True)[:10]:
        s = c["sager"].get(sid)
        if not s:
            continue
        a = s.get("afst") or {}
        seneste.append(
            {
                "nummer": s["nummer"],
                "kort": tekst(s)[0],
                "svar": r["svar"],
                "vedtaget": a.get("vedtaget"),
                "for": parti_sider(c, a)["for"] if a else [],
                "imod": parti_sider(c, a)["imod"] if a else [],
                "url": ft_url(c, s),
            }
        )
    # Hele listen til Folketing-siden (custom:folketing-liste-card): ubesvarede
    # i kø-rækkefølge (uafgjorte først), så de besvarede, seneste svar først.
    # Korte nøgler — 170 sager; sensoren er udenfor recorderen.
    besvarede = sorted(
        ((sid, s) for sid, s in c["sager"].items() if sid in svar),
        key=lambda x: svar[x[0]].get("tid", ""),
        reverse=True,
    )
    alle = []
    for sid, s in pushet + q + besvarede:
        a = s.get("afst")
        r = {"id": sid, "n": s["nummer"], "k": tekst(s)[0], "st": a is not None, "u": ft_url(c, s)}
        if a:
            r["d"] = a.get("dato")
        if sid in svar:
            r["s"] = svar[sid]["svar"]
            if svar[sid].get("vaegt", "NORMAL") != "NORMAL":
                r["w"] = svar[sid]["vaegt"]
            # Partiernes stemmer først EFTER dit svar (1a).
            if a:
                sider = parti_sider(c, a)
                r.update(v=a.get("vedtaget"), f=sider["for"], i=sider["imod"])
        alle.append(r)
    return {
        "state": len(ubesvarede),
        "alle": alle,
        "aktuel": aktuel,
        "naeste": [
            {"nummer": s["nummer"], "kort": tekst(s)[0]}
            for _, s in [x for x in q if not aktuel or x[0] != aktuel["id"]][:5]
        ],
        "besvaret": len(svar),
        "vigtige": sum(1 for r in svar.values() if r.get("vaegt") == "VIGTIG"),
        "uvigtige": sum(1 for r in svar.values() if r.get("vaegt") == "UVIGTIG"),
        "sammenlignet": sammenlignet,
        # Besvaret med For/Imod, men Folketinget har ikke stemt endnu.
        "venter": sum(
            1
            for sid, r in svar.items()
            if r["svar"] != "NEUTRAL" and not (c["sager"].get(sid) or {}).get("afst")
        ),
        "partier": pl,
        "politikere": ml[:10],
        # Bunden af listen, uden overlap med top 10 (ved få medlemmer: tom).
        "politikere_mindst": ml[10:][-5:][::-1],
        "seneste": seneste,
        "sidst_scannet": c.get("sidst_scannet"),
    }


def scan_forfalden(c):
    t = c.get("sidst_scannet")
    if not t:
        return True
    return (datetime.now(TZ) - datetime.fromisoformat(t)).total_seconds() > SCAN_HVER_MIN * 60


def start_scan(*ekstra):
    """Detached scan (logger til LOGFILE) — kalderen venter ikke på oda.ft.dk."""
    with open(LOGFILE, "a") as logf:
        subprocess.Popen(
            [sys.executable, os.path.abspath(__file__), "scan", *ekstra],
            stdout=logf,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            cwd=os.path.dirname(os.path.abspath(__file__)),
        )


def status():
    c = load_cache()
    if scan_forfalden(c):
        start_scan()
    print(json.dumps(status_doc(c, load_svar()), ensure_ascii=False))
    return 0


def gem_svar(sid, svar, kilde):
    svar = svar.upper()
    if not re.fullmatch(r"\d{1,9}", sid) or svar not in SVAR:
        log(f"ugyldigt svar: {sid!r} {svar!r}")
        return 1
    s = load_cache()["sager"].get(sid) or {}
    os.makedirs(os.path.dirname(SVAR_FIL), exist_ok=True)
    with open(SVAR_FIL, "a", encoding="utf-8") as f:
        rec = {
            "tid": now_iso(),
            "sag": sid,
            "nummer": s.get("nummer"),
            "svar": svar,
            "kilde": kilde,
        }
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    # Svaret på siden mens pushen lå i hjemkomst-køen → ud af køen, ellers
    # leveres et allerede besvaret forslag ved ankomst (11-04: B 37/38).
    try:
        notif_queue.cmd_drop_tag(f"folketing_{sid}")
    except Exception as ex:  # noqa: BLE001
        log(f"kø-oprydning fejlede: {ex}")
    return 0


def gem_vaegt(sid, vaegt, kilde):
    vaegt = vaegt.upper()
    if not re.fullmatch(r"\d{1,9}", sid) or vaegt not in VAEGTE:
        log(f"ugyldig vægt: {sid!r} {vaegt!r}")
        return 1
    s = load_cache()["sager"].get(sid) or {}
    with open(SVAR_FIL, "a", encoding="utf-8") as f:
        rec = {
            "tid": now_iso(),
            "sag": sid,
            "nummer": s.get("nummer"),
            "vaegt": vaegt,
            "kilde": kilde,
        }
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return 0


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "status"
    if cmd == "status":
        return status()
    if cmd == "scan":
        return scan(dry="--dry-run" in argv, push="--uden-push" not in argv)
    if cmd == "opdater":
        start_scan("--uden-push")
        return 0
    if cmd == "svar" and len(argv) >= 4:
        return gem_svar(
            argv[2],
            argv[3],
            re.sub(r"[^a-z]", "", (argv[4] if len(argv) > 4 else "ukendt").lower())[:20],
        )
    if cmd == "vaegt" and len(argv) >= 4:
        return gem_vaegt(
            argv[2],
            argv[3],
            re.sub(r"[^a-z]", "", (argv[4] if len(argv) > 4 else "ukendt").lower())[:20],
        )
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
