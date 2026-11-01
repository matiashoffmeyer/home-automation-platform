#!/usr/bin/env python3
"""Ugentligt tjek af huset mod Home Assistants NÆSTE beta (2026-10-31).

frenck/home-assistant-config kører HA's config-check mod stable, beta og dev i
CI. Vores stable-ben er prod og holdes af `ha_offline.py pin` (pre-push); dette
er beta-benet: en uge før den månedlige udgivelse ser vi om huset knækker.

Kører i HA core-containeren via command_line-sensoren `sensor.ha_beta_tjek`
(packages/ha_beta_tjek.yaml), som en automation opdaterer torsdag 03:40:

  (ingen argumenter)  skriv status som JSON til sensoren. I tjek-vinduet
                      (torsdag 03-06) — eller når flag-filen `koer_nu` findes —
                      startes et tjek i baggrunden, HVIS PyPI har en beta nyere
                      end huset som ikke er tjekket før.
  --barn VERSION      selve tjekket (detached): `ha_offline.py --version VERSION
                      check --json`. Push KUN ved fejl, aldrig i AirBnB.

Tilstand + log: .cache/ha-offline-core/beta_tjek.json og beta_tjek.log.
Eget cache-dir: et venv bygget i core-containeren peger på dens Python og kan
ikke bruges fra SSH-add-on'et (og omvendt) — de ville rive hinandens ned.
Bestil et tjek nu (fra SSH): `touch .cache/ha-offline-core/koer_nu` og opdatér
sensoren.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

TZ = ZoneInfo("Europe/Copenhagen")
CACHE = REPO / ".cache" / "ha-offline-core"
STATE = CACHE / "beta_tjek.json"
LOG = CACHE / "beta_tjek.log"
KOER_NU = CACHE / "koer_nu"
NOTIFY = "notify/mobile_app_phone_a"
PYPI = "https://pypi.org/pypi/homeassistant/json"
# Torsdag 03-06: beta 0 udkommer normalt onsdag aften, ugen før udgivelsen.
VINDUE_DAG, VINDUE_FRA, VINDUE_TIL = 3, 3, 6
TIMEOUT_S = 30 * 60

STABIL = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
BETA = re.compile(r"^(\d+)\.(\d+)\.(\d+)b(\d+)$")


def vkey(v: str) -> tuple:
    """Sorterings-nøgle: en beta ligger FØR sin egen udgivelse (b < stabil)."""
    if m := STABIL.match(v):
        return (*map(int, m.groups()), 1, 0)
    if m := BETA.match(v):
        y, mo, p, b = map(int, m.groups())
        return (y, mo, p, 0, b)
    return (0,)


def nu() -> datetime:
    return datetime.now(TZ)


def log(msg: str) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{nu().isoformat(timespec='seconds')} {msg}\n")


def load() -> dict:
    try:
        return json.loads(STATE.read_text())
    except OSError, ValueError:
        return {}


def save(st: dict) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1))
    tmp.replace(STATE)


def prod_version() -> str:
    try:
        return (REPO / ".HA_VERSION").read_text().strip()
    except OSError:
        return ""


def nyeste_beta() -> str | None:
    req = urllib.request.Request(PYPI, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=25) as r:
        rel = json.load(r)["releases"]
    betaer = [
        v
        for v, filer in rel.items()
        if BETA.match(v) and filer and not all(f.get("yanked") for f in filer)
    ]
    return max(betaer, key=vkey) if betaer else None


# ---------------------------------------------------------------------------
# HA-API: core-containerens SUPERVISOR_TOKEN afvises for /core/api (401) →
# ha_api_token + 127.0.0.1:8123 (som sky_notify/plant_notify); fra SSH-add-on'et
# virker supervisor-proxyen.
# ---------------------------------------------------------------------------
def _api(method: str, path: str, body: dict | None = None):
    veje = []
    try:
        import ha_secrets  # noqa: PLC0415

        veje.append(("http://127.0.0.1:8123", ha_secrets.get(ha_secrets.HA_API_TOKEN)))
    except Exception:  # noqa: BLE001
        pass
    if os.environ.get("SUPERVISOR_TOKEN"):
        veje.append(("http://supervisor/core", os.environ["SUPERVISOR_TOKEN"]))
    sidste = None
    for base, tok in veje:
        try:
            req = urllib.request.Request(
                f"{base}/api/{path}",
                data=json.dumps(body).encode() if body is not None else None,
                method=method,
                headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                raw = r.read()
            return json.loads(raw) if raw else None
        except Exception as e:  # noqa: BLE001
            sidste = e
    raise RuntimeError(f"HA-API utilgængeligt: {sidste}")


def push(titel: str, besked: str) -> str:
    """Én push til Parent A — men ALDRIG i AirBnB (telefonen kan være i en gæsts hænder)."""
    try:
        mode = (_api("GET", "states/input_select.house_mode") or {}).get("state")
        if mode == "AirBnB":
            log("push sprunget over: AirBnB")
            return "airbnb"
        _api("POST", f"services/{NOTIFY}", {"title": titel, "message": besked})
        return "sendt"
    except Exception as e:  # noqa: BLE001
        log(f"push fejlede: {e}")
        return "fejlede"


# ---------------------------------------------------------------------------
# Barnet: selve tjekket
# ---------------------------------------------------------------------------
def system_pakker() -> dict[str, str]:
    """{navn: version@mtime} for DENNE Pythons pakker — i core-containeren er det
    produktionens. Selvtjekket i barn() sammenligner før og efter kørslen."""
    import importlib.metadata as md  # noqa: PLC0415

    ud = {}
    for d in md.distributions():
        sti = getattr(d, "_path", None)
        try:
            mt = int(Path(sti).stat().st_mtime) if sti else 0
        except OSError:
            mt = 0
        ud[d.metadata["Name"]] = f"{d.version}@{mt}"
    return ud


def barn(version: str) -> int:
    log(f"start {version} (prod {prod_version()})")
    foer = system_pakker()
    # UV_SYSTEM_PYTHON/UV_PYTHON fjernes også her (livrem + seler; ha_offline.py
    # fjerner dem selv): arvet fra core-containeren installerede beta-HA'en sine
    # krav i PRODUKTIONENS Python (31/10, se ha_offline.reexec_in_venv).
    env = {k: v for k, v in os.environ.items() if k not in ("UV_SYSTEM_PYTHON", "UV_PYTHON")}
    env = dict(
        env,
        HA_OFFLINE_CACHE=str(CACHE),
        UV_CACHE_DIR=str(REPO / ".cache" / "uv-core"),
        UV_PYTHON_INSTALL_DIR=str(REPO / ".cache" / "uv-python-core"),
    )
    st = load()
    try:
        r = subprocess.run(
            [
                sys.executable,
                str(REPO / "scripts" / "ha_offline.py"),
                "--version",
                version,
                "check",
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_S,
            env=env,
        )
        out, err, kode = r.stdout, r.stderr, r.returncode
    except subprocess.TimeoutExpired:
        out, err, kode = "", f"timeout efter {TIMEOUT_S // 60} min", -1
    resultat = None
    if "{" in out and kode in (0, 1):
        try:
            res = json.loads(out[out.index("{") : out.rindex("}") + 1])
            fejl = res.get("errors", [])
            resultat = {
                "resultat": "fejl" if fejl else "ok",
                "antal_fejl": len(fejl),
                "fejl": [f[:200] for f in fejl[:5]],
                "advarsler": len(res.get("warnings", [])),
                # Teksterne: en ny advarsel mod betaen er ofte en deprecation
                # der bliver til en fejl i en senere udgivelse.
                "advarsler_tekst": [w[:200] for w in res.get("warnings", [])[:10]],
            }
        except ValueError:
            pass
    if resultat is None:
        hale = [linje for linje in err.strip().splitlines() if linje.strip()][-3:]
        resultat = {
            "resultat": "kunne_ikke_koere",
            "antal_fejl": 0,
            "fejl": [h[:200] for h in hale],
            "kode": kode,
        }
    # Selvtjek (31/10-hændelsen): må ALDRIG røre produktionens pakker. Gjorde den
    # det, er det en alarm — ikke et beta-resultat.
    efter = system_pakker()
    roert = sorted(n for n in set(foer) | set(efter) if foer.get(n) != efter.get(n))
    if roert:
        resultat = {
            "resultat": "alarm",
            "antal_fejl": 0,
            "fejl": [f"ÆNDREDE PRODUKTIONENS PAKKER: {', '.join(roert)[:180]}"],
            "kode": kode,
        }
        log(f"ALARM: produktionens pakker ændret: {roert}")
    st.update(
        resultat, version=version, slut=nu().isoformat(timespec="seconds"), prod=prod_version()
    )
    # Én push pr. (version, udfald): et genforsøg der fejler på samme måde
    # (kunne_ikke_koere køres igen næste vindue) må ikke pushe igen.
    sidst = st.get("sidst_push") or {}
    gentaget = sidst.get("version") == version and sidst.get("resultat") == resultat["resultat"]
    if resultat["resultat"] == "ok":
        st["push"] = "ingen"
    elif gentaget:
        st["push"] = "allerede_sendt"
    elif resultat["resultat"] == "alarm":
        st["push"] = push(
            "🚨 HA-beta-tjekket ændrede produktionens Python-pakker",
            f"{resultat['fejl'][0][:220]}\nIkke genstarte HA før de er gendannet. Tjekket er spærret.",
        )
    elif resultat["resultat"] == "fejl":
        linjer = "\n".join(f"• {f[:140]}" for f in resultat["fejl"][:3])
        st["push"] = push(
            f"⚠️ HA-beta {version}: {resultat['antal_fejl']} fejl i husets config",
            f"{linjer}\nFør opdateringen: python3 scripts/ha_offline.py --version {version} check",
        )
    else:
        st["push"] = push(
            f"⚠️ HA-beta-tjekket kunne ikke køre ({version})",
            (resultat["fejl"][-1] if resultat["fejl"] else f"exit {kode}")[:200],
        )
    if st["push"] == "sendt":
        st["sidst_push"] = {"version": version, "resultat": resultat["resultat"]}
    save(st)
    # Kun ét beta-venv ad gangen (≈1,1 GB hver) — de forrige bygges aldrig igen.
    for p in CACHE.glob("venv-*"):
        if p.is_dir() and p.name != f"venv-{version}" and BETA.match(p.name.removeprefix("venv-")):
            shutil.rmtree(p, ignore_errors=True)
            log(f"slettede {p.name}")
    log(f"slut {version}: {st['resultat']} ({st.get('antal_fejl', 0)} fejl, push {st['push']})")
    return 0


# ---------------------------------------------------------------------------
# Sensoren: status + evt. start
# ---------------------------------------------------------------------------
def start_barn(version: str, st: dict) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    logf = LOG.open("a", encoding="utf-8")
    subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "--barn", version],
        stdin=subprocess.DEVNULL,
        stdout=logf,
        stderr=logf,
        start_new_session=True,
    )
    sidst = st.get("sidst_push")
    st.clear()
    if sidst:
        st["sidst_push"] = sidst
    st.update(
        version=version,
        resultat="koerer",
        start=nu().isoformat(timespec="seconds"),
        prod=prod_version(),
    )
    save(st)


def koerer(st: dict) -> bool:
    if st.get("resultat") != "koerer":
        return False
    try:
        return (nu() - datetime.fromisoformat(st["start"])).total_seconds() < TIMEOUT_S + 600
    except KeyError, ValueError:
        return False


def sensor() -> int:
    st = load()
    t = nu()
    bestilt = KOER_NU.exists()
    note = ""
    if bestilt or (t.weekday() == VINDUE_DAG and VINDUE_FRA <= t.hour < VINDUE_TIL):
        KOER_NU.unlink(missing_ok=True)
        prod = prod_version()
        try:
            beta = nyeste_beta()
        except Exception as e:  # noqa: BLE001
            beta, note = None, f"PyPI: {e}"[:120]
        if st.get("resultat") == "alarm":
            note = "spærret efter alarm — ryd beta_tjek.json når pakkerne er gendannet"
        elif beta and vkey(beta) > vkey(prod) and not koerer(st):
            ny = beta != st.get("version") or st.get("resultat") == "kunne_ikke_koere"
            if ny:
                start_barn(beta, st)
                log(f"startet {beta} ({'bestilt' if bestilt else 'vindue'})")
        elif not note:
            note = "ingen beta nyere end huset" if not beta or vkey(beta) <= vkey(prod) else ""
    v = st.get("version", "")
    r = st.get("resultat", "")
    tilstand = {
        "ok": f"ok · {v}",
        "fejl": f"{st.get('antal_fejl', '?')} fejl · {v}",
        "koerer": f"kører · {v}",
        "kunne_ikke_koere": f"kunne ikke køre · {v}",
        "alarm": f"ALARM · produktionens pakker ændret · {v}",
    }.get(r, "intet tjek endnu")
    print(
        json.dumps(
            {
                "state": tilstand[:250],
                "version": v,
                "resultat": r,
                "tjekket": st.get("slut") or st.get("start", ""),
                "antal_fejl": st.get("antal_fejl", 0),
                "advarsler": st.get("advarsler", 0),
                "fejl": st.get("fejl", []),
                "prod": prod_version(),
                "note": note,
                "miljoe": {
                    "git": bool(shutil.which("git")),
                    "uv": bool(shutil.which("uv")),
                    "python": sys.version.split()[0],
                },
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--barn":
        sys.exit(barn(sys.argv[2]))
    sys.exit(sensor())
