#!/usr/bin/env python3
"""nemlig_selftest.py — kør matcheren mod HELE ret-katalogets råvarer.

Formål: finde faldgruber FØR de lander i en rigtig kurv. Kørslen er read-only
mod Nemlig (kun søgning) og rører hverken kurv, parringsfil eller HA-state.

    python3 scripts/nemlig_selftest.py                 # alle unikke råvarer
    python3 scripts/nemlig_selftest.py --antal 60      # tilfældigt udsnit
    python3 scripts/nemlig_selftest.py --frø 7         # reproducerbart udsnit
    python3 scripts/nemlig_selftest.py --ud /tmp/r.json
    python3 scripts/nemlig_selftest.py --cache          # optag/genbrug søgesvar
    python3 scripts/nemlig_selftest.py --offline        # KUN cachen, 0 kald
    python3 scripts/nemlig_selftest.py --offline --diff /tmp/foer.json

KATALOG-DIFF (2026-10-01): en ændring i matcheren skal måles på de SAMME
søgesvar før og efter — ellers blander lagerstatus og Nemligs sortiment sig
ind i tallet (30/9 viste tre "regressioner" der var udsolgt-skift). `--cache`
optager hvert søgesvar i `CACHE_FIL`; `--offline` kører hele kataloget mod
cachen på sekunder, og `--diff` viser hver råvare hvis VALG eller STATUS
ændrede sig mod en tidligere rapport.

Rapporten grupperer efter FALDGRUBE, ikke efter vare: en liste med 495 linjer
er ikke en analyse. Hver detektor svarer på "hvilken slags fejl kan denne
kørsel producere", så et fund kan rettes i koden frem for i en enkelt vare.
"""

import argparse
import collections
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mad_planner as MP  # noqa: E402
import nemlig_api as NA  # noqa: E402

# Enheder pakke-matematikken ikke kan omregne fra. Ikke en fejl i sig selv —
# men bliver den til et stort behov, køber vi 1 pakke til noget der kræver ti.
UOMREGNELIGE = {
    "spsk",
    "tsk",
    "fed",
    "bdt",
    "potte",
    "kviste",
    "knsp",
    "stang",
    "skiver",
    "rulle",
    "bakke",
    "pose",
    "daase",
    "haandfuld",
}

# Over dette antal pakker lugter det af en fejllæst pakningsstørrelse
# (fx behov i gram mod en pakning der blev læst som "1 stk").
MISTAENKT_ANTAL = 8
# En enkelt vare der koster mere end det her er sjældent den rigtige råvare.
MISTAENKT_PRIS = 250.0

# Rå søgesvar, nøglet på søgeordet. Uden for git (~20 MB, og svarene er et
# øjebliksbillede af Nemligs lager — de bliver forældede, ikke forkerte).
CACHE_FIL = "/config/.nemlig_soegecache.json"
# Cachen optager altid OPTAG_TAKE træf og skærer til det take kalderen beder
# om. Målt 2026-10-01 ("hvidvin", "ris"): de første 8 af take=30 er identiske
# med take=8, så et større felt kan afprøves offline uden nye kald.
OPTAG_TAKE = 30


class CachetSoegning:
    """Lægger sig foran `Nemlig.search`, så `search_bredt`s stige også caches.

    offline=True: et søgeord der ikke er i cachen giver et TOMT svar og
    tælles som `mangler` — så en ny stige-variant ses som hul i stedet for
    tavst at gå til nettet."""

    def __init__(self, n, sti, offline=False):
        self.n, self.sti, self.offline = n, sti, offline
        self.mangler, self.nye = 0, 0
        try:
            with open(sti, encoding="utf-8") as f:
                self.data = json.load(f)
        except FileNotFoundError, json.JSONDecodeError:
            self.data = {}
        self._live = n.search if n else None
        if n:
            n.search = self.search

    def search(self, query, take=12):
        if query in self.data:
            return self.data[query][:take]
        if self.offline or not self._live:
            self.mangler += 1
            return []
        svar = self._live(query, max(take, OPTAG_TAKE))
        self.data[query] = svar
        svar = svar[:take]
        self.nye += 1
        if self.nye % 50 == 0:
            self.gem()
        return svar

    def gem(self):
        tmp = self.sti + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False)
        os.replace(tmp, self.sti)


class _OfflineNemlig:
    """Nok af `Nemlig` til at `search_bredt` kan køre uden login."""

    search_bredt = NA.Nemlig.search_bredt
    _kvalitet = staticmethod(NA.Nemlig._kvalitet)

    def search(self, query, take=12):
        return []


def log(m):
    print(f"[selftest] {m}", file=sys.stderr)


def alle_raavarer():
    """→ {normaliseret navn: (maengde, enhed, raat navn)} over hele katalogret.

    Vi tager den STØRSTE mængde vi har set for en råvare: det er dér
    pakke-matematikken har mest at tage fejl af, og et 2 kg-behov afslører en
    fejllæst pakning som et 100 g-behov skjuler.
    """
    dishes, kilde = MP.fetch_dishes()
    log(f"{len(dishes)} retter fra {kilde}")
    unik = {}
    for d in dishes:
        for m, e, n in MP.ingredienser_for(d):
            if not n:
                continue
            k = MP.normaliser_navn(n)
            fam = MP.enheds_familie(e)
            faktor = (
                MP.MASSE.get(e)
                if fam == "masse"
                else MP.VOLUMEN.get(e)
                if fam == "volumen"
                else 1.0
            ) or 1.0
            basis = (m or 0) * faktor
            if k not in unik or basis > unik[k][0]:
                unik[k] = (
                    basis,
                    "g" if fam == "masse" else "ml" if fam == "volumen" else e,
                    n,
                    fam,
                )
    return unik


def undersoeg(
    n, navn, maengde, enhed, familie, oeko_loft, tilbud, min_score, favorit_loft=NA.FAVORIT_LOFT_PCT
):
    # Driften søger og scorer på SYNONYMET (nemlig_kurv.py: soegeord), ikke på
    # arkets råe ord. Målte testen det rå navn, målte den en anden kode end den
    # der kører (fejlklasse #2) — og rapporterede fx hvidvin som "ingen træf"
    # selv om kurven finder den fint.
    soegeord = NA.synonym(navn)
    try:
        traef = NA.find_bedste(n.search_bredt(soegeord, 8), soegeord)
    except NA.NemligFejl as e:
        return {"navn": navn, "status": "fejl", "grund": str(e)}
    if not traef:
        return {"navn": navn, "status": "ingen_traef"}
    valgt, begrundelse, ref = NA.vaelg_produkt(
        NA.kun_relevante(traef, soegeord),
        oeko_loft,
        tilbud,
        soegt=NA.form_ord(soegeord, enhed),
        favorit_loft_pct=favorit_loft,
        behov=(maengde, enhed),
    )
    if valgt is None:
        return {"navn": navn, "status": "ingen_traef"}
    antal, hvorfor = NA.antal_pakker(maengde, enhed, valgt["_raw"], navn=soegeord)
    pm, pe = NA.pakning(valgt["_raw"])
    return {
        "navn": navn,
        "soegeord": soegeord,
        "maengde": maengde,
        "enhed": enhed,
        "familie": familie,
        "produkt": valgt["navn"],
        "id": valgt["id"],
        "score": valgt["score"],
        "kategori": valgt.get("kategori"),
        "undergruppe": valgt["_raw"].get("ProductSubGroupName"),
        "alternativer": [
            f"{t['navn']} [{t['_raw'].get('ProductSubGroupName')}]"
            f" {t['score']:.2f}{'' if t['hoved'] else ' -h'}"
            for t in traef
            if t["id"] != valgt["id"]
        ][:4],
        "hoved": valgt["hoved"],
        "paa_lager": valgt["paa_lager"],
        "oeko": valgt["oeko"],
        "tilbud": valgt["tilbud"],
        "pris": valgt["pris"],
        "gruppe": (valgt["_raw"].get("ProductMainGroupName") or ""),
        "antal": antal,
        "pakke_laest": bool(pm),
        "hvorfor": hvorfor,
        "begrundelse": begrundelse,
        # Spejler nemlig_kurv.parr()s gates — ellers måler testen noget andet
        # end driften gør (fejlklasse #2: samme regel kodet to steder).
        "status": (
            "ingen_traef"
            if not NA.relevant_nok(
                soegeord, valgt["navn"], valgt.get("taksonomi") or valgt.get("kategori")
            )
            else "udsolgt"
            if not valgt["paa_lager"]
            else "usikker"
            if valgt["score"] < min_score
            else "usikker"
            if NA.form_advarsel(valgt, soegeord)
            else "usikker"
            if not valgt["hoved"]
            else "ok"
        ),
    }


def faldgruber(res):
    """→ {navn: [rækker]}. Hver detektor er en fejlKLASSE, ikke en enkelt vare."""
    f = collections.OrderedDict()

    def put(k, r):
        f.setdefault(k, []).append(r)

    for r in res:
        if r["status"] in ("fejl", "ingen_traef"):
            put("Intet træf overhovedet", r)
            continue
        ok = r["status"] == "ok"

        # Den farligste klasse: accepteret UDEN at produktets hovedord blev
        # bedt om. Det var præcis "jordbær" -> "Smoothie m. jordbær".
        if ok and not r["hoved"]:
            put("ACCEPTERET med fremmed hovedord", r)

        # Pakningen kunne ikke læses -> antal defaulter til 1. Harmløst ved
        # små behov, men et 2 kg-behov bliver til én pakke.
        if ok and not r["pakke_laest"] and r["maengde"] and r["maengde"] > 500:
            put("Stort behov + ulæselig pakning -> kun 1 pakke", r)

        # Enheden kan ikke omregnes OG behovet er stort.
        if ok and r["enhed"] in UOMREGNELIGE and (r["maengde"] or 0) >= 4:
            put("Uomregnelig enhed + stort antal", r)

        if ok and r["antal"] >= MISTAENKT_ANTAL:
            put(f"Mistænkeligt mange pakker (>={MISTAENKT_ANTAL})", r)

        if ok and (r["pris"] or 0) >= MISTAENKT_PRIS:
            put(f"Dyr enkeltvare (>={MISTAENKT_PRIS:.0f} kr)", r)

        if r["status"] == "usikker":
            put("Usikker parring (spørges der om)", r)
        if r["status"] == "udsolgt":
            put("Udsolgt (spørges der om)", r)
    return f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--antal", type=int, help="tilfældigt udsnit i stedet for alle")
    ap.add_argument("--frø", type=int, default=1, help="seed for udsnittet")
    ap.add_argument("--ud", default="/config/.nemlig_selftest.json")
    ap.add_argument("--oeko-loft", type=float, default=100.0)
    ap.add_argument("--min-score", type=float, default=NA.SIKKER_SCORE)
    ap.add_argument("--favorit-loft", type=float, default=NA.FAVORIT_LOFT_PCT)
    ap.add_argument("--cache", action="store_true", help=f"optag/genbrug søgesvar i {CACHE_FIL}")
    ap.add_argument(
        "--offline", action="store_true", help="kun cachen — nul kald til Nemlig (impl. --cache)"
    )
    ap.add_argument(
        "--diff", metavar="RAPPORT", help="vis råvarer hvis valg/status ændrede sig mod RAPPORT"
    )
    a = ap.parse_args()

    unik = alle_raavarer()
    noegler = sorted(unik)
    if a.antal and a.antal < len(noegler):
        random.Random(a.frø).shuffle(noegler)
        noegler = sorted(noegler[: a.antal])
    log(f"tester {len(noegler)} af {len(unik)} unikke råvarer")

    n = _OfflineNemlig() if a.offline else NA.Nemlig()
    cache = CachetSoegning(n, CACHE_FIL, offline=a.offline) if (a.cache or a.offline) else None
    res = []
    for i, k in enumerate(noegler, 1):
        maengde, enhed, raat, fam = unik[k]
        res.append(
            undersoeg(n, raat, maengde, enhed, fam, a.oeko_loft, True, a.min_score, a.favorit_loft)
        )
        if i % 25 == 0 and not a.offline:
            log(f"{i}/{len(noegler)}")
    if cache:
        if cache.nye:
            cache.gem()
        log(f"cache: {cache.nye} nye søgesvar, {cache.mangler} manglede")

    tael = collections.Counter(r["status"] for r in res)
    f = faldgruber(res)
    with open(a.ud, "w", encoding="utf-8") as fh:
        json.dump(
            {"resultater": res, "faldgruber": {k: [r["navn"] for r in v] for k, v in f.items()}},
            fh,
            ensure_ascii=False,
            indent=1,
        )

    print(f"\n{'=' * 66}\nTESTET: {len(res)} råvarer")
    for s, c in tael.most_common():
        print(f"  {s:14} {c:4}  ({c / len(res) * 100:.0f} %)")
    print(f"\nFALDGRUBER\n{'=' * 66}")
    for k, v in sorted(f.items(), key=lambda kv: -len(kv[1])):
        print(f"\n### {k}  ({len(v)})")
        for r in v[:12]:
            hvad = r.get("produkt", "-")
            ekstra = ""
            if "antal" in r:
                ekstra = f" ×{r['antal']}  [{r.get('hvorfor', '')}]"
            print(
                f"  {(r['navn'] or '')[:26]:26} -> {hvad[:34]:34} {r.get('score', 0):.2f}{ekstra}"
            )
        if len(v) > 12:
            print(f"  … +{len(v) - 12} flere (se {a.ud})")
    print(f"\nFuld rapport: {a.ud}")
    if a.diff:
        diff(a.diff, res)
    return 0


def diff(sti, res):
    """Råvarer hvis VALG eller STATUS er ændret mod en tidligere rapport."""
    with open(sti, encoding="utf-8") as f:
        gammel = {r["navn"]: r for r in json.load(f)["resultater"]}
    rang = {"ok": 0, "udsolgt": 1, "usikker": 2, "ingen_traef": 3, "fejl": 4}
    op, ned, skift = [], [], []
    for r in res:
        g = gammel.get(r["navn"])
        if not g:
            continue
        gs, ns = g["status"], r["status"]
        gp, np_ = g.get("produkt"), r.get("produkt")
        if gs == ns and gp == np_:
            continue
        linje = (
            f"  {r['navn'][:26]:26} {gs:>11} → {ns:11} {(gp or '-')[:30]:30} → {(np_ or '-')[:30]}"
        )
        if rang.get(ns, 9) < rang.get(gs, 9):
            op.append(linje)
        elif rang.get(ns, 9) > rang.get(gs, 9):
            ned.append(linje)
        else:
            skift.append(linje)
    print(
        f"\nDIFF mod {sti}: {len(op)} op, {len(ned)} ned, {len(skift)} samme status/andet produkt"
    )
    for titel, xs in (("OP", op), ("NED", ned), ("PRODUKTSKIFT", skift)):
        if xs:
            print(f"\n## {titel}")
            print("\n".join(xs))


if __name__ == "__main__":
    sys.exit(main())
