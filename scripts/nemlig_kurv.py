#!/usr/bin/env python3
"""nemlig_kurv.py — læg mad-planlægningens indkøbsliste i Nemlig-kurven.

FASE 2. Bygger på scripts/nemlig_api.py (API + matcher) og scripts/mad_planner.py
(retter + den summerede indkøbsliste). Se docs/nemlig_kurv.md.

⚠️ DER AFGIVES ALDRIG EN ORDRE HERFRA. Kun kurven fyldes; leveringstid og
   betaling vælger et menneske i Nemligs egen app. Der findes bevidst ingen
   kode-vej til checkout — en matcher-fejl skal kunne koste en forkert vare,
   aldrig en gennemført handel.

HVILKEN LISTE?  `st["indkoeb"]["retter"]` — den AKTUELLE liste, husket ved
NAVN. Vi genberegner ikke et udvalg: kurven skal indeholde det brugeren kan se
på Mad-siden, ikke en ny tilfældig trækning. Nøglen er navnet og ikke id'et,
fordi arkets id-kolonne har dubletter (jf. noten i mad_planner.py) — et
id-opslag kan lande på en helt anden ret.

IDEMPOTENS: `AddToBasket.quantity` er absolut, så vi sender ØNSKET SLUT-ANTAL
pr. produkt. To kørsler i træk giver derfor samme kurv, ikke dobbelt indkøb.
Vi rører kun de produkter VI har regnet os frem til — varer brugeren selv har
lagt i kurven bliver stående urørt.

CLI:
    --kurv            byg kurven (respekterer tørkørsels-switchen)
    --kurv --force    ignorér kill-switchen (manuel knap/test)
    --dry             regn igennem, rør ikke kontoen (uanset switches)
    --basis           læg den faste basiskurv i (mælk, smør, ost, frugt …)
    --ryd-vores       fjern kun det DENNE integration har lagt i kurven
    --vis             vis hvad listen ville blive parret med (ingen skrivning)
    --republish       gen-publicér sensoren fra sidste kørsel (rører ikke Nemlig)
    --tilbud          læg ugens tilbud på de faste varer i kurven (inden for budget)
    --toem-alt        tøm HELE kurven + regnskab + sensor
    --svar ACTION     besvar et parrings-spørgsmål (kaldes af action-handleren)

SPØRGSMÅLENE (fase 3): en vare der ikke kunne parres sikkert — eller er udsolgt
— lægges IKKE i kurven. I stedet stiller SCRIPTET et spørgsmål på Parent A's
telefon med de faktiske produkter som knapper. Svaret skrives til
`.nemlig_varer.json`, og næste kørsel bruger parringen direkte uden at spørge
igen (`laert` springer score-tærsklen over). Det er hele indlæringen: ingen
model er involveret, kun et menneskes valg der huskes.
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ai_forbrug  # noqa: E402  (sti skal sættes først)
import ha_secrets  # noqa: E402
import mad_planner as MP  # noqa: E402
import nemlig_api as NA  # noqa: E402

# Hvad vi selv har lagt i kurven, så --ryd-vores ikke rører brugerens egne varer.
KOERSEL_FIL = "/config/.nemlig_sidste_kurv.json"
# Sidste sensor-payload. sensor.nemlig_kurv publiceres via REST og FORSVINDER
# ved restart (samme vilkår som mad-sensorerne) — en tile der peger på den ville
# ellers være en død reference indtil næste kurv-kørsel, og en kørsel koster 44
# søgninger mod Nemlig. Derfor gemmes payloaden, så --republish kan genskabe
# sensoren ved homeassistant:start uden at røre deres API.
SENSOR_FIL = "/config/.nemlig_sensor.json"
# Åbne parrings-spørgsmål: ask_id -> varen + de produkter knapperne peger på.
# Skal overleve en restart — svaret kan komme timer efter spørgsmålet.
SPOERG_FIL = "/config/.nemlig_spoerg.json"

# "Spring over" holder i så mange dage — ikke for evigt.
# 2026-08-31: brugeren sprang alle fem spørgsmål over på ét minut, fordi
# forslagene var ubrugelige ("Soltørrede fersken" til rødspættefileter), ikke
# fordi han aldrig vil spørges. En permanent konsekvens af ét tryk på et
# dårligt forslag er en fælde: varen ville aldrig blive nævnt igen, heller
# ikke efter matcheren var rettet. Et tidsboks er stadig fred fra nagging,
# men taber ikke varen for altid.
SPRING_OVER_DAGE = 30

E_AUTO = "input_boolean.nemlig_auto_tilfoej_enabled"
E_SCORE = "input_number.nemlig_match_min_score"
E_SPOERG_MAX = "input_number.nemlig_spoerg_max"
E_OEKO = "input_boolean.nemlig_foretraek_oeko"
E_OEKO_LOFT = "input_number.nemlig_oeko_loft_pct"
E_FAV_LOFT = "input_number.nemlig_favorit_loft_pct"
E_TILBUD = "input_boolean.nemlig_foretraek_tilbud"
# Multikøb (2026-11-14): rund op til et helt "X for Y"-sæt, når den ekstra
# pakke kan holde sig til næste indkøb (`NA.lager_holdbar`) og er købt før.
E_MULTI = "input_boolean.nemlig_multikoeb"
E_MULTI_MAX = "input_number.nemlig_multikoeb_max_kr"
E_TILBUD_MIN = "input_number.nemlig_tilbud_min_pct"
E_TILBUD_BUDGET = "input_number.nemlig_tilbud_budget_kr"
NID = "nemlig"

# =============================================================================
# KILDER — hvor kom en vare i kurven fra?
# =============================================================================
# Hver linje vi lægger i kurven bærer sin kilde HELE vejen: gennem
# køerselsfilen (så de to knapper ikke kan slette hinandens varer) og ud i
# sensoren (så siden kan vise dem hver for sig, user-spec 2026-09-01: "det skal
# være meget tydeligt ... hvilke varer der blev tilføjet via den knap og hvilke
# der kom fra opskrifter"). Linjer uden `kilde` er fra før feltet fandtes og
# læses som opskrift-linjer.
KILDE_LISTE = "opskrift"
KILDE_BASIS = "basis"
# En TREDJE kilde: en færdig liste fra en fil (samme format som BASISKURV:
# {"titel": …, "poster": [{"navn", "maengde", "enhed"}]}). Skrives af det
# script der ejer listen lige før kørslen; filen er runtime (gitignoreret).
KILDE_EKSTRA = "ekstra"
EKSTRA_FIL = "/config/.nemlig_ekstra.json"
# En FJERDE kilde (2026-11-14, user: "spare flere penge … 2 for 1 tilbud og
# lignende"): ugens tilbud på de FASTE varer (købt i ≥ 2 af de seneste 16
# ordrer), holdbare og på lager. Knappen "Læg tilbud i kurven" → `--tilbud`;
# mængden er ét helt sæt i et "X for Y" (ellers det antal vi plejer at købe),
# billigste besparelse pr. krone først, inden for et budget pr. tryk.
KILDE_TILBUD = "tilbud"

# =============================================================================
# BASISKURVEN — den faste husholdningsliste bag knappen "Tilføj basisvarer"
# =============================================================================
# ⚠️ IKKE det samme som `mad_planner.BASISVARER`, som er spisekammer-varer
# (salt, peber, olie) der filtreres UD af indkøbslisten. Dette er varer vi
# køber uanset hvilke retter der står på listen.
#
# MÆNGDERNE ER SKREVET I EN ENHED, IKKE I PAKKER — med vilje. `antal_pakker`
# regner om til det antal pakker der dækker behovet, så listen overlever at
# Nemlig skifter pakkestørrelse eller at en vare er udsolgt og matchet flytter
# sig. Målt 2026-09-01: "banan" rammer både «Banan øko.» (1 stk) og «Bananer
# små øko.» (4 stk). "6 stk" giver 6 hhv. 2 pakker = 6 hhv. 8 bananer; "1
# pakke" ville give 1 hhv. 4. Et fast pakke-tal ville altså svinge 6× med
# lagerstatus.
#
# SØGEORDENE SKAL STAVES MED DANSKE BOGSTAVER. Målt 2026-09-01 mod den ægte
# søgning: "soedmaelk" og "sodmaelk" gav score 0,00 og «Coca-Cola» som bedste
# bud, mens "sødmælk" gav 1,15 mod «Sødmælk 3,5%». Nemligs søgning er ikke
# ascii-foldende — resten af koden normaliserer ø→oe internt, men det der
# sendes til dem skal være dansk.
#
# OSTEN: user bad om "mild i blok, noget vi har købt før". Målt samme dag var
# der INGEN tidligere købt mild blok-ost i feltet (favoritterne var Emmentaler
# i blok, ost i skiver, revet cheddar og Grana Padano). "ost i blok" rammer
# derimod «Hvid ost i blok» 200 g med score 1,15 og hovedord-træf — mild hvid
# ost i blok, altså varen han beskrev. Første kørsel lægger den i; er den
# forkert, retter ét svar på et spørgsmål (eller en linje i
# `.nemlig_varer.json`) den permanent.
BASISKURV = [
    {"navn": "sødmælk", "maengde": 1, "enhed": "l"},
    {"navn": "minimælk", "maengde": 2, "enhed": "l"},
    {"navn": "smør", "maengde": 200, "enhed": "g"},
    {"navn": "ost i blok", "maengde": 200, "enhed": "g"},
    {"navn": "bananer", "maengde": 6, "enhed": "stk"},
    {"navn": "cherrytomater", "maengde": 250, "enhed": "g"},
]

# Knapperne hedder "1" og "2"; valgmulighederne står i BESKEDEN med fuldt
# navn, pris og pakning (user-spec: knap-teksterne er svære at læse).
#
# HVORFOR KUN TO: Android-companion viser præcis TRE action-knapper — målt
# 2026-08-31, hvor fire numre blev sendt og kun tre kom frem. Den tredje plads
# er reserveret til "Ingen af dem", som er den vigtigste knap af dem alle:
# uden den er der ingen ærlig udvej når begge forslag er forkerte, og et
# tilfældigt valg bliver til en PERMANENT parring.
KNAP_KANDIDATER = 2

# Linjeskift i push-beskeder. Egen konstant fordi beskederne bygges med
# %-formatering, hvor et bart escape-tegn inde i mønsteret er svært at se.
NL = chr(10)


def log(msg):
    print(f"[nemlig-kurv] {msg}", file=sys.stderr)


# =============================================================================
# Listen
# =============================================================================
def aktuel_liste(states):
    """→ (poster, retnavne). Den liste brugeren ser på Mad-siden, som data."""
    st = MP.load_state()
    navne = ((st.get("indkoeb") or {}).get("retter")) or []
    if not navne:
        return [], []
    dishes, _kilde = MP.fetch_dishes()  # returnerer (liste, kilde)
    # Match på navn; arket kan have flyttet rundt på rækkerne siden listen blev
    # lavet, men navnet er stabilt (og er dét state-filen gemmer).
    pr_navn = {}
    for d in dishes:
        pr_navn.setdefault(d["ret"], d)
    valgt = [pr_navn[n] for n in navne if n in pr_navn]
    if len(valgt) != len(navne):
        mangler = [n for n in navne if n not in pr_navn]
        log(f"ADVARSEL: {len(mangler)} ret(ter) fra listen findes ikke i arket: {mangler}")
    poster, _sprunget, _trukket = MP.indkoebsposter(
        valgt, MP.is_on(states, MP.E_SKIP_BASIS), st.get("har_hjemme")
    )
    return poster, [d["ret"] for d in valgt]


# =============================================================================
# Parring
# =============================================================================
def tilbudsfelter(x, antal):
    """Kampagnen på et søge-træf og hvad den sparer på `antal` pakker.

    `spar_kr` er Nemligs egen rabat: normalpris × antal minus det kassen tager
    (et "X for Y" kun for hele sæt, `NA.pris_for`). `holdbar`/`favorit` er
    multikøbets to krav (`multikoeb_runding`)."""
    k = x.get("kampagne")
    pris = x.get("pris") or 0
    spar = round(antal * float(pris) - NA.pris_for(k, pris, antal), 2) if k else 0.0
    return {
        "kampagne": k,
        "spar_kr": spar if spar > 0.005 else 0.0,
        "holdbar": NA.lager_holdbar(x),
        "favorit": bool(x.get("favorit")),
    }


def parr(
    n,
    poster,
    min_score,
    varer_cache,
    oeko_loft=None,
    foretraek_tilbud=True,
    favorit_loft=NA.FAVORIT_LOFT_PCT,
):
    """→ liste af beslutninger, én pr. vare. Skriver ikke til kurven.

    Lagerstatus læses ALTID friskt fra søgningen — den er volatil (målt:
    en vare skiftede status inden for fem minutter), så den må ikke caches
    sammen med produkt-id'et.
    """
    ud = []
    for p in poster:
        navn = p["navn"]
        noegle = NA.normaliser(navn)
        husket = varer_cache.get(noegle)
        soegeord = (husket or {}).get("soegeord") or NA.synonym(navn)
        try:
            traef = NA.find_bedste(n.search_bredt(soegeord, 8), soegeord)
        except NA.NemligFejl as e:
            ud.append({**p, "status": "fejl", "grund": str(e)})
            continue
        if not traef:
            ud.append({**p, "status": "ingen_traef"})
            continue

        # Har vi lært et bestemt produkt-id for denne vare, så vinder det —
        # men KUN hvis det stadig findes i søgeresultatet, så vi får frisk
        # lagerstatus med. Ellers falder vi tilbage til bedste match.
        valgt = None
        if husket and husket.get("id"):
            valgt = next((t for t in traef if t["id"] == husket["id"]), None)
        laert = valgt is not None
        begrundelse, reference = "lært valg", None
        if valgt is None:
            # Præferencerne anvendes KUN her. Et lært valg er brugerens eget og
            # må aldrig overtrumfes af en øko- eller tilbuds-regel.
            # Relevans-filteret ligger FØR valget (2026-09-01b): ellers kan én
            # dårlig topkandidat koste hele søgesvaret, selv om der lå en
            # brugbar vare lige under den.
            valgt, begrundelse, reference = NA.vaelg_produkt(
                NA.kun_relevante(traef, soegeord),
                oeko_loft,
                foretraek_tilbud,
                soegt=NA.form_ord(soegeord, p.get("enhed")),
                favorit_loft_pct=favorit_loft,
                behov=(p.get("maengde"), p.get("enhed")),
            )
            if valgt is None:
                ud.append({**p, "status": "ingen_traef"})
                continue

        antal, hvorfor = NA.antal_pakker(p["maengde"], p["enhed"], valgt["_raw"], navn=soegeord)
        # Merprisen for øko og `besparelse_est` regnes mod den billigste
        # SAMMENLIGNELIGE vare i samme match-felt — forskellen mod det
        # alternativ vi valgte FRA, med kampagnepris på begge sider
        # (vaelg_produkt → NA._med_kampagne). Nemligs EGEN rabat (normalpris
        # minus det vi betaler) står i `spar_kr`. 31/8 så det ud som om API'et
        # ingen kampagner havde; de står i `Campaign` (målt 14/11: 777 gyldige
        # af 1310 produkter), og `Price` er altid normalprisen.
        merpris = besparelse = None
        if (
            reference is not None
            and valgt["id"] != reference["id"]
            and NA._sammenlignelig(valgt, reference)
        ):
            diff = (valgt["enhedspris"] - reference["enhedspris"]) * antal
            if valgt["oeko"] and diff > 0:
                merpris = round(diff, 2)
            elif diff < 0:
                besparelse = round(-diff, 2)
        post = {
            **p,
            "produkt": valgt["navn"],
            "id": valgt["id"],
            "score": round(valgt["score"], 2),
            "antal": antal,
            "pakke": valgt["pakning"],
            "hvorfor": hvorfor,
            "pris": valgt["pris"],
            "laert": laert,
            "oeko": valgt["oeko"],
            "tilbud": valgt["tilbud"],
            "kategori": valgt.get("kategori"),
            "begrundelse": begrundelse,
            "merpris_oeko": merpris,
            "besparelse_est": besparelse,
            **tilbudsfelter(valgt, antal),
            # Ekskludér det VALGTE produkt eksplicit. traef[1:] ville
            # være forkert: øko-/tilbuds-reglerne kan vælge noget andet
            # end traef[0], og så ville det valgte dukke op som sit eget
            # alternativ = to identiske knapper i spørgsmålet.
            "alternativer": [
                {
                    "id": t["id"],
                    "navn": t["navn"],
                    "pris": t["pris"],
                    "lager": t["paa_lager"],
                    "pakning": t["pakning"],
                    "score": t["score"],
                    "kategori": t.get("kategori"),
                }
                for t in traef
                if t["id"] != valgt["id"]
            ][:4],
            # Kun til ai_tjek (et byt skal regne pakker ud fra den RÅ vare);
            # fjernes før noget publiceres.
            "_traef": {t["id"]: t for t in traef},
        }
        # Kategorien SKAL med: for vin står vareordet slet ikke i navnet
        # («P.Maufoux Chardonnay Horizon»), kun i ProductCategoryGroupName.
        # Uden den faldt hvidvin i "ingen træf" selv om matchet var perfekt.
        if not laert and not NA.relevant_nok(
            soegeord, valgt["navn"], valgt.get("taksonomi") or valgt.get("kategori")
        ):
            # Vi har bogstaveligt talt intet brugbart at foreslå. En besked om
            # at varen ikke blev fundet er mere værd for brugeren end et
            # gætteri: fallback-søgningen kan finde "Snublejuice IPA" til
            # "paellaris", og dét som "bedste bud" er ren støj.
            ud.append(
                {**p, "status": "ingen_traef", "bedste_bud": valgt["navn"], "score": valgt["score"]}
            )
            continue
        if not valgt["paa_lager"]:
            post["status"] = "udsolgt"
        elif laert:
            post["status"] = "ok"  # brugerens eget valg — ingen gates
        elif valgt["score"] < min_score:
            post["status"] = "usikker"
        elif NA.form_advarsel(valgt, soegeord):
            post["status"] = "usikker"
            post["begrundelse"] = NA.form_advarsel(valgt, soegeord)
        elif not valgt["hoved"]:
            # Fuld score, men på et ord der kun beskriver hvad der er I varen.
            # "citrongræs" fik 1,15 på «Tofu m. citrongræs» og ville være røget
            # i kurven (målt over alle 495 råvarer). Scoren alene kan ikke
            # skelne "varen" fra "en ingrediens i varen" — hovedord-regionen
            # kan, så den er en GATE her, ikke bare en tie-breaker.
            post["status"] = "usikker"
            post["begrundelse"] = "fremmed hovedord — " + begrundelse
        else:
            post["status"] = "ok"
        ud.append(post)
    return ud


# =============================================================================
# AI-tjekket (2026-11-04, user: "en ai går igennem at de rigtige vare er blevet
# valgt og retter forkerte vare")
# =============================================================================
# ÉT samlet kald pr. kørsel (≈ 3-4k tokens ind, ~200 ud ≈ 3-5 øre) via
# scripts/ai_forbrug.py, der fører regnskab og stopper ved månedsloftet. Kun
# matcherens EGNE valg tjekkes: et lært valg er brugerens, og det rører AI'en
# aldrig. AI'en må kun vælge blandt de produkter søgningen faktisk fandt —
# den kan ikke finde på et produkt-id — og et byt kræver lager.
#   ok      + "c er rigtig"    → byttes (begrundelse "AI-rettet")
#   ok      + "ingen passer"   → usikker = et spørgsmål til dig, ikke i kurven
#   usikker + "tag c"          → ok (det var den slags matcheren spurgte om)
# Fejl, timeout eller nået loft → kurven bygges som før, uden AI.
AI_PROMPT = """Du tjekker en dansk indkøbsliste, der automatisk er parret med varer
i netbutikken Nemlig. For hver linje står opskriftens vare og nogle produkter;
a) er det produkt der er valgt nu. Er a) den vare opskriften mener, er alt godt
— også hvis mærke, øko, smag, variant eller pakke er en anden. Ret KUN når a)
er en ANDEN slags vare (fx edamame til "grønne bønner", sodavand til "squash",
croissant til "smør").

Svar KUN med linjer for de varer hvor a) er forkert, i formatet
  <nr>: <bogstav på det rigtige produkt, eller - hvis intet passer>
Er alle a) rigtige, svar præcis: OK

{linjer}"""


def _ai_linje(nr, b):
    navne = [b["produkt"]] + [a["navn"] for a in b["alternativer"]]
    return f"{nr}. {b['navn']}: " + " ".join(f"{chr(97 + i)}) {n}" for i, n in enumerate(navne))


def _byt(b, ny, grund):
    """Skift beslutningen til alternativet `ny` (et søge-træf med `_raw`)."""
    antal, hvorfor = NA.antal_pakker(b["maengde"], b["enhed"], ny["_raw"], navn=b["navn"])
    gammel = b["produkt"]
    b.update(
        produkt=ny["navn"],
        id=ny["id"],
        score=round(ny["score"], 2),
        antal=antal,
        pakke=ny["pakning"],
        hvorfor=hvorfor,
        pris=ny["pris"],
        oeko=ny["oeko"],
        tilbud=ny["tilbud"],
        kategori=ny.get("kategori"),
        merpris_oeko=None,
        besparelse_est=None,
        **tilbudsfelter(ny, antal),
        status="ok",
        begrundelse=f"AI: {grund}" if grund else "AI-rettet",
        ai_rettet_fra=gammel,
    )


def ai_tjek(beslutninger):
    """→ liste af {navn, fra, til, grund} for det AI'en ændrede."""
    tjek = [
        b
        for b in beslutninger
        if b["status"] in ("ok", "usikker") and not b.get("laert") and b.get("produkt")
    ]
    if not tjek:
        return []
    prompt = AI_PROMPT.format(linjer="\n".join(_ai_linje(i + 1, b) for i, b in enumerate(tjek)))
    try:
        svar = str(ai_forbrug.generer(f"nemlig {len(tjek)} varer", prompt) or "")
    except Exception as e:  # AiLoft, timeout, HA nede → uden AI, som før
        log(f"AI-tjek sprunget over: {e}")
        return []
    log(f"AI-tjek ({len(tjek)} varer): {svar.strip()[:400]!r}")
    rettet = []
    for linje in svar.splitlines():
        m = re.match(r"\s*(\d+)\s*[:.)]\s*([a-e]|-)(?![a-zæøå])", linje, re.I)
        if not m or not 1 <= int(m.group(1)) <= len(tjek):
            continue
        b = tjek[int(m.group(1)) - 1]
        valg, grund = m.group(2).lower(), ""
        fra = b["produkt"]
        if valg == "a":
            continue  # det valgte er rigtigt
        if valg == "-":
            if b["status"] == "ok":
                b["status"] = "usikker"
                b["begrundelse"] = f"AI: {grund or 'ingen passer'}"
                rettet.append({"navn": b["navn"], "fra": fra, "til": None, "grund": grund})
            continue
        i = ord(valg) - 98  # b) = første alternativ
        if i >= len(b["alternativer"]):
            continue
        alt = b["alternativer"][i]
        ny = (b.get("_traef") or {}).get(alt["id"])
        if ny is None or not ny["paa_lager"]:
            # Det rigtige alternativ er udsolgt → spørg hellere end at købe forkert.
            b["status"] = "usikker"
            b["begrundelse"] = f"AI: {alt['navn']} er rigtig, men udsolgt"
            rettet.append(
                {"navn": b["navn"], "fra": fra, "til": None, "grund": "rigtig vare udsolgt"}
            )
            continue
        gammel = (b.get("_traef") or {}).get(b["id"]) or {}
        if gammel.get("undergruppe") and gammel["undergruppe"] == ny.get("undergruppe"):
            # Samme blad i Nemligs varetræ = samme vareart (fx to rugbrød):
            # en smagssag, ikke en fejl. Målt 4/11: Haiku byttede rugbrød.
            continue
        _byt(b, ny, grund)
        b["alternativer"] = [a for a in b["alternativer"] if a["id"] != ny["id"]]
        rettet.append({"navn": b["navn"], "fra": fra, "til": ny["navn"], "grund": grund})
    return rettet


# =============================================================================
# Multikøb (2026-11-14)
# =============================================================================
# "2 for 206,95" sparer kun noget hvis man køber TO. Behovet er ofte én, og så
# betaler kassen normalpris. Er varen holdbar (`NA.lager_holdbar`: ≥ 14 dages
# salgsdato, aldrig "undgå madspild") og købt før, runder vi op til et helt
# sæt — den ekstra pakke venter til næste gang. Målt 14/11 over 649 holdbare
# oprundinger: oprundingen koster p50 28 kr / p90 67 kr / max 159 kr ekstra og
# sparer p50 20 % / p90 53 % på de ekstra stk. Rækkefølge: gratis oprundinger
# først (nogle sæt er billigere end færre stk), dernæst mest sparet pr. krone,
# inden for `max_kr` pr. kørsel.
def multikoeb_runding(beslutninger, mine, andres, politik):
    """→ {pid: {ekstra, i_alt, ekstra_kr, spar_kr, tekst}} for de id'er DENNE
    kilde runder op. `mine`/`andres` er stk pr. id før oprunding; summen er
    det kurven ellers ville få (andres egne oprundinger tæller med)."""
    if not politik:
        return {}
    bud = []
    for pid, egne in mine.items():
        b = next(
            (
                b
                for b in beslutninger
                if str(b.get("id")) == pid and b.get("status") == "ok" and b.get("kampagne")
            ),
            None,
        )
        if b is None:
            continue
        k, pris = b["kampagne"], float(b.get("pris") or 0)
        nu = egne + andres.get(pid, 0)
        r = NA.multikoeb(k, pris, nu)
        if r is None:
            continue
        nyt, ekstra_kr, spar_kr = r
        normal = (nyt - nu) * pris
        pct = 100 * spar_kr / normal if normal else 0
        gratis = ekstra_kr <= 0.005
        if not gratis and not (b.get("holdbar") and b.get("favorit") and pct >= politik["min_pct"]):
            continue
        bud.append(
            (
                gratis,
                spar_kr / max(ekstra_kr, 0.01),
                pid,
                {
                    "ekstra": nyt - nu,
                    "i_alt": nyt,
                    "ekstra_kr": ekstra_kr,
                    "spar_kr": spar_kr,
                    "tekst": k["tekst"],
                },
            )
        )
    ud, brugt = {}, 0.0
    for gratis, _ratio, pid, r in sorted(bud, key=lambda x: (not x[0], -x[1])):
        if not gratis and brugt + r["ekstra_kr"] > politik["max_kr"] + 0.005:
            log(f"multikøb over budget: {pid} ({r['tekst']}, +{NA.kr(r['ekstra_kr'])} kr)")
            continue
        brugt += max(r["ekstra_kr"], 0.0)
        ud[pid] = r
    return ud


# =============================================================================
# Kurven
# =============================================================================
def laeg_i_kurv(n, beslutninger, kilde=KILDE_LISTE, dry=False, multikoeb=None):
    """Sender ØNSKET SLUT-ANTAL pr. produkt (absolut → idempotent).

    Flere råvarer kan pege på samme produkt (fx to opskrifter der begge vil
    have citron); de lægges sammen FØR kaldet, ellers ville den anden
    overskrive den første med et lavere tal i stedet for at lægge til.

    2026-09-01 — TO KILDER I SAMME KURV. Basis-knappen og listen skriver til
    de samme produkt-id'er, og `quantity` er ABSOLUT (CLAUDE.md). Derfor må en
    kørsel ALDRIG sende sit eget tal alene: køber listen 1 smør og basiskurven
    1 smør, ville den sidste kørsel sætte linjen til 1 og tavst slette den
    anden. Vi sender summen over BEGGE kilder for hvert rørt id, og rydder kun
    de id'er DENNE kilde lagde sidst, som ingen kilde længere vil have.

    2026-11-14 — MULTIKØB. `multikoeb` = {max_kr, min_pct} (None = slået fra)
    runder et "X for Y" op til et helt sæt (`multikoeb_runding`). De ekstra stk
    står i regnskabslinjens `antal` (summen skal passe med kurven, ellers ligner
    næste kørsel en rettelse i hånden) og desuden i `ekstra`; beslutningen får
    `multikoeb` til rapporten og siden.
    """
    mine = {}
    for b in beslutninger:
        if b.get("status") != "ok":
            continue
        mine[str(b["id"])] = mine.get(str(b["id"]), 0) + b["antal"]

    tidligere = hent_koersel()
    andres = {}
    for l in tidligere:
        if (l.get("kilde") or KILDE_LISTE) == kilde:
            continue
        andres[str(l["id"])] = andres.get(str(l["id"]), 0) + int(l["antal"])

    # Hvad vi selv lagde i SIDST (begge kilder). Divergerer kurven fra dette
    # tal, er forskellen brugerens egen hånd på nemlig.com.
    lagde_sidst = {}
    for l in tidligere:
        lagde_sidst[str(l["id"])] = lagde_sidst.get(str(l["id"]), 0) + int(l["antal"])

    # BRUGERENS RETTELSER ER FACIT (user-spec 12/9). Den absolutte `quantity`
    # gør kørslen idempotent — men den gør også hvert tryk på en knap til en
    # gen-påtvingning af ALLE id'er i regnskabet, også dem brugeren lige har
    # slettet i hånden. Målt 12/9: et tryk på basis-knappen lagde hele
    # liste-kurven tilbage, fordi `andres` sendes med hver gang.
    # En tom kurv er IKKE en sletning — den er en afgivet ordre, og så skal
    # alt bygges op forfra.
    i_kurven, kurv_kendt, kurv_laest = {}, False, False
    if not dry:
        try:
            i_kurven = {l["id"]: int(l["antal"] or 0) for l in n.basket_linjer()}
            kurv_kendt = bool(i_kurven)
            kurv_laest = True
        except NA.NemligFejl as e:
            log(f"kunne ikke læse kurven ({e}) — skriver uden respekt-tjek")

    # DEN ANDEN KILDES VARER GENOPLIVES ALDRIG (B217, 11/10). `andres` er
    # regnskab fra den andens SIDSTE kørsel — og ligger varen ikke længere i
    # kurven, er den bestilt eller slettet. Målt 11/10: ordren var afgivet,
    # ny madplan 14:29, basis-knappen 14:31 → hele den GAMLE liste (31 varer)
    # lå i kurven igen, fordi hvert id i `andres` blev sendt med. Nu tæller den
    # anden kilde kun for id'er der stadig ligger i kurven, og dens forældede
    # linjer ryger ud af regnskabet (returneres som `foraeldet`).
    foraeldet = set()
    if kurv_laest:
        foraeldet = {pid for pid in andres if i_kurven.get(pid, 0) <= 0}
        andres = {pid: a for pid, a in andres.items() if pid not in foraeldet}

    def roert_i_haanden(pid):
        return (
            kurv_kendt and lagde_sidst.get(pid, 0) > 0 and i_kurven.get(pid, 0) != lagde_sidst[pid]
        )

    def glem_multikoeb(pid):
        for b in beslutninger:
            if str(b.get("id")) == pid:
                b.pop("multikoeb", None)

    runding = multikoeb_runding(beslutninger, mine, andres, multikoeb)
    for pid, r in runding.items():
        mine[pid] += r["ekstra"]
        b = next(b for b in beslutninger if str(b.get("id")) == pid and b.get("status") == "ok")
        b["multikoeb"] = r
    lagt = [
        {"id": pid, "antal": antal, "kilde": kilde}
        | ({"ekstra": runding[pid]["ekstra"]} if pid in runding else {})
        for pid, antal in mine.items()
    ]
    mine_gamle = {str(l["id"]) for l in tidligere if (l.get("kilde") or KILDE_LISTE) == kilde}
    if not dry:
        # Kun id'er DENNE kilde har en andel i — nu eller sidst. Et id kun den
        # anden kilde ejer, er dens sag; at sende det igen er B217.
        for pid in set(mine) | (mine_gamle & set(andres)):
            if roert_i_haanden(pid):
                # Behold FORRIGE regnskabslinje urørt: så består divergensen
                # mod kurven, og fredningen holder ved næste kørsel også.
                gammel = next(
                    (
                        l
                        for l in tidligere
                        if str(l["id"]) == pid and (l.get("kilde") or KILDE_LISTE) == kilde
                    ),
                    None,
                )
                lagt = [l for l in lagt if l["id"] != pid]
                glem_multikoeb(pid)
                if gammel:
                    lagt.append(
                        {"id": pid, "antal": int(gammel["antal"]), "kilde": kilde}
                        | ({"ekstra": int(gammel["ekstra"])} if gammel.get("ekstra") else {})
                    )
                log(
                    f"rettet i hånden ({i_kurven.get(pid, 0)} mod vores "
                    f"{lagde_sidst[pid]}) — fredet: {pid}"
                )
                continue
            try:
                n.add(pid, mine.get(pid, 0) + andres.get(pid, 0))
            except NA.NemligFejl as e:
                # Et udgået produkt-id må ikke vælte HELE kørslen: gør det det,
                # når vi aldrig ned til gem_koersel(), og regnskabet over hvad
                # vi selv lagde i kurven bliver aldrig skrevet.
                lagt = [l for l in lagt if l["id"] != pid]
                glem_multikoeb(pid)
                for b in beslutninger:
                    if str(b.get("id")) == pid and b.get("status") == "ok":
                        b["status"], b["grund"] = "fejl", str(e)
                log(f"kunne ikke lægge {pid} i kurven ({e})")

        # AFSTEM mod forrige kørsel. Den absolutte `quantity` gør gentagne
        # kørsler idempotente for varer der forbliver DE SAMME — men et match
        # kan ændre sig (favorit-fixet flyttede burgerboller fra «Kinesiske»
        # til «Brioche»), og så blev den gamle vare hængende i kurven for
        # evigt. Målt 2026-08-31: «Kinesiske burgerboller» overlevede tre
        # kørsler.
        #
        # Vi fjerner KUN id'er vi selv lagde i sidst og ikke længere vil have —
        # brugerens egne varer står aldrig i køerselsfilen og røres ikke.
        for pid in mine_gamle - set(mine) - set(andres):
            if roert_i_haanden(pid):
                log(f"rettet i hånden — fjerner IKKE {pid}")
                continue
            try:
                n.add(pid, 0)
                log(f"fjernet forældet valg ({kilde}): {pid}")
            except NA.NemligFejl as e:
                # Nemlig svarer «Product was not found» på id'er de har taget
                # ud af sortimentet. Et produkt der ikke findes, kan heller
                # ikke ligge i kurven, så fjernelsen er allerede opfyldt —
                # og fordi pid'et ryger ud af regnskabet med denne kørsel,
                # prøver vi ikke igen i morgen. Målt 12/9: to id'er blev
                # fjernet, det tredje kastede, og kørslen døde HER — så
                # sensoren hang på «kører …» og kurven blev aldrig afstemt.
                log(f"kunne ikke fjerne {pid} ({e}) — udgået vare, glemt")
    if foraeldet:
        log(
            f"{len(foraeldet)} af den anden kildes varer er ude af kurven "
            f"(bestilt/slettet) — glemt, ikke sendt igen"
        )
    return lagt, foraeldet


def gem_koersel(lagt, kilde=KILDE_LISTE, foraeldet=()):
    """Skriv DENNE kildes linjer; de andres bevares. `kilde=None` = erstat alt.

    `foraeldet`: de andres id'er der ikke længere ligger i kurven (B217) —
    bestilt eller slettet, så de skal ikke stå i regnskabet og blive sendt igen.
    """
    beholdt = (
        []
        if kilde is None
        else [
            l
            for l in hent_koersel()
            if (l.get("kilde") or KILDE_LISTE) != kilde and str(l["id"]) not in foraeldet
        ]
    )
    tmp = f"{KOERSEL_FIL}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"tid": time.time(), "linjer": beholdt + lagt}, f)
    os.replace(tmp, KOERSEL_FIL)


# Sensor-attributterne er ~23 KB (52 varer, 14/11) — over recorderens 16 KB, så
# kun det siden viser skrives ud: kampagnen som tekst, holdbar/favorit (multi-
# købets interne krav) og et 0-spar udelades.
SENSOR_UDEN = ("alternativer", "kampagne", "holdbar", "favorit", "koster")


def til_sensor(b):
    v = {k: x for k, x in b.items() if k not in SENSOR_UDEN}
    if b.get("kampagne"):
        v["tilbud_tekst"] = b["kampagne"]["tekst"]
    if not v.get("spar_kr"):
        v.pop("spar_kr", None)
    return v


def gem_sensor(state, attrs):
    tmp = f"{SENSOR_FIL}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"state": state, "attrs": attrs}, f, ensure_ascii=False)
    os.replace(tmp, SENSOR_FIL)


def laes_sensor():
    try:
        with open(SENSOR_FIL, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError, json.JSONDecodeError, OSError:
        return {}


def varer_fra_andre_kilder(kilde, foraeldet=()):
    """Sidste kørsels varer fra de ANDRE kilder.

    Uden dette ville et tryk på "Tilføj basisvarer" tømme opskrift-varerne af
    siden (og omvendt), selv om de stadig ligger i kurven — sensoren er det
    eneste sted brugeren kan SE hvad der blev lagt i.
    """
    d = laes_sensor()
    ude = (d.get("attrs") or {}).get("varer") or []
    return [
        v
        for v in ude
        if (v.get("kilde") or KILDE_LISTE) != kilde and str(v.get("id")) not in foraeldet
    ]


def republish(token):
    """Gen-publicér sensoren fra sidste kørsel. Rører ikke Nemlig."""
    try:
        with open(SENSOR_FIL, encoding="utf-8") as f:
            d = json.load(f)
    except FileNotFoundError, json.JSONDecodeError, OSError:
        # Endnu ingen kørsel: publicér en ærlig tom sensor, så tilen og
        # ref-valideringen har noget at pege på.
        d = {
            "state": "ingen kørsel endnu",
            "attrs": {
                "friendly_name": "Nemlig — kurv",
                "icon": "mdi:cart-arrow-down",
                "varer": [],
                "tekst": "Kurven er ikke bygget endnu.",
            },
        }
    MP.publish_sensor(token, "sensor.nemlig_kurv", d["state"], d["attrs"])
    return d["state"]


def toem_sensor(token, state, tekst):
    """Sensoren efter en rydning (B221). Uden den viste Mad-siden stadig
    sidste kørsels 35 produkter i en tom kurv — og `varer_fra_andre_kilder`
    læser netop de varer, så næste "Tilføj basisvarer" ville vise den gamle
    indkøbsliste ved siden af basisvarerne igen (B217-symptomet)."""
    attrs = dict(
        (laes_sensor().get("attrs") or {}),
        varer=[],
        retter=[],
        total=0,
        basis_antal=0,
        ekstra_antal=0,
        tilbud_antal=0,
        liste_antal=0,
        regnskab={},
        tekst=tekst,
    )
    attrs.setdefault("friendly_name", "Nemlig — kurv")
    attrs.setdefault("icon", "mdi:cart-arrow-down")
    gem_sensor(state, attrs)
    MP.publish_sensor(token, "sensor.nemlig_kurv", state, attrs)


def hent_koersel():
    try:
        with open(KOERSEL_FIL, encoding="utf-8") as f:
            return json.load(f).get("linjer") or []
    except FileNotFoundError, json.JSONDecodeError, OSError:
        return []


def ryd_vores(n, dry=False):
    """Fjern kun det vi selv lagde i. Brugerens egne varer bliver stående."""
    lagt = hent_koersel()
    i_kurv = {l["id"] for l in n.basket_linjer()}
    fjernet = []
    for l in lagt:
        if l["id"] not in i_kurv:
            continue  # allerede væk (brugeren, eller en tidligere rydning)
        if not dry:
            n.add(l["id"], 0)  # 0 = fjern linjen
        fjernet.append(l["id"])
    if not dry:
        gem_koersel([], kilde=None)  # begge kilder — knappen hedder "vores varer"
    return fjernet


# =============================================================================
# Spørgsmål (fase 3)
# =============================================================================
def hent_spoerg():
    try:
        with open(SPOERG_FIL, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError, json.JSONDecodeError, OSError:
        return {"naeste": 1, "aabne": {}}


def gem_spoerg(d):
    tmp = f"{SPOERG_FIL}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, SPOERG_FIL)


def spring_over_aktiv(post):
    """Er varen sprunget over, og gælder det stadig?

    Et udløbet spring-over er ikke et spring-over: matcheren kan være blevet
    bedre siden, og så fortjener varen et nyt forsøg.
    """
    if not post or not post.get("spring_over"):
        return False
    til = post.get("spring_over_til")
    if not til:
        return False  # gammelt format uden udløb -> genoptag
    try:
        return MP.now_local() < MP.parse_dato(til)
    except Exception:
        return False


def kandidater_for(b):
    """Produkterne der skal blive til knapper — kun dem der er PÅ LAGER.

    For en udsolgt vare er hele pointen at finde noget man kan FÅ, og for en
    usikker parring ville et udsolgt forslag være et blindt spor.
    """
    raekke = [
        {
            "id": b.get("id"),
            "navn": b.get("produkt"),
            "pris": b.get("pris"),
            "lager": b["status"] != "udsolgt",
            "pakning": b.get("pakke"),
            "score": b.get("score", 0),
            "kategori": b.get("kategori"),
        }
    ] + (b.get("alternativer") or [])
    # Et forslag under FORSLAG_MIN_SCORE er værre end ingen: fallback-søgningen
    # kan finde rent skrald ("brystflæsk" -> "Brystkarameller"), og en knap med
    # den slags inviterer til et forkert tryk.
    return [
        k
        for k in raekke
        if k.get("id")
        and k.get("lager")
        and (
            k.get("score") is None
            or NA.relevant_nok(b["navn"], k.get("navn") or "", k.get("kategori"))
        )
    ][:KNAP_KANDIDATER]


def stil_spoergsmaal(token, beslutninger, maks, dry=False):
    """Ét spørgsmål pr. uafklaret vare, med produkterne som knapper."""
    st = hent_spoerg()
    aabne = st.setdefault("aabne", {})
    # Varer der allerede har et åbent spørgsmål: spørg ikke igen. Ellers ville
    # hver kørsel lægge en ny notifikation oveni en ubesvaret.
    kendte = {q["navn"] for q in aabne.values()}
    varer_cache = NA.hent_varer()
    sendt = 0
    for b in beslutninger:
        if sendt >= maks:
            break
        if b["status"] not in ("udsolgt", "usikker", "ingen_traef"):
            continue
        if b["navn"] in kendte:
            continue
        if spring_over_aktiv(varer_cache.get(NA.normaliser(b["navn"]))):
            continue
        valg = kandidater_for(b)
        if not valg:
            continue  # intet på lager at foreslå — ren info
        aid = "q%d" % st.get("naeste", 1)
        st["naeste"] = st.get("naeste", 1) + 1
        aabne[aid] = {
            "navn": b["navn"],
            "maengde": b["maengde"],
            "enhed": b["enhed"],
            "familie": b["familie"],
            "status": b["status"],
            "valg": valg,
            "tid": time.time(),
        }
        hvorfor = (
            "udsolgt"
            if b["status"] == "udsolgt"
            else "usikker parring (score %s)" % b.get("score", 0)
        )
        behov = MP.formatér_maengde(b["maengde"], b["familie"], b["enhed"])
        # Beskeden bærer valgmulighederne i fuld længde og nummereret;
        # knapperne bærer kun cifferet.
        linjer = ["%s %s" % (behov, b["navn"]), "(%s)" % hvorfor, ""]
        for i, k in enumerate(valg, 1):
            pak = (" · %s" % k["pakning"]) if k.get("pakning") else ""
            linjer.append("%d)  %s — %s kr%s" % (i, k["navn"], k["pris"], pak))
        linjer += [
            "",
            "Tryk på nummeret — så husker jeg det.",
            "Passer ingen af dem: tryk «Ingen af dem».",
        ]
        actions = [
            {"action": "NEMLIG_%s_%d" % (aid, i), "title": str(i + 1)} for i in range(len(valg))
        ]
        actions.append({"action": "NEMLIG_%s_SKIP" % aid, "title": "Ingen af dem"})
        MP.push_notify(
            token,
            NID,
            "🛒 Hvilken vare mente du?",
            NL.join(linjer),
            payload={"tag": "nemlig_%s" % aid, "actions": actions},
            dry=dry,
        )
        sendt += 1
    if not dry:
        gem_spoerg(st)
    return sendt


def besvar(token, action):
    """action = NEMLIG_<ask_id>_<index|SKIP>. Kaldes af action-handleren.

    Skriver parringen til `.nemlig_varer.json`, så varen aldrig spørges om
    igen — næste kørsel bruger id'et direkte og springer score-tærsklen over.
    """
    dele = action.split("_")
    if len(dele) != 3 or dele[0] != "NEMLIG":
        raise SystemExit("ugyldig action: %s" % action)
    aid, valg = dele[1], dele[2]
    st = hent_spoerg()
    q = (st.get("aabne") or {}).get(aid)
    if not q:
        # Dobbelt-tryk, eller en gammel notifikation der stadig lå på skærmen.
        # Ikke en fejl — men vi må ikke skrive en parring vi ikke kan slå op.
        log("%s er ikke et åbent spørgsmål (allerede besvaret?)" % aid)
        return {"ok": True, "kendt": False}

    varer = NA.hent_varer()
    noegle = NA.normaliser(q["navn"])
    if valg == "SKIP":
        til = MP.now_local() + timedelta(days=SPRING_OVER_DAGE)
        varer[noegle] = {
            "spring_over": True,
            "navn": q["navn"],
            "spring_over_til": til.isoformat(timespec="seconds"),
            "dato": MP.now_local().isoformat(timespec="seconds"),
        }
        NA.gem_varer(varer)
        st["aabne"].pop(aid, None)
        gem_spoerg(st)
        MP.push_notify(
            token,
            NID,
            "🛒 Sprunget over",
            "«%s» springes over i %d dage.%sFortryd ved at slette "
            "linjen i .nemlig_varer.json." % (q["navn"], SPRING_OVER_DAGE, NL),
        )
        return {"ok": True, "valg": "skip"}

    try:
        k = q["valg"][int(valg)]
    except ValueError, IndexError:
        raise SystemExit("ugyldigt valg: %s" % valg) from None

    varer[noegle] = {
        "id": k["id"],
        "navn": k["navn"],
        "soegeord": q["navn"],
        "dato": MP.now_local().isoformat(timespec="seconds"),
    }
    NA.gem_varer(varer)
    st["aabne"].pop(aid, None)
    gem_spoerg(st)

    # Læg den i kurven med det samme — svaret ER intentionen. Antallet
    # genberegnes mod det VALGTE produkts pakning, ikke mod det vi gættede på:
    # brugeren kan have valgt en 400 g-pakke hvor gættet var 1 kg.
    lagt = ""
    states = MP.ha_get_states(token)
    if MP.is_on(states, E_AUTO, default=False):
        try:
            n = NA.Nemlig()
            traef = NA.find_bedste(n.search(k["navn"], 8), k["navn"])
            p = next((t for t in traef if t["id"] == k["id"]), None)
            antal = (
                NA.antal_pakker(q["maengde"], q["enhed"], p["_raw"], navn=q["navn"])[0] if p else 1
            )
            # `quantity` er ABSOLUT. Ligger produktet allerede i kurven — fordi
            # en anden råvare pegede på det, eller brugeren selv lagde det i —
            # ville et bart `add(id, antal)` SÆTTE antallet ned i stedet for at
            # lægge til. Samme invariant som laeg_i_kurv beskytter.
            i_kurv = (
                next((l["antal"] for l in n.basket_linjer() if l["id"] == str(k["id"])), 0) or 0
            )
            antal_total = int(i_kurv) + antal
            n.add(k["id"], antal_total)
            # Køerselsfilen holder ØNSKET slut-antal pr. produkt, ikke en
            # historik — ellers ville --ryd-vores tælle samme id to gange.
            koersel = [l for l in hent_koersel() if l["id"] != str(k["id"])]
            koersel.append({"id": str(k["id"]), "antal": antal_total})
            gem_koersel(koersel)
            lagt = "%sLagt i kurven: %d stk." % (NL, antal)
        except NA.NemligFejl as e:
            lagt = "%sKunne ikke lægge i kurven: %s" % (NL, e)
    MP.push_notify(token, NID, "🛒 Husket", "«%s» → %s%s" % (q["navn"], k["navn"], lagt))
    return {"ok": True, "valg": k["navn"]}


# =============================================================================
# Tilbuds-kilden (--tilbud)
# =============================================================================
def tilbud_beslutninger(n, budget_kr, min_pct, i_kurven=None, egne_sidst=None):
    """→ (beslutninger, over_budget) for ugens tilbud på de FASTE varer.

    Kun varer vi har købt i ≥ `NA.FASTE_MIN_GANGE` af de seneste ordrer, som
    kan holde sig til næste indkøb, er på lager og har mindst `min_pct` rabat.
    En vare der allerede ligger i kurven fra en anden kilde (eller brugerens
    egen hånd) springes over — dens tilbud er allerede i spil. Budgettet
    fyldes med mest sparet pr. krone først (grådig rygsæk)."""
    i_kurven, egne_sidst = i_kurven or {}, egne_sidst or {}
    faste = NA.faste_varer(n)
    kandidater, set_ = [], set()
    for p in n.tilbud(kun_favoritter=True, soeg=NA.faste_soegeord(faste)):
        pid = str(p.get("Id"))
        if pid in set_:  # tilbud() deduperer allerede; værn mod kilder der ikke gør
            continue
        set_.add(pid)
        f = faste.get(pid)
        k = NA.kampagne(p)
        if not f or f.get("gange", 0) < NA.FASTE_MIN_GANGE or not k or k["madspild"]:
            continue
        if k["rabat_pct"] < min_pct or not NA.lager_holdbar(p):
            continue
        if not (p.get("Availability") or {}).get("IsAvailableInStock"):
            continue
        if i_kurven.get(pid, 0) - egne_sidst.get(pid, 0) > 0:
            continue
        m = k["min_antal"]
        typisk = max(1, round(f.get("stk", 1) / max(1, f["gange"])))
        antal = max(1, round(typisk / m)) * m
        if k["max_antal"]:
            antal = min(antal, k["max_antal"] // m * m)
        pris = float(p.get("Price") or 0)
        koster = NA.pris_for(k, pris, antal)
        spar = round(antal * pris - koster, 2)
        if antal < 1 or spar <= 0.005:
            continue
        pm, pe = NA.pakning(p)
        kandidater.append(
            {
                "navn": f.get("navn") or p.get("Name"),
                "maengde": antal,
                "enhed": "stk",
                "produkt": p.get("Name"),
                "id": pid,
                "antal": antal,
                "pakke": f"{pm:g}{pe}" if pm else None,
                "hvorfor": f"købt {f['gange']} gange, typisk {typisk} stk",
                "pris": p.get("Price"),
                "laert": False,
                "oeko": NA.er_oeko(p),
                "tilbud": True,
                "kategori": p.get("ProductCategoryGroupName") or "",
                "begrundelse": "tilbud på fast vare",
                "kampagne": k,
                "spar_kr": spar,
                "holdbar": True,
                "favorit": True,
                "koster": koster,
                "status": "ok",
            }
        )
    kandidater.sort(key=lambda c: -c["spar_kr"] / max(c["koster"], 0.01))
    valgt, over, brugt = [], [], 0.0
    for c in kandidater:
        if brugt + c["koster"] > budget_kr + 0.005:
            over.append(c)
            continue
        brugt += c["koster"]
        valgt.append(c)
    return valgt, over


# =============================================================================
# Rapport
# =============================================================================
def regnskab(beslutninger):
    """→ dict med øko-/tilbuds-opgørelsen for de varer der kom i kurven.

    `spar_kr` er Nemligs EGEN rabat på det vi køber — normalpris minus
    kampagnepris (`tilbudsfelter`) plus det multikøbenes oprunding sparer på de
    ekstra stk. `besparelse_est` er noget andet: forskellen mod det alternativ
    matcheren valgte FRA (begge med kampagnepris siden 14/11).
    """
    ok = [b for b in beslutninger if b["status"] == "ok"]
    multi = [b["multikoeb"] for b in ok if b.get("multikoeb")]
    return {
        "varer": len(ok),
        "oeko_antal": sum(1 for b in ok if b.get("oeko")),
        "tilbud_antal": sum(1 for b in ok if b.get("tilbud")),
        "merpris_oeko": round(sum(b.get("merpris_oeko") or 0 for b in ok), 2),
        "besparelse_est": round(sum(b.get("besparelse_est") or 0 for b in ok), 2),
        "spar_kr": round(
            sum(b.get("spar_kr") or 0 for b in ok) + sum(m["spar_kr"] for m in multi), 2
        ),
        "multikoeb_antal": len(multi),
        "multikoeb_kr": round(sum(m["ekstra_kr"] for m in multi), 2),
    }


def rapport(
    beslutninger, lagt, kurv_total, retter, tørkørsel, kilde=KILDE_LISTE, ai_rettet=(), titel=""
):
    udsolgt = [b for b in beslutninger if b["status"] == "udsolgt"]
    usikre = [b for b in beslutninger if b["status"] in ("usikker", "ingen_traef", "fejl")]

    hoved = "🛒 Tørkørsel — intet lagt i kurven" if tørkørsel else "🛒 Lagt i Nemlig-kurven"
    if kilde == KILDE_BASIS:
        hoved = (
            "🧺 Tørkørsel (basisvarer) — intet lagt i kurven"
            if tørkørsel
            else "🧺 Basisvarer lagt i Nemlig-kurven"
        )
    omfang = (
        f"basiskurv · {len(beslutninger)} varer"
        if kilde == KILDE_BASIS
        else f"{len(retter)} retter · {len(beslutninger)} varer"
    )
    if kilde == KILDE_EKSTRA:
        hoved = (
            f"🥤 Tørkørsel ({titel}) — intet lagt i kurven"
            if tørkørsel
            else f"🥤 {titel} lagt i Nemlig-kurven"
        )
        omfang = f"{len(beslutninger)} varer"
    if kilde == KILDE_TILBUD:
        hoved = (
            "🏷️ Tørkørsel (tilbud) — intet lagt i kurven"
            if tørkørsel
            else "🏷️ Tilbud lagt i Nemlig-kurven"
        )
        omfang = f"{len(beslutninger)} tilbud på faste varer"
    linjer = [f"{hoved}", f"{omfang} · {len(lagt)} produkter"]
    if kurv_total is not None:
        linjer.append(
            f"Kurv i alt: {kurv_total:.0f} kr"
            + ("  ⚠️ under min-ordre 500 kr" if kurv_total < 500 else "")
        )
    r = regnskab(beslutninger)
    if r["varer"]:
        linjer.append(
            f"🌱 øko: {r['oeko_antal']}/{r['varer']}"
            + (f" (+{r['merpris_oeko']:.0f} kr)" if r["merpris_oeko"] else "")
            + f"  ·  🏷️ tilbud: {r['tilbud_antal']}/{r['varer']}"
            + (f" · spar {r['spar_kr']:.0f} kr" if r["spar_kr"] >= 0.5 else "")
        )
    if kilde == KILDE_TILBUD:
        linjer.append("")
        linjer += [
            f"• {b['produkt']} ×{b['antal']} — {b['kampagne']['tekst']}"
            f" · spar {NA.kr(b['spar_kr'])} kr"
            for b in beslutninger
            if b["status"] == "ok"
        ]
    multi = [b for b in beslutninger if b["status"] == "ok" and b.get("multikoeb")]
    if multi:
        linjer.append("\n📦 MULTIKØB (rundet op til et helt tilbud):")
        for b in multi:
            m = b["multikoeb"]
            linjer.append(
                f"• {b['produkt']}: {m['i_alt'] - m['ekstra']} → {m['i_alt']} ({m['tekst']})"
                f" · +{NA.kr(m['ekstra_kr'])} kr · spar {NA.kr(m['spar_kr'])} kr"
            )
    if ai_rettet:
        linjer.append("\n🤖 AI RETTEDE:")
        linjer += [
            f"• {r['navn']}: «{r['fra']}» → " + (f"«{r['til']}»" if r["til"] else "spørger dig")
            for r in ai_rettet
        ]
    if udsolgt:
        linjer.append("\n❌ UDSOLGT (ikke lagt i):")
        linjer += [f"• {b['navn']} — {b.get('produkt', '?')}" for b in udsolgt]
    if usikre:
        linjer.append("\n❓ USIKKER PARRING (ikke lagt i):")
        for b in usikre:
            if b["status"] == "usikker":
                linjer.append(f"• {b['navn']} → bedste bud «{b['produkt']}» (score {b['score']})")
            elif b["status"] == "ingen_traef":
                linjer.append(f"• {b['navn']} — INGEN produkter fundet, søg selv i appen")
            else:
                linjer.append(f"• {b['navn']} — {b['status']}")
    return "\n".join(linjer)


# =============================================================================
# Hoved
# =============================================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kurv", action="store_true")
    ap.add_argument(
        "--basis", action="store_true", help="læg den faste basiskurv i (i stedet for listen)"
    )
    ap.add_argument("--vis", action="store_true", help="parr og vis, skriv intet")
    ap.add_argument("--ryd-vores", action="store_true")
    ap.add_argument(
        "--toem-alt", action="store_true", help="tøm HELE kurven, også brugerens egne varer"
    )
    ap.add_argument(
        "--republish", action="store_true", help="gen-publicér sensoren fra sidste kørsel"
    )
    ap.add_argument(
        "--svar", metavar="ACTION", help="besvar et parrings-spørgsmål (NEMLIG_<id>_<valg>)"
    )
    ap.add_argument("--ekstra", action="store_true", help=f"læg listen i {EKSTRA_FIL} i kurven")
    ap.add_argument(
        "--tilbud", action="store_true", help="læg ugens tilbud på de faste varer i kurven"
    )
    ap.add_argument("--force", action="store_true", help="ignorér kill-switch")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--uden-ai", action="store_true", help="spring AI-tjekket over")
    a = ap.parse_args()

    token = ha_secrets.get(ha_secrets.HA_API_TOKEN)
    states = MP.ha_get_states(token)

    if a.svar:
        print(json.dumps(besvar(token, a.svar), ensure_ascii=False))
        return 0

    if a.republish:
        print(json.dumps({"ok": True, "state": republish(token)}, ensure_ascii=False))
        return 0

    if a.ryd_vores:
        n = NA.Nemlig(dry=a.dry)
        fjernet = ryd_vores(n, a.dry)
        if not a.dry:
            rest = len(n.basket_linjer())
            toem_sensor(
                token,
                f"vores varer fjernet · {rest} tilbage",
                f"🧹 {len(fjernet)} af vores varer fjernet — {rest} linjer tilbage i kurven.",
            )
        print(json.dumps({"ok": True, "fjernet": len(fjernet), "ids": fjernet}))
        return 0

    if a.toem_alt:
        n = NA.Nemlig(dry=a.dry)
        fjernet = n.ryd_kurv()
        if not a.dry:
            gem_koersel([], kilde=None)
            toem_sensor(token, "kurven er tom", "🧹 Kurven er tømt.")
        print(json.dumps({"ok": True, "fjernet": fjernet}))
        return 0

    # B215: kill-switchen (input_boolean.nemlig_kurv_enabled) er fjernet — kun
    # knapperne bygger kurven, og de sender --force (knappen ER intentionen).
    if not (a.force or a.vis):
        log("hverken --force eller --vis — springer over")
        print(json.dumps({"ok": True, "sprunget": "ingen --force"}))
        return 0

    # Tørkørsel er en EGEN switch: man skal kunne se hvad kurven VILLE blive,
    # uden at røre kontoen. --vis og --dry tvinger den også.
    tørkørsel = a.vis or a.dry or not MP.is_on(states, E_AUTO, default=False)
    min_score = MP.num(states, E_SCORE, NA.SIKKER_SCORE)

    kilde = (
        KILDE_TILBUD
        if a.tilbud
        else KILDE_EKSTRA
        if a.ekstra
        else KILDE_BASIS
        if a.basis
        else KILDE_LISTE
    )
    ekstra_titel = "Ekstra varer"
    if a.tilbud:
        return koer_tilbud(token, states, tørkørsel, a.json, vis=a.vis)
    if a.ekstra:
        try:
            with open(EKSTRA_FIL, encoding="utf-8") as f:
                ekstra = json.load(f)
            ekstra_titel = str(ekstra.get("titel") or ekstra_titel)[:60]
            poster = [
                {"navn": str(p["navn"]), "maengde": float(p["maengde"]), "enhed": str(p["enhed"])}
                for p in ekstra["poster"]
            ]
        except (OSError, ValueError, KeyError, TypeError) as e:
            log(f"--ekstra: kan ikke læse {EKSTRA_FIL}: {e}")
            print(json.dumps({"ok": False, "fejl": "ingen ekstra-liste"}))
            return 1
        retter = (laes_sensor().get("attrs") or {}).get("retter") or []
    elif a.basis:
        # Den faste liste er DATA, ikke en indkøbsliste — den skal ikke hentes
        # fra arket og skal ikke kunne blive tom fordi ingen har valgt retter.
        poster = [dict(b) for b in BASISKURV]
        retter = (laes_sensor().get("attrs") or {}).get("retter") or []
    else:
        poster, retter = aktuel_liste(states)
    if poster:
        # Knappen skal kvittere med det samme. Uden dette ser en detached
        # kørsel ud som om intet skete i halvandet minut, og brugeren trykker
        # igen — hvilket er præcis hvad der skete første gang.
        MP.publish_sensor(
            token,
            "sensor.nemlig_kurv",
            (
                "kører … %d basisvarer"
                if a.basis
                else "kører … %d ekstra varer"
                if a.ekstra
                else "kører … %d varer"
            )
            % len(poster),
            {
                "friendly_name": "Nemlig — kurv",
                "icon": "mdi:progress-clock",
                "retter": retter,
                "koerer": True,
            },
            dry=False,
        )
    if not poster:
        log("ingen aktuel indkøbsliste")
        print(json.dumps({"ok": False, "fejl": "ingen aktuel indkøbsliste"}))
        return 1

    n = NA.Nemlig(dry=tørkørsel)
    oeko_loft = (
        MP.num(states, E_OEKO_LOFT, 100.0) if MP.is_on(states, E_OEKO, default=False) else None
    )
    beslutninger = parr(
        n,
        poster,
        min_score,
        NA.hent_varer(),
        oeko_loft,
        MP.is_on(states, E_TILBUD, default=True),
        MP.num(states, E_FAV_LOFT, NA.FAVORIT_LOFT_PCT),
    )
    ai_rettet = [] if a.uden_ai else ai_tjek(beslutninger)
    for b in beslutninger:
        b.pop("_traef", None)
    # Kilden følger varen HELE vejen — ind i kurv-afstemningen og ud i
    # sensoren, hvor siden viser de to grupper hver for sig.
    for b in beslutninger:
        b["kilde"] = kilde
    lagt, foraeldet = laeg_i_kurv(
        n, beslutninger, kilde, dry=tørkørsel, multikoeb=multikoeb_politik(states)
    )
    if not tørkørsel:
        gem_koersel(lagt, kilde, foraeldet)
    andre = varer_fra_andre_kilder(kilde, foraeldet)
    if (a.basis or a.ekstra) and not any(
        v.get("status") == "ok" and (v.get("kilde") or KILDE_LISTE) == KILDE_LISTE for v in andre
    ):
        retter = []  # listen er ude af kurven — vis ikke dens retter (B217)

    total = None
    try:
        total = n.basket().get("TotalPrice")
    except NA.NemligFejl:
        pass

    # Spørgsmålene stilles KUN når kørslen var ægte: en tørkørsel skal kunne
    # læses igennem uden at fylde telefonen med knapper der peger på en kurv
    # vi ikke rørte.
    spurgt = 0
    if not tørkørsel:
        spurgt = stil_spoergsmaal(token, beslutninger, int(MP.num(states, E_SPOERG_MAX, 8)))

    besked = rapport(beslutninger, lagt, total, retter, tørkørsel, kilde, ai_rettet, ekstra_titel)
    # Sensoren viser BEGGE kilder: denne kørsels varer + hvad den anden knap
    # lagde i sidst. Ellers ville et tryk på den ene knap tømme den anden
    # gruppe af siden, selv om varerne stadig ligger i kurven. Gælder også en
    # tørkørsel — den anden gruppe er fra en ÆGTE kørsel og ligger der stadig.
    varer = [til_sensor(b) for b in beslutninger] + andre
    sensor_state = (
        f"{len(lagt)} produkter · "
        f"{len([b for b in beslutninger if b['status'] != 'ok'])} til afklaring"
    )
    sensor_attrs = sensor_attributter(
        retter, total, tørkørsel, kilde, varer, spurgt, ai_rettet, besked
    )
    MP.publish_sensor(token, "sensor.nemlig_kurv", sensor_state, sensor_attrs)
    gem_sensor(sensor_state, sensor_attrs)

    if a.json:
        print(
            json.dumps(
                {"ok": True, "toerkoersel": tørkørsel, "lagt": lagt, "beslutninger": beslutninger},
                ensure_ascii=False,
                indent=1,
            )
        )
    else:
        print(besked)
    return 0


def multikoeb_politik(states):
    """{max_kr, min_pct} fra skyderne, eller None når multikøb er slået fra."""
    if not MP.is_on(states, E_MULTI, default=True):
        return None
    return {
        "max_kr": MP.num(states, E_MULTI_MAX, 200.0),
        "min_pct": MP.num(states, E_TILBUD_MIN, 15.0),
    }


def sensor_attributter(retter, total, tørkørsel, kilde, varer, spurgt, ai_rettet, besked):
    def antal(k):
        return len(
            [v for v in varer if (v.get("kilde") or KILDE_LISTE) == k and v.get("status") == "ok"]
        )

    return {
        "friendly_name": "Nemlig — kurv",
        "icon": "mdi:cart-arrow-down",
        "retter": retter,
        "total": total,
        "toerkoersel": tørkørsel,
        "kilde": kilde,
        "varer": varer,
        "basis_antal": antal(KILDE_BASIS),
        "ekstra_antal": antal(KILDE_EKSTRA),
        "tilbud_antal": antal(KILDE_TILBUD),
        "liste_antal": antal(KILDE_LISTE),
        "spurgt": spurgt,
        "ai_rettet": ai_rettet,
        "regnskab": regnskab(varer),
        "aabne_spoergsmaal": len(hent_spoerg().get("aabne") or {}),
        "tekst": besked,
    }


def koer_tilbud(token, states, tørkørsel, som_json=False, vis=False):
    """--tilbud: ugens tilbud på de faste varer i kurven, inden for budget.

    `vis` = kun vis: hverken kurv, regnskab eller sensor røres.
    """
    n = NA.Nemlig(dry=tørkørsel)
    retter = (laes_sensor().get("attrs") or {}).get("retter") or []
    if not vis:
        MP.publish_sensor(
            token,
            "sensor.nemlig_kurv",
            "kører … tilbud",
            {"friendly_name": "Nemlig — kurv", "icon": "mdi:progress-clock", "koerer": True},
            dry=False,
        )
    try:
        i_kurven = {l["id"]: int(l["antal"] or 0) for l in n.basket_linjer()}
    except NA.NemligFejl as e:
        log(f"kunne ikke læse kurven ({e})")
        i_kurven = {}
    egne_sidst = {}
    for l in hent_koersel():
        if l.get("kilde") == KILDE_TILBUD:
            egne_sidst[str(l["id"])] = egne_sidst.get(str(l["id"]), 0) + int(l["antal"])
    try:
        beslutninger, over = tilbud_beslutninger(
            n,
            MP.num(states, E_TILBUD_BUDGET, 300.0),
            MP.num(states, E_TILBUD_MIN, 15.0),
            i_kurven,
            egne_sidst,
        )
    except NA.NemligFejl as e:
        log(f"tilbuddene kunne ikke hentes: {e}")
        if not vis:
            republish(token)
        print(json.dumps({"ok": False, "fejl": str(e)}, ensure_ascii=False))
        return 1
    for b in beslutninger:
        b["kilde"] = KILDE_TILBUD
    lagt, foraeldet = laeg_i_kurv(n, beslutninger, KILDE_TILBUD, dry=tørkørsel)
    if not tørkørsel:
        gem_koersel(lagt, KILDE_TILBUD, foraeldet)
    andre = varer_fra_andre_kilder(KILDE_TILBUD, foraeldet)
    if not any(
        v.get("status") == "ok" and (v.get("kilde") or KILDE_LISTE) == KILDE_LISTE for v in andre
    ):
        retter = []
    total = None
    try:
        total = n.basket().get("TotalPrice")
    except NA.NemligFejl:
        pass
    besked = rapport(beslutninger, lagt, total, retter, tørkørsel, KILDE_TILBUD)
    if over:
        besked += "\n\n💸 Over budget (ikke lagt i): " + ", ".join(
            f"{c['produkt']} ({c['kampagne']['tekst']})" for c in over[:8]
        )
    varer = [til_sensor(b) for b in beslutninger] + andre
    state = (
        f"{len(lagt)} tilbud lagt i" if not tørkørsel else f"{len(beslutninger)} tilbud (tørkørsel)"
    )
    attrs = sensor_attributter(retter, total, tørkørsel, KILDE_TILBUD, varer, 0, [], besked)
    if not vis:
        MP.publish_sensor(token, "sensor.nemlig_kurv", state, attrs)
        gem_sensor(state, attrs)
    if som_json:
        print(
            json.dumps(
                {"ok": True, "toerkoersel": tørkørsel, "lagt": lagt, "beslutninger": beslutninger},
                ensure_ascii=False,
                indent=1,
            )
        )
    else:
        print(besked)
    return 0


if __name__ == "__main__":
    sys.exit(main())
