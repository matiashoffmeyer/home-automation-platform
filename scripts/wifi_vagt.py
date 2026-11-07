#!/usr/bin/env python3
"""Wifi-vagt: nye enheder på husets wifi skal godkendes eller blokeres (2026-11-07).

User-spec 7/11: "byg notifikationen og find bloker-API'et. både parent_b og jeg
skal kunne godkende nye devices." packages/wifi_vagt.yaml kalder scriptet; det
taler routerens web-API (Sagemcom F@st 3896, samme login som gaeste_wifi.py).

  scan [--stille]   læs routerens host-liste, find nye enheder → JSON {"nye": [...]}
  godkend <mac>     flyt en enhed til de kendte
  bloker <mac>      sæt MAC-filteret i blokliste-tilstand + regel på 2,4 og 5 GHz
  fjern <mac>       slet blokerings-reglen (enheden må komme på igen)
  init              alle aktive enheder i dag bliver kendte (første kørsel)
  status            tæl kendte/afventer/blokeret

HVAD ER "NY": en MAC der hverken er kendt, afventer eller blokeret, og som
enten er forbundet nu, eller hvis `lastseen` har flyttet sig siden sidste scan
(en der var på i to minutter mellem to scan, tæller også). Inaktive ukendte
uden bevægelse står i `baseline` med deres `lastseen` — de giver først et
varsel den dag de kommer igen.

GÆSTE-NETTET: routerens host-liste skelner ikke gæste-nettet fra husets net,
men dens tilknytnings-lister gør (fundet i GUI'ens kode 7/11, `assoclist`):
  GET /api/v1/wireless/assoclist/{24,5}            → husets SSID'er
  GET /api/v1/wireless/assoclist/{guest24,guest5}  → gæste-nettet
  → [{"hosts": {"list": [{id, macaddress, rate}]}}] — kun de forbundne lige nu.
Står gæste-wifi'en tændt (AirBnB eller test), eller kalder HA med `--stille`
(AirBnB-mode), varsles KUN en ny enhed der står i husets assoclist eller er
forbundet med kabel (user 7/11: "under airbnb, hvis nogen connector til main
wifi (ikke gæste-nettet), så skal alerten også gå af"). Alt andet → baseline.

MAC-FILTERET (læst i router-GUI'ens kode 7/11, `wifiMacfilter`):
  GET/PUT /api/v1/wireless/{24,5}/acl   {"acl": {"enable": -1|0|1, "rules": []}}
    -1 = blokliste (DENY), 0 = fra, 1 = tilladt-liste (ALLOW) — ALDRIG 1 her:
    en tilladt-liste med én regel smider hele huset af wifi'en.
  POST /api/v1/wireless/{24,5}/acl/rules  {device, macaddress, enable: 1}
  DELETE /api/v1/wireless/acl/rules/<id>
Tilstanden skrives kun når den afviger, fordi hver wifi-ændring giver husets
enheder et kort blip (målt 25/10 på gæste-nettet: Apollo'er < 1 s, højttaler 5 s).

Tilstanden ligger i /config/.wifi_vagt_state.json (git-ignoreret: MAC-adresser
og enhedsnavne er husets data, ikke kode).
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import sys
import time
import urllib.error
from pathlib import Path

import ha_secrets
from gaeste_wifi import ADGANG, Router

STATE = Path(__file__).resolve().parent.parent / ".wifi_vagt_state.json"
LOCK = STATE.with_suffix(".lock")
MAC_RE = re.compile(r"^[0-9a-f]{2}(:[0-9a-f]{2}){5}$")
ACL = {"24": "/api/v1/wireless/24/acl", "5": "/api/v1/wireless/5/acl"}
BLOKLISTE = -1


def norm(mac: str) -> str:
    m = (mac or "").strip().lower().replace("-", ":")
    if not MAC_RE.match(m):
        raise ValueError(f"ugyldig MAC: {mac!r}")
    return m


def laes() -> dict:
    try:
        d = json.loads(STATE.read_text())
    except FileNotFoundError:
        d = {}
    for k in ("kendte", "afventer", "blokeret", "baseline"):
        d.setdefault(k, {})
    return d


def skriv(d: dict) -> None:
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1, sort_keys=True))
    os.replace(tmp, STATE)


def navn_af(h: dict) -> str:
    n = (h.get("hostname") or "").strip()
    # Routeren bruger MAC'en som navn når enheden ikke sender et (tilfældig
    # "privat" adresse på iPhone/Android) — det er ikke et navn.
    if not n or MAC_RE.match(n.lower()) or re.fullmatch(r"[0-9a-fA-F]{12}", n):
        return ""
    return n[:40]


def login() -> Router:
    r = Router()
    r.login(ha_secrets.get("router_admin_user"), ha_secrets.get("router_admin_password"))
    return r


def hosts(r: Router) -> list[dict]:
    return r._kald("GET", "/api/v1/hosts")[0]["hosts"]["list"]


def gaestenet_taendt(r: Router) -> bool:
    a = r._kald("GET", ADGANG)[0]["guestSettings"]
    return bool(a.get("guest_24g_status") or a.get("guest_5g_status"))


def paa_hovednettet(r: Router, liste: list[dict]) -> set[str]:
    """MAC'er forbundet til husets egne SSID'er + aktive kabel-enheder."""
    macs = set()
    for b in ("24", "5"):
        for h in r._kald("GET", f"/api/v1/wireless/assoclist/{b}")[0]["hosts"]["list"]:
            try:
                macs.add(norm(h.get("macaddress", "")))
            except ValueError:
                pass
    for h in liste:
        if h.get("active") and h.get("link") == "Ethernet":
            try:
                macs.add(norm(h.get("macaddress", "")))
            except ValueError:
                pass
    return macs


def acl(r: Router) -> dict[str, dict]:
    return {b: r._kald("GET", sti)[0]["acl"] for b, sti in ACL.items()}


def scan(d: dict, stille: bool) -> dict:
    r = login()
    try:
        liste = hosts(r)
        gaest = gaestenet_taendt(r)
        hoved = paa_hovednettet(r, liste)
    finally:
        r.logout()
    stille = stille or gaest
    nu = int(time.time())
    nye = []
    for h in liste:
        try:
            mac = norm(h.get("macaddress", ""))
        except ValueError:
            continue
        navn = navn_af(h)
        band = h.get("link") or ""
        ls = h.get("lastseen") or ""
        for k in ("kendte", "afventer", "blokeret"):
            if mac in d[k]:
                if navn:
                    d[k][mac]["navn"] = navn
                break
        else:
            flyttet = ls and ls != d["baseline"].get(mac, "")
            # Stille (gæste-nettet tændt): kun en enhed på HUSETS net varsles.
            if mac in hoved or (not stille and (h.get("active") or flyttet)):
                d["afventer"][mac] = {"navn": navn, "band": band, "set": nu}
                d["baseline"].pop(mac, None)
                nye.append(
                    {
                        "mac": mac,
                        "navn": navn,
                        "band": band,
                        "aktiv": bool(h.get("active")),
                        "hovednet": mac in hoved,
                    }
                )
            else:
                d["baseline"][mac] = ls
    d["sidste_scan"] = nu
    return {"ok": True, "nye": nye, "stille": stille, "gaestenet": gaest, **taelling(d)}


def taelling(d: dict) -> dict:
    return {k: len(d[k]) for k in ("kendte", "afventer", "blokeret")}


def find_navn(d: dict, mac: str) -> str:
    for k in ("afventer", "kendte", "blokeret"):
        if mac in d[k]:
            return d[k][mac].get("navn", "")
    return ""


def godkend(d: dict, mac: str) -> dict:
    if mac in d["blokeret"]:
        return {"ok": False, "fejl": "blokeret — fjern blokeringen først", "mac": mac}
    info = d["afventer"].pop(mac, None) or {}
    d["kendte"][mac] = {"navn": info.get("navn", ""), "godkendt": int(time.time())}
    d["baseline"].pop(mac, None)
    return {"ok": True, "mac": mac, "navn": d["kendte"][mac]["navn"], **taelling(d)}


def bloker(d: dict, mac: str) -> dict:
    navn = find_navn(d, mac)
    r = login()
    try:
        foer = acl(r)
        for b, sti in ACL.items():
            if foer[b].get("enable") == 1:
                # En tilladt-liste har nogen sat i GUI'en — at blande en blokliste
                # ind i den er ikke vores beslutning.
                raise RuntimeError(f"MAC-filteret på {b} GHz står som tilladt-liste")
            if foer[b].get("enable") != BLOKLISTE:
                r._kald("PUT", sti, {"enable": BLOKLISTE})
            har = {
                norm(x.get("macaddress", ""))
                for x in foer[b].get("rules", [])
                if x.get("macaddress")
            }
            if mac not in har:
                r._kald(
                    "POST", sti + "/rules", {"device": navn or mac, "macaddress": mac, "enable": 1}
                )
        efter = acl(r)
    finally:
        r.logout()
    ok = all(
        v.get("enable") == BLOKLISTE
        and mac
        in {norm(x.get("macaddress", "")) for x in v.get("rules", []) if x.get("macaddress")}
        for v in efter.values()
    )
    if ok:
        d["afventer"].pop(mac, None)
        d["kendte"].pop(mac, None)
        d["baseline"].pop(mac, None)
        d["blokeret"][mac] = {"navn": navn, "blokeret": int(time.time())}
    return {"ok": ok, "mac": mac, "navn": navn, **taelling(d)}


def fjern(d: dict, mac: str) -> dict:
    navn = find_navn(d, mac)
    r = login()
    try:
        for _ in range(2):
            ids = {
                x["id"]
                for v in acl(r).values()
                for x in v.get("rules", [])
                if x.get("macaddress") and norm(x["macaddress"]) == mac and "id" in x
            }
            for i in ids:
                try:
                    r._kald("DELETE", f"/api/v1/wireless/acl/rules/{int(i)}")
                except urllib.error.HTTPError:
                    pass  # samme id på begge bånd: andet kald finder den slettet
        tilbage = [
            b
            for b, v in acl(r).items()
            if mac
            in {norm(x.get("macaddress", "")) for x in v.get("rules", []) if x.get("macaddress")}
        ]
    finally:
        r.logout()
    if not tilbage:
        d["blokeret"].pop(mac, None)
        # Ikke kendt bagefter: kommer den igen, spørges der igen.
        d["baseline"][mac] = ""
    return {"ok": not tilbage, "mac": mac, "navn": navn, "tilbage": tilbage, **taelling(d)}


def init(d: dict) -> dict:
    r = login()
    try:
        liste = hosts(r)
    finally:
        r.logout()
    for h in liste:
        try:
            mac = norm(h.get("macaddress", ""))
        except ValueError:
            continue
        if h.get("active"):
            d["kendte"].setdefault(mac, {"navn": navn_af(h), "godkendt": int(time.time())})
        elif mac not in d["kendte"]:
            d["baseline"][mac] = h.get("lastseen") or ""
    return {"ok": True, **taelling(d), "baseline": len(d["baseline"])}


def main() -> int:
    a = sys.argv[1:]
    cmd = a[0] if a else ""
    if cmd not in ("scan", "godkend", "bloker", "fjern", "init", "status"):
        print(
            "brug: wifi_vagt.py scan [--stille]|godkend <mac>|bloker <mac>|fjern <mac>|init|status",
            file=sys.stderr,
        )
        return 2
    with open(LOCK, "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        d = laes()
        try:
            if cmd == "scan":
                svar = scan(d, "--stille" in a)
            elif cmd == "init":
                svar = init(d)
            elif cmd == "status":
                svar = {"ok": True, **taelling(d)}
            else:
                mac = norm(a[1] if len(a) > 1 else "")
                svar = {"godkend": godkend, "bloker": bloker, "fjern": fjern}[cmd](d, mac)
        except (
            urllib.error.URLError,
            OSError,
            ValueError,
            KeyError,
            IndexError,
            RuntimeError,
        ) as e:
            print(json.dumps({"ok": False, "fejl": type(e).__name__, "detalje": str(e)[:120]}))
            return 2
        if cmd != "status":
            skriv(d)
    print(json.dumps(svar, ensure_ascii=False))
    return 0 if svar.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
