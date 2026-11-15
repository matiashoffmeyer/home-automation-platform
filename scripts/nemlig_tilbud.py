#!/usr/bin/env python3
"""nemlig_tilbud.py — ugens Nemlig-tilbud som grundlag for madplanen (2026-11-14).

User 14/11: "Nemlig retter og indkøb skal være mere baseret på nemlig tilbud
… vi vil gerne spare flere penge på indkøb." To halvdele:

  1. KURVEN (nemlig_kurv.py --tilbud + multikøbs-rundingen) køber holdbare
     faste varer på tilbud og runder op til "2 for"-sæt.
  2. RETTERNE (denne fil): én daglig scanning af HELE butikkens mad-tilbud →
     `.nemlig_tilbud.json`. mad_planner.vaelg_indkoeb giver en ret en bonus
     når dens ingredienser er på tilbud, så tilbuddene styrer HVAD vi spiser,
     ikke kun hvad vi hamstrer.

MATCH = VAREART, ikke navn. En ingrediens ("kyllingebryst") slås op i
søge-cachen, og bladet i Nemligs varetræ (`ProductSubGroupName`, fx "Kylling
filet, fersk") er dens vareart — så ENHVER kyllingebrystfilet på tilbud tæller,
ikke kun den vi plejer at købe (.claude/rules/nemlig.md: bladet ER varearten).
Ingrediens uden cache-hit → navne-match mod tilbuds-produktets navn (prefix på
hele ord ≥ 5 tegn), så nye retter ikke står helt uden.

CLI:
    scan        hent tilbud, gem filen, publicér sensor.nemlig_tilbud
    republish   publicér sensoren fra filen (efter HA-restart; rører ikke Nemlig)
    vis         vis de bedste tilbud fra filen
"""

import json
import os
import sys
from datetime import UTC, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ha_secrets  # noqa: E402
import nemlig_api as NA  # noqa: E402

TILBUD_FIL = "/config/.nemlig_tilbud.json"
SOEGECACHE = "/config/.nemlig_soegecache.json"
SENSOR = "sensor.nemlig_tilbud"
E_MIN_PCT = "input_number.nemlig_tilbud_min_pct"
MAX_ALDER_DAGE = 3  # ældre scanning = ingen bonus (kampagnerne er skiftet)
BONUS_MAETTET_KR = 40.0  # sparede kroner på rettens ingredienser der giver fuld bonus (1,0)
MAX_KR_PR_INGREDIENS = 20.0
BASIS_ANDEL = 0.08  # en ingrediens i ≥ 8 % af retterne er en basisvare (ingen bonus)


def log(msg):
    print(f"[nemlig-tilbud] {msg}", file=sys.stderr, flush=True)


def _er_mad(p):
    return NA.normaliser(p.get("ProductMainGroupName") or "").strip() not in NA.IKKE_MAD


def basis_ingredienser(dishes, ingredienser_for, andel=BASIS_ANDEL):
    """Ingredienser der står i ≥ `andel` af retterne = basisvarer (ingen bonus)."""
    from collections import Counter

    c = Counter()
    for d in dishes:
        c.update({i[2].strip().lower() for i in ingredienser_for(d) if i[2]})
    graense = max(3, andel * len(dishes))
    return frozenset(k for k, v in c.items() if v >= graense)


def ingrediens_soegeord():
    """Alle ingrediens-navne i rettepuljen (≈ 450) — søgeordene for scanningen."""
    import mad_planner as MP

    dishes, _ = MP.fetch_dishes()
    return sorted({i[2].strip().lower() for d in dishes for i in MP.ingredienser_for(d) if i[2]})


def scan(n, min_pct, soeg=None):
    """→ liste af tilbud (mad, ≥ min_pct, på lager), mest rabat først.

    Søgningen når kun de første 100 hits (nemlig_api.SOEG_LOFT), så butikkens
    ~6600 tilbud kan ikke pages igennem → én tilbuds-søgning pr. ingrediens i
    rettepuljen + pr. fast vare (≈ 650 kald × 0,7 s ≈ 8 min, kl. 05:45)."""
    faste = NA.faste_varer(n)
    if soeg is None:
        soeg = ingrediens_soegeord() + NA.faste_soegeord(faste)
    ud, set_ = [], set()
    for p in n.tilbud(kun_favoritter=False, soeg=soeg):
        pid = str(p.get("Id"))
        if pid in set_ or not _er_mad(p):
            continue
        set_.add(pid)
        k = NA.kampagne(p)
        if not k or k["rabat_pct"] < min_pct:
            continue
        if not (p.get("Availability") or {}).get("IsAvailableInStock"):
            continue
        f = faste.get(pid) or {}
        ud.append(
            {
                "id": pid,
                "navn": p.get("Name"),
                "vareart": p.get("ProductSubGroupName") or "",
                "kategori": p.get("ProductCategoryGroupName") or "",
                "tekst": k["tekst"],
                "rabat_pct": round(k["rabat_pct"], 1),
                # sparet pr. styk (normalpris − tilbudspris) — bonussens valuta
                "spar_kr": round(
                    k["stk_pris"] * k["rabat_pct"] / max(1.0, 100 - k["rabat_pct"]), 2
                ),
                "min_antal": k["min_antal"],
                "madspild": k["madspild"],
                "holdbar": NA.lager_holdbar(p),
                "fast": int(f.get("gange") or 0),
                "slut": (p.get("Campaign") or {}).get("IntervalEnd"),
            }
        )
    ud.sort(key=lambda t: (-t["rabat_pct"], t["navn"] or ""))
    return ud


def gem(tilbud):
    d = {"dato": datetime.now(UTC).isoformat(), "tilbud": tilbud}
    tmp = f"{TILBUD_FIL}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    os.replace(tmp, TILBUD_FIL)


def laes(max_alder_dage=MAX_ALDER_DAGE):
    """→ tilbuds-listen, eller [] hvis filen mangler eller er for gammel."""
    try:
        with open(TILBUD_FIL, encoding="utf-8") as f:
            d = json.load(f)
        alder = datetime.now(UTC) - datetime.fromisoformat(d["dato"])
    except OSError, ValueError, KeyError:
        return []
    if alder.days >= max_alder_dage:
        return []
    nu = datetime.now(UTC)
    ud = []
    for t in d.get("tilbud") or []:
        slut = t.get("slut")
        try:
            if slut and datetime.fromisoformat(slut.replace("Z", "+00:00")) < nu:
                continue
        except ValueError:
            pass
        ud.append(t)
    return ud


# Beskrivende ord i ingrediens-navne: de skal ikke matches ("rød peberfrugt" ≁
# "Chili rød", "grønne asparges" ≁ "grøn karrypasta"). Navneordet bærer varen.
FYLDORD = frozenset(
    "rød røde grøn grønne gul gule hvid hvide sort sorte frisk friske fersk revet "
    "revne hakket hakkede stor store små lille tern skiver skive hel hele øko "
    "dåse mild stærk tørret tørrede kogte kogt bagt bagte finthakket og med til".split()
)


# =============================================================================
# Ret → bonus
# =============================================================================
class Matcher:
    """Ingrediens-navn → de tilbud den rammer. Bygges én gang pr. planner-kørsel."""

    def __init__(self, tilbud, soegecache=None):
        self.tilbud = [t for t in tilbud if not t.get("madspild")]
        self.pr_vareart = {}
        for t in self.tilbud:
            if t["vareart"]:
                self.pr_vareart.setdefault(NA.normaliser(t["vareart"]).strip(), []).append(t)
        self._cache = soegecache
        self._memo = {}

    def _soegecache(self):
        if self._cache is None:
            try:
                with open(SOEGECACHE, encoding="utf-8") as f:
                    self._cache = json.load(f)
            except OSError, ValueError:
                self._cache = {}
        return self._cache

    def vareart(self, ingrediens):
        """Bladet for søgningens første MAD-resultat, eller None."""
        c = self._soegecache()
        for q in (ingrediens, NA.normaliser(ingrediens).strip()):
            r = c.get(q)
            if isinstance(r, list):
                for p in r[:1]:
                    if isinstance(p, dict) and _er_mad(p) and p.get("ProductSubGroupName"):
                        return NA.normaliser(p["ProductSubGroupName"]).strip()
        return None

    @staticmethod
    def _ord(tekst, fyld=frozenset()):
        ud = []
        for o in (tekst or "").lower().replace(",", " ").replace(".", " ").split():
            if len(o) >= 3 and o not in fyld:
                ud.append(NA.normaliser(o).strip())
        return ud

    @staticmethod
    def _ord_match(w, o):
        """Sammensatte danske ord: "kyllingebryst" ~ "kyllingebrystfilet",
        "mælk" ~ "sødmælk" — men "kyllingebryst" ≁ "kyllingeoverlår"."""
        return (
            o.startswith(w) or (len(o) >= 4 and w.startswith(o)) or (len(w) >= 4 and o.endswith(w))
        )

    def rammer(self, ingrediens):
        """Tilbud på SAMME vare: navne-ord fælles med ingrediensen, og (når
        søge-cachen kender ingrediensen) samme vareart. Varearten alene er for
        grov (målt 15/11: "karry" → sugar snaps, "røde linser" → boller i
        karry), navnet alene for løst ("smør" → smørbart)."""
        key = (ingrediens or "").strip().lower()
        if key in self._memo:
            return self._memo[key]
        ord_ = self._ord(key, FYLDORD)
        hit = []
        if ord_:
            va = self.vareart(key)
            kandidater = self.pr_vareart.get(va, []) if va else self.tilbud
            for t in kandidater:
                navn_ord = self._ord(t["navn"])
                if all(any(self._ord_match(w, o) for o in navn_ord) for w in ord_):
                    hit.append(t)
        self._memo[key] = hit
        return hit

    def ret(self, ingredienser, basis=frozenset()):
        """[(mængde, enhed, navn)] → (bonus 0..1, [tekst pr. ramt ingrediens]).
        Bonussen er SPAREDE KRONER (bedste tilbud pr. ingrediens) / 40 kr —
        rabat-% summeret gav fuld bonus til enhver ret med tre krydderurter.
        `basis` = ingredienser der står i mange retter (olie, smør, kartofler):
        de giver ingen bonus, ellers fik ALLE retter fuld bonus (målt 15/11:
        431/439)."""
        sum_kr, tekster = 0.0, []
        for ing in ingredienser:
            navn = ing[2] if isinstance(ing, (list, tuple)) else str(ing)
            if navn.strip().lower() in basis:
                continue
            hit = self.rammer(navn)
            if not hit:
                continue
            bedst = max(hit, key=lambda t: t.get("spar_kr") or 0.0)
            # Loft pr. ingrediens: en flaske sesamolie (44 kr sparet) bruges i
            # mange retter og må ikke alene give fuld bonus.
            sum_kr += min(MAX_KR_PR_INGREDIENS, bedst.get("spar_kr") or 0.0)
            tekster.append(f"{navn}: {bedst['navn']} {bedst['tekst']}")
        return min(1.0, sum_kr / BONUS_MAETTET_KR), tekster


# =============================================================================
# Sensor
# =============================================================================
def sensor_payload(tilbud):
    top = [t for t in tilbud if t["fast"]][:25] + [t for t in tilbud if not t["fast"]][:15]
    return {
        "state": str(len(tilbud)),
        "attributes": {
            "friendly_name": "Nemlig — tilbud",
            "icon": "mdi:sale",
            "unit_of_measurement": "tilbud",
            "faste": len([t for t in tilbud if t["fast"]]),
            "top": [
                {k: t[k] for k in ("navn", "tekst", "rabat_pct", "holdbar", "fast")} for t in top
            ],
            "opdateret": datetime.now(UTC).isoformat(),
        },
    }


def publish(token, tilbud):
    import urllib.request

    body = json.dumps(sensor_payload(tilbud)).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:8123/api/states/{SENSOR}",
        data=body,
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    urllib.request.urlopen(req, timeout=15).read()


def _min_pct(token):
    import urllib.request

    req = urllib.request.Request(
        f"http://127.0.0.1:8123/api/states/{E_MIN_PCT}",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        return float(json.load(urllib.request.urlopen(req, timeout=10))["state"])
    except Exception:
        return 15.0


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "vis"
    if cmd == "vis":
        for t in laes()[:40]:
            fast = f" · købt {t['fast']}×" if t["fast"] else ""
            print(f"{t['rabat_pct']:5.1f} %  {t['navn']} — {t['tekst']}{fast}")
        return 0
    token = ha_secrets.get(ha_secrets.HA_API_TOKEN)
    if cmd == "republish":
        publish(token, laes(max_alder_dage=999))
        return 0
    if cmd == "scan":
        try:
            tilbud = scan(NA.Nemlig(), _min_pct(token))
        except NA.NemligFejl as e:
            log(f"scanning fejlede: {e}")
            return 1
        gem(tilbud)
        publish(token, tilbud)
        log(f"{len(tilbud)} tilbud gemt ({len([t for t in tilbud if t['fast']])} på faste varer)")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
