#!/usr/bin/env python3
"""nemlig_ordbog.py — ret ret-arkets ord så varerne kan findes hos Nemlig.

Skriver KUN kolonnen `Ingredienser_struktureret` (den maskin-vendte). Den
menneske-læste `Ingredienser` med opskriftens egen formulering røres ALDRIG —
den skal stadig kunne læses som en opskrift.

SIKKERHEDSREGEL: kun råvarer der FAKTISK fejler foreslås ændret. Et navn der
allerede rammer rigtigt, lades i fred — også selv om et kortere ord findes.
"hakket oksekød" må ikke blive til "oksekød"; forskellen er hele retten.

Hvert forslag VERIFICERES mod Nemlig før det skrives: kandidaten skal score
mindst lige så højt som SIKKER_SCORE, ramme rigtig vareart (hovedord) og være
en reel forbedring af den nuværende. Ellers droppes det.

    python3 scripts/nemlig_ordbog.py                 # kun forslag (tørkørsel)
    python3 scripts/nemlig_ordbog.py --apply         # skriv til arket
    python3 scripts/nemlig_ordbog.py --antal 40      # begræns (test)
    python3 scripts/nemlig_ordbog.py --oversaet           # ARK_OVERSAETTELSER, tørkørsel
    python3 scripts/nemlig_ordbog.py --oversaet --apply   # … skriv (CAS + log)
    python3 scripts/nemlig_ordbog.py --fortryd            # rul sidste skrivning tilbage

SIKKER SKRIVNING (2026-10-01): Apps Script'ets `struct`-kald skriver på ID
alene og har INGEN navne-vagt (modsat `vote`) — og ID-kolonnen har dubletter
(76-80 findes to gange) og forskydes når Gemini indsætter en række. Derfor er
hver skrivning compare-and-set FRA KLIENTEN: dublet-ID springes over, rækken
skal stadig bære det ret-navn og den struct vi læste, og arket læses igen
bagefter for at bevise at KUN de tilsigtede rækker ændrede sig. Hver skrivning
logges i ARK_LOG med før/efter, så `--fortryd` kan rulle den tilbage.

Konventionen der kommer ud af det står i docs/nemlig_kurv.md og er ment som
rettesnor for Gemini, der normalt fylder arket ud.
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mad_planner as MP  # noqa: E402
import nemlig_api as NA  # noqa: E402

RAPPORT = "/config/.nemlig_ordbog.json"
ARK_LOG = "/config/.nemlig_ark_log.json"

# ARKETS ORD → NEMLIGS ORD (2026-10-01, user: "du kan jo også ændre ordene i
# arket systematisk"). Kun i den maskin-vendte struct-kolonne: opskriftens egen
# tekst er urørt, men INDKØBSLISTEN viser det nye ord — så et menneske ser
# byttet. Det er derfor erstatninger hører HER og ikke i nemlig_api.SYNONYMER,
# hvor de ville købe en anden vare usynligt (jf. iteration 4: kuller → torsk).
# Hver linje er målt live mod den rigtige matcher (status ok, rigtig vare) —
# se docs/sprint_log.md 2026-10-01d. To slags:
#   SAMME VARE   — butikkens ord for præcis det opskriften beder om
#   ERSTATNING   — Nemlig fører ikke varen; standard-erstatningen i køkkenet
# Tabellen bliver stående: bruger Gemini det gamle ord i en NY ret, oversætter
# næste kørsel den også.
ARK_OVERSAETTELSER = {
    # --- SAMME VARE, butikkens ord ------------------------------------------
    "blandede rodfrugter": "rodfrugter",  # «Rodfrugter øko.» ER blandingen
    "rodfrugt": "rodfrugter",  # før: «Rodfrugtmix» = revet salat
    "orzo": "risoni",  # orzo = risoni; før: laks-færdigret
    "soja fars": "plantefars",  # plante-/sojafars til tacos
    "stjerne anis": "stjerneanis",
    "sweet chilisauce": "sød chilisauce",
    "svinekæber": "grisekæber",  # rå kæber; før: braiseret færdigret
    "mørk øl": "porter",  # til braisering
    "mørkt øl": "porter",
    "oksekød i wokstrimler": "oksestrimler",
    "ristet brød": "toastbrød",  # før: frost-hvidløgsbrød
    "lyst brød": "toastbrød",  # 4 skiver hvidt brød
    "frisk pasta": "frisk tagliatelle",  # "frisk" er stopord → tør penne
    "salsa": "chunky salsa",  # rød, mild; før: tomatillo
    "tortellini med ost": "tortelloni med ricotta",
    "griseslag": "svinebryst",  # griseslag = svinebryst
    "wontonpapir": "gyoza dej",  # dumpling-plader til momo
    "hvid fisk": "torskefilet",  # før: «Fiskefars m. hvidfisk»
    # --- ERSTATNING: Nemlig fører ikke varen ---------------------------------
    "brune linser": "grønne linser",
    "gule linser": "røde linser",  # dal
    "kalkunschnitzel": "kalkunbryst",  # skæres i skiver og bankes
    "grisekød i strimler": "mørbrad af gris",  # skæres i strimler (wok)
    "kuller": "torskefilet",
    "romainesalat": "hjertesalat",
    "lammekød": "lammeculotte",  # i tern til gryde/karry
    "kewpie mayonnaise": "mayonnaise",
    "instant nudler": "nudler m. kyllingesmag",  # ramen-pakke; smagsposen udelades
    # MÅLT OG FRAVALGT (bliver spørgsmål): "hel nellike" → "nelliker" køber
    # kun stødt; "karahi/nihari masala" → "garam masala" er en BASISVARE og
    # ville forsvinde fra listen; "ravioli med svampe" → "ravioli" mister
    # fyldet; "andebryst" → kun confit; "kormapasta" → kun korma-SAUCE.
}

# Ord der beskriver tilstand/tilberedning frem for vare. De prøves fjernet —
# men kun som KANDIDAT, og kun hvis det nuværende navn allerede fejler.
# "hakket" og "revet" står bevidst IKKE her: hakket oksekød og revet ost er
# egne varer hos Nemlig, ikke en tilstand af noget andet.
FYLDORD = [
    "frisk",
    "friske",
    "frosne",
    "frossen",
    "færdig",
    "færdige",
    "færdigstegt",
    "færdigstegte",
    "ukogt",
    "ukogte",
    "optøet",
    "afpudsede",
    "afpudset",
    "blandede",
    "blandet",
    "store",
    "stort",
    "små",
    "lille",
    "ferske",
    "fersk",
]
# NB: "syltet/syltede", "mosede", "røget", "tørret" står bevidst IKKE her.
# De ER varen: syltede rødbeder er en anden hylde end friske rødbeder, og at
# fjerne ordet ville skifte mad. De to der faktisk skulle oversættes
# ("mosede tomater", "syltede agurker") ligger i SYNONYMER, hvor de kan
# oversættes præcist i stedet for at blive strippet.


def log(m):
    print(f"[ordbog] {m}", file=sys.stderr)


def _hent_rapport():
    try:
        with open(RAPPORT, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError, json.JSONDecodeError, OSError:
        return {}


def _gem_rapport(forslag, opgivet, ok, ok_navne):
    tmp = f"{RAPPORT}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(
            {"forslag": forslag, "opgivet": opgivet, "ok": ok, "ok_navne": ok_navne},
            fh,
            ensure_ascii=False,
            indent=1,
        )
    os.replace(tmp, RAPPORT)


def parse_struct(v):
    """'250|g|hakket oksekød;…' → [(mængde, enhed, vare), …]"""
    ud = []
    for post in (v or "").split(";"):
        dele = [d.strip() for d in post.split("|")]
        if len(dele) >= 3 and dele[2]:
            ud.append((dele[0], dele[1], dele[2]))
    return ud


def byg_struct(poster):
    return ";".join("%s|%s|%s" % p for p in poster)


def kandidater(navn):
    """Erstatninger der BEVARER BETYDNINGEN — intet andet.

    Første udgave genererede også afkortninger og "sidste ord alene", og
    verificerede kun at det nye ord fandt et produkt med høj sikkerhed. Det er
    den forkerte test: den spørger "findes der noget der hedder sådan", ikke
    "er det stadig den samme mad". Målt 2026-08-31 ville den have skrevet
    `brystflæsk`→`bryst` (Brystkarameller), `kyllingebouillon`→`kyllingeb`
    (kyllingebrystfilet), `pastinakker`→`pasti` (Ga-jol lakrids) og
    `oksekød i strimler`→`strimler` (skinkestrimler) ind i brugerens ark.

    Derfor kun de fire operationer der ikke kan skifte vare:
      1. et kendt synonym (samme vare, butikkens ord)
      2. fjern tilstands-ord ("frosne ærter" → "ærter")
      3. fjern parentes-tilføjelse ("bao buns (frost)" → "bao buns")
      4. ental af sidste ord ("laksefileter" → "laksefilet")

    Afkortning og "sidste ord alene" er væk. De fandt godt nok limejuice→lime,
    men prisen var pastinakker→lakrids, og et ark er ikke stedet at gætte.
    """
    ud = []
    lav = navn.lower().strip()

    syn = NA.synonym(navn)
    if syn.lower() != lav:
        ud.append(syn)

    ord_ = [o for o in re.split(r"\s+", lav) if o]
    uden = [o for o in ord_ if o.strip("(),.") not in FYLDORD]
    if uden and uden != ord_:
        ud.append(" ".join(uden))

    uparen = re.sub(r"\s*\([^)]*\)", "", navn).strip()
    if uparen and uparen.lower() != lav:
        ud.append(uparen)
        # fyldord OG parentes på én gang ("hakket spinat (frost)")
        up = [o for o in re.split(r"\s+", uparen.lower()) if o and o.strip("(),.") not in FYLDORD]
        if up:
            ud.append(" ".join(up))

    if ord_:
        sidste = ord_[-1]
        # KUN "-er". Dansk flertals-e er ikke sikkert at fjerne: det gjorde
        # "teriyaki sauce" til "teriyaki sauc", som ikke er et ord — og et
        # ark er ikke stedet for stumper.
        for suf in ("er",):
            if len(sidste) > 4 and sidste.endswith(suf):
                ud.append(" ".join(ord_[:-1] + [sidste[: -len(suf)]]))
                break

    seen, rene = set(), []
    for k in ud:
        k = k.strip()
        if not k or k.lower() == lav or k.lower() in seen:
            continue
        if len(k) < 4 or not k.strip("()., "):
            continue  # aldrig et stump eller et tegn
        if any(c in k for c in "()"):
            continue  # halve parenteser er ikke ord
        seen.add(k.lower())
        rene.append(k)
    return rene


def betyder_det_samme(gammelt, nyt):
    """Beholder forslaget rettens KERNEORD?

    Sidste ord er hovedordet på dansk. Bevares det (eller er ændringen et
    kendt synonym), er varen den samme; ellers har vi skiftet mad.
    "frosne ærter"→"ærter" består; "halloumi ost"→"ost" gør ikke, for "ost"
    alene er en helt anden hylde.
    """
    if NA.normaliser(NA.synonym(gammelt)) == NA.normaliser(nyt):
        return True
    g = NA.ord_af(gammelt)
    n_ = NA.ord_af(nyt)
    if not g or not n_:
        return False
    if len(n_) == 1 and len(g) > 1 and n_[0] == g[-1]:
        # Kun ét ord tilbage, og det er kerneordet. Tillades kun når det ord
        # er specifikt nok til at stå alene — ellers er "ost", "øl", "ris" og
        # "linser" pludselig hele varen.
        if n_[0] in _FOR_GENERISKE:
            return False
    return NA.ord_matcher(g[-1], n_[-1]) or NA.ord_matcher(n_[-1], g[-1])


# Ord der er en hylde, ikke en vare. Bliver de tilbage alene, har vi tabt
# det der gjorde varen til netop den vare.
_FOR_GENERISKE = {
    "ost",
    "oel",
    "ris",
    "linser",
    "svampe",
    "strimler",
    "skind",
    "soja",
    "koed",
    "fisk",
    "salat",
    "sauce",
    "bouillon",
    "melon",
    "pasta",
    "broed",
    "kage",
    "juice",
    "olie",
    "mel",
    "sukker",
}


def bedoem(n, term):
    """→ (score, hoved, produktnavn, paa_lager) for et søgeord."""
    try:
        traef = NA.find_bedste(n.search_bredt(NA.synonym(term), 8), term)
    except NA.NemligFejl:
        return 0.0, False, None, False
    if not traef:
        return 0.0, False, None, False
    v, _b, _r = NA.vaelg_produkt(traef, 100.0, True)
    if v is None:
        return 0.0, False, None, False
    return v["score"], v["hoved"], v["navn"], v["paa_lager"]


# =============================================================================
# Sikker skrivning
# =============================================================================
def _hent_log():
    try:
        with open(ARK_LOG, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError, json.JSONDecodeError, OSError:
        return []


def _gem_log(poster):
    tmp = f"{ARK_LOG}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(poster, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, ARK_LOG)


def _snapshot(dishes):
    """→ {id: (ret, struct)} — og mængden af ID'er der står mere end én gang."""
    snap, dubletter = {}, set()
    for d in dishes:
        i = str(d.get("id", "")).strip()
        if i in snap:
            dubletter.add(i)
        snap[i] = (d.get("ret", ""), d.get("struct", "") or "")
    return snap, dubletter


def skriv_sikkert(plan, dry=False):
    """plan = [{id, ret, foer, efter, aendringer}] → (skrevet, sprunget, fejl).

    Compare-and-set mod en FRISK læsning lige før skrivningen, og en ny
    læsning bagefter der skal vise at præcis de planlagte rækker ændrede sig.
    """
    dishes, kilde = MP.fetch_dishes()
    if kilde != "api":
        raise RuntimeError("arket kunne ikke læses via API'et — skriver ikke")
    foer, dubletter = _snapshot(dishes)
    skrevet, sprunget = [], []
    for p in plan:
        i = p["id"]
        if i in dubletter:
            sprunget.append((p, "dublet-ID — Apps Script kan ramme en anden række"))
            continue
        if foer.get(i) != (p["ret"], p["foer"]):
            sprunget.append((p, "rækken har ændret sig siden planen blev lagt"))
            continue
        if dry:
            skrevet.append(p)
            continue
        MP.sheet_api("struct", id=i, value=p["efter"])
        skrevet.append(p)
    if dry or not skrevet:
        return skrevet, sprunget, []
    efter, _d = _snapshot(MP.fetch_dishes()[0])
    forventet = {p["id"]: (p["ret"], p["efter"]) for p in skrevet}
    fejl = []
    for i, v in efter.items():
        if i in forventet:
            if v != forventet[i]:
                fejl.append(f"id {i}: forventede ny struct, fandt {v[1][:60]!r}")
        elif foer.get(i) not in (None, v):
            fejl.append(f"id {i} ({v[0]}) ændrede sig UDEN at være i planen")
    log_ = _hent_log()
    stempel = MP.now_local().strftime("%Y-%m-%dT%H:%M:%S")
    for p in skrevet:
        log_.append(
            {
                "dato": stempel,
                "id": p["id"],
                "ret": p["ret"],
                "foer": p["foer"],
                "efter": p["efter"],
                "aendringer": p["aendringer"],
            }
        )
    _gem_log(log_)
    return skrevet, sprunget, fejl


def plan_oversaettelser(dishes, tabel):
    """→ plan for alle retter hvis struct bruger et ord fra `tabel`."""
    noegler = {MP.normaliser_navn(k): v for k, v in tabel.items()}
    plan = []
    for d in dishes:
        poster = parse_struct(d.get("struct"))
        if not poster:
            continue
        nye, aendr = [], []
        for m, e, vare in poster:
            ny = noegler.get(MP.normaliser_navn(vare))
            if ny and ny != vare:
                nye.append((m, e, ny))
                aendr.append([vare, ny])
            else:
                nye.append((m, e, vare))
        if aendr:
            plan.append(
                {
                    "id": str(d.get("id", "")).strip(),
                    "ret": d.get("ret", ""),
                    "foer": d.get("struct", "") or "",
                    "efter": byg_struct(nye),
                    "aendringer": aendr,
                }
            )
    return plan


def mode_oversaet(apply_):
    dishes, kilde = MP.fetch_dishes()
    log(f"{len(dishes)} retter fra {kilde}")
    plan = plan_oversaettelser(dishes, ARK_OVERSAETTELSER)
    for p in plan:
        print(
            f"  {p['id']:>4} {p['ret'][:40]:40} "
            + "; ".join(f"{a} → {b}" for a, b in p["aendringer"])
        )
    skrevet, sprunget, fejl = skriv_sikkert(plan, dry=not apply_)
    print(
        f"\n{len(plan)} retter i planen · {len(skrevet)} "
        f"{'skrevet' if apply_ else 'kan skrives'} · {len(sprunget)} sprunget over"
    )
    for p, why in sprunget:
        print(f"  SPRUNGET {p['id']} {p['ret']}: {why}")
    for f in fejl:
        print(f"  ⚠️ VERIFIKATION: {f}")
    if not apply_:
        print("\n(tørkørsel — kør med --apply for at skrive til arket)")
    return 1 if fejl else 0


def mode_fortryd():
    """Rul den SENESTE skrivning (samme tidsstempel) tilbage — også med CAS."""
    log_ = _hent_log()
    if not log_:
        print("intet at fortryde")
        return 0
    sidste = log_[-1]["dato"]
    plan = [
        {
            "id": p["id"],
            "ret": p["ret"],
            "foer": p["efter"],
            "efter": p["foer"],
            "aendringer": [[b, a] for a, b in p["aendringer"]],
        }
        for p in log_
        if p["dato"] == sidste
    ]
    skrevet, sprunget, fejl = skriv_sikkert(plan)
    print(f"fortrudt {len(skrevet)} retter fra {sidste}; {len(sprunget)} sprunget over")
    for p, why in sprunget:
        print(f"  SPRUNGET {p['id']} {p['ret']}: {why}")
    for f in fejl:
        print(f"  ⚠️ VERIFIKATION: {f}")
    return 1 if fejl else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="skriv til arket")
    ap.add_argument(
        "--oversaet", action="store_true", help="anvend ARK_OVERSAETTELSER (med --apply: skriv)"
    )
    ap.add_argument("--fortryd", action="store_true", help="rul den seneste ark-skrivning tilbage")
    ap.add_argument("--antal", type=int, help="begræns antal råvarer (test)")
    ap.add_argument(
        "--frisk", action="store_true", help="ignorér tidligere delresultat og start forfra"
    )
    a = ap.parse_args()
    if a.fortryd:
        return mode_fortryd()
    if a.oversaet:
        return mode_oversaet(a.apply)

    dishes, kilde = MP.fetch_dishes()
    log(f"{len(dishes)} retter fra {kilde}")

    # Unikke varenavne på tværs af alle retter
    unik = {}
    for d in dishes:
        for _m, _e, vare in parse_struct(d.get("struct")):
            unik.setdefault(vare.strip(), []).append(str(d.get("id")))
    navne = sorted(unik)
    if a.antal:
        navne = navne[: a.antal]
    log(f"{len(navne)} unikke varenavne")

    # GENOPTAGELIG. En fuld kørsel er ~1100 Nemlig-opslag = et kvarter, og
    # den overlever ikke at SSH-sessionen lukkes. Delresultatet gemmes derfor
    # løbende, og et nyt kald springer det allerede afgjorte over — flere kald
    # samler sig til én kørsel i stedet for at starte forfra hver gang.
    tidligere = {} if a.frisk else _hent_rapport()
    forslag = dict(tidligere.get("forslag") or {})
    opgivet = list(tidligere.get("opgivet") or [])
    ok_i_forvejen = int(tidligere.get("ok") or 0)
    afgjort = set(forslag) | set(opgivet) | set(tidligere.get("ok_navne") or [])
    ok_navne = list(tidligere.get("ok_navne") or [])
    if afgjort:
        log(f"genoptager — {len(afgjort)} allerede afgjort")

    n = NA.Nemlig()
    for i, navn in enumerate(navne, 1):
        if navn in afgjort:
            continue
        if i % 25 == 0:
            log(f"{i}/{len(navne)}  (afgjort {len(afgjort)})")
        sc, hoved, prod, lager = bedoem(n, navn)
        if sc >= NA.SIKKER_SCORE and hoved:
            ok_i_forvejen += 1
            ok_navne.append(navn)
            afgjort.add(navn)
            _gem_rapport(forslag, opgivet, ok_i_forvejen, ok_navne)
            continue  # virker — rør den ikke
        bedst = None
        for k in kandidater(navn):
            ksc, khoved, kprod, klager = bedoem(n, k)
            if not betyder_det_samme(navn, k):
                continue
            if ksc >= NA.SIKKER_SCORE and khoved and ksc > sc:
                bedst = {
                    "nyt": k,
                    "score": ksc,
                    "produkt": kprod,
                    "lager": klager,
                    "foer": {"score": sc, "produkt": prod},
                }
                break
        if bedst:
            forslag[navn] = bedst
        else:
            opgivet.append(navn)
        afgjort.add(navn)
        _gem_rapport(forslag, opgivet, ok_i_forvejen, ok_navne)

    print(f"\n{'=' * 70}")
    print(
        f"{len(navne)} varenavne · {ok_i_forvejen} virkede allerede · "
        f"{len(forslag)} kan rettes · {len(opgivet)} uden løsning"
    )
    print(f"{'=' * 70}\n")
    for gammelt, f in sorted(forslag.items()):
        print(
            f"  {gammelt[:30]:30} → {f['nyt'][:26]:26} "
            f"({f['foer']['score']:.2f} → {f['score']:.2f})  {f['produkt'][:30]}"
        )
    if opgivet:
        print(
            f"\nUden løsning ({len(opgivet)}): {', '.join(opgivet[:25])}"
            + (" …" if len(opgivet) > 25 else "")
        )

    with open(RAPPORT, "w", encoding="utf-8") as fh:
        json.dump({"forslag": forslag, "opgivet": opgivet}, fh, ensure_ascii=False, indent=1)
    print(f"\nRapport: {RAPPORT}")

    if not a.apply:
        print("\n(tørkørsel — kør med --apply for at skrive til arket)")
        return 0

    # --- skriv ---------------------------------------------------------------
    # Kun retter der faktisk indeholder et af de ændrede ord røres, og kun
    # vare-feltet i struct: mængde og enhed er brugerens tal.
    plan = plan_oversaettelser(dishes, {k: f["nyt"] for k, f in forslag.items()})
    skrevet, sprunget, fejl = skriv_sikkert(plan)
    print(f"\nSkrev {len(skrevet)} retter til arket; {len(sprunget)} sprunget over.")
    for f in fejl:
        print(f"  ⚠️ VERIFIKATION: {f}")
    return 1 if fejl else 0


if __name__ == "__main__":
    sys.exit(main())
