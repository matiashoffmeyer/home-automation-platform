#!/usr/bin/env python3
"""Health — motoren bag siden (dashboards/helbred.yaml).

Al data bor i /config/helbred/ (HELBRED_DIR):
  profil.yaml, program.yaml, kost.yaml, historik.md, spoergsmaal.yaml   (dine filer)
  log/*.jsonl                                                           (skrevet her)
  .state.json                                                           (påmindelser)

Kommandoer:
  status idag|kost|statistik|historik   JSON til command_line-sensorerne
  cmd <base64-json>                     en handling fra siden (www/helbred-card.js)
  svar <ACTION> [<base64-tekst>]        et knap-/tekstsvar fra en push
  tick                                  hvert 5. min: send forfaldne påmindelser
  tjek                                  validér datafilerne (kør efter hver redigering)
  program                               hele programmet + kosten som læsbar tekst (markdown)

Token: en Long-Lived Access Token (HA → din profil → Sikkerhed → Opret token),
gemt som eneste linje i /config/helbred/.token (eller HELBRED_TOKEN_FIL).
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from oevelse_billeder import billeder  # noqa: E402

TZ = ZoneInfo("Europe/Copenhagen")
ROD = Path(os.environ.get("HELBRED_DIR", "/config/helbred"))
LOG = ROD / "log"
STATE = ROD / ".state.json"
TOKEN_FIL = Path(os.environ.get("HELBRED_TOKEN_FIL", str(ROD / ".token")))
HA_URL = "http://127.0.0.1:8123"
DASH = "/helbred-dash"
SENSORER = ["idag", "kost", "statistik", "historik"]

NIVEAUER = {
    -2: "Meget værre end forventet",
    -1: "Værre end forventet",
    0: "Som forventet",
    1: "Bedre end forventet",
    2: "Meget bedre end forventet",
}
# Grupper der ikke kræver 48 t pause (lav belastning / dagligt).
LETTE = {"kerne", "gang", "mobilitet", "greb", "kondition", "knaebasis"}
UGEDAGE = ["mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"]
STEDER = ("fitness", "hjemme")


# --- små hjælpere -------------------------------------------------------------


def nu() -> datetime:
    return datetime.now(TZ)


def idag() -> date:
    return nu().date()


def d(s) -> date:
    return s if isinstance(s, date) else date.fromisoformat(str(s)[:10])


def laes_yaml(navn):
    with open(ROD / navn, encoding="utf-8") as f:
        return yaml.safe_load(f)


def laes_log(navn) -> list[dict]:
    p = LOG / f"{navn}.jsonl"
    if not p.exists():
        return []
    ud = []
    for linje in p.read_text(encoding="utf-8").splitlines():
        linje = linje.strip()
        if linje:
            try:
                ud.append(json.loads(linje))
            except json.JSONDecodeError:
                continue
    return ud


def skriv_log(navn, post: dict):
    LOG.mkdir(parents=True, exist_ok=True)
    post = {"ts": nu().isoformat(timespec="seconds"), "dato": idag().isoformat(), **post}
    with open(LOG / f"{navn}.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(post, ensure_ascii=False) + "\n")
    return post


def omskriv_log(navn, poster: list[dict]):
    LOG.mkdir(parents=True, exist_ok=True)
    tmp = LOG / f"{navn}.jsonl.tmp"
    tmp.write_text(
        "".join(json.dumps(p, ensure_ascii=False) + "\n" for p in poster), encoding="utf-8"
    )
    os.replace(tmp, LOG / f"{navn}.jsonl")


def laes_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError:
        return {}


def gem_state(s: dict):
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, STATE)


def _token() -> str:
    try:
        t = TOKEN_FIL.read_text(encoding="utf-8").strip()
    except OSError:
        t = ""
    if not t:
        raise RuntimeError(f"token mangler i {TOKEN_FIL} (se README, trin 4)")
    return t


def ha(method, path, payload=None, timeout=15):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        f"{HA_URL}{path}",
        data=data,
        method=method,
        headers={"Authorization": "Bearer " + _token(), "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def ha_state(eid, default=None):
    try:
        return ha("GET", f"/api/states/{eid}").get("state", default)
    except Exception:
        return default


def notify_tjeneste() -> str:
    """profil.yaml `notify: mobile_app_<telefon>` → 'notify/mobile_app_<telefon>'."""
    n = str(laes_yaml("profil.yaml").get("notify") or "").strip()
    if not re.fullmatch(r"(notify[./])?[a-z0-9_]{3,80}", n):
        raise RuntimeError("profil.yaml: notify skal være fx mobile_app_min_telefon")
    return "notify/" + re.sub(r"^notify[./]", "", n)


def tal(x, dec=1):
    """12.0 → '12', 12.5 → '12,5' (dansk komma)."""
    if x is None:
        return ""
    x = round(float(x), dec)
    s = str(int(x)) if x == int(x) else f"{x:.{dec}f}".rstrip("0")
    return s.replace(".", ",")


def kort_dato(x) -> str:
    x = d(x)
    return f"{x.day}/{x.month}"


def smerte_navn(profil=None) -> str:
    """Det sted der følges ugentligt 0-10 (profil.yaml `smerte.navn`, fx "Knæ")."""
    profil = profil or laes_yaml("profil.yaml")
    return str((profil.get("smerte") or {}).get("navn") or "Knæ")


# --- programmet: dagens anbefaling -------------------------------------------


class Plan:
    """Dagens program udledt af program.yaml + træningsloggen."""

    def __init__(self, dag: date | None = None):
        self.dag = dag or idag()
        self.profil = laes_yaml("profil.yaml")
        self.prog = laes_yaml("program.yaml")
        self.ov = self.prog["oevelser"]
        self.ses = self.prog["sessioner"]
        self.regler = self.prog["regler"]
        self.start = d(self.profil["start_dato"])
        self.log = [l for l in laes_log("traening") if l.get("id") in self.ov]
        self.smerte = laes_log("smerte")
        self.smerte_navn = smerte_navn(self.profil)
        self.dag_nr = (self.dag - self.start).days + 1
        self.indkoering = self.dag_nr <= int(self.regler["indkoering_dage"])
        self.skaansom = self._skaansom()
        fitness = self.profil.get("fitness_dage", [0, 1, 2, 3, 4])
        self.sted = "fitness" if self.dag.weekday() in fitness else "hjemme"
        self.hoved_id = self._vaelg_session()

    # -- tilstand --
    def _skaansom(self) -> str | None:
        r = [x for x in self.smerte if (self.dag - d(x["dato"])).days <= 8]
        if not r:
            return None
        sidste = r[-1]["score"]
        if sidste >= self.regler["skaansom_smerte_score"]:
            return f"{self.smerte_navn} fik {sidste}/10 i sidste uge"
        tidl = [x for x in self.smerte if d(x["dato"]) < d(r[-1]["dato"])]
        if tidl and sidste - tidl[-1]["score"] >= 2:
            return f"{self.smerte_navn} gik fra {tidl[-1]['score']} til {sidste}"
        return None

    def _type(self, sid) -> str | None:
        return (self.ses.get(sid) or {}).get("type")

    def _dage_med(self, typ, fra, til) -> set[date]:
        """Datoer i [dag-fra, dag-til] (dage tilbage) med et logget pas af typen."""
        ud = set()
        for l in self.log:
            n = (self.dag - d(l["dato"])).days
            if til <= n <= fra and self._type(l.get("session")) == typ:
                ud.add(d(l["dato"]))
        return ud

    def _vaelg_session(self) -> str | None:
        i_dag = [l for l in self.log if d(l["dato"]) == self.dag and l.get("session")]
        for typ in ("styrke", "langtur", "kondition"):
            for l in reversed(i_dag):
                if self._type(l["session"]) == typ:
                    return l["session"]
        if self.dag_nr < 1:
            return None
        weekend = self.dag.weekday() >= 5
        if weekend and not self.indkoering and "langtur" in self.ses:
            if not self._dage_med("langtur", self.regler["langtur_min_dage_imellem"] - 1, 1):
                return "langtur"
        if (
            not self._dage_med("styrke", 1, 1)
            and len(self._dage_med("styrke", 6, 1)) < self.regler["styrke_max_pr_7_dage"]
        ):
            rot = self.prog["rotation"]
            tidl = [
                l["session"]
                for l in self.log
                if d(l["dato"]) < self.dag and l.get("session") in rot
            ]
            return rot[(rot.index(tidl[-1]) + 1) % len(rot)] if tidl else rot[0]
        if (
            "kondition" in self.ses
            and len(self._dage_med("kondition", 6, 1)) < self.regler["kondition_max_pr_7_dage"]
        ):
            return "kondition"
        return None

    # -- anbefaling pr. øvelse --
    def anbefal(self, oid) -> dict:
        o = self.ov[oid]
        tidl = [l for l in self.log if l["id"] == oid and d(l["dato"]) < self.dag]
        saet = int(o.get("saet", 1))
        antal, kg = o["lo"], o.get("kg")
        frys = self.indkoering or bool(self.skaansom)
        if tidl:
            s = tidl[-1]
            antal = float(s.get("antal", o["lo"]))
            kg = s.get("kg", kg) if "kg" in o else None
            if not frys:
                if antal >= o["hi"] and "kg" in o:
                    kg = float(kg or 0) + float(o.get("kg_trin", 0))
                    antal = o["lo"]
                else:
                    antal = min(o["hi"], antal + o.get("trin", 1))
            antal = max(o["lo"], min(o["hi"], antal))
        if self.indkoering:
            saet = min(saet, 2)
        if self.skaansom:
            saet = max(1, saet - 1)
        sidst = None
        if tidl:
            s = tidl[-1]
            sidst = f"{tal(s.get('antal'))} {o['enhed']}"
            if s.get("kg"):
                sidst += f" · {tal(s['kg'])} kg"
            sidst += f" ({kort_dato(s['dato'])})"
        return {"saet": saet, "antal": antal, "kg": kg, "sidst": sidst}

    def _hvile(self, oid) -> str | None:
        o = self.ov[oid]
        tunge = set(o.get("grupper", [])) - LETTE
        if not tunge:
            return None
        # Hele kalenderdage, ikke timer: et pas i går eftermiddags spærrer i dag,
        # et pas i forgårs gør ikke — uanset hvornår på dagen siden åbnes.
        dage = max(1, round(float(self.regler["restitution_timer"]) / 24) - 1)
        for l in reversed(self.log):
            n = (self.dag - d(l["dato"])).days
            if n <= 0:
                continue
            if n > dage:
                break
            faelles = tunge & set(self.ov[l["id"]].get("grupper", []))
            if faelles:
                return (
                    f"{', '.join(sorted(faelles))} trænet {kort_dato(l['dato'])} — giv det 2 døgn"
                )
        return None

    def post(self, oid, steder=None, session=None) -> dict:
        o = self.ov[oid]
        a = self.anbefal(oid)
        gjort = [l for l in self.log if l["id"] == oid and d(l["dato"]) == self.dag]
        return {
            "id": oid,
            "navn": o["navn"],
            "enhed": o["enhed"],
            "saet": a["saet"],
            "antal": a["antal"],
            "kg": a["kg"],
            "har_kg": "kg" in o,
            "trin": o.get("trin", 1),
            "kg_trin": o.get("kg_trin", 0),
            "hvordan": o.get("hvordan", ""),
            "hvorfor": o.get("hvorfor", ""),
            "billeder": billeder(o.get("billede")),
            "sidst": a["sidst"],
            "steder": steder or list(STEDER),
            "session": session,
            "hvile": None if gjort else self._hvile(oid),
            "gjort": (
                {"antal": gjort[-1].get("antal"), "kg": gjort[-1].get("kg")} if gjort else None
            ),
        }

    def session_poster(self, sid) -> list[dict]:
        s = self.ses[sid]
        if "alle" in s:
            return [self.post(o, session=sid) for o in s["alle"]]
        ud, set_ = [], {}
        for sted in STEDER:
            for o in s.get(sted, []):
                set_.setdefault(o, []).append(sted)
        for o, steder in set_.items():
            ud.append(self.post(o, steder, sid))
        return ud

    def bannere(self) -> list[str]:
        b = []
        if self.dag_nr < 1:
            b.append(f"Programmet starter {kort_dato(self.start)}. I dag: hvil.")
        elif self.indkoering:
            b.append(
                f"Indkøring, dag {self.dag_nr} af {self.regler['indkoering_dage']}: højst 2 sæt, "
                "let vægt du kunne tage 4-5 gange mere. Sener og knæ skal vænne sig til det."
            )
        if self.skaansom:
            b.append(f"Skånsom uge: {self.skaansom}. Ét sæt mindre, ingen stigning.")
        return b


def status_idag() -> dict:
    p = Plan()
    daglig = p.session_poster("daglig")
    hoved = p.session_poster(p.hoved_id) if p.hoved_id else []
    brugt = {x["id"] for x in daglig + hoved}
    andre = [p.post(o) for o in p.ov if o not in brugt]
    vaegt = laes_log("vaegt")
    aktive = [x for x in daglig + hoved if p.sted in x["steder"] and not x["hvile"]]
    klaret = len([x for x in aktive if x["gjort"]])
    navne = p.profil.get("sted_navne") or {}
    return {
        "state": f"{klaret}/{len(aktive)}",
        "dato": p.dag.isoformat(),
        "ugedag": UGEDAGE[p.dag.weekday()],
        "dag_nr": p.dag_nr,
        "sted": p.sted,
        "steder": [{"id": s, "navn": navne.get(s, s.capitalize())} for s in STEDER],
        "session": (
            {
                "id": p.hoved_id,
                "navn": p.ses[p.hoved_id]["navn"],
                "type": p._type(p.hoved_id),
                "hvorfor": p.ses[p.hoved_id].get("hvorfor", ""),
            }
            if p.hoved_id
            else {
                "id": None,
                "navn": "Hviledag — kun basis og gåtur",
                "type": "hvile",
                "hvorfor": "Musklerne bliver stærkere, mens du hviler, ikke mens du træner. "
                "Basis-øvelserne og gåturen holder knæene i gang og forbrændingen oppe.",
            }
        ),
        "daglig_navn": p.ses["daglig"].get("navn", "Hver dag"),
        "daglig_hvorfor": p.ses["daglig"].get("hvorfor", ""),
        "daglig": daglig,
        "hoved": hoved,
        "andre": andre,
        "bannere": p.bannere(),
        "vaegt": {
            "sidst": vaegt[-1]["kg"] if vaegt else None,
            "sidst_dato": vaegt[-1]["dato"] if vaegt else None,
            "i_dag": bool(vaegt and d(vaegt[-1]["dato"]) == p.dag),
        },
        "smerte_navn": p.smerte_navn,
        "smerte_sidst": (p.smerte[-1] if p.smerte else None),
    }


# --- kost ---------------------------------------------------------------------


def vaegt_trend(dage=28):
    """Lineær regression over de sidste `dage` → (kg/uge, antal punkter) eller (None, n)."""
    pts = [
        ((d(v["dato"]) - idag()).days, float(v["kg"]))
        for v in laes_log("vaegt")
        if (idag() - d(v["dato"])).days <= dage
    ]
    if len(pts) < 3 or max(x for x, _ in pts) - min(x for x, _ in pts) < 10:
        return None, len(pts)
    n = len(pts)
    mx, my = sum(x for x, _ in pts) / n, sum(y for _, y in pts) / n
    sxx = sum((x - mx) ** 2 for x, _ in pts)
    return (sum((x - mx) * (y - my) for x, y in pts) / sxx * 7 if sxx else None), n


def start_kcal(profil, kost) -> tuple[int, str]:
    """kost.yaml `maal.kcal: auto` → Mifflin-St Jeor × aktivitet − underskud."""
    m = kost["maal"]
    if str(m.get("kcal", "auto")) != "auto":
        return int(m["kcal"]), ""
    vaegt = laes_log("vaegt")
    kg = float(vaegt[-1]["kg"]) if vaegt else float(profil["vaegt_kg"])
    alder = idag().year - int(profil["foedt"])
    bmr = 10 * kg + 6.25 * float(profil["hoejde_cm"]) - 5 * alder
    bmr += 5 if profil.get("koen", "mand") == "mand" else -161
    forbrug = bmr * float(m.get("aktivitet", 1.5))
    kcal = int(round((forbrug - float(m.get("underskud", 500))) / 50) * 50)
    kcal = max(int(m["justering"]["gulv"]), kcal)
    return kcal, (
        f"Regnet ud fra {tal(kg)} kg: forbrug ca. {int(round(forbrug, -1))} kcal "
        f"− {m.get('underskud', 500)} kcal underskud."
    )


def protein_maal(profil, kost) -> int:
    m = kost["maal"]
    if m.get("protein_g") not in (None, "auto"):
        return int(m["protein_g"])
    # 1,6 g pr. kg MÅLVÆGT (den vægt du vil ende på) — rigeligt til at bevare musklerne.
    return int(round(1.6 * float(profil["maalvaegt_kg"]) / 5) * 5)


def kcal_maal(profil, kost) -> tuple[int, str]:
    """Kalorie-målet følger vægten: justeringer gemmes i loggen, højst én pr. 14 dage."""
    j = kost["maal"]["justering"]
    just = laes_log("kcal")
    start, forkl = start_kcal(profil, kost)
    kcal = just[-1]["kcal"] if just else start
    trend, n = vaegt_trend()
    if trend is None:
        return kcal, (forkl + " " if not just else "") + (
            f"For få vejninger til at justere endnu ({n} de sidste 4 uger, der skal 3 over 10 dage til)."
        )
    tab = -trend  # positivt = taber
    tekst = f"Vægt-trend: {'+' if trend >= 0 else ''}{tal(trend, 2)} kg/uge."
    sidst = d(just[-1]["dato"]) if just else d(profil["start_dato"])
    if (idag() - sidst).days >= 14:
        ny = kcal
        if tab < j["min_tab"]:
            ny = max(j["gulv"], kcal - j["trin"])
        elif tab > j["max_tab"]:
            ny = kcal + j["trin"]
        if ny != kcal:
            skriv_log("kcal", {"kcal": ny, "trend": round(trend, 2), "fra": kcal})
            tekst += f" Målet er derfor ændret fra {kcal} til {ny} kcal."
            kcal = ny
    return kcal, tekst


def _raad(x) -> dict:
    """Et kost-råd er {gør, hvorfor} (eller en ren streng)."""
    if isinstance(x, dict):
        return {"goer": x.get("gør", ""), "hvorfor": x.get("hvorfor", "")}
    return {"goer": str(x), "hvorfor": ""}


KOST_AFSNIT = (
    ("principper", "Sådan gør du", "mdi:silverware-fork-knife"),
    ("drikke", "Drikke", "mdi:cup"),
    ("tilskud", "Tilskud", "mdi:pill"),
    ("snacks", "Når sulten kommer", "mdi:food-apple-outline"),
)
DAG_TITLER = {"hverdag": "Hverdag", "weekend": "Weekend"}


def status_kost() -> dict:
    k = laes_yaml("kost.yaml")
    profil = laes_yaml("profil.yaml")
    kcal, just = kcal_maal(profil, k)
    protein = protein_maal(profil, k)
    dage = []
    spist = {(x["dag"], x["id"]): x for x in laes_log("kost") if d(x["dato"]) == idag()}
    for navn, maal in k["maaltider"].items():
        dag = {
            "id": navn,
            "titel": DAG_TITLER.get(navn, navn.capitalize()),
            "kcal": sum(x["kcal"] for x in maal),
            "protein": sum(x["protein"] for x in maal),
            "maaltider": [
                {
                    "tid": x["tid"],
                    "hvad": x["hvad"],
                    "hvorfor": x.get("hvorfor", ""),
                    "kcal": x["kcal"],
                    "protein": x["protein"],
                    "id": x.get("id", str(i)),
                    "spist": (spist.get((navn, x.get("id", str(i)))) or {}).get("andel"),
                }
                for i, x in enumerate(maal)
            ],
        }
        dage.append(dag)
    # Planen er skrevet til ét kalorie-niveau; afviger målet, siges det tydeligt.
    plan = max((x["kcal"] for x in dage), default=kcal)
    diff = kcal - plan
    ekstra = (
        f"Dit mål er {abs(diff)} kcal {'over' if diff > 0 else 'under'} dagsplanen herunder: "
        + (
            "læg fx en ekstra frugt og et glas mælk til."
            if diff > 0
            else "skær lidt af stivelsen (ris/pasta/kartofler/brød) og drop olien på aftensmaden."
        )
        if abs(diff) >= 150
        else ""
    )
    afsnit = []
    for noegle, titel, ikon in KOST_AFSNIT:
        raad = [_raad(x) for x in k.get(noegle) or []]
        if raad:
            afsnit.append({"titel": titel, "ikon": ikon, "raad": raad})
    ind = [f"{v['navn']}: {tal(v['uge1'])} {v['enhed']}" for v in k.get("indkoeb") or []]
    i_dag = {
        "kcal": round(sum(x["kcal"] for x in spist.values())),
        "protein": round(sum(x["protein"] for x in spist.values())),
        "antal": len(spist),
    }
    return {
        "state": kcal,
        "dato": idag().isoformat(),
        "i_dag": i_dag,
        "protein": protein,
        "justering": just,
        "ekstra": ekstra,
        "hvorfor_maal": k["maal"].get("hvorfor", ""),
        "dage": dage,
        "afsnit": afsnit,
        "indkoeb": "\n".join(f"- {x}" for x in ind),
    }


# --- statistik og vurdering ---------------------------------------------------


def forventet(profil, basis, dag: date) -> float:
    """Forventet vægt (kg/uge i profil.yaml er negative ved vægttab)."""
    uger = max(0, (dag - d(profil["start_dato"])).days / 7)
    f = profil["forventet_kg_uge"]
    v = basis + min(uger, 12) * f["foerste_12_uger"] + max(0, uger - 12) * f["derefter"]
    return max(v, float(profil["maalvaegt_kg"]))


def basisvaegt(profil, vaegt):
    start = d(profil["start_dato"])
    foerste = [float(v["kg"]) for v in vaegt if (d(v["dato"]) - start).days <= 10][:3]
    return sum(foerste) / len(foerste) if foerste else None


def uge_noegle(x: date) -> str:
    iso = x.isocalendar()
    return f"{iso[0]}-{iso[1]:02d}"


def beregn_vurdering() -> dict:
    profil = laes_yaml("profil.yaml")
    p = Plan()
    start = d(profil["start_dato"])
    dage = (idag() - start).days + 1
    dele = []
    sn = p.smerte_navn

    # Vægt: forventet tab ca. 0,5 kg/uge. Hurtigere end ~1 kg/uge koster muskler.
    trend, n = vaegt_trend()
    if trend is None:
        dele.append(
            {"navn": "Vægt", "niveau": None, "tekst": f"For få vejninger ({n}) til en trend."}
        )
    else:
        tab = -trend
        niv = -2 if tab < 0 else -1 if tab < 0.2 else 0 if tab < 0.45 else 1 if tab <= 1.0 else 0
        t = f"{'+' if trend >= 0 else ''}{tal(trend, 2)} kg/uge (målet er ca. −0,5)."
        if tab > 1.0:
            t += " Hurtigere end godt er — spis lidt mere, så det er fedt og ikke muskler der forsvinder."
        dele.append({"navn": "Vægt", "niveau": niv, "tekst": t})

    # Smerte (0-10, lavere er bedre). Forventet: stabil eller faldende.
    sm = p.smerte
    if len(sm) < 2:
        dele.append(
            {
                "navn": sn,
                "niveau": None,
                "tekst": f"Mindst to ugentlige {sn.lower()}-svar skal til.",
            }
        )
    else:
        ref = sm[max(0, len(sm) - 5)]
        uger = max(1, (d(sm[-1]["dato"]) - d(ref["dato"])).days / 7)
        rate = (sm[-1]["score"] - ref["score"]) / uger
        niv = (
            2
            if rate <= -1
            else 1
            if rate <= -0.5
            else 0
            if rate < 0.15
            else -1
            if rate < 0.75
            else -2
        )
        if sm[-1]["score"] <= 1:
            niv = max(niv, 1)
        dele.append(
            {
                "navn": sn,
                "niveau": niv,
                "tekst": f"{ref['score']} → {sm[-1]['score']} på {tal(uger, 0)} uge(r).",
            }
        )

    # Træning: styrke-dage de sidste 14 dage mod planens antal pr. uge.
    pr_uge = int(p.regler["styrke_max_pr_7_dage"])
    vindue = min(14, max(1, dage))
    styrke = len(p._dage_med("styrke", vindue - 1, 0))
    plan = max(1, round(pr_uge * vindue / 7))
    andel = styrke / plan
    daglig = len(
        {
            d(l["dato"])
            for l in p.log
            if (idag() - d(l["dato"])).days < vindue and l.get("session") == "daglig"
        }
    )
    niv = 1 if andel >= 0.85 else 0 if andel >= 0.6 else -1 if andel >= 0.3 else -2
    if dage < 4:
        niv = None  # for få dage til at sige noget om fremmødet
    dele.append(
        {
            "navn": "Træning",
            "niveau": niv,
            "tekst": f"{styrke} af {plan} styrkepas og basis {daglig} af {vindue} dage.",
        }
    )

    vaegte = {"Vægt": 0.45, sn: 0.3, "Træning": 0.25}
    kendte = [x for x in dele if x["niveau"] is not None]
    if dage < 14 or not kendte:
        niveau = 0
        tekst = f"Dag {max(dage, 0)}: for tidligt at dømme. Første rigtige vurdering efter to uger."
    else:
        v = sum(vaegte[x["navn"]] for x in kendte)
        niveau = max(-2, min(2, round(sum(x["niveau"] * vaegte[x["navn"]] for x in kendte) / v)))
        svag = min(kendte, key=lambda x: x["niveau"])
        staerk = max(kendte, key=lambda x: x["niveau"])
        tekst = f"Stærkest: {staerk['navn'].lower()}. "
        if svag["niveau"] < 0:
            raad = {
                "Vægt": "Kalorie-målet på Kost-fanen justerer sig selv — hold dig til det, og log hvad du spiser i en uge.",
                sn: "Programmet tager selv en skånsom uge. Bliver det ved med at stige, så vis forløbet til en fysioterapeut.",
                "Træning": "Det er fremmødet der flytter mest: hellere korte pas end ingen.",
            }[svag["navn"]]
            tekst += f"Halter: {svag['navn'].lower()}. {raad}"
    return {
        "dato": idag().isoformat(),
        "niveau": niveau,
        "label": NIVEAUER[niveau],
        "tekst": tekst,
        "dele": dele,
    }


def status_statistik() -> dict:
    profil = laes_yaml("profil.yaml")
    p = Plan()
    vaegt = laes_log("vaegt")
    basis = basisvaegt(profil, vaegt)
    start = d(profil["start_dato"])
    forv = []
    if basis:
        slut = idag() + timedelta(days=28)
        x = start
        while x <= slut:
            forv.append([x.isoformat(), round(forventet(profil, basis, x), 2)])
            x += timedelta(days=7)
    trend, _ = vaegt_trend()

    # Uger: styrkepas, kondition, basis-dage, km
    uger: dict[str, dict] = {}
    for l in p.log:
        u = uger.setdefault(
            uge_noegle(d(l["dato"])),
            {"styrke": set(), "kondition": set(), "daglig": set(), "km": 0.0},
        )
        typ = p._type(l.get("session"))
        if typ in ("styrke", "kondition", "daglig"):
            u[typ].add(l["dato"])
        if p.ov[l["id"]].get("enhed") == "km":
            u["km"] += float(l.get("antal", 0))
    uge_liste = [
        {
            "uge": k[-2:],
            "styrke": len(v["styrke"]),
            "kondition": len(v["kondition"]),
            "daglig": len(v["daglig"]),
            "km": round(v["km"], 1),
        }
        for k, v in sorted(uger.items())[-12:]
    ]

    # Løft: første mod seneste logning pr. øvelse (kun dem med ≥ 2 logninger)
    loeft = []
    for oid, o in p.ov.items():
        ls = [l for l in p.log if l["id"] == oid]
        if len(ls) < 2 or set(o.get("grupper", [])) <= LETTE:
            continue

        def fmt(l, o=o):
            return f"{tal(l.get('antal'))}" + (
                f" × {tal(l['kg'])} kg" if l.get("kg") else f" {o['enhed']}"
            )

        def score(l):
            return float(l.get("kg") or 0) * (1 + float(l.get("antal", 0)) / 30) or float(
                l.get("antal", 0)
            )

        s0, s1 = score(ls[0]), score(ls[-1])
        loeft.append(
            {
                "navn": o["navn"],
                "foerste": fmt(ls[0]),
                "sidste": fmt(ls[-1]),
                "pct": round((s1 / s0 - 1) * 100) if s0 else 0,
            }
        )

    maal_log = laes_log("maal")
    maal = []
    for m in profil["maalinger"]:
        ls = [x for x in maal_log if x.get("id") == m["id"]]
        if ls:
            maal.append(
                {
                    "navn": m["navn"].split(" (")[0],
                    "foerste": ls[0]["cm"],
                    "sidste": ls[-1]["cm"],
                    "diff": round(ls[-1]["cm"] - ls[0]["cm"], 1),
                }
            )

    vurd = laes_log("vurdering")
    aktuel = vurd[-1] if vurd else beregn_vurdering()
    f = profil["forventet_kg_uge"]["foerste_12_uger"]
    return {
        "state": aktuel["label"],
        "vurdering": aktuel,
        "vurderinger": [[v["dato"], v["niveau"]] for v in vurd[-26:]],
        "foreloebig": not vurd,
        "vaegt": [[v["dato"], v["kg"], v.get("note", "")] for v in vaegt[-200:]],
        "forventet": forv,
        "forventet_tekst": f"{'+' if f >= 0 else '−'}{tal(abs(f), 2)} kg/uge",
        "basis": round(basis, 1) if basis else None,
        "trend": round(trend, 2) if trend is not None else None,
        "milepaele": sorted(profil["milepaele_kg"], reverse=True),
        "smerte_navn": p.smerte_navn,
        "smerte": [[r["dato"], r["score"]] for r in p.smerte[-52:]],
        "styrke_pr_uge": int(p.regler["styrke_max_pr_7_dage"]),
        "uger": uge_liste,
        "loeft": loeft,
        "maal": maal,
    }


# --- historik og spørgsmål ----------------------------------------------------


def status_historik() -> dict:
    profil = laes_yaml("profil.yaml")
    sp = laes_yaml("spoergsmaal.yaml") or []
    svar = {}
    for s in laes_log("svar"):
        svar[s["id"]] = s
    maal_log = laes_log("maal")
    maalinger = []
    for m in profil["maalinger"]:
        ls = [x for x in maal_log if x.get("id") == m["id"]]
        maalinger.append(
            {
                "id": m["id"],
                "navn": m["navn"],
                "sidst": ls[-1]["cm"] if ls else None,
                "dato": ls[-1]["dato"] if ls else None,
            }
        )
    aabne = [q for q in sp if q["id"] not in svar]
    hp = ROD / "historik.md"
    tekst = hp.read_text(encoding="utf-8") if hp.exists() else ""
    besv = [q for q in sp if q["id"] in svar]
    if besv:
        tekst += "\n## Dine svar\n\n" + "\n".join(
            f"- **{q['tekst']}** — {svar[q['id']]['tekst']} *({kort_dato(svar[q['id']]['dato'])})*"
            for q in besv
        )
    return {"state": len(aabne), "tekst": tekst, "spoergsmaal": aabne, "maalinger": maalinger}


# --- handlinger fra siden -----------------------------------------------------


class Fejl(Exception):
    pass


def _tal(x, lo, hi, navn):
    try:
        v = float(str(x).replace(",", "."))
    except TypeError, ValueError:
        raise Fejl(f"{navn}: ikke et tal") from None
    if not lo <= v <= hi:
        raise Fejl(f"{navn}: {v} uden for {lo}-{hi}")
    return v


def log_vaegt(kg, note=""):
    kg = round(_tal(kg, 40, 250, "vægt"), 1)
    alle = [v for v in laes_log("vaegt") if d(v["dato"]) != idag()]  # én vejning pr. dag
    omskriv_log("vaegt", alle)
    skriv_log("vaegt", {"kg": kg, **({"note": note} if note else {})})
    faerdig("vaegt")


def log_oevelse(oid, antal, kg=None, saet=None, session=None):
    p = Plan()
    if oid not in p.ov:
        raise Fejl("ukendt øvelse")
    o = p.ov[oid]
    post = {"id": oid, "antal": _tal(antal, 0, 100000, "antal")}
    if "kg" in o and kg is not None:
        post["kg"] = _tal(kg, 0, 300, "kg")
    post["saet"] = int(_tal(saet if saet is not None else o.get("saet", 1), 1, 10, "sæt"))
    if session in p.ses:
        post["session"] = session
    # Ét resultat pr. øvelse pr. dag: et nyt Done erstatter dagens tidligere.
    behold = [
        l for l in laes_log("traening") if not (l.get("id") == oid and d(l["dato"]) == idag())
    ]
    omskriv_log("traening", behold)
    skriv_log("traening", post)


def fortryd_oevelse(oid):
    behold = [
        l for l in laes_log("traening") if not (l.get("id") == oid and d(l["dato"]) == idag())
    ]
    omskriv_log("traening", behold)


def log_alt_anbefalet():
    """Push-knappen "Klaret som anbefalet": alt på dagens liste der ikke er logget."""
    s = status_idag()
    n = 0
    for x in s["daglig"] + s["hoved"]:
        if s["sted"] in x["steder"] and not x["gjort"] and not x["hvile"]:
            log_oevelse(x["id"], x["antal"], x["kg"], x["saet"], x["session"])
            n += 1
    return n


def log_smerte(score):
    skriv_log("smerte", {"score": int(_tal(score, 0, 10, "score"))})
    faerdig("smerte")


def log_svar(qid, tekst):
    sp = {q["id"] for q in (laes_yaml("spoergsmaal.yaml") or [])}
    if qid not in sp:
        raise Fejl("ukendt spørgsmål")
    tekst = str(tekst).strip()[:1500]
    if not tekst:
        raise Fejl("tomt svar")
    skriv_log("svar", {"id": qid, "tekst": tekst})


def log_maal(mid, cm):
    if mid not in {m["id"] for m in laes_yaml("profil.yaml")["maalinger"]}:
        raise Fejl("ukendt mål")
    skriv_log("maal", {"id": mid, "cm": round(_tal(cm, 10, 250, "cm"), 1)})
    faerdig("maal")


def log_maaltid(dag, mid, andel):
    """Kost-fanens Spist/Halvt: ét svar pr. måltid pr. dag (nyt tryk erstatter,
    andel 0 = fortryd). kcal/protein gemmes som de var, så loggen overlever at
    planen ændres."""
    maal = {x.get("id"): x for x in (laes_yaml("kost.yaml")["maaltider"].get(dag) or [])}
    if mid not in maal:
        raise Fejl("ukendt måltid")
    andel = _tal(andel, 0, 1, "andel")
    if andel not in (0, 0.5, 1):
        raise Fejl("andel skal være 0, 0,5 eller 1")
    behold = [
        x
        for x in laes_log("kost")
        if not (x.get("dag") == dag and x.get("id") == mid and d(x["dato"]) == idag())
    ]
    omskriv_log("kost", behold)
    if andel:
        m = maal[mid]
        skriv_log(
            "kost",
            {
                "dag": dag,
                "id": mid,
                "andel": andel,
                "kcal": round(m["kcal"] * andel),
                "protein": round(m["protein"] * andel),
            },
        )


def kør_cmd(c: dict):
    op = c.get("op")
    if op == "vaegt":
        log_vaegt(c.get("kg"), str(c.get("note", ""))[:200])
    elif op == "oevelse":
        log_oevelse(c.get("id"), c.get("antal"), c.get("kg"), c.get("saet"), c.get("session"))
        fejr_hvis_klaret()
    elif op == "fortryd":
        fortryd_oevelse(c.get("id"))
    elif op == "smerte":
        log_smerte(c.get("score"))
    elif op == "svar":
        log_svar(c.get("id"), c.get("tekst"))
    elif op == "maal":
        log_maal(c.get("id"), c.get("cm"))
    elif op == "maaltid":
        log_maaltid(c.get("dag"), c.get("id"), c.get("andel"))
    else:
        raise Fejl("ukendt handling")


def cmd(b64: str):
    if not re.fullmatch(r"[A-Za-z0-9+/=]{4,8000}", b64 or ""):
        raise Fejl("ugyldig indpakning")
    c = json.loads(base64.b64decode(b64).decode("utf-8"))
    if not isinstance(c, dict):
        raise Fejl("ugyldig handling")
    kør_cmd(c)


# --- påmindelser --------------------------------------------------------------


def faerdig(noegle):
    s = laes_state()
    s.setdefault(noegle, {})["faerdig"] = idag().isoformat()
    s[noegle].pop("udsat_til", None)
    gem_state(s)
    ryd_push(noegle)


def ryd_push(noegle):
    try:
        ha(
            "POST",
            f"/api/services/{notify_tjeneste()}",
            {"message": "clear_notification", "data": {"tag": f"helbred_{noegle}"}},
        )
    except Exception:
        pass


def push(noegle, titel, besked, knapper=(), side="idag"):
    data = {
        "tag": f"helbred_{noegle}",
        "clickAction": f"{DASH}/{side}",
        "url": f"{DASH}/{side}",
        "channel": "Helbred",
        "visibility": "private",
        "actions": [
            {
                "action": f"HELBRED_{op}_{noegle}",
                "title": t,
                **({"behavior": "textInput"} if op == "SVAR" else {}),
            }
            for op, t in knapper
        ],
    }
    ha(
        "POST",
        f"/api/services/{notify_tjeneste()}",
        {"title": titel, "message": besked, "data": data},
    )


def fejr_hvis_klaret():
    """Push når ALLE dagens øvelser er gjort — én gang pr. dag."""
    try:
        s = status_idag()
        aktive = [
            x for x in s["daglig"] + s["hoved"] if s["sted"] in x["steder"] and not x["hvile"]
        ]
        if not aktive or any(not x["gjort"] for x in aktive):
            return
        st = laes_state()
        if st.get("klaret", {}).get("sendt") == s["dato"]:
            return
        st.setdefault("klaret", {})["sendt"] = s["dato"]
        gem_state(st)
        ryd_push("traening")
        push(
            "klaret",
            "Dagens træning er klaret 💪",
            f"Alle {len(aktive)} øvelser er gjort. Godt gået!",
        )
    except Exception as e:  # logningen må aldrig fejle pga. pushen
        print(f"fejr: {e}", file=sys.stderr)


def _kl(tid: str) -> datetime:
    h, m = (int(x) for x in tid.split(":"))
    return nu().replace(hour=h, minute=m, second=0, microsecond=0)


def tick():
    if ha_state("input_boolean.helbred_paamindelser", "on") != "on":
        return
    n = nu()
    if not (_kl("06:30") <= n <= _kl("21:45")):
        return
    profil = laes_yaml("profil.yaml")
    pm = profil["paamindelser"]
    start = d(profil["start_dato"])
    dag = idag()
    if dag < start:
        return
    wd = dag.weekday()
    st = laes_state()
    i_dag = dag.isoformat()
    sn = smerte_navn(profil)

    def forfalden(noegle, tid, relevant):
        s = st.setdefault(noegle, {})
        if s.get("faerdig") == i_dag:
            return False
        udsat = s.get("udsat_til")
        if udsat:
            if n >= datetime.fromisoformat(udsat):
                s.pop("udsat_til")
                return True
            return False
        return bool(relevant and n >= _kl(tid) and s.get("sendt") != i_dag)

    def sendt(noegle):
        st[noegle]["sendt"] = i_dag

    udsaet = [("U1T", "Udsæt 1 time"), ("U1D", "I morgen")]
    sidste = lambda navn: (laes_log(navn) or [{}])[-1].get("dato")  # noqa: E731

    try:
        # Vejning
        if forfalden("vaegt", pm["vaegt"]["tid"], wd in pm["vaegt"]["dage"] or dag == start):
            sv = sidste("vaegt")
            # En vejning inden for min_dage dækker dagens plan.
            if sv and (dag - d(sv)).days < pm["vaegt"].get("min_dage", 1):
                st["vaegt"]["faerdig"] = i_dag
                st["vaegt"].pop("udsat_til", None)
            else:
                push(
                    "vaegt",
                    "Vej dig",
                    "Efter toilettet, før kaffe og mad. Svar med tallet i kg.",
                    [("SVAR", "Skriv kg"), *udsaet],
                )
                sendt("vaegt")

        s = status_idag()
        mangler = [
            x
            for x in s["daglig"] + s["hoved"]
            if s["sted"] in x["steder"] and not x["gjort"] and not x["hvile"]
        ]
        # Morgenens overblik
        if forfalden("program", pm["program"]["tid"], wd in pm["program"]["dage"]):
            hoved = [x["navn"] for x in s["hoved"] if s["sted"] in x["steder"] and not x["hvile"]]
            besked = (
                s["session"]["navn"]
                + (": " + ", ".join(hoved) if hoved else "")
                + ". Basis 10 min + gåtur."
            )
            push("program", f"I dag ({s['ugedag']})", besked, side="traening")
            sendt("program")
            st["program"]["faerdig"] = i_dag
        # Trænings-påmindelse
        tid = pm["traening"]["hverdag" if wd < 5 else "weekend"]
        if forfalden("traening", tid, True):
            if not mangler:
                st["traening"]["faerdig"] = i_dag
            else:
                push(
                    "traening",
                    f"Træning: {len(mangler)} tilbage",
                    ", ".join(x["navn"].split(" (")[0] for x in mangler)[:180],
                    [("OK", "Klaret som anbefalet"), *udsaet],
                    side="traening",
                )
                sendt("traening")
        # Ugens smerte-score
        if forfalden("smerte", pm["smerte"]["tid"], wd in pm["smerte"]["dage"]):
            sr = sidste("smerte")
            if sr and (dag - d(sr)).days < 5:
                st["smerte"]["faerdig"] = i_dag
            else:
                push(
                    "smerte",
                    f"Ugens {sn.lower()}",
                    f"Hvor slemt har {sn.lower()} været den forløbne uge? 0 = intet, 10 = værst tænkelige.",
                    [("SVAR", "Svar 0-10"), *udsaet],
                )
                sendt("smerte")
        # Kropsmål
        n_uger = int(pm["maal"]["hver_n_uger"])
        if forfalden("maal", pm["maal"]["tid"], (dag - start).days % (7 * n_uger) == 0):
            sm = sidste("maal")
            if sm and (dag - d(sm)).days < 20:
                st["maal"]["faerdig"] = i_dag
            else:
                push(
                    "maal",
                    "Målebånd",
                    f"Tid til kropsmål ({len(profil['maalinger'])} mål, 3 minutter). Tryk for at åbne.",
                    udsaet,
                    side="historik",
                )
                sendt("maal")
        # Ugens vurdering
        if forfalden("vurdering", pm["vurdering"]["tid"], wd in pm["vurdering"]["dage"]):
            v = beregn_vurdering()
            skriv_log("vurdering", v)
            push("vurdering", f"Ugens vurdering: {v['label']}", v["tekst"], side="statistik")
            sendt("vurdering")
            st["vurdering"]["faerdig"] = i_dag
    finally:
        gem_state(st)


def svar(action: str, reply_b64: str = ""):
    m = re.fullmatch(r"HELBRED_(SVAR|OK|U1T|U1D|SKIP)_([a-z]{2,20})", action or "")
    if not m:
        raise Fejl("ukendt knap")
    op, noegle = m.groups()
    tekst = ""
    if reply_b64 and re.fullmatch(r"[A-Za-z0-9+/=]{1,400}", reply_b64):
        tekst = base64.b64decode(reply_b64).decode("utf-8", "replace").strip()
    st = laes_state()
    s = st.setdefault(noegle, {})
    if op in ("U1T", "U1D"):
        profil = laes_yaml("profil.yaml")
        if op == "U1T":
            til = nu() + timedelta(hours=1)
        else:
            pm = profil["paamindelser"].get(noegle, {})
            tid = pm.get("tid") or pm.get("hverdag") or "09:00"
            til = _kl(tid) + timedelta(days=1)
        s["udsat_til"] = til.isoformat(timespec="minutes")
        s["sendt"] = idag().isoformat()
        gem_state(st)
        return
    if op == "SKIP":
        gem_state(st)
        faerdig(noegle)
        return
    if op == "OK" and noegle == "traening":
        log_alt_anbefalet()
        faerdig("traening")
        fejr_hvis_klaret()
        return
    if op == "SVAR":
        tal_ = re.search(r"\d+(?:[.,]\d+)?", tekst)
        if not tal_:
            raise Fejl("intet tal i svaret")
        if noegle == "vaegt":
            log_vaegt(tal_.group())
        elif noegle == "smerte":
            log_smerte(tal_.group())
        else:
            raise Fejl("ukendt svar")
        return
    raise Fejl("ukendt knap")


# --- læsbar udgave ------------------------------------------------------------


def program_md() -> str:
    """Hele programmet + kosten som markdown — til print, eller hvis man ikke har HA."""
    prog = laes_yaml("program.yaml")
    kost = laes_yaml("kost.yaml")
    profil = laes_yaml("profil.yaml")
    ov = prog["oevelser"]
    navne = profil.get("sted_navne") or {}
    ud = ["# Træningsprogram", ""]
    for p in prog.get("principper") or []:
        ud.append(f"- {p}")
    ud.append("")
    for s in prog["sessioner"].values():
        ud += [f"## {s['navn']}", f"*{s.get('hvorfor', '')}*", ""]
        grupper = (
            [("", s["alle"])]
            if "alle" in s
            else [(navne.get(st, st.capitalize()), s.get(st, [])) for st in STEDER if s.get(st)]
        )
        for titel, ids in grupper:
            if titel:
                ud.append(f"**{titel}:**")
            for oid in ids:
                o = ov[oid]
                kg = f", start {tal(o['kg'])} kg" if o.get("kg") else ""
                ud.append(
                    f"- **{o['navn']}** — {o.get('saet', 1)} × {o['lo']}-{o['hi']} {o['enhed']}{kg}. "
                    f"{o.get('hvordan', '')}  \n  *Hvorfor: {o.get('hvorfor', '')}*"
                )
            ud.append("")
    r = prog["regler"]
    ud += [
        "## Ugens rytme",
        f"- Styrke højst {r['styrke_max_pr_7_dage']} dage om ugen, aldrig to dage i træk "
        f"(rotation: {', '.join(prog['sessioner'][x]['navn'] for x in prog['rotation'])}).",
        f"- Kondition op til {r['kondition_max_pr_7_dage']} dage om ugen på de andre dage.",
        "- Basis + gåtur hver dag. Lang tur i weekenden, højst én gang om ugen.",
        "- Når du når toppen af spændet (fx 12 reps) i alle sæt: læg vægt på og start forfra i bunden.",
        "",
        "# Kost",
        "",
        f"*{kost['maal'].get('hvorfor', '')}*",
        "",
    ]
    for noegle, titel, _ in KOST_AFSNIT:
        raad = [_raad(x) for x in kost.get(noegle) or []]
        if raad:
            ud.append(f"## {titel}")
            ud += [f"- **{x['goer']}** {x['hvorfor']}" for x in raad]
            ud.append("")
    for navn, maal in kost["maaltider"].items():
        ud.append(
            f"## {DAG_TITLER.get(navn, navn)} — ca. {sum(x['kcal'] for x in maal)} kcal, "
            f"{sum(x['protein'] for x in maal)} g protein"
        )
        ud += [f"- **{x['tid']}** ({x['kcal']} kcal): {x['hvad']}" for x in maal]
        ud.append("")
    return "\n".join(ud)


# --- main ---------------------------------------------------------------------


def tjek_data():
    profil = laes_yaml("profil.yaml")
    fejl = []
    for felt in ("foedt", "hoejde_cm", "vaegt_kg", "maalvaegt_kg", "start_dato", "notify"):
        if not profil.get(felt) or str(profil.get(felt)).startswith("UDFYLD"):
            fejl.append(f"profil.yaml: udfyld {felt}")
    if fejl:
        print("\n".join(fejl))
        return 1
    p = Plan()
    for sid, s in p.ses.items():
        for felt in ("alle", *STEDER):
            for o in s.get(felt, []):
                if o not in p.ov:
                    fejl.append(f"session {sid}: ukendt øvelse {o}")
    if "daglig" not in p.ses:
        fejl.append("program.yaml: sessionen 'daglig' mangler")
    for oid, o in p.ov.items():
        for felt in ("navn", "enhed", "lo", "hi", "hvorfor"):
            if felt not in o:
                fejl.append(f"øvelse {oid}: mangler {felt}")
    for r in p.prog["rotation"]:
        if r not in p.ses:
            fejl.append(f"rotation: ukendt session {r}")
    k = laes_yaml("kost.yaml")
    for dag, maal in k["maaltider"].items():
        ids = [x.get("id") for x in maal]
        if None in ids or len(set(ids)) != len(ids):
            fejl.append(f"måltider {dag}: hvert måltid skal have et unikt id")
    if not fejl:
        for navn in SENSORER:
            json.dumps(STATUS[navn]())
    print("\n".join(fejl) if fejl else "ok")
    return 1 if fejl else 0


STATUS = {
    "idag": status_idag,
    "kost": status_kost,
    "statistik": status_statistik,
    "historik": status_historik,
}


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    k = argv[1]
    try:
        if k == "status":
            print(json.dumps(STATUS[argv[2]](), ensure_ascii=False))
        elif k == "cmd":
            cmd(argv[2])
        elif k == "svar":
            svar(argv[2], argv[3] if len(argv) > 3 else "")
        elif k == "tick":
            tick()
        elif k == "tjek":
            return tjek_data()
        elif k == "program":
            print(program_md())
        else:
            print(__doc__)
            return 2
    except Fejl as e:
        print(f"[helbred] afvist: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
