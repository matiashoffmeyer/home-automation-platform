#!/usr/bin/env python3
"""Cyber-vagt — husets bevis-spor for "ingen udefra har prøvet eller er kommet ind".

Køres af HA core (packages/cyber_vagt.yaml, hvert 10. min) og virker også fra
SSH-add-on'et. Læser KUN metadata — aldrig en kode, et token eller en nøgle:

  hurtigt (hver kørsel)
    * HA's journal        → afviste logins, IP-ban
    * SSH-add-on'ets log  → godkendte/afviste logins + afsender
    * Trail Buddys log    → kald udefra, afviste kald, forkert turkode,
                            ufuldendte TLS-håndtryk ("bank på døren")
    * .storage/auth       → nye login-tokens/brugere, token brugt fra fremmed IP
    * /proc/net/tcp*      → lyttende porte uden for loopback mod godkendt liste
  langsomt (højst én gang i timen)
    * routeren            → port-forward, DMZ, UPnP, fjernadgang, port-trigger
    * Supervisor          → add-ons med host-port, backups, opdateringer
    * målte svagheder     → MFA, SSH-kodeord, Apollo-web uden login, filrettigheder

HA skriver ikke længere home-assistant.log, og journalen rækker ~1 uge — derfor
gemmes hver hændelse her (/config/.cyber_vagt_state.json + cyber_vagt_log.jsonl,
begge git-ignoreret: de rummer IP-adresser).

Grænser (ærligt): porte >= 32768 skifter ved hver genstart og kan ikke knyttes
til en proces fra core → de tælles, men kun porte < 32768 sammenlignes med
listen. Et hul i en log (flere linjer end vinduet mellem to kørsler) meldes
som hændelsen "loghul" i stedet for at blive tiet væk.

Brug: cyber_vagt.py koer | kvitter | godkend-porte | status
"""

from __future__ import annotations

import fcntl
import hashlib
import ipaddress
import json
import os
import re
import socket
import sys
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

ROD = Path(__file__).resolve().parent.parent
STATE = ROD / ".cyber_vagt_state.json"
LOCK = ROD / ".cyber_vagt_state.lock"
LOG = ROD / "cyber_vagt_log.jsonl"
SUP = "http://supervisor"

# (kilde, sti, linjer pr. kørsel). Core skriver ~4 linjer/min, Trail Buddy
# ~1/min på turen; vinduerne rækker til timer, ikke minutter.
KILDER = {
    "ha": ("/core/logs", 6000),
    "ssh": ("/addons/a0d7b954_ssh/logs", 2000),
    "tb": ("/addons/local_trailbuddy/logs", 4000),
}
FOERSTE_VINDUE = 2_000_000
LANGSOM_S = 3300
APOLLO = ["192.0.2.220", "192.0.2.32", "192.0.2.184", "192.0.2.117", "192.0.2.13"]
EFEMER = 32768
TB_KODE_GRAENSE = 3  # forkerte turkoder på 24 t før det er et "forsøg"
MAX_HAENDELSER = 300
ANSI = re.compile(r"\x1b\[[0-9;]*m")
TS_NET = re.compile(r"[a-z0-9-]+\.ts\.net")

RE_HA_FEJL = re.compile(
    r"invalid authentication from (\S+?)(?: \(([^)]+)\))?\. Requested URL: '([^']*)'"
)
RE_HA_BAN = re.compile(r"Banned IP ([0-9a-fA-F.:]+)")
RE_SSH_OK = re.compile(r"Accepted (\S+) for (\S+) from (\S+)")
RE_SSH_FEJL = re.compile(
    r"(?:Failed \S+ for (?:invalid user )?(\S*) from (\S+)|Invalid user (\S*) from (\S+))"
)
RE_TB = re.compile(r': (\S+) - - \[[^\]]+\] "(\w+) (\S+) HTTP/[\d.]+" (\d{3})')


def nu() -> float:
    return time.time()


def iso(t: float) -> str:
    return datetime.fromtimestamp(t).astimezone().isoformat(timespec="seconds")


def ip_klasse(ip: str | None) -> str:
    """LAN / tailnet / intern / FREMMED — 'FREMMED' er alt der ikke er husets."""
    if not ip:
        return "ukendt"
    try:
        a = ipaddress.ip_address(ip.strip("[]"))
    except ValueError:
        return "ukendt"
    if a.version == 6 and a.ipv4_mapped:
        a = a.ipv4_mapped
    if a.is_loopback:
        return "intern"
    if a.version == 4:
        if a in ipaddress.ip_network("192.168.0.0/24"):
            return "LAN"
        if a in ipaddress.ip_network("100.64.0.0/10"):
            return "tailnet"
        if a in ipaddress.ip_network("172.30.32.0/23"):
            return "intern"
    elif a in ipaddress.ip_network("fd76:1255:d756::/48"):
        return "tailnet"
    elif a.is_link_local:
        return "LAN"
    return "FREMMED"


def sup(sti: str, raa: bool = False, linjer: int = 0, timeout: int = 40):
    h = {"Authorization": "Bearer " + os.environ.get("SUPERVISOR_TOKEN", "")}
    if raa:
        h["Accept"] = "text/x-log"
        h["Range"] = f"entries=:-{linjer}:{linjer}"
    with urllib.request.urlopen(urllib.request.Request(SUP + sti, headers=h), timeout=timeout) as r:
        d = r.read()
    if raa:
        return d.decode("utf-8", "replace")
    return json.loads(d).get("data", {})


def laes() -> dict:
    try:
        return json.loads(STATE.read_text())
    except OSError, ValueError:
        return {}


def skriv(d: dict) -> None:
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")))
    os.chmod(tmp, 0o600)
    tmp.replace(STATE)


class Vagt:
    def __init__(self, d: dict) -> None:
        self.d = d
        self.frisk = not d.get("maalt_fra")
        self.nye: list[dict] = []
        self.blind: list[str] = []
        d.setdefault("cursor", {})
        d.setdefault("dag", {})
        d.setdefault("haendelser", [])
        d.setdefault("tokens", {})
        d.setdefault("kilder", {"ssh": [], "ha": []})
        d.setdefault("kvitteret", 0)
        d.setdefault("langsom", {})

    # -- hændelser ---------------------------------------------------------
    def haend(
        self, niveau: str, slags: str, tekst: str, t: float | None = None, push: bool = True
    ) -> None:
        h = {
            "t": iso(t or nu()),
            "niveau": niveau,
            "type": slags,
            "tekst": TS_NET.sub("<tailnet>", tekst)[:200],
        }
        self.d["haendelser"].append(h)
        try:
            with LOG.open("a") as f:
                f.write(json.dumps(h, ensure_ascii=False) + "\n")
            os.chmod(LOG, 0o600)
        except OSError:
            pass
        # Første kørsel sår historikken: den vises, men pusher ikke en uge gammelt nyt.
        if push and not self.frisk:
            self.nye.append(h)

    def tael(self, t: float, noegle: str, n: int = 1) -> None:
        dag = datetime.fromtimestamp(t).strftime("%Y-%m-%d")
        self.d["dag"].setdefault(dag, {})
        self.d["dag"][dag][noegle] = self.d["dag"][dag].get(noegle, 0) + n

    # -- logs ---------------------------------------------------------------
    def nye_linjer(self, kilde: str) -> list[tuple[float, str]]:
        sti, vindue = KILDER[kilde]
        cur = self.d["cursor"].get(kilde)
        n = vindue if cur else FOERSTE_VINDUE
        try:
            tekst = sup(sti, raa=True, linjer=n, timeout=120 if not cur else 40)
        except Exception as e:  # noqa: BLE001 — enhver fejl = vi var blinde her
            self.blind.append(f"{kilde}-log ({type(e).__name__})")
            return []
        ud: list[tuple[float, str]] = []
        for raa in tekst.splitlines():
            try:
                t = datetime.fromisoformat(raa[:29]).timestamp()
            except ValueError:
                continue
            ud.append((t, ANSI.sub("", raa[30:])))
        if not ud:
            return []
        if not self.d.get("maalt_fra") or kilde not in self.d.get("fra", {}):
            self.d.setdefault("fra", {})[kilde] = iso(ud[0][0])
        if cur:
            if ud[0][0] > cur["t"] and len(ud) >= n - 1:
                self.haend(
                    "info",
                    "loghul",
                    f"{kilde}-loggen skrev mere end {n} linjer mellem to kørsler — "
                    f"{iso(cur['t'])} til {iso(ud[0][0])} er ikke læst",
                    push=True,
                )
            set_h = set(cur.get("h", []))
            ud = [(t, s) for t, s in ud if t > cur["t"] or (t == cur["t"] and _h(s) not in set_h)]
        if ud:
            sidste = ud[-1][0]
            gamle = cur.get("h", []) if cur and cur["t"] == sidste else []
            self.d["cursor"][kilde] = {
                "t": sidste,
                "h": gamle + [_h(s) for t, s in ud if t == sidste],
            }
        return ud

    def ha_log(self) -> None:
        for t, s in self.nye_linjer("ha"):
            m = RE_HA_FEJL.search(s)
            if m:
                ip = m.group(2) or m.group(1)
                self.tael(t, "ha_fejl")
                self.haend(
                    "forsoeg",
                    "ha_login_afvist",
                    f"Afvist login på Home Assistant fra {ip} ({ip_klasse(ip)}), adresse {m.group(3)[:60]}",
                    t,
                )
                continue
            m = RE_HA_BAN.search(s)
            if m:
                self.haend(
                    "alarm",
                    "ha_ip_ban",
                    f"Home Assistant har spærret {m.group(1)} efter 10 afviste logins",
                    t,
                )

    def ssh_log(self) -> None:
        kendte = self.d["kilder"]["ssh"]
        for t, s in self.nye_linjer("ssh"):
            m = RE_SSH_OK.search(s)
            if m:
                ip, kl = m.group(3), ip_klasse(m.group(3))
                self.tael(t, "ssh_ok")
                if kl == "FREMMED":
                    self.haend(
                        "alarm",
                        "ssh_fremmed",
                        f"SSH-login GODKENDT fra fremmed adresse {ip} ({m.group(1)})",
                        t,
                    )
                elif ip not in kendte:
                    self.haend(
                        "info", "ssh_ny_kilde", f"SSH-login fra en ny adresse på {kl}: {ip}", t
                    )
                if ip not in kendte:
                    kendte.append(ip)
                continue
            m = RE_SSH_FEJL.search(s)
            if m:
                ip = m.group(2) or m.group(4)
                self.tael(t, "ssh_fejl")
                self.haend(
                    "forsoeg", "ssh_afvist", f"Afvist SSH-login fra {ip} ({ip_klasse(ip)})", t
                )

    def tb_log(self) -> None:
        koder = [x for x in self.d.get("tb403", []) if x > nu() - 86400]
        for t, s in self.nye_linjer("tb"):
            if "TLS handshake error" in s:
                self.tael(t, "tb_bank")
                continue
            m = RE_TB.search(s)
            if not m or m.group(1).startswith(
                "172.30.32."
            ):  # alt andet end HA selv = udefra (Funnel)
                continue
            kode = int(m.group(4))
            if kode < 400:
                self.tael(t, "tb_ok")
                continue
            self.tael(t, "tb_afvist")
            sti = re.sub(r"(/api/[a-z]+(?:/plan)?)/.*", r"\1", m.group(3).split("?")[0])[:40]
            if m.group(1) != "127.0.0.1":
                sti += f" fra {m.group(1)}"
            if kode == 403:
                koder.append(t)
                self.haend(
                    "info",
                    "tb_forkert_kode",
                    f"Trail Buddy: forkert turkode ({m.group(2)} {sti})",
                    t,
                    push=False,
                )
                if len([x for x in koder if x > t - 86400]) == TB_KODE_GRAENSE:
                    self.haend(
                        "forsoeg",
                        "tb_kodegaet",
                        f"Trail Buddy: {TB_KODE_GRAENSE} forkerte turkoder på et døgn (spærres ved 10)",
                        t,
                    )
            else:
                self.haend(
                    "info",
                    "tb_afvist",
                    f"Trail Buddy afviste {m.group(2)} {sti} ({kode})",
                    t,
                    push=False,
                )
        self.d["tb403"] = koder

    # -- HA's login-tokens ----------------------------------------------------
    def tokens(self) -> dict:
        try:
            a = json.loads((ROD / ".storage" / "auth").read_text())["data"]
        except (OSError, ValueError, KeyError) as e:
            self.blind.append(f"login-tokens ({type(e).__name__})")
            return {}
        navne = {u["id"]: u.get("name") or "?" for u in a["users"]}
        mennesker = sorted(u["id"] for u in a["users"] if not u.get("system_generated"))
        gamle_br = self.d.get("brugere")
        if gamle_br is not None:
            for uid in mennesker:
                if uid not in gamle_br:
                    self.haend("alarm", "ha_ny_bruger", f"Ny bruger i Home Assistant: {navne[uid]}")
        self.d["brugere"] = mennesker
        kendt = self.d["tokens"]
        liste, fremmede = [], 0
        for tk in a["refresh_tokens"]:
            if tk.get("token_type") == "system":
                continue
            tid, ip = tk["id"], tk.get("last_used_ip")
            kl = ip_klasse(ip) if ip else "aldrig brugt"
            klient = tk.get("client_name") or (
                "app" if "home-assistant" in (tk.get("client_id") or "") else "browser"
            )
            hvem = navne.get(tk.get("user_id"), "?")
            if kl == "FREMMED":
                fremmede += 1
            gl = kendt.get(tid)
            if gl is None and not self.frisk:
                self.haend(
                    "info",
                    "ha_nyt_login",
                    f"Nyt login på Home Assistant: {hvem} · {klient} · fra {kl}",
                )
            if kl == "FREMMED" and (gl is None or gl.get("ip") != ip):
                self.haend(
                    "alarm",
                    "ha_token_fremmed",
                    f"Home Assistant-login ({hvem} · {klient}) brugt fra fremmed adresse {ip}",
                )
            kendt[tid] = {"ip": ip}
            liste.append(
                {
                    "hvem": hvem,
                    "klient": klient[:40],
                    "type": tk.get("token_type"),
                    "sidst": (tk.get("last_used_at") or "")[:10],
                    "fra": kl,
                }
            )
        for tid in [x for x in kendt if x not in {t["id"] for t in a["refresh_tokens"]}]:
            del kendt[tid]
        return {"tokens": liste, "token_fremmede": fremmede, "brugere": len(mennesker)}

    # -- lyttende porte -------------------------------------------------------
    def porte(self) -> dict:
        faste, efemere = set(), 0
        for fil in ("/proc/net/tcp", "/proc/net/tcp6"):
            try:
                rk = Path(fil).read_text().splitlines()[1:]
            except OSError:
                self.blind.append("lyttende porte")
                continue
            for r in rk:
                f = r.split()
                if len(f) < 4 or f[3] != "0A":
                    continue
                adr, port = f[1].rsplit(":", 1)
                p = int(port, 16)
                if (
                    adr.startswith("0100007F")
                    or adr == "00000000000000000000000001000000"
                    or adr.startswith("0000000000000000FFFF00000100007F")
                ):
                    continue
                if p >= EFEMER:
                    efemere += 1
                else:
                    faste.add(p)
        godk = self.d.get("porte")
        if godk is None:
            godk = self.d["porte"] = sorted(faste)
        ukendte = sorted(faste - set(godk))
        meldt = self.d.setdefault("porte_meldt", [])
        for p in ukendte:
            if p not in meldt:
                meldt.append(p)
                self.haend(
                    "alarm",
                    "ny_port",
                    f"NUC'en lytter på en ny port: {p} (ikke på den godkendte liste)",
                )
        self.d["porte_meldt"] = [p for p in meldt if p in ukendte]
        return {"porte": sorted(faste), "porte_ukendte": ukendte, "porte_efemere": efemere}

    # -- langsomme tjek ---------------------------------------------------------
    def langsom(self, tving: bool = False) -> dict:
        la = self.d["langsom"]
        if not tving and nu() - la.get("t", 0) < LANGSOM_S:
            return la
        ny: dict = {"t": nu(), "svagheder": []}
        sv = ny["svagheder"]

        # Routerens perimeter (samme login som wifi-vagten; dens kørsler ligger på /5).
        try:
            import ha_secrets
            from gaeste_wifi import Router

            r = Router()
            r.login(ha_secrets.get("router_admin_user"), ha_secrets.get("router_admin_password"))
            try:
                nat = (r._kald("GET", "/api/v1/nat/rules") or [{}])[0].get("nat", {})
                dmz = (r._kald("GET", "/api/v1/nat/dmz") or [{}])[0].get("nat", {}).get("dmz", [])
                upnp = (r._kald("GET", "/api/v1/advanced/upnp") or [{}])[0].get("UPNPEnable", 0)
                fjern = (r._kald("GET", "/api/v1/remote-access") or [{}])[0].get("remoteAccess", [])
                trig = (r._kald("GET", "/api/v1/port_triggering") or [{}])[0].get("list", [])
            finally:
                try:
                    r.logout()
                except Exception:  # noqa: BLE001
                    pass
            aabent = []
            if nat.get("rules"):
                aabent.append(f"{len(nat['rules'])} port-forward")
            if any(str(x.get("enable")) not in ("0", "False", "false") for x in dmz):
                aabent.append("DMZ")
            if upnp:
                aabent.append("UPnP")
            if any(x.get("wan") for x in fjern):
                aabent.append("fjernadgang fra internettet")
            if trig:
                aabent.append(f"{len(trig)} port-trigger")
            ny["router"] = {"ok": True, "aabent": aabent, "t": nu()}
            if aabent and aabent != la.get("router", {}).get("aabent"):
                self.haend(
                    "alarm", "router_aaben", "Routeren har åbnet udadtil: " + ", ".join(aabent)
                )
        except Exception as e:  # noqa: BLE001
            ny["router"] = {
                **la.get("router", {"aabent": []}),
                "ok": False,
                "fejl": type(e).__name__,
            }

        # Add-ons: host-porte og beskyttelse.
        try:
            hp: dict[str, list] = {}
            ubeskyttet, opd = [], 0
            for ad in sup("/addons").get("addons", []):
                if ad.get("update_available"):
                    opd += 1
                if ad.get("state") != "started":
                    continue
                info = sup(f"/addons/{ad['slug']}/info")
                pr = sorted(str(v) for v in (info.get("network") or {}).values() if v)
                if pr:
                    hp[ad["slug"]] = pr
                if not info.get("protected", True):
                    ubeskyttet.append(ad["slug"])
                if ad["slug"] == "a0d7b954_ssh":
                    o = (info.get("options") or {}).get("ssh", {})
                    if o.get("password"):
                        sv.append("SSH tillader login med kodeord (ikke kun nøgle)")
            gl = self.d.get("addon_porte")
            if gl is not None:
                for slug, pr in hp.items():
                    for p in pr:
                        if p not in gl.get(slug, []):
                            self.haend(
                                "alarm", "addon_port", f"Add-on {slug} har åbnet host-port {p}"
                            )
            self.d["addon_porte"] = hp
            ny["addon_porte"] = hp
            ny["addon_ubeskyttet"] = ubeskyttet
            ny["addon_opdateringer"] = opd
        except Exception as e:  # noqa: BLE001
            self.blind.append(f"add-ons ({type(e).__name__})")
            for k in ("addon_porte", "addon_ubeskyttet", "addon_opdateringer"):
                ny[k] = la.get(k)

        try:
            bk = sorted(sup("/backups").get("backups", []), key=lambda b: b.get("date", ""))
            ukrypt = [b for b in bk if not b.get("protected")]
            ny["backup"] = {
                "antal": len(bk),
                "ukrypteret": len(ukrypt),
                "nyeste": bk[-1]["date"][:19] if bk else None,
                "nyeste_krypteret": bool(bk and bk[-1].get("protected")),
            }
            if ukrypt:
                sv.append(f"{len(ukrypt)} af {len(bk)} backups er ikke krypteret")
            core = sup("/core/info")
            ny["core"] = {
                "version": core.get("version"),
                "opdatering": bool(core.get("update_available")),
            }
            if core.get("update_available"):
                sv.append(f"Home Assistant {core.get('version')} har en opdatering der venter")
        except Exception as e:  # noqa: BLE001
            self.blind.append(f"supervisor ({type(e).__name__})")
            ny["backup"], ny["core"] = la.get("backup"), la.get("core")

        # MFA: antal brugere med en tilmeldt TOTP (kun optælling).
        try:
            totp = json.loads((ROD / ".storage" / "auth_module.totp").read_text())["data"].get(
                "users", {}
            )
            med = len(totp)
        except OSError, ValueError, KeyError:
            med = 0
        br = len(self.d.get("brugere") or [])
        if med < br:
            sv.append(f"{br - med} af {br} konti har ikke to-trins-login (MFA)")

        aabne = 0
        for ip in APOLLO:
            try:
                with urllib.request.urlopen(f"http://{ip}/", timeout=3) as rsp:
                    aabne += rsp.status == 200
            except Exception:  # noqa: BLE001 — 401 eller væk = ikke åben
                pass
        if aabne:
            sv.append(f"{aabne} radar-sensorer har en webside uden login på lokalnettet")
        try:
            import ha_secrets

            if ha_secrets.SECRETS_FILE.stat().st_mode & 0o077:
                sv.append("Husets kodefil kan læses af andre end root")
        except OSError, ImportError:
            pass
        self.d["langsom"] = ny
        return ny


def _h(s: str) -> str:
    return hashlib.sha1(s.encode()).hexdigest()[:10]


def resultat(v: Vagt, tok: dict, prt: dict, la: dict) -> dict:
    d = v.d
    graense = nu() - 7 * 86400
    d["haendelser"] = d["haendelser"][-MAX_HAENDELSER:]
    for dag in sorted(d["dag"])[:-400]:
        del d["dag"][dag]

    def t_af(h: dict) -> float:
        return datetime.fromisoformat(h["t"]).timestamp()

    aabne = [
        h
        for h in d["haendelser"]
        if t_af(h) > max(graense, d["kvitteret"]) and h["niveau"] != "info"
    ]
    if any(h["niveau"] == "alarm" for h in aabne):
        status = "Alarm"
    elif aabne:
        status = "Forsøg set"
    elif v.blind:
        status = "Blind"
    else:
        status = "Ingen tegn"
    dage = [(datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]

    def sum7(k: str) -> int:
        return sum(d["dag"].get(x, {}).get(k, 0) for x in dage)

    i_dag = d["dag"].get(dage[0], {})
    router = la.get("router", {})
    return {
        "ok": True,
        "status": status,
        "grunde": [h["tekst"] for h in aabne][-5:] + [f"Kunne ikke læse: {b}" for b in v.blind],
        "blind": v.blind,
        "koert": iso(nu()),
        "maalt_fra": d.get("maalt_fra"),
        "ha_fejl_7d": sum7("ha_fejl"),
        "ssh_ok_7d": sum7("ssh_ok"),
        "ssh_fejl_7d": sum7("ssh_fejl"),
        "tb_ok_7d": sum7("tb_ok"),
        "tb_afvist_7d": sum7("tb_afvist"),
        "tb_bank_7d": sum7("tb_bank"),
        "tb_ok_i_dag": i_dag.get("tb_ok", 0),
        "tb_afvist_i_dag": i_dag.get("tb_afvist", 0),
        "tb_bank_i_dag": i_dag.get("tb_bank", 0),
        "forsoeg_7d": len(
            [h for h in d["haendelser"] if t_af(h) > graense and h["niveau"] != "info"]
        ),
        "uge": [
            {
                "dag": x[5:],
                **{
                    k: d["dag"].get(x, {}).get(k, 0)
                    for k in ("ha_fejl", "ssh_ok", "ssh_fejl", "tb_ok", "tb_afvist", "tb_bank")
                },
            }
            for x in reversed(dage)
        ],
        **tok,
        **prt,
        "ssh_kilder": [f"{ip} ({ip_klasse(ip)})" for ip in d["kilder"]["ssh"]][-8:],
        "router": "Ukendt"
        if "aabent" not in router
        else ("Åben" if router["aabent"] else "Lukket"),
        "router_aabent": router.get("aabent", []),
        "router_laest": iso(router["t"]) if router.get("t") else None,
        "router_ok": router.get("ok", False),
        "addon_porte": la.get("addon_porte") or {},
        "addon_ubeskyttet": la.get("addon_ubeskyttet") or [],
        "addon_opdateringer": la.get("addon_opdateringer") or 0,
        "backup": la.get("backup") or {},
        "core": la.get("core") or {},
        "svagheder": la.get("svagheder", []),
        "kvitteret": iso(d["kvitteret"]) if d["kvitteret"] else None,
        "log": list(reversed(d["haendelser"][-40:])),
        "nye": v.nye[-8:],
    }


def koer(d: dict, tving: bool = False) -> dict:
    v = Vagt(d)
    v.ha_log()
    v.ssh_log()
    v.tb_log()
    tok = v.tokens()
    prt = v.porte()
    la = v.langsom(tving or v.frisk)
    if v.frisk:
        d["maalt_fra"] = min(d.get("fra", {}).values(), default=iso(nu()))
    return resultat(v, tok, prt, la)


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    socket.setdefaulttimeout(40)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    with LOCK.open("w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        d = laes()
        try:
            if cmd == "kvitter":
                d["kvitteret"] = nu()
                res = koer(d)
            elif cmd == "godkend-porte":
                d.pop("porte", None)
                d["porte_meldt"] = []
                res = koer(d)
            elif cmd in ("koer", "koer-alt"):
                res = koer(d, tving=cmd == "koer-alt")
            else:
                print(
                    json.dumps(
                        {
                            "ok": True,
                            "maalt_fra": d.get("maalt_fra"),
                            "haendelser": len(d.get("haendelser", [])),
                        }
                    )
                )
                return 0
        except Exception as e:  # noqa: BLE001 — HA skal altid have et JSON-svar
            print(json.dumps({"ok": False, "fejl": type(e).__name__, "detalje": str(e)[:120]}))
            return 1
        skriv(d)
    print(json.dumps(res, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
