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
import sys
import time
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ha_secrets  # noqa: E402  (sti skal sættes først)
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
        # Merprisen for øko og besparelsen på tilbud regnes mod den billigste
        # SAMMENLIGNELIGE konventionelle vare i samme match-felt. Det er ikke
        # Nemligs "før-pris" — den findes ikke i deres API (Campaign og
        # CampaignAttribute er null overalt, målt 2026-08-31). Det er
        # forskellen mod det alternativ vi faktisk valgte fra.
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
# Kurven
# =============================================================================
def laeg_i_kurv(n, beslutninger, kilde=KILDE_LISTE, dry=False):
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

    lagt = [{"id": pid, "antal": antal, "kilde": kilde} for pid, antal in mine.items()]
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
                if gammel:
                    lagt.append({"id": pid, "antal": int(gammel["antal"]), "kilde": kilde})
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
# Rapport
# =============================================================================
def regnskab(beslutninger):
    """→ dict med øko-/tilbuds-opgørelsen for de varer der kom i kurven.

    ⚠️ `besparelse_est` er IKKE Nemligs rabat. Deres API har ingen før-pris
    (Campaign/CampaignAttribute er null overalt, målt 2026-08-31), så en ægte
    "spar X kr"-opgørelse kan ikke laves. Det her er forskellen mod det
    alternativ vi valgte FRA — hvilket er det tal der faktisk siger noget om
    vores eget valg.
    """
    ok = [b for b in beslutninger if b["status"] == "ok"]
    return {
        "varer": len(ok),
        "oeko_antal": sum(1 for b in ok if b.get("oeko")),
        "tilbud_antal": sum(1 for b in ok if b.get("tilbud")),
        "merpris_oeko": round(sum(b.get("merpris_oeko") or 0 for b in ok), 2),
        "besparelse_est": round(sum(b.get("besparelse_est") or 0 for b in ok), 2),
    }


def rapport(beslutninger, lagt, kurv_total, retter, tørkørsel, kilde=KILDE_LISTE):
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
            + (f" (−{r['besparelse_est']:.0f} kr vs. fravalgte)" if r["besparelse_est"] else "")
        )
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
    ap.add_argument("--force", action="store_true", help="ignorér kill-switch")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--json", action="store_true")
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

    kilde = KILDE_BASIS if a.basis else KILDE_LISTE
    if a.basis:
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
            ("kører … %d basisvarer" if a.basis else "kører … %d varer") % len(poster),
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
    # Kilden følger varen HELE vejen — ind i kurv-afstemningen og ud i
    # sensoren, hvor siden viser de to grupper hver for sig.
    for b in beslutninger:
        b["kilde"] = kilde
    lagt, foraeldet = laeg_i_kurv(n, beslutninger, kilde, dry=tørkørsel)
    if not tørkørsel:
        gem_koersel(lagt, kilde, foraeldet)
    andre = varer_fra_andre_kilder(kilde, foraeldet)
    if a.basis and not any(v.get("status") == "ok" for v in andre):
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

    besked = rapport(beslutninger, lagt, total, retter, tørkørsel, kilde)
    # Sensoren viser BEGGE kilder: denne kørsels varer + hvad den anden knap
    # lagde i sidst. Ellers ville et tryk på den ene knap tømme den anden
    # gruppe af siden, selv om varerne stadig ligger i kurven. Gælder også en
    # tørkørsel — den anden gruppe er fra en ÆGTE kørsel og ligger der stadig.
    varer = [{k: v for k, v in b.items() if k != "alternativer"} for b in beslutninger] + andre
    sensor_state = (
        f"{len(lagt)} produkter · "
        f"{len([b for b in beslutninger if b['status'] != 'ok'])} til afklaring"
    )
    sensor_attrs = {
        "friendly_name": "Nemlig — kurv",
        "icon": "mdi:cart-arrow-down",
        "retter": retter,
        "total": total,
        "toerkoersel": tørkørsel,
        "kilde": kilde,
        "varer": varer,
        "basis_antal": len(
            [v for v in varer if v.get("kilde") == KILDE_BASIS and v.get("status") == "ok"]
        ),
        "liste_antal": len(
            [
                v
                for v in varer
                if (v.get("kilde") or KILDE_LISTE) == KILDE_LISTE and v.get("status") == "ok"
            ]
        ),
        "spurgt": spurgt,
        "regnskab": regnskab(varer),
        "aabne_spoergsmaal": len(hent_spoerg().get("aabne") or {}),
        "tekst": besked,
    }
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


if __name__ == "__main__":
    sys.exit(main())
