#!/usr/bin/env python3
"""Mad-planlægning — daglige ret-afstemninger + samlet indkøbsliste til nemlig.com.

Katalog + stemmer lever i Google Sheets (Gemini fylder retter på løbende). HA
læser/skriver via en Apps Script web-app (scripts/mad_sheet_api.gs); uden den
falder scriptet tilbage til offentlig CSV-eksport = LÆS-ONLY (stemmer kan ikke
gemmes i arket, kun lokalt).

MODES (wiring i packages/mad_planlaegning.yaml + automations/mad_planlaegning.yaml):
  --refresh                 publicér sensorer (ingen notifikationer)
  --ask                     dagens ret-spørgsmål til begge telefoner
  --indkoeb                 indkøbsliste (gater selv på ugedag + uge-interval)
  --udskift-valgt           udskift valgt ret med en anden godkendt ret
  --vote --id N --person X --svar JA|SUPERJA|NIX
  --stem-slot --slot N --person X --svar Y   stem fra Mad-sidens knapper
  --fjern-valgt [--slot N]  slet ret nr. N på listen (ellers den i input_select.mad_fjern_ret)
  --fortryd-liste           byt den aktuelle indkøbsliste med den forrige (og tilbage)
  --backfill-struct         udled 'Ingredienser_struktureret' for rækker der mangler
  --sync-local              skub lokalt gemte stemmer op i arket (engangs efter setup)
  --dry-run                 print i stedet for at sende/skrive (kan kombineres)

SYNK-KØ (2026-08-07): en ark-skrivning der fejler lægges i state-filens
`usynket` og genforsøges ved HVER kørsel (flush_usynket) — før divergerede arket
og HA tavst, og kun en manuel --sync-local kunne opdage det. Stemmer resolves på
rettens NAVN, ikke id'et: arkets id'er forskydes når en række slettes, så en
gammel notifikation kan ellers lande på naboretten.

UDVÆLGELSE
  Spørgsmål: retten trækkes fra den kombination (børnevenlig × sværhedsgrad) der
  er MEST underrepræsenteret i den godkendte pulje — så puljen er balanceret når
  der skal købes ind. Tilfældigt inden for den kombination.
  Indkøb: retter (min/max-slider) med ~50/50 børnevenlig (slider), spredt på
  sværhedsgrad OG mad-kategori, med et sundheds-gennemsnit mod en slider.
  Ingen "bestilt"-markering (user-valg 2026-07-29), men fra 2026-08-20 vælges
  en ret ALDRIG hvis der findes en der ikke har været på en tidligere liste:
  "tilfældighed i en lang liste" holdt ikke, fordi den godkendte sommer-pulje er
  17 retter og én liste bruger ~9 af dem (4 af 5 gik igen 11/8 → 20/8).
  Inden for friskheden går begge-ja forud for "godkendt via svarfristen"
  (2026-10-01, Jordskokkesuppe) — se `vaelg_indkoeb`.

2026-08-05 (user-batch item 1), fire arkkolonner mere:
  L "Mad kategori" (Vegetar/Rødt kød/Fisk/Lyst kød/Salat), M "Sundhed" (1-10),
  N "Tilberedningstid (minutter)", O "Sæson".
  1a  sæson-præference + mix på mad-kategori og sundhed.
  1b  sensor.mad_opskrifter = fulde opskrifter for retterne på den AKTUELLE
      indkøbsliste (nyeste post i historikken, ikke et dato-vindue).
  1c  hver N'te plads/spørgsmål er en salat (input_number.mad_salat_hver).
  1d  arkets kolonne B "Tilbehør" → retten fylder kun 0,5 i kurven.
  Sæson og salat er PRÆFERENCER med fallback: den godkendte pulje er 11 retter
  (nul salater), så hårde filtre ville tømme listen helt.

SVAR-MULIGHEDER (user-spec 2026-08-29): JA! · SUPERJA! · NIX!
  "Måske" er IKKE længere en knap — den er blevet en TIMEOUT: har man ikke
  svaret inden for `mad_svar_timeout_dage` (7) regnet fra FØRSTE gang retten
  blev spurgt om, tæller det som et Måske. Retten er dermed færdigbehandlet og
  holder op med at jage.
  SUPERJA garanterer retten en plads på den FØRSTKOMMENDE indkøbsliste, uanset
  hvad den anden svarer. Kvote: én pr. person pr. `mad_superja_dage` (7) —
  bruges den oftere, bliver den et almindeligt JA, og det står i kvitteringen.
  Arket kender kun JA/NIX/MAASKE, så et SUPERJA skrives som JA, og stemplet
  lever lokalt i state-filen (`superja`) indtil listen er leveret.

GODKENDT = begge har svaret, ingen NIX, mindst ét JA (et SUPERJA godkender alene).
Indkøbsdagen slækker kravet hvis der er for få godkendte (user 2026-08-03):
godkendte → retter med mindst ét JA → helt tilfældige. NIX udelukker altid;
listen skal leveres, ellers står familien uden mad-plan i to uger.

Kun stdlib. Test lokalt:  python3 scripts/mad_planner.py --refresh --dry-run
"""

import argparse
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

import ha_secrets

try:
    from zoneinfo import ZoneInfo

    TZ = ZoneInfo("Europe/Copenhagen")
except Exception:  # pragma: no cover
    TZ = None

# --- HA-adgang ---------------------------------------------------------------
HA_URL = "http://127.0.0.1:8123"
TOKEN_KEY = ha_secrets.HA_API_TOKEN  # delt long-lived token (scripts/ha_secrets.py)
STATE_FILE = "/config/.mad_planner_state.json"

# --- Google Sheet ------------------------------------------------------------
# Apps Script web-app (skriveadgang). Sættes i /config/secrets.yaml:
#   mad_sheet_url: https://script.google.com/macros/s/…/exec
#   mad_sheet_token: <samme streng som TOKEN i mad_sheet_api.gs>
SHEET_URL_KEY = "mad_sheet_url"
SHEET_TOKEN_KEY = "mad_sheet_token"
# Fallback (læs-only) hvis web-app'en ikke er sat op endnu — arkets id står i
# secrets.yaml (mad_sheet_id), ikke i git: CSV-eksporten er en læse-nøgle.
SHEET_ID_KEY = "mad_sheet_id"

# --- Personer ----------------------------------------------------------------
# `tracker` bruges af påmindelses-vagten: et svar-tryk er et HTTP-kald TILBAGE
# til HA (mobile_app-webhook), så det virker kun på hjemme-wifi eller med
# Tailscale. Er telefonen hjemme, virker svar-vejen med sikkerhed.
PEOPLE = {
    "parent_a": {
        "navn": "Parent A",
        "notify": "notify/mobile_app_phone_a",
        "tracker": "device_tracker.phone_a",
    },
    "parent_b": {
        "navn": "Parent B",
        "notify": "notify/mobile_app_phone_b",
        "tracker": "device_tracker.phone_b",
        "hjemme": "binary_sensor.parent_b_hjemme_anker",
        # "side" = ingen påmindelse pr. ret, men en samlet "stem på
        # Mad-siden" engang imellem (side_paamind, user 2026-10-20).
        "paamind": "side",
    },
}

# --- HA-helpers (sliders) ----------------------------------------------------
E_ASK_ON = "input_boolean.mad_spoergsmaal_enabled"
E_ASK_ANTAL = "input_number.mad_spoergsmaal_antal"
E_ASK_REASK = "input_number.mad_genspoerg_dage"
E_SVAR_TIMEOUT = "input_number.mad_svar_timeout_dage"
E_SUPERJA_DAGE = "input_number.mad_superja_dage"
E_BUY_ON = "input_boolean.mad_indkoeb_enabled"
E_BUY_UGEDAG = "input_select.mad_indkoeb_ugedag"
E_BUY_INTERVAL = "input_number.mad_indkoeb_interval_uger"
E_BUY_ANKER = "input_datetime.mad_indkoeb_anker"
E_BUY_SPRUNGET = "input_datetime.mad_indkoeb_sprunget_dato"
E_RETTER_MIN = "input_number.mad_retter_min"
E_RETTER_MAX = "input_number.mad_retter_max"
E_BV_PCT = "input_number.mad_boernevenlig_pct"
E_SALAT_HVER = "input_number.mad_salat_hver"
E_SUNDHED = "input_number.mad_sundhed_maal"
E_SKIP_BASIS = "input_boolean.mad_basisvarer_filter_enabled"
E_FJERN = "input_select.mad_fjern_ret"
# Faste knap-slots på Mad → Afstemning. Lovelace kan ikke loope, så listen har
# et loft; resten dukker op efterhånden som de øverste bliver besvaret.
STEM_SLOTS = 8
# Mad-siden holder rækkefølgen FAST så længe man stemmer (user 14/10: "mega
# svært at trykke rigtigt på nr 2 fordi det hopper rundt"). Hver stemme
# forlænger holdet; en besvaret ret bliver stående med sit svar til holdet
# udløber, og først da rykker listen op.
STEM_HOLD_MIN = 15

# Svar-mulighederne. MAASKE kan ikke længere VÆLGES (user-spec 2026-08-29) —
# den bevares som gyldig værdi fordi arket, synk-køen og gamle stemmer bærer
# den, og fordi timeouten selv skriver den.
JA_SVAR = ("JA", "SUPERJA")
SVAR_VALG = ("JA", "SUPERJA", "NIX", "MAASKE")
# Sat i main() fra input_number.mad_svar_timeout_dage. Global, fordi de rene
# klassifikations-funktioner (er_godkendt, afventer, kan_spoerges) kaldes fra
# et dusin steder uden adgang til `states`. 0 = timeouten er slået fra.
SVAR_TIMEOUT_DAGE = 7
E_REM_ON = "input_boolean.mad_paamind_enabled"
E_REM_EFTER = "input_number.mad_paamind_efter_timer"
E_REM_MAKS = "input_number.mad_paamind_maks"
E_REM_UDE = "input_number.mad_paamind_ude_timer"
# Samlet Mad-side-påmindelse (2026-10-20, user: "giv hende i stedet en
# påmindelse om at tjekke mad siden og stemme derinde en gang i mellem … match
# det"). Målt 27/9-20/10: Parent B svarede på 2 af 25 påmindelser pr. ret, men
# stemte 37 gange på Mad-siden i 6 sessioner — 4 af dem startede 17:41-21:10
# (20:27, 20:43, 21:10, 17:41; ellers lør 12:25 og 07:41), med 1-5 dages
# mellemrum. Derfor kl. 20:00, hver 3. dag, regnet fra hendes SENESTE stemme.
E_SIDE_TID = "input_datetime.mad_side_paamind_tid"
E_SIDE_DAGE = "input_number.mad_side_paamind_dage"
E_SIDE_MIN = "input_number.mad_side_paamind_min"

# Højst ÉN påmindelse pr. person pr. `mad_paamind_efter_timer` — uanset hvor
# mange retter der venter. Uden det loft ville en ophobet bunke (18 ubesvarede
# retter målt 2026-08-06) lande som en mur af notifikationer, og så er vi
# tilbage ved 07-30d's fejl: en påmindelse man scroller forbi er ingen
# påmindelse. Den ældste ubesvarede ret går først.
PAAMIND_PR_KOERSEL = 1

HISTORIK_DAGE = 60

UGEDAGE = ["Mandag", "Tirsdag", "Onsdag", "Torsdag", "Fredag", "Lørdag", "Søndag"]

# --- Basisvarer der IKKE kommer på indkøbslisten (input_boolean styrer om) ----
# Rediger frit — normaliserede navne (småt, uden mængde).
BASISVARER = {
    "salt",
    "peber",
    "salt og peber",
    "sort peber",
    "vand",
    "olie",
    "olivenolie",
    "sesamolie",
    "rapsolie",
    "madolie",
    "sukker",
    "mel",
    "hvedemel",
    "eddike",
    "æblecidereddike",
    "paprika",
    "chilipulver",
    "karrypulver",
    "spidskommen",
    "garam masala",
    "tørret timian",
    "tørret oregano",
    "tørret basilikum",
    "stødt kanel",
}

# --- Ingrediens-enheder ------------------------------------------------------
MASSE = {"g": 1.0, "gram": 1.0, "kg": 1000.0}
VOLUMEN = {"ml": 1.0, "cl": 10.0, "dl": 100.0, "l": 1000.0, "liter": 1000.0}
# Alt andet er "stykke-agtigt" og summeres i sin egen enhed:
STK_ENHEDER = {
    "stk",
    "spsk",
    "tsk",
    "fed",
    "ds",
    "dåse",
    "pk",
    "pakke",
    "pose",
    "glas",
    "bdt",
    "bundt",
    "brev",
    "potte",
    "bøtte",
    "kugler",
    "kugle",
    "plader",
    "skiver",
    "store",
    "stort",
    "stor",
    "små",
    "lille",
    "nip",
    "knsp",
}
ALLE_ENHEDER = set(MASSE) | set(VOLUMEN) | STK_ENHEDER

# Slå varianter sammen så de kan lægges sammen på listen.
SYNONYMER = {
    "creme fraiche": "cremefraiche",
    "crème fraiche": "cremefraiche",
    "flåede tomater": "hakkede tomater",
    "hakket tomat": "hakkede tomater",
    "oksekød, hakket": "hakket oksekød",
    "hakket oksekod": "hakket oksekød",
    "kyllingebryster": "kyllingebryst",
    "revet ost": "revet ost",
    "frisk spinat": "spinat",
    "hakket spinat (frost)": "spinat (frost)",
}


def log(msg):
    print(f"[mad] {msg}", file=sys.stderr)


def now_local():
    return datetime.now(TZ) if TZ else datetime.now()


# =============================================================================
# HA REST
# =============================================================================
def ha_get_states(token):
    req = urllib.request.Request(
        f"{HA_URL}/api/states", headers={"Authorization": "Bearer " + token}
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return {s["entity_id"]: s for s in json.load(r)}


def num(states, entity, default):
    try:
        return float(states[entity]["state"])
    except KeyError, ValueError, TypeError:
        return default


def txt(states, entity, default=""):
    s = states.get(entity, {}).get("state", default)
    return default if s in ("unknown", "unavailable", None) else s


def is_on(states, entity, default=True):
    s = states.get(entity, {}).get("state")
    if s in ("on", "off"):
        return s == "on"
    return default


def ha_post(token, path, payload):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{HA_URL}{path}",
        data=body,
        method="POST",
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status


def publish_sensor(token, entity, state, attrs, dry=False):
    state = str(state)[:255]
    if dry:
        log(f"(dry) {entity} = {state}")
        return
    ha_post(token, f"/api/states/{entity}", {"state": state, "attributes": attrs})


def _hhmm(state):
    try:
        h, m = str(state).split(":")[:2]
        return int(h) * 60 + int(m)
    except ValueError, AttributeError:
        return None


def gate_ok(states, nid, person=None):
    """SPEJL af script.push_notify's gate_ok + targets (packages/notifikationer.yaml).

    Ret BEGGE steder hvis gaten ændres (fejlklasse #2). Bruges KUN til
    ret-spørgsmålet, som ikke kan gå gennem den centrale dispatch: hver telefon
    skal have sine egne svar-knapper, og dispatchen sender samme payload til
    alle valgte telefoner. Fail-open ved uvished (som plant_notify).
    """
    try:
        if not is_on(states, "input_boolean.notifikationer_master_enabled"):
            return False
        if not is_on(states, f"input_boolean.notif_{nid}_enabled"):
            return False
        if txt(states, "input_select.house_mode") == "AirBnB" and not is_on(
            states, f"input_boolean.notif_{nid}_airbnb", False
        ):
            return False
        if person and not is_on(states, f"input_boolean.notif_{nid}_{person}"):
            return False
        s = _hhmm(txt(states, f"input_datetime.notif_{nid}_start"))
        e = _hhmm(txt(states, f"input_datetime.notif_{nid}_slut"))
        if s is None or e is None or s == e:
            return True
        n = now_local().hour * 60 + now_local().minute
        return (s <= n < e) if s < e else (n >= s or n < e)
    except Exception as err:
        log(f"gate-tjek fejlede ({err}) — fail-open")
        return True


def notify_direct(token, person, payload, dry=False):
    """Direkte push (uden om dispatchen) — kun til ret-spørgsmålet."""
    service = PEOPLE[person]["notify"]
    if dry:
        log(f"(dry) → {service}\n{json.dumps(payload, ensure_ascii=False, indent=2)}")
        return
    ha_post(token, f"/api/services/{service}", payload)


def push_notify(token, nid, title, message, payload=None, dry=False):
    """Central dispatch (script.push_notify): master/type/AirBnB/tid/telefon-valg
    + hjemkomst-kø håndteres ét sted."""
    data = {"notif_id": nid, "title": title, "message": message}
    if payload:
        data["payload"] = payload
    if dry:
        log(f"(dry) → script.push_notify {nid}\n{json.dumps(data, ensure_ascii=False, indent=2)}")
        return
    ha_post(token, "/api/services/script/push_notify", data)


def logbook(token, name, message, dry=False):
    if dry:
        return
    try:
        ha_post(
            token,
            "/api/services/logbook/log",
            {"name": name, "message": message, "entity_id": "sensor.mad_status"},
        )
    except Exception as err:  # logbook må aldrig vælte en kørsel
        log(f"logbook fejlede: {err}")


# =============================================================================
# Lokal state (spejl af arket — overlever at Gemini rydder kolonner)
# =============================================================================
LOCK_FILE = STATE_FILE + ".lock"
BAK_FILE = STATE_FILE + ".bak"


def state_lock(vent=True):
    """Serialisér HELE kørslen mod andre mad_planner-processer.

    HA kan fyre to shell_commands i samme sekund (målt 08-25 19:00:00:
    `mad_indkoeb` + `mad_paamind`) — begge gør read-modify-write på hele
    state-dict'en, så uden lås er både korruption og lost-update mulig.

    vent=False (2026-10-06, kun --paamind): HA dræber en shell_command efter
    60 s INKL. ventetiden her, og en kørsel tager ~30 s når Apps Script svarer
    på 3-6 s pr. kald. Målt 10-06: påmind ventede bag en stemme og blev dræbt
    11:41:03; kl. 11:01 dræbte den samme kø dagens spørgsmål. Påmind er
    backstoppen (næste tick om ≤ 40 min) — den må aldrig æde en interaktiv
    kørsels budget, så den opgiver straks og stille.
    """
    import fcntl

    fh = open(LOCK_FILE, "a+")
    # Frakoblet (--detach) står HA ikke med 60-s-stopuret → vent længere, så
    # tre hurtige stemmer i træk ikke taber den sidste i lås-køen.
    maks = 300 if os.environ.get("MAD_DETACHED") else 60
    for forsoeg in range(maks if vent else 1):
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fh
        except OSError:
            if not vent:
                break
            if forsoeg == 0:
                log("state-lås optaget af anden mad_planner — venter")
            time.sleep(1)
    fh.close()
    if not vent:
        log("state-lås optaget — påmind springer over (næste tick prøver igen)")
        raise SystemExit(0)
    raise SystemExit(f"[mad] state-lås ikke opnået på {maks} s — afbryder uden at skrive")


def load_state():
    """Læs state. Er filen ulæselig, PRØV backup — og skriv ALDRIG videre på {}.

    Et tomt dict her er katastrofalt: næste save_state() persisterer det, og
    hele opskriftslisten + stemmehistorikken er væk (skete 08-25 19:40).
    Kun en manglende fil er en legitim tom state.
    """
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        pass
    except json.JSONDecodeError as err:
        log(f"state-filen er korrupt ({err}) — prøver {BAK_FILE}")
        skadet = f"{STATE_FILE}.corrupt-{datetime.now():%Y%m%d-%H%M%S}"
        try:
            os.replace(STATE_FILE, skadet)
            log(f"gemte den skadede fil som {skadet}")
        except OSError:
            pass
        try:
            with open(BAK_FILE, encoding="utf-8") as f:
                genskabt = json.load(f)
            log(f"genskabte state fra backup ({len(genskabt)} nøgler)")
            return genskabt
        except FileNotFoundError, json.JSONDecodeError:
            raise SystemExit(
                "[mad] state-filen er korrupt og backup'en kan ikke læses — "
                "afbryder hellere end at overskrive med tom state"
            ) from None
    # Ingen fil: legitimt tomt, MEN har vi en backup er filen forsvundet
    # bag ryggen på os, og backup'en er sandheden.
    try:
        with open(BAK_FILE, encoding="utf-8") as f:
            genskabt = json.load(f)
        if genskabt:
            log(f"state-filen manglede — genskabt fra backup ({len(genskabt)} nøgler)")
            return genskabt
    except FileNotFoundError, json.JSONDecodeError:
        pass
    return {}


# Nøgler der aldrig må FORSVINDE ved en skrivning. Ingen kodesti sletter dem
# (de sættes kun), så et tab er pr. definition en bug — og prisen er hele
# opskriftslisten + stemmehistorikken.
BEVAR_NOEGLER = ("indkoeb", "historik", "stemmer", "spurgt", "ask_nr", "superja")


def save_state(state, dry=False):
    if dry:
        return
    # Sidste værn: bær nøgler med over som findes på disken men mangler i den
    # state vi er ved at skrive. Fanger enhver fremtidig sti der læser en
    # delvis state og skriver den tilbage (08-25: hele listen forsvandt sådan).
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            paa_disk = json.load(f)
    except OSError, json.JSONDecodeError:
        paa_disk = {}
    if isinstance(paa_disk, dict):
        for noegle in BEVAR_NOEGLER:
            if paa_disk.get(noegle) and not state.get(noegle):
                log(f"ADVARSEL: '{noegle}' ville være gået tabt — beholder disk-værdien")
                state[noegle] = paa_disk[noegle]
    # Unik tmp pr. proces: en delt sti lader to samtidige kørsler skrive i
    # hinandens fil, så os.replace flytter en halv JSON på plads.
    tmp = f"{STATE_FILE}.tmp.{os.getpid()}"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        # Rullende backup af den FORRIGE gode state, så load_state har noget
        # at falde tilbage på hvis en skrivning alligevel går galt.
        try:
            if os.path.getsize(STATE_FILE) > 2:
                os.replace(STATE_FILE, BAK_FILE)
        except OSError:
            pass
        os.replace(tmp, STATE_FILE)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


# =============================================================================
# Google Sheet
# =============================================================================
def sheet_api(action, dry=False, **params):
    """Kald Apps Script web-app'en. Returnerer dict; rejser ved fejl."""
    url = ha_secrets.get(SHEET_URL_KEY, required=False)
    tok = ha_secrets.get(SHEET_TOKEN_KEY, required=False)
    if not url or not tok:
        raise RuntimeError("mad_sheet_url/mad_sheet_token mangler i secrets.yaml")
    q = {"token": tok, "action": action}
    q.update({k: v for k, v in params.items() if v is not None})
    full = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(q)
    if dry and action not in ("dishes", "ping"):
        log(f"(dry) sheet {action} {params}")
        return {"ok": True, "dry": True}
    # Apps Script svarer sporadisk 404/429/5xx på et kald der virker sekundet
    # efter — set 2026-08-05 midt i en sync på 51 kald i træk, mens de samme
    # kald enkeltvis gav 200. Uden retry ville et JA/NIX-tryk på en
    # notifikation kunne gå tavst tabt, fordi der ikke er nogen anden kvittering
    # end selve ark-skrivningen. Backoff er beskeden (0,8/1,6/3,2 s): kaldet
    # sker inde i en shell_command som HA venter på.
    sidste = None
    for forsoeg in range(4):
        if forsoeg:
            time.sleep(0.8 * (2 ** (forsoeg - 1)))
        req = urllib.request.Request(full, headers={"User-Agent": "ha-mad-planner"})
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                data = json.load(r)
        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            TimeoutError,
            json.JSONDecodeError,
        ) as e:
            sidste = e
            continue
        if not data.get("ok"):
            # Et ærligt "ukendt id" er permanent — kun transport-fejl gentages.
            raise RuntimeError(f"sheet {action}: {data.get('error')}")
        return data
    raise RuntimeError(f"sheet {action}: opgav efter 4 forsøg ({sidste})")


def api_available():
    return bool(
        ha_secrets.get(SHEET_URL_KEY, required=False)
        and ha_secrets.get(SHEET_TOKEN_KEY, required=False)
    )


def koe_tilfoej(st, post):
    """Læg en ark-skrivning der ikke kunne leveres i synk-køen (muterer `st`).

    En fejlet skrivning var før permanent og TAVS: state-filen fik stemmen,
    arket gjorde ikke, og kun en manuel --sync-local kunne opdage forskellen.
    Målt 2026-08-07 på 'Biksemad med spejlæg' — Parent B's JA stod lokalt, arket
    havde kun Parent A's. Køen er nøglet på (type, id, person), så et nyt svar på
    samme ret overskriver det gamle i stedet for at hobe sig op.
    """
    koe = st.setdefault("usynket", [])
    noegle = (post.get("type"), str(post.get("id")), post.get("person"))
    koe[:] = [k for k in koe if (k.get("type"), str(k.get("id")), k.get("person")) != noegle]
    koe.append(post)


def flush_usynket(dishes, dry=False):
    """Genforsøg køen. Kaldes ved HVER kørsel, så /40-tick'en selv rydder op."""
    st = load_state()
    koe = st.get("usynket") or []
    if not koe or not api_available():
        return 0
    rest, n = [], 0
    for post in koe:
        # NAVNET vinder over id'et (samme regel som loes_id): arkets id'er
        # forskydes når en række slettes, og en stemme må aldrig lande på
        # naboretten. Findes retten slet ikke længere, droppes posten —
        # ellers ville køen prøve i det uendelige.
        maal = loes_id(post.get("id"), post.get("ret"), dishes)
        if maal is None:
            log(
                f"synk-kø: dropper {post.get('type')} for "
                f"{post.get('ret') or post.get('id')} (ikke i arket)"
            )
            continue
        if post.get("type") == "vote" and not post.get("ret"):
            # Uden navn kan id'et ikke verificeres (positionel ID-kolonne), og
            # en stemme på naboretten forurener puljen usynligt.
            log(f"synk-kø: dropper stemme uden ret-navn (id {post.get('id')})")
            continue
        try:
            if post.get("type") == "vote":
                sheet_api(
                    "vote",
                    dry=dry,
                    id=maal,
                    person=post["person"],
                    svar=post["svar"],
                    **({"ret": post["ret"]} if post.get("ret") else {}),
                )
            else:
                sheet_api(
                    "asked",
                    dry=dry,
                    ids=maal,
                    **({"dato": post["dato"]} if post.get("dato") else {}),
                )
        except Exception as err:
            log(f"synk-kø: {post.get('type')} {post.get('ret')} fejlede igen ({err})")
            rest.append(post)
            continue
        n += 1
    if dry or len(rest) == len(koe):
        return n
    st = load_state()  # genlæs: kaldere kan have skrevet imens
    st["usynket"] = rest
    save_state(st, dry)
    if n:
        log(f"synk-kø: {n} udestående ark-skrivning(er) leveret")
    return n


def parse_csv(text):
    """Minimal RFC4180-parser (retter indeholder kommaer i citationstegn)."""
    rows, row, cell, quoted, i = [], [], [], False, 0
    while i < len(text):
        c = text[i]
        if quoted:
            if c == '"':
                if i + 1 < len(text) and text[i + 1] == '"':
                    cell.append('"')
                    i += 1
                else:
                    quoted = False
            else:
                cell.append(c)
        elif c == '"':
            quoted = True
        elif c == ",":
            row.append("".join(cell))
            cell = []
        elif c in "\r\n":
            if c == "\r" and i + 1 < len(text) and text[i + 1] == "\n":
                i += 1
            row.append("".join(cell))
            rows.append(row)
            row, cell = [], []
        else:
            cell.append(c)
        i += 1
    if cell or row:
        row.append("".join(cell))
        rows.append(row)
    return [r for r in rows if any(x.strip() for x in r)]


def csv_rows():
    url = f"https://docs.google.com/spreadsheets/d/{ha_secrets.get(SHEET_ID_KEY)}/export?format=csv"
    req = urllib.request.Request(url, headers={"User-Agent": "ha-mad-planner"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return parse_csv(r.read().decode("utf-8"))


def suppler_nye_kolonner(dishes):
    """Hent 2026-08-05-kolonnerne fra CSV når web-app'en ikke leverer dem.

    Apps Script-versionen i arket skal redeployes for at kende 'Mad kategori',
    'Sundhed', 'Tilberedningstid (minutter)' og 'Sæson'. Indtil da ville sæson-
    og salat-reglerne være tavse no-ops (fejlklasse #6: koden ser rigtig ud,
    men den eksekverede sti har tomme felter). CSV-eksporten er offentlig og
    altid frisk, så vi fletter felterne ind på ARKETS RÆKKENUMMER — arkets
    id-kolonne har dubletter, og to retter kan hedde det samme.
    """
    if not dishes or any(d.get("mad_kategori") for d in dishes):
        return dishes
    try:
        rows = csv_rows()
    except Exception as err:
        log(f"kunne ikke supplere nye kolonner fra CSV ({err})")
        return dishes
    if not rows:
        return dishes
    head = [h.strip() for h in rows[0]]
    ekstra = {}
    for n, row in enumerate(rows[1:], start=2):
        ekstra[n] = nye_felter(row, head)
    for d in dishes:
        d.update(ekstra.get(d.get("row"), TOMME_FELTER))
    return dishes


NYE_KOLONNER = {
    "mad_kategori": "Mad kategori",
    "sundhed": "Sundhed",
    "tilberedningstid": "Tilberedningstid (minutter)",
    "saeson": "Sæson",
}
TOMME_FELTER = {k: "" for k in NYE_KOLONNER}


def nye_felter(row, head):
    ud = {}
    for felt, kolonne in NYE_KOLONNER.items():
        i = head.index(kolonne) if kolonne in head else -1
        ud[felt] = row[i].strip() if 0 <= i < len(row) else ""
    return ud


def fetch_dishes():
    """[{id,ret,kategori,boernevenlig,svaerhedsgrad,ingredienser,guide,struct,
    parent_a,parent_b,spurgt,mad_kategori,sundhed,tilberedningstid,saeson}], kilde."""
    if api_available():
        try:
            return suppler_nye_kolonner(sheet_api("dishes")["dishes"]), "api"
        except Exception as err:
            log(f"web-app utilgængelig ({err}) — falder tilbage til CSV")

    rows = csv_rows()
    if not rows:
        return [], "csv"
    head = [h.strip() for h in rows[0]]

    def col(row, name):
        return row[head.index(name)].strip() if name in head and head.index(name) < len(row) else ""

    dishes = []
    for n, row in enumerate(rows[1:], start=2):
        ret = col(row, "Ret")
        if not ret:
            continue
        d = {
            "id": col(row, "ID") or f"r{n}",
            "row": n,
            "ret": ret,
            "kategori": col(row, "Kategori"),
            "boernevenlig": col(row, "Børnevenlig"),
            "svaerhedsgrad": col(row, "Sværhedsgrad"),
            "ingredienser": col(row, "Ingredienser"),
            "guide": col(row, "Trin-for-trin Guide"),
            "struct": col(row, "Ingredienser_struktureret"),
            "parent_a": col(row, "Parent A").upper(),
            "parent_b": col(row, "Parent B").upper(),
            "spurgt": col(row, "Sidst spurgt"),
        }
        d.update(nye_felter(row, head))
        dishes.append(d)
    return dishes, "csv"


def ret_bag_spoergsmaal(did, navn, dishes):
    """Den ret en lokal post FAKTISK handler om — NAVNET vinder over id'et.

    💡 Arkets ID-kolonne er POSITIONEL, ikke en nøgle: målt 2026-08-07 er
    id == rækkenummer − 1 for alle 289 rækker, og der er nul dublet-id'er.
    Sletter/indsætter Gemini en række, forskydes hvert eneste id under den —
    men state-filens poster er stemplet med id'et som det så ud DA vi spurgte.

    Målt facit 2026-08-07 (præcis brugerens klage): 'Svamperisotto med
    trøffelolie' blev spurgt under id 187 den 08-04 og besvaret JA/JA samme
    dag. Rækkerne forskød sig ~14 pladser, id 187 blev til 'Koteletter i fad
    med æbler og timian', og påmindelses-vagten læste DEN rets (tomme) stemmer
    → 21:40 blev Parent A mindet om en ret han aldrig har set, og da han svarede
    22:18 fik han '"Svamperisotto med trøffelolie" findes ikke længere i
    mad-arket — svaret er ikke gemt'. Begge udsagn var forkerte.

    ENESTE ejer af reglen (fejlklasse #2): påmindelse, stemme, merge og synk-kø
    går alle herigennem.
    """
    did = str(did)
    if not navn:
        # Legacy-post uden navn: id'et er alt vi har.
        return next((d for d in dishes if str(d["id"]) == did), None)
    traef = [d for d in dishes if d.get("ret") == navn]
    if not traef:
        return None
    for d in traef:
        if str(d["id"]) == did:
            return d  # id + navn passer
    # Navnet findes et andet sted → følg navnet. Ved dublet-NAVNE (målt 5 par)
    # vælges den nærmeste række: id'et er positionelt, så driften er lille
    # (målt 14 rækker), mens to ens navne kan ligge hundredvis fra hinanden.
    # Begge bærer samme navn, så brugeren ser den rigtige ret uanset valget.
    if did.isdigit():
        num = [d for d in traef if str(d["id"]).isdigit()]
        if num:
            return min(num, key=lambda d: abs(int(d["id"]) - int(did)))
    return traef[0]


def loes_id(did, navn, dishes):
    """Ark-id'et for en lokal post — None hvis retten ikke findes længere.

    Returnerer None frem for at gætte: en stemme på en ret brugeren aldrig har
    set er værre end en tabt stemme, fordi den forurener puljen usynligt.
    """
    d = ret_bag_spoergsmaal(did, navn, dishes)
    return str(d["id"]) if d is not None else None


def post_index(poster, dishes):
    """Map fra ark-id → lokal post, opløst via navnet.

    Nøglen i state-filen er ask-tidens id og kan være forældet; her oversættes
    den til retten som den ligger i arket NU.
    """
    ud = {}
    for did, post in (poster or {}).items():
        p = som_post(post)
        d = ret_bag_spoergsmaal(did, p.get("ret"), dishes)
        if d is None:
            continue
        k = str(d["id"])
        cur = ud.get(k)
        if cur is None:
            ud[k] = dict(p)
            continue
        # To poster om SAMME ret (id'et flyttede sig mellem to spørgsmål):
        # foren dem frem for at lade den ene overskrive den anden — ellers
        # kunne den enes svar forsvinde fra visningen. Poster er ordnet efter
        # indsættelse, så den seneste vinder ved konflikt.
        for felt, v in p.items():
            if not v:
                continue
            if felt in ("dato", "sendt", "svar_at"):
                if str(v) > str(cur.get(felt) or ""):
                    cur[felt] = v
            elif felt == "foerst":
                # Svar-fristen måles fra det TIDLIGSTE spørgsmål — ellers ville
                # en genspørgsel forlænge den (se svar_udloebet).
                if str(v) < str(cur.get(felt) or "9999"):
                    cur[felt] = v
            else:
                cur[felt] = v
    return ud


def merge_local_state(dishes, state):
    """Arket er sandheden; lokal state fylder huller (fx uden skriveadgang)."""
    local_asked = post_index(state.get("spurgt", {}), dishes)
    local_votes = post_index(state.get("stemmer", {}), dishes)
    # Et SUPERJA skrives til arket som et almindeligt JA (arkets Apps Script
    # kender kun JA/NIX/MAASKE), så stemplet kan kun bo lokalt. Det følger
    # rettens NAVN — id-kolonnen er positionel og forskyder sig.
    superja = {}
    for person, post in (state.get("superja") or {}).items():
        p = som_post(post)
        if p.get("ret") and not p.get("leveret"):
            superja[normaliser_navn(p["ret"])] = person
    for d in dishes:
        did = str(d["id"])
        a = local_asked.get(did)
        if not d.get("spurgt") and a and a.get("dato"):
            d["spurgt"] = a["dato"]
        if a and a.get("foerst"):
            d["foerst_spurgt"] = a["foerst"]
        sj = superja.get(normaliser_navn(d.get("ret", "")))
        if sj:
            d["superja"] = sj
        v = local_votes.get(did) or {}
        if v.get("svar_at"):
            # Additivt: arket har ingen svar-tid-kolonne, så her er intet at
            # overtrumfe — modsat stemmerne selv, hvor arket er sandheden.
            d["svar_at"] = v["svar_at"]
        for p in ("parent_a", "parent_b"):
            if not d.get(p) and v.get(p):
                d[p] = v[p]
    return dishes


def som_post(vaerdi, felt="dato"):
    """Legacy-poster er bare datoen/svaret; nye bærer også rettens navn."""
    return vaerdi if isinstance(vaerdi, dict) else {felt: vaerdi}


# =============================================================================
# Klassifikation
# =============================================================================
_JS_DATE_RE = re.compile(r"\b([A-Z][a-z]{2})\s+(\d{1,2})\s+(\d{4})\b")
_DK_DATE_RE = re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b")
_MAANED = {
    m: i
    for i, m in enumerate(
        ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
        start=1,
    )
}


def parse_dato(raw):
    """'Sidst spurgt' kan komme i flere former → date eller None.

    Google Sheets auto-konverterer 'ÅÅÅÅ-MM-DD' til en ægte dato-celle, som
    Apps Script læser som JS-Date ('Wed Jul 29 2026 00:00:00 GMT+0200 (…)').
    Skriver user eller Gemini datoen i hånden, kan den også være dansk
    (29-07-2026). Alle tre former accepteres — ellers ville en ret blive
    spurgt om igen hver eneste dag.
    """
    s = (raw or "").strip()
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except ValueError:
        pass
    m = _JS_DATE_RE.search(s)
    if m and m.group(1) in _MAANED:
        try:
            return date(int(m.group(3)), _MAANED[m.group(1)], int(m.group(2)))
        except ValueError:
            return None
    m = _DK_DATE_RE.search(s)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    return None


def er_boernevenlig(d):
    return d.get("boernevenlig", "").strip().lower().startswith("ja")


def svaerhed(d):
    return (d.get("svaerhedsgrad") or "Ukendt").strip().title()


# Arket staver samme kategori på to måder (9 retter "Vegetarisk" ved siden af
# 103 "Vegetar"). Kategori er mixets tungeste akse, og en stavevariant er en
# EGEN spand der aldrig er brugt — så den vandt en plads på næsten hver liste
# (Palak Paneer på 99 % af 2000 replays af 30/9-listen).
KATEGORI_ALIAS = {"Vegetarisk": "Vegetar"}


def mad_kategori(d):
    """Kolonne L: Vegetar / Rødt kød / Fisk / Lyst kød / Salat / Suppe."""
    k = (d.get("mad_kategori") or "Ukendt").strip().title()
    return KATEGORI_ALIAS.get(k, k)


KATEGORI_IKON = {
    "vegetar": "🥬",
    "rødt kød": "🥩",
    "fisk": "🐟",
    "lyst kød": "🍗",
    "salat": "🥗",
    "suppe": "🍲",
}


def kategori_ikon(navn):
    return KATEGORI_IKON.get((navn or "").strip().lower(), "🍽️")


def sundhed(d, fallback=5.0):
    """Kolonne M, 1-10 (10 = ekstremt sundt). Tom celle = midt på skalaen, så
    en manglende værdi hverken belønnes eller straffes i mikset."""
    v = til_tal(d.get("sundhed"))
    return v if v is not None and 0 <= v <= 10 else fallback


def tilberedningstid(d):
    """Kolonne N i minutter. None = tom celle (vises da slet ikke)."""
    v = til_tal(d.get("tilberedningstid"))
    return v if v is not None and v > 0 else None


def ret_fakta(d):
    """De to tal user vil se i ENHVER notifikation om en ret (2026-08-05):
    tilberedningstid og sundhedsgrad. Ét sted, fordi begge notifikations-typer
    (dagens spørgsmål + indkøbslisten) skal vise det samme (fejlklasse #2).
    Et manglende tal udelades frem for at vise en gætteværdi — sundhedens
    fallback på 5 er et miks-input, ikke en påstand om retten.
    """
    dele = []
    t = tilberedningstid(d)
    if t is not None:
        dele.append(f"⏱️ {t:g} min")
    if til_tal(d.get("sundhed")) is not None:
        dele.append(f"❤️ sundhed {sundhed(d):g}/10")
    return " · ".join(dele)


def er_tilbehoer(d):
    """Kolonne B (Kategori) = 'Tilbehør' → retten er en side, ikke et måltid."""
    return "tilbehør" in (d.get("kategori") or "").lower()


def er_salat(d):
    return "salat" in (d.get("mad_kategori") or "").lower()


def kurv_vaegt(d):
    """1d (user 2026-08-05): et tilbehør fylder kun en halv plads i kurven."""
    return 0.5 if er_tilbehoer(d) else 1.0


SAESON_MAANED = {
    12: "Vinter",
    1: "Vinter",
    2: "Vinter",
    3: "Forår",
    4: "Forår",
    5: "Forår",
    6: "Sommer",
    7: "Sommer",
    8: "Sommer",
    9: "Efterår",
    10: "Efterår",
    11: "Efterår",
}


def aktuel_saeson(today=None):
    return SAESON_MAANED[(today or now_local().date()).month]


def saeson_ok(d, saeson):
    """Kolonne O. FAIL-OPEN: tom celle = altid i sæson.

    Kolonnen fyldes af user/Gemini løbende, og web-app'en leverer den først
    efter en redeploy — en tom celle må aldrig fjerne en ret fra puljen, ellers
    ville hele kataloget forsvinde stille (fejlklasse #5-familien: den
    uinitialiserede tilstand skal være den ufarlige).
    """
    s = (d.get("saeson") or "").strip().lower()
    if not s or "hele" in s:
        return True
    return saeson.lower() in s  # tåler "Sommer/Efterår"


def saeson_eksplicit(d, saeson):
    """True kun hvis retten NAVNGIVER den aktuelle sæson. Helårs-/tomme retter
    er lovlige året rundt (saeson_ok), men skal ikke have sæson-bonussen."""
    s = (d.get("saeson") or "").strip().lower()
    if not s or "hele" in s:
        return False
    return saeson.lower() in s


def raa_stemmer(d):
    """Kun FAKTISK afgivne svar — til visning og til "hvem mangler vi svar fra"."""
    return d.get("parent_a", "").strip().upper(), d.get("parent_b", "").strip().upper()


def svar_udloebet(d, today=None):
    """Er svarfristen løbet ud? (= de manglende svar tæller som Måske.)

    Fristen måles fra FØRSTE spørgsmål, ikke fra det seneste: `--ask` gensender
    ubesvarede retter efter `mad_genspoerg_dage` og stempler 'Sidst spurgt' på
    ny, så en genspørgsel ville ellers forlænge fristen i det uendelige hver
    gang genspørg-vinduet er kortere end timeouten.
    """
    if SVAR_TIMEOUT_DAGE <= 0:
        return False
    d0 = parse_dato(d.get("foerst_spurgt")) or parse_dato(d.get("spurgt"))
    if d0 is None:
        return False  # aldrig spurgt om → ingen frist at overskride
    return ((today or now_local().date()) - d0).days >= SVAR_TIMEOUT_DAGE


def stemmer(d):
    """EFFEKTIVE stemmer: udeblevet svar bliver 'MAASKE' når fristen er ude.

    User-spec 2026-08-29: "at man ikke har svaret inden for en uge skal være
    ensbetydende med at man svarer måske." Alt der klassificerer en ret
    (godkendt/afvist/afventer/kan spørges) læser derfor herfra — så ét sted
    ejer reglen, og en udløbet ret holder op med at jage af sig selv.
    """
    m, c = raa_stemmer(d)
    if (not m or not c) and svar_udloebet(d):
        return m or "MAASKE", c or "MAASKE"
    return m, c


def har_ja(d):
    """Mindst ét ja — SUPERJA tæller med."""
    return any(v in JA_SVAR for v in stemmer(d))


def har_superja(d):
    """Et aktivt SUPERJA (endnu ikke leveret på en indkøbsliste)."""
    return bool(d.get("superja")) or "SUPERJA" in raa_stemmer(d)


def begge_ja(d):
    """Har BEGGE faktisk svaret ja? Rå svar: et udløbet svar er et måske, ikke
    et ja — så en ret godkendt via svarfristen er godkendt, men ikke begge-ja."""
    m, c = raa_stemmer(d)
    return m in JA_SVAR and c in JA_SVAR


def er_godkendt(d):
    """Begge har svaret, ingen NIX, mindst ét JA (user-valg 2026-07-29).

    Et SUPERJA godkender ALENE — også mod den andens NIX (user-spec
    2026-08-29: "lige meget hvad den anden svarer til det").
    """
    if har_superja(d):
        return True
    m, c = stemmer(d)
    if not m or not c:
        return False
    if "NIX" in (m, c):
        return False
    return har_ja(d)


_SVAR_TEKST = {"JA": "ja", "SUPERJA": "superja", "NIX": "nix", "MAASKE": "måske"}


def godkendelse(d):
    """→ {"begge_ja": bool, "markering": str} — sagde BEGGE ja til retten?

    User-spec 2026-09-30/10-01: "det skal være tydeligt på mad siden når retter
    blev lagt på indkøbslisten uden at vi begge havde sagt ja til den. fx
    jordskokkesuppe". En ret kan nå listen uden to ja ad tre veje:
      · puljen slækkes når der er for få godkendte (`_pulje_stige`: "delvise
        svar" = ét ja, den anden har ikke svaret — Jordskokkesuppe 30/9),
      · svarfristen udløb, så det manglende svar tæller som måske
        (`stemmer`) — Palak Paneer 30/9,
      · et SUPERJA godkender alene.
    Markeringen bygges af de RÅ svar (ikke de effektive), så siden siger hvad
    hver af jer faktisk har svaret. Eneste ejer af teksten (fejlklasse #2):
    indkøbs-sensoren, opskrift-sensoren og push-beskeden læser herfra.
    """
    if begge_ja(d):
        return {"begge_ja": True, "markering": ""}
    m, c = raa_stemmer(d)
    udloebet = svar_udloebet(d)

    def tekst(v):
        if not v:
            return "ikke svaret" + (" (tæller som måske)" if udloebet else "")
        return _SVAR_TEKST.get(v, v.lower())

    if er_godkendt(d):
        grund = "Kun ét superja" if har_superja(d) else "Godkendt via svarfristen"
    else:
        grund = "Ikke godkendt af begge"
    return {"begge_ja": False, "markering": f"{grund}: Parent A {tekst(m)}, Parent B {tekst(c)}"}


def er_afvist(d):
    if har_superja(d):
        return False
    return "NIX" in stemmer(d)


def unikke_retter(dishes):
    """Kataloget har dubletter (samme ret to gange) — de må ikke ende på samme
    liste, og to ens navne vælter slet-vælgerens set_options."""
    seen = set()
    ud = []
    for d in dishes:
        navn = normaliser_navn(d.get("ret", ""))
        if navn not in seen:
            seen.add(navn)
            ud.append(d)
    return ud


def indkoeb_pulje(dishes, n_min, saeson=None):
    """Kun retter der må laves NU; godkendt-kravet slækkes hvis puljen bliver
    for tynd (user 2026-08-03: listen SKAL leveres).

    Sæson er en SPÆRRING (user 2026-08-18): har retten en bestemt årstid i
    kolonne O, må den ikke foreslås i en anden. Tom celle / "Hele året" er
    lovlig året rundt, så puljen kan ikke tømmes af filteret alene.
    """
    dishes = unikke_retter(dishes)
    if not saeson:
        return _pulje_stige(dishes, n_min)
    return _pulje_stige([d for d in dishes if saeson_ok(d, saeson)], n_min)


def _pulje_stige(dishes, n_min):
    """Godkendte retter først; er der for få, slækkes kravet (user 2026-08-03).
    Et NIX udelukker altid — en gættet liste er bedre end en uønsket ret."""
    godkendt = [d for d in dishes if er_godkendt(d)]
    if len(godkendt) >= n_min:
        return godkendt, "godkendt"
    set_id = {id(d) for d in godkendt}
    delvis = [d for d in dishes if id(d) not in set_id and not er_afvist(d) and har_ja(d)]
    pulje = godkendt + delvis
    if len(pulje) >= n_min:
        return pulje, "delvise svar"
    set_id |= {id(d) for d in delvis}
    rest = [d for d in dishes if id(d) not in set_id and not er_afvist(d)]
    random.shuffle(rest)
    return pulje + rest, "delvise svar" if pulje else "uden svar"


def afventer(d):
    """Spurgt, men mangler stadig mindst ét svar (og ikke afvist)."""
    m, c = stemmer(d)
    return bool(d.get("spurgt")) and not er_afvist(d) and (not m or not c)


# Ret-TEMAER med egen karantæne på SPØRGE-siden (user-spec 2026-08-26:
# "maks spørg om 1 kartoffelsalat per måned"). Nøgle = delstreng af det
# normaliserede ret-navn, værdi = karantæne i dage.
#
# Parent B klagede over kartoffelsalat, og målingen gav hende ret: der blev
# spurgt om tre forskellige kartoffelsalater på fire dage (22., 24. og 25.
# august 2026). Puljen er ikke skæv — 6 af arkets 406 retter er kartoffelsalat
# — men INTET på spørge-siden så temaet. `naer_dublet` bruges kun når KURVEN
# fyldes, og `vaelg_spoergsmaal` balancerer på (børnevenlig, sværhedsgrad),
# akser hvor de seks fordeler sig pænt (Lyst kød / Salat / Vegetar / Rødt kød).
# Alle seks er desuden `Sommer`, som vejer 3× i august, så klyngen var
# sandsynlig, ikke uheldig.
RET_TEMA_KARANTAENE = {
    "kartoffelsalat": 30,
}


def ret_temaer(d):
    n = normaliser_navn(d.get("ret", ""))
    return {t for t in RET_TEMA_KARANTAENE if t in n}


def temaer_i_karantaene(dishes, today):
    """{tema} der er spurgt om for nylig → må ikke spørges om igen.

    Arkets `Sidst spurgt` ER logbogen over hvad vi har spurgt om, så der er
    ingen sidevogns-state at holde i sync. En ret uden dato er aldrig spurgt
    og bidrager ikke.
    """
    spaerret = set()
    for d in dishes:
        temaer = ret_temaer(d)
        if not temaer:
            continue
        d0 = parse_dato(d.get("spurgt"))
        if d0 is None:
            continue
        for t in temaer:
            if (today - d0).days < RET_TEMA_KARANTAENE[t]:
                spaerret.add(t)
    return spaerret


def kan_spoerges(d, reask_days, today):
    """Kandidat til dagens spørgsmål."""
    if er_afvist(d):
        return False
    m, c = stemmer(d)
    if m and c:
        return False  # færdigbehandlet
    d0 = parse_dato(d.get("spurgt"))
    if d0 is None:
        return True  # aldrig spurgt (eller ulæselig dato)
    if reask_days <= 0:
        return False
    return (today - d0).days >= reask_days


# =============================================================================
# Balance-styret udvælgelse
# =============================================================================
def buckets(dishes):
    out = {}
    for d in dishes:
        out.setdefault((er_boernevenlig(d), svaerhed(d)), []).append(d)
    return out


def bucket_targets(alle, bv_pct):
    """Ønsket andel pr. (børnevenlig, sværhedsgrad) — sværhedsgrader ligeligt."""
    svaerheder = sorted({svaerhed(d) for d in alle}) or ["Ukendt"]
    andel_bv = max(0.0, min(1.0, bv_pct / 100.0))
    t = {}
    for bv in (True, False):
        share_bv = andel_bv if bv else (1.0 - andel_bv)
        for sv in svaerheder:
            t[(bv, sv)] = share_bv / len(svaerheder)
    return t


def vaelg_spoergsmaal(alle, kandidater, antal, bv_pct, saeson=None):
    """Vælg de retter der bedst retter op på skævheden i den godkendte pulje."""
    godkendt = [d for d in alle if er_godkendt(d)]
    targets = bucket_targets(alle, bv_pct)
    tael = {k: 0 for k in targets}
    for d in godkendt:
        k = (er_boernevenlig(d), svaerhed(d))
        if k in tael:
            tael[k] += 1
    # Retter der allerede er spurgt og afventer svar tæller halvt med — ellers
    # spørger vi hele ugen ind i samme hjørne før det første svar lander.
    for d in alle:
        if afventer(d):
            k = (er_boernevenlig(d), svaerhed(d))
            if k in tael:
                tael[k] += 0.5

    pulje = buckets(kandidater)
    valgt = []
    for _ in range(antal):
        total = max(sum(tael.values()), 1.0)
        rangeret = sorted(
            (k for k in targets if pulje.get(k)),
            key=lambda k: (tael[k] / total) - targets[k],
        )
        if not rangeret:
            break
        k = rangeret[0]
        # Årstidens retter vejer 3× inden for bucket'en — helårsretter kan
        # stadig vinde, de er bare ikke lige så sandsynlige (user 2026-08-18).
        vaegte = [3.0 if saeson and saeson_eksplicit(d, saeson) else 1.0 for d in pulje[k]]
        d = random.choices(pulje[k], weights=vaegte, k=1)[0]
        pulje[k].remove(d)
        if not pulje[k]:
            del pulje[k]
        tael[k] += 1
        valgt.append(d)
    return valgt


RET_STOPORD = {
    "med",
    "og",
    "i",
    "til",
    "på",
    "uden",
    "af",
    "en",
    "et",
    "den",
    "det",
    "fra",
    "samt",
    "eller",
}


def ret_stamme(navn):
    """Rettens navn → mængde af 6-tegns ord-stammer, uden fyldord.

    Arket har nær-dubletter der IKKE er tegn-identiske ("Quinoasalat med
    edamame" vs. "Quinoasalat med edamamebønner"), så `normaliser_navn` alene
    kan ikke se at de er samme ret. 6 tegn er nok til at edamame/edamamebønner
    falder sammen, og kort nok til at bøjninger gør det samme.
    """
    ord = re.findall(r"[0-9a-zà-öø-ÿ]+", normaliser_navn(navn))
    return {o[:6] for o in ord if len(o) > 2 and o not in RET_STOPORD}


def naer_dublet(a, b, graense=0.5):
    """Jaccard på ord-stammer. 0,5 rammer de ægte dubletter uden at slå
    "Grillet X" og "Grillet Y" sammen (de deler kun tilberedningsordet)."""
    if not a or not b:
        return False
    return len(a & b) / float(len(a | b)) >= graense


def nylige_retter(*logs):
    """Normaliseret ret-navn → datoen for den SENESTE liste retten stod på.

    Loggene rulles allerede ved skrivning (HISTORIK_DAGE), så alt heri er
    "nyligt". Datoen gemmes fordi en tynd pulje skal kunne falde tilbage på den
    ret der har været væk LÆNGST — ikke på en tilfældig genganger.
    """
    ud = {}
    for log_ in logs:
        for p in log_ or []:
            dato = p.get("dato", "")
            for navn in p.get("retter") or []:
                n = normaliser_navn(navn)
                if dato > ud.get(n, ""):
                    ud[n] = dato
    return ud


def vaelg_indkoeb(
    pulje,
    maal,
    bv_pct,
    salat_hver=0,
    sundhed_maal=7.0,
    salat_reserve=None,
    saeson=None,
    nylige=None,
    bredere=None,
    vist_i_dag=None,
):
    """Fyld kurven til VÆGT `maal` med et mix på fire akser.

    Vægt (1d): et tilbehør tæller 0,5 — ellers ville "4 retter" kunne blive
    fire salater. Akserne (lavest score vinder, tilfældig rækkefølge bryder
    uafgjort):
      • mad-kategori  — den tungeste, så listen ikke bliver fire rødt-kød-retter
      • sværhedsgrad  — som før
      • børnevenlig   — holder andelen på bv_pct-slideren undervejs
      • sundhed       — trækker listens GENNEMSNIT mod sundhed_maal (kolonne M)
    Sundhed og kategori er stærkt korrelerede i arket (salat 8,0 → rødt kød
    5,4), så kategori-spredningen gør det meste af arbejdet; sundheds-leddet er
    bevidst let, så det kun afgør tætte valg.

    `salat_hver` (1c): hver N'te PLADS skal være en salat. Findes der ingen
    salat i puljen, tages den fra `salat_reserve` (bredere pulje) — der er nul
    GODKENDTE salater i arket pt., så et rent pulje-opslag ville aldrig give en.

    `nylige` (2026-08-20): en ret der har stået på en tidligere liste vælges
    ALDRIG så længe der findes en frisk kandidat. Det er en STIGE, ikke et
    filter — puljen er 17 godkendte sommer-retter og en liste bruger ~9 af dem,
    så et hårdt forbud ville tømme kurven. Rangen er (friskhed, styrke):

        aldrig set:  begge ja → godkendt (ja + måske/svarfrist) → ét ja/intet
        brugt før:   samme tre, ældst brugt først inden for hvert trin

    Friskhed slår altså approval (user 2026-08-20, efter to fejlende lister i
    træk: "den skal jo komme med en NY liste"), men et NIX udelukker stadig
    alt — `bredere` må kun indeholde retter uden NIX.

    Styrken skelner "begge ja" fra "godkendt" (2026-10-01): et udeblevet svar
    tæller som måske, og ja + måske ER godkendt — men som samme trin vandt
    Jordskokkesuppe (ja + svarfrist) en plads på 100 % af 2000 replays af
    30/9-listen, mens 21 friske begge-ja-retter i sæson stod ubrugte, fordi
    kategori-mixet afgør alt inden for et trin og den var eneste suppe.

    `vist_i_dag` er en TIE-BREAKER inden for samme trin, ikke et trin i sig
    selv: en kasseret kladde må ikke opbruge puljen (user 2026-08-20), så en
    godkendt frisk ret vælges igen frem for en ugodkendt, også selv om den
    stod på kladden for ti minutter siden.

    Nær-dubletter tælles som samme ret BEGGE veje: to retter der ligner
    hinanden kan ikke stå på samme liste, og en ret der ligner noget nyligt
    brugt arver dens dato ("Quinoasalat med edamame" + "… med edamamebønner"
    stod på samme liste 20/8).
    """
    rest = list(pulje) + list(bredere or [])
    random.shuffle(rest)
    reserve = list(salat_reserve or [])
    random.shuffle(reserve)
    andel_bv = max(0.0, min(1.0, bv_pct / 100.0))
    nylige = nylige or {}
    nylige_stammer = [(ret_stamme(n), dato) for n, dato in nylige.items()]

    stamme_cache = {}

    def stamme(d):
        n = normaliser_navn(d.get("ret", ""))
        if n not in stamme_cache:
            stamme_cache[n] = ret_stamme(n)
        return stamme_cache[n]

    def sidst_brugt(d):
        """Seneste dato hvor retten — ELLER en nær-dublet af den — var på en
        liste. Tom streng = aldrig set."""
        s = stamme(d)
        bedst = ""
        for t, dato in nylige_stammer:
            if dato > bedst and naer_dublet(s, t):
                bedst = dato
        return bedst

    vist = {normaliser_navn(n) for n in (vist_i_dag or [])}

    def rang(d):
        i_dag = 1 if normaliser_navn(d.get("ret", "")) in vist else 0
        brugt = sidst_brugt(d)
        styrke = 0 if begge_ja(d) else 1 if er_godkendt(d) else 2
        return (1 if brugt else 0, styrke, brugt, i_dag)

    valgte_stammer = []

    def ny_paa_listen(d):
        return not any(naer_dublet(stamme(d), s) for s in valgte_stammer)

    def foerste_brugbare(*niveauer):
        """Første niveau der har mindst én kandidat som ikke allerede ligner
        noget på listen. Et tomt niveau må falde VIDERE — brød man løkken her,
        stoppede en enkelt nær-dublet på salat-pladsen hele kurven."""
        for niveau in niveauer:
            ud = [d for d in niveau if ny_paa_listen(d)]
            if ud:
                return ud
        return []

    def bedste_lag(kandidater):
        """Kun kandidaterne på det laveste trin af stigen (se docstring)."""
        top = min(rang(d) for d in kandidater)
        return [d for d in kandidater if rang(d) == top]

    valgt, vaegt_sum, sund_sum = [], 0.0, 0.0
    brugt_sv, brugt_kat = {}, {}
    n_bv = 0
    while vaegt_sum < maal:
        plads = len(valgt) + 1
        # Salat-pladsen er en KVOTE (mindst én salat pr. `salat_hver` pladser),
        # ikke en ekstra salat: kategori-mixet vælger selv salater, og på 30/9-
        # replayet havde det brugt begge friske begge-ja-salater før plads 5,
        # så pladsen tvang en ja + svarfrist-salat ind på 64 % af listerne.
        vil_salat = (
            salat_hver > 0
            and plads % salat_hver == 0
            and sum(1 for v in valgt if er_salat(v)) < plads // salat_hver
        )
        kandidater = []
        if vil_salat:
            # Salat-pladsen tager friskhed FØR pulje-tilhør: der er ~18 friske
            # sommersalater i reserven og typisk nul godkendte, så et opslag i
            # `rest` alene ville servere den samme salat igen og igen.
            kandidater = foerste_brugbare(
                [d for d in rest if er_salat(d) and not sidst_brugt(d)],
                [d for d in reserve if not sidst_brugt(d)],
                [d for d in rest if er_salat(d)],
                reserve,
            )
        if not kandidater:
            kandidater = foerste_brugbare(rest)
        if not kandidater:
            break
        kandidater = bedste_lag(kandidater)

        def score(d):
            bv_efter = (n_bv + (1 if er_boernevenlig(d) else 0)) / plads  # noqa: B023 - min() runs now
            sund_efter = (sund_sum + sundhed(d)) / plads  # noqa: B023
            return (
                1.0 * brugt_kat.get(mad_kategori(d), 0)
                + 0.7 * brugt_sv.get(svaerhed(d), 0)
                + 2.0 * abs(bv_efter - andel_bv)
                + 0.5 * abs(sund_efter - sundhed_maal) / 10.0
                - (0.8 if saeson and saeson_eksplicit(d, saeson) else 0.0)
            )

        d = min(kandidater, key=score)
        for liste in (rest, reserve):
            if d in liste:
                liste.remove(d)
        valgte_stammer.append(stamme(d))
        brugt_kat[mad_kategori(d)] = brugt_kat.get(mad_kategori(d), 0) + 1
        brugt_sv[svaerhed(d)] = brugt_sv.get(svaerhed(d), 0) + 1
        n_bv += 1 if er_boernevenlig(d) else 0
        sund_sum += sundhed(d)
        vaegt_sum += kurv_vaegt(d)
        valgt.append(d)
    return valgt


# =============================================================================
# Ingredienser → indkøbsliste
# =============================================================================
def normaliser_navn(navn):
    n = re.sub(r"\s+", " ", navn.strip().lower())
    n = n.strip(" .,-–")
    return SYNONYMER.get(n, n)


def enheds_familie(enhed):
    if enhed in MASSE:
        return "masse"
    if enhed in VOLUMEN:
        return "volumen"
    return enhed or "stk"


def til_tal(s):
    try:
        return float(str(s).replace(",", ".").strip())
    except ValueError, AttributeError:
        return None


def parse_struct(struct):
    """'500|g|hakket oksekød;2|stk|løg' → [(mængde, enhed, navn)]"""
    ud = []
    for del_ in (struct or "").split(";"):
        bits = [b.strip() for b in del_.split("|")]
        if len(bits) < 3:
            continue
        m = til_tal(bits[0])
        if m is None:
            continue
        ud.append((m, bits[1].strip().lower(), normaliser_navn(bits[2])))
    return ud


_UNIT_ALT = "|".join(sorted((re.escape(u) for u in ALLE_ENHEDER), key=len, reverse=True))
ING_RE = re.compile(
    r"^\s*(?P<m>\d+(?:[.,]\d+)?)?\s*"
    r"(?P<enheder>(?:(?:" + _UNIT_ALT + r")(?![a-zA-ZæøåÆØÅ])\s*)*)"
    r"(?:\((?P<paren>[^)]*)\))?\s*"
    r"(?P<navn>.+?)\s*$",
    re.IGNORECASE,
)
PAREN_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*([a-zA-ZæøåÆØÅ]+)")


def _vaelg_enhed(tokens):
    """['g','små'] → ('g', ['små'])  ·  ['stort','bdt'] → ('bdt', []).

    Masse/volumen vinder altid (det er den mængde man køber efter). Ellers er
    den SIDSTE enhed den rigtige ('1 stort bdt' → bdt), og ord EFTER enheden
    hører til varenavnet ('500 g små kartofler' → små kartofler).
    """
    if not tokens:
        return "", []
    idx = next((i for i, t in enumerate(tokens) if t in MASSE or t in VOLUMEN), len(tokens) - 1)
    return tokens[idx], tokens[idx + 1 :]


def parse_fritekst(tekst):
    """Fallback: '2 ds (800 g) hakkede tomater' → (800, 'g', 'hakkede tomater').

    Parentesen vinder når den indeholder en rigtig mængde — det er den man
    faktisk skal købe efter.
    """
    ud = []
    for raw in re.split(r",(?![^(]*\))", tekst or ""):
        raw = raw.strip()
        if not raw:
            continue
        m = ING_RE.match(raw)
        if not m:
            ud.append((1.0, "stk", normaliser_navn(raw)))
            continue
        maengde = til_tal(m.group("m"))
        tokens = [t.lower() for t in (m.group("enheder") or "").split()]
        enhed, rest = _vaelg_enhed(tokens)
        navn = " ".join(rest + [m.group("navn") or ""]).strip()
        p = m.group("paren")
        if p:
            pm = PAREN_RE.search(p)
            if pm and pm.group(2).lower() in ALLE_ENHEDER:
                maengde = til_tal(pm.group(1))
                enhed = pm.group(2).lower()
        if maengde is None:
            maengde = 1.0
        ud.append((maengde, enhed or "stk", normaliser_navn(navn)))
    return ud


def ingredienser_for(d):
    if (d.get("struct") or "").strip():
        parsed = parse_struct(d["struct"])
        if parsed:
            return parsed
    return parse_fritekst(d.get("ingredienser", ""))


def _tal(v, decimaler=2):
    """2.0 → '2' · 1.2 → '1,2' · 2.5 → '2,5' (ingen falske nuller på listen)."""
    s = f"{v:.{decimaler}f}"
    if "." in s:  # kun decimaler må trimmes — ikke '500' → '5'
        s = s.rstrip("0").rstrip(".")
    return (s or "0").replace(".", ",")


def formatér_maengde(maengde, familie, enhed):
    if familie == "masse":
        if maengde >= 1000:
            return f"{_tal(maengde / 1000)} kg"
        return f"{_tal(maengde, 0)} g"
    if familie == "volumen":
        if maengde >= 1000:
            return f"{_tal(maengde / 1000)} L"
        if maengde >= 100:
            return f"{_tal(maengde / 100, 1)} dl"
        return f"{_tal(maengde, 0)} ml"
    return f"{_tal(maengde, 1)} {enhed}"


def indkoebsposter(retter, spring_basis_over=True, har_hjemme=None):
    """→ (poster, sprunget_over, trukket_fra) — den summerede liste som DATA.

    poster = [{"navn", "maengde", "enhed", "familie"}], hvor mængden er
    omregnet til familiens basis-enhed (masse → g, volumen → ml) og `enhed`
    er den enhed mængden faktisk er udtrykt i. For "styk"-familien er der
    ingen omregning, så enheden er rettens egen (stk/bdt/ds/…).

    Skilt ud fra `byg_indkoebsliste` 2026-08-31, fordi Nemlig-kurven har brug
    for summen som tal + enhed. Alternativet — at genparse de strenge vi selv
    lige har formateret — ville gøre en visuel ændring i listen til en tavs
    fejl i indkøbet.

    `har_hjemme` trækkes fra SUMMEN, ikke fra opskriften: retten skal stadig
    laves på sine 800 g, vi skal bare ikke købe dem vi har stående.
    """
    sum_ = {}
    sprunget = set()
    for d in retter:
        for maengde, enhed, navn in ingredienser_for(d):
            if not navn:
                continue
            if spring_basis_over and navn in BASISVARER:
                sprunget.add(navn)
                continue
            fam = enheds_familie(enhed)
            faktor = (
                MASSE.get(enhed)
                if fam == "masse"
                else VOLUMEN.get(enhed)
                if fam == "volumen"
                else 1.0
            )
            key = (navn, fam)
            post = sum_.setdefault(key, {"maengde": 0.0, "enhed": enhed})
            post["maengde"] += maengde * (faktor or 1.0)

    trukket = []
    for p in har_hjemme or []:
        enhed = (p.get("enhed") or "stk").strip().lower()
        fam = enheds_familie(enhed)
        post = sum_.get((normaliser_navn(p.get("vare", "")), fam))
        if not post:
            continue
        faktor = (
            MASSE.get(enhed) if fam == "masse" else VOLUMEN.get(enhed) if fam == "volumen" else 1.0
        )
        traek = min(post["maengde"], (til_tal(p.get("maengde")) or 0.0) * (faktor or 1.0))
        if traek <= 0:
            continue
        post["maengde"] -= traek
        trukket.append(
            f"{formatér_maengde(traek, fam, post['enhed'])} {normaliser_navn(p.get('vare', ''))}"
        )

    poster = []
    for (navn, fam), post in sorted(sum_.items(), key=lambda kv: kv[0][0]):
        if post["maengde"] <= 1e-6:  # dækket helt af det vi har hjemme
            continue
        enhed = "g" if fam == "masse" else "ml" if fam == "volumen" else post["enhed"]
        poster.append({"navn": navn, "maengde": post["maengde"], "enhed": enhed, "familie": fam})
    return poster, sorted(sprunget), trukket


def byg_indkoebsliste(retter, spring_basis_over=True, har_hjemme=None):
    """→ (linjer, sprunget_over, trukket_fra) — samme sum, menneske-formateret.

    Tynd skal om `indkoebsposter`. Signaturen er bevaret, så de fire kaldere
    ikke skal røres.
    """
    poster, sprunget, trukket = indkoebsposter(retter, spring_basis_over, har_hjemme)
    linjer = [
        f"{formatér_maengde(p['maengde'], p['familie'], p['enhed'])} {p['navn']}" for p in poster
    ]
    return linjer, sprunget, trukket


# =============================================================================
# Notifikationer
# =============================================================================
def spoergsmaal_payload(person, d, did=None):
    """`did` = det id spørgsmålet blev STILLET under (default: rettens id nu).

    Invariant: en påmindelse skal bære SAMME id som det oprindelige spørgsmål,
    så (a) tag'et erstatter den gamle notifikation i stedet for at lægge en ny
    ovenpå, og (b) svaret slår op i `spurgt[did]` og kan opløses til retten.
    Rettens id i arket kan nå at flytte sig imens (positionel ID-kolonne).
    """
    did = str(d["id"] if did is None else did)
    bv = "👶 Børnevenlig" if er_boernevenlig(d) else "🍷 Voksen"
    ing = d.get("ingredienser", "")
    if len(ing) > 240:
        ing = ing[:237] + "…"
    # NB: ingen `sticky` her — se ⛔️-noten i packages/notifikationer.yaml.
    # Sticky forhindrer også appen i at rydde notifikationen ved et KNAP-svar,
    # så spørgsmålet så ubesvaret ud uanset hvor mange gange man trykkede.
    fakta = ret_fakta(d)
    return {
        "title": "🍽️ Skal den med på indkøbslisten?",
        "message": f"{d['ret']}\n{bv} · {svaerhed(d)}"
        + (f"\n{fakta}" if fakta else "")
        + f"\n\n{ing}",
        "data": {
            "actions": [
                {"action": f"MAD_{person}_JA_{did}", "title": "JA!"},
                {"action": f"MAD_{person}_SUPERJA_{did}", "title": "SUPERJA!"},
                {"action": f"MAD_{person}_NIX_{did}", "title": "NIX!"},
            ],
            "tag": f"mad_ret_{did}_{person}",
            "group": "mad_spoergsmaal",
            # Rammer man ved siden af de tre knapper, skal man lande på
            # afstemningen — ikke på Opskrifter (user 2026-08-31).
            "url": "/mad-dash/afstemning",
            "clickAction": "/mad-dash/afstemning",
        },
    }


def paamind_payload(person, d, forsoeg, did=None):
    """Samme spørgsmål, samme knapper, samme tag (= erstatter den gamle) —
    men med forklaringen på hvorfor det kommer igen.

    Teksten er hele pointen for brugeren: uden den ligner en gentagelse en fejl
    i systemet, og han ville stadig ikke vide HVORFOR hans tryk forsvandt.
    """
    p = spoergsmaal_payload(person, d, did)
    # Samme spørgsmål som titel (2026-10-20): "Vi mangler stadig dit svar"
    # sagde ikke HVAD der manglede svar på, og VPN-forklaringen var jargon.
    p["title"] = "🔁 Skal den med på indkøbslisten?"
    p["message"] = (
        "Har du allerede svaret, nåede det ikke frem — prøv igen på hjemme-wifi.\n\n" + p["message"]
    )
    p["data"]["group"] = "mad_spoergsmaal"
    return p


def kvitterings_payload(person, d, svar, did=None, note=None):
    ikon = {"JA": "✅", "SUPERJA": "⭐", "NIX": "🚫", "MAASKE": "🤷"}.get(svar, "•")
    m, c = raa_stemmer(d)
    andre = "parent_b" if person == "parent_a" else "parent_a"
    andet_svar = c if person == "parent_a" else m
    if andet_svar:
        status = "Begge har svaret"
    elif svar_udloebet(d):
        status = f"{PEOPLE[andre]['navn']} nåede ikke at svare — det tæller som Måske"
    else:
        status = f"Afventer {PEOPLE[andre]['navn']}"
    # Tag = ASK-tidens id, så kvitteringen erstatter netop den notifikation
    # brugeren trykkede på (jf. samme invariant i spoergsmaal_payload).
    return {
        "message": f"{ikon} {d['ret']}: {svar}\n{status}" + (f"\n{note}" if note else ""),
        "data": {
            "tag": f"mad_ret_{str(d['id'] if did is None else did)}_{person}",
            "group": "mad_spoergsmaal",
        },
    }


# =============================================================================
# Modes
# =============================================================================
def spurgt_dato(d):
    """Arket skriver 'Wed Jul 29' (uden år), state-filen ISO — begge forekommer
    i samme datasæt, så streng-sortering ville blande dem alfabetisk."""
    raw = str(d.get("spurgt") or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        pass
    # Apps Script sender Date.toString(): "Mon Aug 03 2026 00:00:00 GMT+0200 (…)"
    tokens = raw.split()
    kort = " ".join(tokens[:4])
    for fmt in ("%a %b %d %Y", "%b %d %Y", "%d-%m-%Y", "%d/%m/%Y"):
        for kandidat in (
            raw,
            kort,
            " ".join(tokens[:3]),
            f"{' '.join(tokens[:3])} {now_local().year}",
        ):
            try:
                return datetime.strptime(kandidat, fmt).date()
            except ValueError:
                continue
    return None


def svar_tid(d):
    """Hvornår der sidst blev trykket på en svar-knap for retten (naiv lokaltid).

    Falder tilbage på 'Sidst spurgt' ved midnat for gamle stemmer fra før
    tidsstemplet fandtes. Alt gøres naivt, så et aware ISO-stempel og en ren
    dato kan sammenlignes uden TypeError.
    """
    raw = d.get("svar_at")
    if raw:
        try:
            return datetime.fromisoformat(str(raw)).replace(tzinfo=None)
        except ValueError:
            pass
    dt = spurgt_dato(d)
    return datetime.combine(dt, datetime.min.time()) if dt else None


def seneste_svar(dishes, antal=10):
    """De sidst besvarede retter — sorteret på hvornår SVARET kom ind.

    Tidligere sorteredes der på 'Sidst spurgt', fordi stemmerne ikke havde
    noget tidsstempel. Det gjorde kortet statisk: et nyt svar på et gammelt
    spørgsmål rykkede ikke op, og var alle spørgsmål stillet samme dag,
    afgjorde ret-navnet rækkefølgen (fejlklasse #14-familien: et felt der
    ikke varierer kan ikke bruges som sorteringsnøgle).
    """
    besvaret = [d for d in dishes if any(raa_stemmer(d)) and svar_tid(d)]
    besvaret.sort(key=lambda d: (svar_tid(d), str(d.get("ret"))), reverse=True)
    ud = []
    for d in besvaret[:antal]:
        m, c = raa_stemmer(d)
        # Et manglende svar TÆLLER som Måske når fristen er ude — men det vises
        # mærket, så kortet ikke påstår at nogen trykkede på noget.
        tomt = "🤷 udløbet" if svar_udloebet(d) else "—"
        ud.append(
            {
                "dato": (
                    svar_tid(d).strftime("%Y-%m-%d %H:%M")
                    if d.get("svar_at")
                    else svar_tid(d).date().isoformat()
                ),
                "ret": d.get("ret", "") + (" ⭐" if har_superja(d) else ""),
                "parent_a": m or tomt,
                "parent_b": c or tomt,
                "status": "Godkendt"
                if er_godkendt(d)
                else ("Afvist" if er_afvist(d) else ("Afventer" if afventer(d) else "Måske")),
            }
        )
    return ud


def bar_md(titel, par, i_alt, top=None, vis_pct=True, undertitel=None, fmt="{:.0f}"):
    """Vandret søjlediagram som markdown — Lovelace har ingen graf-kort til
    kategoriske tal, og formatet hører i datakilden (én formatter, ikke N
    kopier i YAML)."""
    if not par:
        return f"### {titel}\n\n_ingen data_"
    top = top or max(v for _, v in par) or 1
    linjer = [f"### {titel}", "", f"_{undertitel or f'{i_alt} retter i alt'}_", ""]
    for navn, v in par:
        blokke = "█" * max(1, round(v / top * 18))
        hale = f" · {round(v / i_alt * 100) if i_alt else 0}%" if vis_pct else ""
        linjer.append(f"`{blokke:<18}` **{fmt.format(v)}**{hale} — {navn}")
    return "\n".join(linjer)


def fordelinger_md(dishes):
    """(type_md, saeson_md, sundhed_md) — fordelinger over kataloget."""
    dishes = [d for d in unikke_retter(dishes) if not er_afvist(d)]
    n = len(dishes)
    typer = {}
    for d in dishes:
        k = (mad_kategori(d) or "Ukendt").strip().title()
        typer[k] = typer.get(k, 0) + 1
    saes = {s: 0 for s in ("Forår", "Sommer", "Efterår", "Vinter")}
    helaar = 0
    for d in dishes:
        truffet = [s for s in saes if saeson_eksplicit(d, s)]
        if truffet:
            for s in truffet:  # "Sommer/Efterår" tæller i begge
                saes[s] += 1
        else:
            helaar += 1
    nu = aktuel_saeson()
    saeson_par = [(f"{s} ← nu" if s == nu else s, v) for s, v in saes.items()]
    saeson_par.append(("Hele året (altid lovlige)", helaar))
    # Sundhed pr. kategori: skalaen er FAST 0-10, ikke feltets egen max —
    # ellers ville den sundeste kategori altid se ud som fuld score.
    sund = {}
    for d in dishes:
        sund.setdefault((mad_kategori(d) or "Ukendt").strip().title(), []).append(sundhed(d))
    sund_par = sorted(
        ((f"{k} ({len(v)} retter)", sum(v) / len(v)) for k, v in sund.items() if v),
        key=lambda kv: -kv[1],
    )
    snit = (sum(sundhed(d) for d in dishes) / n) if n else 0
    return (
        bar_md("Retter pr. type", sorted(typer.items(), key=lambda kv: -kv[1]), n),
        bar_md("Retter pr. årstid", saeson_par, n),
        bar_md(
            "Sundhed pr. kategori",
            sund_par,
            n,
            top=10.0,
            vis_pct=False,
            fmt="{:.1f}",
            undertitel=f"gennemsnit 0-10 · hele kataloget: {snit:.1f}",
        ),
    )


def opbyg_status(dishes, kilde):
    _ford = fordelinger_md(dishes)
    godkendt = [d for d in dishes if er_godkendt(d)]
    afvist = [d for d in dishes if er_afvist(d)]
    venter = [d for d in dishes if afventer(d)]
    uspurgt = [d for d in dishes if not d.get("spurgt") and not er_afvist(d)]

    balance = {}
    for d in godkendt:
        k = f"{'Børnevenlig' if er_boernevenlig(d) else 'Voksen'} · {svaerhed(d)}"
        balance[k] = balance.get(k, 0) + 1

    state = f"{len(godkendt)} godkendt · {len(venter)} afventer svar · {len(dishes)} retter i alt"
    attrs = {
        "friendly_name": "Mad — status",
        "icon": "mdi:silverware-fork-knife",
        "i_alt": len(dishes),
        "godkendt": len(godkendt),
        "afvist": len(afvist),
        "afventer_svar": len(venter),
        # Skævhed mellem de to tal er signaturen på tabte svar-tryk (svar-
        # knapper kræver hjemme-wifi/Tailscale) — derfor er de synlige på Mad-
        # siden og ikke kun i state-filen.
        "mangler_parent_a": sum(1 for d in venter if not stemmer(d)[0]),
        "mangler_parent_b": sum(1 for d in venter if not stemmer(d)[1]),
        "ikke_spurgt": len(uspurgt),
        "balance": balance,
        "godkendte_retter": sorted(d["ret"] for d in godkendt),
        "afventer": [
            f"{d['ret']} ({'M' if not stemmer(d)[0] else ''}"
            f"{'C' if not stemmer(d)[1] else ''} mangler)"
            for d in venter
        ],
        "seneste_svar": seneste_svar(dishes),
        "type_fordeling_md": _ford[0],
        "saeson_fordeling_md": _ford[1],
        "sundhed_fordeling_md": _ford[2],
        "kilde": kilde,
        "skriveadgang": kilde == "api",
        "opdateret": now_local().strftime("%Y-%m-%d %H:%M"),
    }
    return state, attrs


def naeste_indkoeb(states, today):
    ugedag = txt(states, E_BUY_UGEDAG, "Tirsdag")
    interval = max(1, int(num(states, E_BUY_INTERVAL, 2)))
    anker_raw = txt(states, E_BUY_ANKER, "2026-08-04")[:10]
    try:
        anker = datetime.strptime(anker_raw, "%Y-%m-%d").date()
    except ValueError:
        anker = today
    mål_wd = UGEDAGE.index(ugedag) if ugedag in UGEDAGE else 1

    d = today
    for _ in range(370):
        if d >= anker and d.weekday() == mål_wd and ((d - anker).days // 7) % interval == 0:
            return d, ugedag, interval, anker
        d += timedelta(days=1)
    return None, ugedag, interval, anker


SAESON_LAGER_MIN = 5  # færre end så mange = varsel
SAESON_VARSEL_DAGE = 14  # samme sæson varsles højst hver 14. dag


def saeson_lager_varsel(token, dishes, dry):
    """Varsl når en sæson er ved at løbe tør for ÅRSTIDSSPECIFIKKE retter.

    Helårsretter tælles ikke med: de bærer listen alligevel, så de ville
    maskere præcis det hul varslet findes for. Både den aktuelle og den
    kommende sæson tjekkes — et varsel der først kommer 1. december er
    ubrugeligt (user 2026-08-18).
    """
    today = now_local().date()
    st = load_state()
    sendt = dict(st.get("saeson_varsel") or {})
    aendret = False
    for naar, saeson in (
        ("nu", SAESON_MAANED[today.month]),
        ("snart", SAESON_MAANED[today.month % 12 + 1]),
    ):
        antal = sum(
            1 for d in unikke_retter(dishes) if saeson_eksplicit(d, saeson) and not er_afvist(d)
        )
        if antal >= SAESON_LAGER_MIN:
            if sendt.pop(saeson, None) is not None:
                aendret = True  # fyldt op igen → varslet kan gentages
            continue
        sidst = parse_dato(sendt.get(saeson))
        if sidst and (today - sidst).days < SAESON_VARSEL_DAGE:
            continue
        hvornaar = "nu" if naar == "nu" else "fra næste måned"
        push_notify(
            token,
            "mad_saeson_lager",
            f"🍂 {saeson} løber tør for retter",
            f"Kun {antal} {saeson.lower()}-retter tilbage (mindst "
            f"{SAESON_LAGER_MIN} ønskes) — de er de eneste der må foreslås "
            f"som sæsonretter {hvornaar}. Tilføj flere i arket.",
            dry=dry,
        )
        sendt[saeson] = today.isoformat()
        aendret = True
    if aendret:
        st["saeson_varsel"] = sendt
        save_state(st, dry)


def stem_kandidater(dishes):
    """Retter man kan stemme på fra Mad-siden, ældste spørgsmål først.

    Notifikations-knappen er et HTTP-kald tilbage til HA og kan tabes; siden
    kan ikke tabe et tryk (er man inde på den, kan man nå HA). Udvalget er de
    retter der faktisk mangler en stemme: alt der afventer svar, plus de retter
    på den aktuelle indkøbsliste der ikke er fuldt godkendte — det var netop
    dem user opdagede stod på listen uden Parent B's ja (2026-08-20).
    """
    paa_liste = set((load_state().get("indkoeb") or {}).get("retter") or [])
    ud, set_navne = [], set()
    for d in unikke_retter(dishes):
        if d.get("ret") in set_navne or er_afvist(d):
            continue
        if afventer(d) or (d.get("ret") in paa_liste and not er_godkendt(d)):
            set_navne.add(d["ret"])
            ud.append(d)
    # Ældste spørgsmål øverst; retter der aldrig er spurgt om lægger sig sidst.
    ud.sort(key=lambda d: (d.get("spurgt") or "9999", d.get("ret") or ""))
    return ud


def publish_afventer(token, dishes, dry):
    """Rækkefølgen — ÉT sted, så kort og knap er enige.

    Lovelace kan ikke loope over en dynamisk liste, så siden har faste slots
    (samme mønster som opskrift-kortene). Knappen i slot N kan ikke bære
    rettens navn — den er statisk YAML — så den sender bare sit slot-nummer,
    og `mode_stem_slot` slår op i PRÆCIS den sensor kortet blev tegnet efter.
    Ville scriptet i stedet genberegne listen, kunne den have flyttet sig
    siden kortet blev tegnet, og stemmen ville lande på nabo-retten.

    ÉN LISTE PR. PERSON, fordi det er den eneste måde "kun den der mangler kan
    stemme" kan tegnes: Lovelace-`visibility` har hverken template- eller
    attribut-betingelser (kun `state`/`numeric_state` på selve state'en), og en
    ukendt nøgle skjuler kortet TAVST — første forsøg gatede på en `attribute:`
    og leverede en side helt uden knapper. Med et antal pr. person i hver sin
    sensors state klarer `numeric_state above N-0.5` hele arbejdet.
    """
    liste = stem_kandidater(dishes)
    publish_sensor(
        token,
        "sensor.mad_afventer",
        len(liste),
        {
            "friendly_name": "Mad — afventer svar",
            "icon": "mdi:account-question",
            "unit_of_measurement": "retter",
            "retter": [d["ret"] for d in liste],
        },
        dry,
    )

    alle = {d["ret"]: d for d in unikke_retter(dishes)}
    for person in PEOPLE:
        idx = 0 if person == "parent_a" else 1
        poster = [
            {"ret": d["ret"], "krop": stem_krop(d, person)}
            for d in liste
            if not raa_stemmer(d)[idx]
        ]
        raekke = stem_hold(load_state(), person)
        if raekke:
            # Holdets rækkefølge først: ubesvarede på deres plads, besvarede
            # med svaret påskrevet — så slot N stadig er den ret man så.
            rest = {p["ret"]: p for p in poster}
            fast = []
            for navn in raekke:
                if navn in rest:
                    fast.append(rest.pop(navn))
                elif navn in alle and raa_stemmer(alle[navn])[idx]:
                    fast.append(
                        {
                            "ret": navn,
                            "krop": stem_krop(alle[navn], person),
                            "svar": raa_stemmer(alle[navn])[idx],
                        }
                    )
            poster = fast + [p for p in poster if p["ret"] in rest]
        publish_stem(token, person, poster, dry)


def stem_hold(st, person):
    """Den fastholdte rækkefølge på `person`s stem-liste ([] = intet hold)."""
    h = som_post((st.get("stem_hold") or {}).get(person) or {})
    try:
        til = datetime.fromisoformat(str(h.get("til")))
    except ValueError:
        return []
    if til.tzinfo is None or til < now_local():
        return []
    return [str(x) for x in (h.get("raekke") or [])]


def publish_stem(token, person, poster, dry):
    """Udgiv én persons stem-liste. `poster` = [{"ret", "krop"}, …].

    `poster` bærer HELE listen (ikke kun de 8 viste), fordi state'en er antallet
    af viste poster — klippede vi den til slots, ville `optimistisk_fjern`
    genudgive 7 i stedet for 15. Nummeret sidder ikke i `krop`, så listen kan
    klippes og genudgives uden at kende retterne. En post med `svar` er
    besvaret under et stem-hold (STEM_HOLD_MIN): den bliver i sit slot, så
    knapperne under de andre ikke flytter sig — `mangler` er det ærlige tal.
    """
    ikon = {"JA": "✅ JA", "SUPERJA": "⭐ SUPERJA", "NIX": "🚫 NIX", "MAASKE": "🤷 Måske"}
    attrs = {
        "friendly_name": f"Mad — {PEOPLE[person]['navn']} mangler at svare",
        "icon": "mdi:account-question",
        "unit_of_measurement": "retter",
        "mangler": sum(1 for p in poster if not p.get("svar")),
        "poster": poster,
    }
    for i in range(1, STEM_SLOTS + 1):
        p = poster[i - 1] if len(poster) >= i else None
        attrs[f"ret_{i}"] = p["ret"] if p else ""
        if p and p.get("svar"):
            svar = ikon.get(str(p["svar"]).upper(), p["svar"])
            attrs[f"linje_{i}"] = f"**{i}. {p['ret']}** · {svar}  \n{p['krop']}"
        else:
            attrs[f"linje_{i}"] = f"**{i}. {p['ret']}**  \n{p['krop']}" if p else ""
    publish_sensor(token, f"sensor.mad_stem_{person}", len(poster), attrs, dry)


def stem_krop(d, person):
    """Kortets tekst under rettens navn — set fra `person`s side."""
    m, c = raa_stemmer(d)
    andre = ("Parent B", c) if person == "parent_a" else ("Parent A", m)
    ud = [
        f"{mad_kategori(d)} · {svaerhed(d).lower()} · "
        f"{'børnevenlig' if er_boernevenlig(d) else 'voksen'}"
    ]
    if andre[1]:
        ud.append(f"✅ {andre[0]} har svaret **{andre[1]}**")
    elif svar_udloebet(d):
        ud.append(f"🤷 {andre[0]} svarede ikke i tide — tæller som **Måske**")
    else:
        ud.append(f"⏳ {andre[0]} mangler også")
    if har_superja(d):
        ud.append("⭐ **SUPERJA** — retten er sikret plads på næste indkøbsliste")
    if not d.get("spurgt"):
        ud.append("_Aldrig spurgt om — står på indkøbslisten uden godkendelse._")
    return "  \n".join(ud)


def optimistisk_fjern(token, states, person, navn, svar, dry):
    """Fjern retten fra kortet NU — før arket overhovedet er hentet.

    `fetch_dishes` tager 3-8 s mod Google Apps Script, og først DEREFTER kunne
    stemmen skrives og sensorerne genudgives. Trykket så derfor ud som om intet
    skete, og man trykkede igen (user 2026-08-20: "når der så er stemt skal den
    boks så forsvinde med det samme"). Sensoren indeholder allerede alt kortet
    tegner efter, så listen kan klippes og genudgives på ~0,2 s.

    Optimistisk, ikke autoritativt: den rigtige publicering et par sekunder
    senere overskriver med arkets facit, så en stemme der viser sig ugyldig
    (retten slettet i arket imens) får retten til at dukke op igen — hvilket er
    det ærlige svar. Et NIX afviser retten for BEGGE, så den ryger af begge
    lister; JA/Måske rører kun stemmerens egen.
    """
    # Stemmerens egen liste: retten bliver i sit slot med svaret påskrevet
    # (stem-holdet, user 14/10) — ellers rykker alt under den én plads op
    # midt i trykkene. Et NIX fjerner retten fra den ANDENS liste.
    ramt = list(PEOPLE) if svar == "NIX" else [person]
    for p in ramt:
        attrs = (states.get(f"sensor.mad_stem_{p}") or {}).get("attributes") or {}
        poster = []
        for x in attrs.get("poster") or []:
            if not isinstance(x, dict):
                continue
            if x.get("ret") == navn:
                if p != person:
                    continue
                x = dict(x, svar=svar)
            poster.append(x)
        publish_stem(token, p, poster, dry)


def mode_refresh(token, states, dishes, kilde, dry):
    state, attrs = opbyg_status(dishes, kilde)
    publish_sensor(token, "sensor.mad_status", state, attrs, dry)
    publish_afventer(token, dishes, dry)
    saeson_lager_varsel(token, dishes, dry)

    today = now_local().date()
    naeste, ugedag, interval, anker = naeste_indkoeb(states, today)
    publish_sensor(
        token,
        "sensor.mad_naeste_indkoeb",
        naeste.isoformat() if naeste else "ukendt",
        {
            "friendly_name": "Mad — næste indkøbsliste",
            "icon": "mdi:calendar-clock",
            "ugedag": ugedag,
            "interval_uger": interval,
            "anker": anker.isoformat(),
            "dage_til": (naeste - today).days if naeste else None,
            "aktiv": is_on(states, E_BUY_ON),
        },
        dry,
    )

    # Indkøbs-sensoren er REST-publiceret og dør ved restart — genskab fra state.
    st = load_state()
    gemt = st.get("indkoeb") or {}
    aktuel = gemte_retter(dishes, gemt)
    if aktuel:
        publish_indkoeb(token, states, aktuel, dry, gemt.get("genereret"), dishes=dishes)
    else:
        publish_opskrifter(token, states, dishes, st.get("historik"), dry)
    return state


def mode_ask(token, states, dishes, kilde, dry):
    if not is_on(states, E_ASK_ON):
        log("spørgsmål slået fra (input_boolean.mad_spoergsmaal_enabled)")
        return
    today = now_local().date()
    reask = int(num(states, E_ASK_REASK, 7))
    antal = max(1, int(num(states, E_ASK_ANTAL, 1)))
    bv_pct = num(states, E_BV_PCT, 50)

    kandidater = [d for d in dishes if kan_spoerges(d, reask, today)]
    if not kandidater:
        log("ingen retter tilbage at spørge om")
        logbook(token, "Mad", "Ingen nye retter at spørge om i dag", dry)
        return

    # Sæson (1a) er en SPÆRRING, ikke en præference (user 2026-08-18): en ret
    # med en bestemt årstid må ikke spørges om i en anden. Helårs-/tomme
    # retter passerer altid, så listen kan ikke tømmes helt af filteret.
    saeson = aktuel_saeson(today)
    kandidater = [d for d in kandidater if saeson_ok(d, saeson)]
    if not kandidater:
        msg = f"Ingen uspurgte retter i sæson ({saeson}) — spørger ikke i dag"
        log(msg)
        logbook(token, "Mad", msg, dry)
        return

    # TEMA-KARANTÆNE (user-spec 2026-08-26). Filtreres FØR salat-splittet, så
    # kvoten også gælder når dagens spørgsmål er tvunget til at være en salat —
    # to af de seks kartoffelsalater ligger netop i Salat-bucket'en, og uden
    # dette ville salat-kvoten være en bagdør uden om karantænen.
    spaerrede = temaer_i_karantaene(dishes, today)
    if spaerrede:
        foer = len(kandidater)
        kandidater = [d for d in kandidater if not (ret_temaer(d) & spaerrede)]
        log(
            f"tema-karantæne: {', '.join(sorted(spaerrede))} "
            f"({foer - len(kandidater)} retter sprunget over)"
        )
        if not kandidater:
            msg = (
                "Alle resterende retter er i tema-karantæne "
                f"({', '.join(sorted(spaerrede))}) — spørger ikke i dag"
            )
            log(msg)
            logbook(token, "Mad", msg, dry)
            return

    # Hver N'te SPØRGSMÅL er en salat (1c). Tælleren lever i state-filen, fordi
    # vi normalt kun spørger om én ret om dagen — en tæller inde i denne kørsel
    # ville aldrig nå fra 1 til 4.
    st0 = load_state()
    ask_nr = int(st0.get("ask_nr", 0) or 0)
    salat_hver = int(num(states, E_SALAT_HVER, 4))
    n_salat = sum(1 for i in range(antal) if salat_hver > 0 and (ask_nr + i + 1) % salat_hver == 0)
    salat_kand = [d for d in kandidater if er_salat(d)]
    valgt = vaelg_spoergsmaal(dishes, salat_kand, n_salat, bv_pct, saeson) if n_salat else []
    valgt_id = {id(d) for d in valgt}
    valgt += vaelg_spoergsmaal(
        dishes, [d for d in kandidater if id(d) not in valgt_id], antal - len(valgt), bv_pct, saeson
    )
    # Karantænen ovenfor kigger bagud i arket; den kan ikke se at DENNE kørsel
    # er ved at vælge to retter med samme tema (mad_spoergsmaal_antal > 1).
    if len(valgt) > 1:
        set_temaer, unikke = set(), []
        for d in valgt:
            t = ret_temaer(d)
            if t & set_temaer:
                log(
                    f"tema-karantæne: dropper {d.get('ret')} "
                    f"(samme tema som en anden ret i dagens batch)"
                )
                continue
            set_temaer |= t
            unikke.append(d)
        valgt = unikke
    modtagere = [p for p in PEOPLE if gate_ok(states, "mad_spoergsmaal", p)]
    if not modtagere:
        log("ingen modtagere (notifikations-gate) — spørger ikke i dag")
        return
    # Hvem manglede vi svar fra? En ret kan genspørges (mad_genspoerg_dage) efter
    # at den ene allerede har stemt — så skal den anden ikke se sit gamle svar
    # blive spurgt om igen, og påmindelses-vagten skal ikke tro at HAN mangler.
    sendt_til, venter_til = {}, {}
    for d in valgt:
        m, c = raa_stemmer(d)
        har = {"parent_a": m, "parent_b": c}
        modt_d = [p for p in modtagere if not har.get(p)]
        venter_d = [p for p in modt_d if skal_vente(states, p)]
        sendt_til[str(d["id"])] = modt_d
        venter_til[str(d["id"])] = venter_d
        for person in modt_d:
            if person in venter_d:
                log(f"{person} er ikke hjemme — {d['ret']} lagt i svar-køen")
                continue
            notify_direct(token, person, spoergsmaal_payload(person, d), dry)

    # Stempl "Sidst spurgt" — i arket hvis muligt, altid lokalt.
    ids = ",".join(str(d["id"]) for d in valgt)
    stemplet = False
    if api_available():
        try:
            sheet_api("asked", dry=dry, ids=ids)
            stemplet = True
        except Exception as err:
            log(f"kunne ikke stemple 'Sidst spurgt': {err} — lagt i synk-køen")
    st = load_state()
    if not stemplet and api_available():
        for d in valgt:
            koe_tilfoej(
                st,
                {"type": "asked", "id": str(d["id"]), "ret": d["ret"], "dato": today.isoformat()},
            )
    st.setdefault("spurgt", {})
    # Svar-fristen løber fra FØRSTE spørgsmål om retten. En genspørgsel
    # stempler 'Sidst spurgt' på ny, så uden dette felt kunne en kort
    # `mad_genspoerg_dage` udskyde timeouten i det uendelige (se svar_udloebet).
    tidl_foerst = {}
    for post in (st.get("spurgt") or {}).values():
        p = som_post(post)
        n = normaliser_navn(p.get("ret") or "")
        f = str(p.get("foerst") or p.get("dato") or "")
        if n and f and f < tidl_foerst.get(n, "9999"):
            tidl_foerst[n] = f
    for d in valgt:
        did = str(d["id"])
        foerst = tidl_foerst.get(normaliser_navn(d["ret"]), today.isoformat())
        # `dato` er dato-only (arkets format) — påmindelses-vagten skal kunne
        # regne i TIMER, så det præcise afsendelses-tidspunkt gemmes ved siden af.
        st["spurgt"][did] = {
            "dato": today.isoformat(),
            "ret": d["ret"],
            "foerst": foerst,
            "sendt": now_local().isoformat(timespec="seconds"),
            "til": sendt_til.get(did, []),
            "venter": venter_til.get(did, []),
        }
        st.setdefault("paamind", {}).pop(did, None)  # nyt spørgsmål = ny runde
        d["spurgt"] = today.isoformat()
        d["foerst_spurgt"] = foerst
    st["ask_nr"] = ask_nr + len(valgt)
    save_state(st, dry)

    publish_sensor(
        token,
        "sensor.mad_seneste_spoergsmaal",
        " · ".join(d["ret"] for d in valgt),
        {
            "friendly_name": "Mad — seneste spørgsmål",
            "icon": "mdi:comment-question-outline",
            "retter": [
                {
                    "id": d["id"],
                    "ret": d["ret"],
                    "boernevenlig": d.get("boernevenlig"),
                    "svaerhedsgrad": svaerhed(d),
                    "mad_kategori": mad_kategori(d),
                    "sundhed": sundhed(d),
                    "saeson": d.get("saeson") or "Hele året",
                    "tilbehoer": er_tilbehoer(d),
                    "ingredienser": d.get("ingredienser"),
                    "guide": d.get("guide"),
                }
                for d in valgt
            ],
            "sendt": now_local().strftime("%Y-%m-%d %H:%M"),
        },
        dry,
    )
    logbook(token, "Mad", "Spurgte om: " + ", ".join(d["ret"] for d in valgt), dry)
    log(f"spurgte om {len(valgt)} ret(ter): {[d['ret'] for d in valgt]}")


def spurgt_tidspunkt(post):
    """Hvornår spørgsmålet FAKTISK blev sendt (naiv lokaltid) — eller None.

    Nye poster bærer `sendt` med klokkeslæt; ældre har kun `dato` (arkets
    format). For de gamle bruges midnat, hvilket gør dem straks påmindelses-
    modne — netop det ophobede efterslæb vi vil have ryddet.
    """
    raw = post.get("sendt")
    if raw:
        try:
            return datetime.fromisoformat(str(raw)).replace(tzinfo=None)
        except ValueError:
            pass
    d0 = parse_dato(post.get("dato"))
    return datetime.combine(d0, datetime.min.time()) if d0 else None


def svar_vej_aaben(states, person):
    """Kan personens telefon overhovedet AFLEVERE et svar lige nu?

    Et knap-svar er et HTTP-kald tilbage til HA — det virker på hjemme-wifi
    eller med Tailscale, ikke på mobildata uden VPN. Trackerens `home` er det
    eneste signal vi har for "wifi virker med sikkerhed"; Tailscale kan vi ikke
    se pr. telefon. En tracker der er væk/ukendt tæller som ÅBEN (fail-open —
    en brudt tracker må ikke gøre vagten tavs).

    Parent B har et `hjemme`-anker i stedet, og dét fail-open'er IKKE: hendes
    device_tracker er med vilje permanent frossen på 'home' (iOS-tilladelsen
    er sat ned efter migrationen 08-15), så trackeren er nul evidens. Ankeret
    er iOS-genvejen, husets eneste vidne om hende, og kan kun sige on/off →
    alt andet end ON betyder "vent" (user 2026-08-20). At vente koster ikke
    spørgsmålet: det ligger i kø og leveres når hun kommer hjem.
    """
    anker = PEOPLE[person].get("hjemme")
    if anker:
        return is_on(states, anker, False)
    tr = txt(states, PEOPLE[person].get("tracker", ""), "").strip().lower()
    return tr in ("", "unknown", "unavailable", "none", "home")


def skal_vente(states, person):
    """Skal spørgsmålet HOLDES TILBAGE til personen er hjemme? (user 2026-08-20)

    Kun for den hvis svar-kanal beviseligt IKKE virker ude: Parent B har svaret
    på 30 af 47 spurgte retter, Parent A 46 af 47 — hans Android når HA over
    Tailscale uanset hvor han er, så at holde HANS spørgsmål tilbage ville
    forsinke uden at redde noget. Reglen hænger derfor på `hjemme`-ankeret, ikke
    på `svar_vej_aaben`: sidstnævnte er "er de hjemme lige nu", som også er
    falsk for en der sagtens kan svare.
    """
    return bool(PEOPLE[person].get("hjemme")) and not svar_vej_aaben(states, person)


def mode_paamind(token, states, dishes, dry):
    """Send ubesvarede ret-spørgsmål igen — helst mens telefonen er hjemme.

    Baggrund (user 2026-08-06): svarer man uden hjemme-wifi/Tailscale, når
    action-kaldet aldrig frem til HA. Appen rydder notifikationen ved tryk
    UANSET (autoCancel), og kvitteringen udebliver — så stemmen er tabt, og
    familien tror de har stemt. `sticky: true` er ikke en udvej: det blev
    prøvet 2026-07-30b og slog appens oprydning fra, så man slet ikke kunne
    svare (rullet tilbage samme dag).
    Målt facit i state-filen 2026-08-06: 25 retter spurgt, Parent A 22 stemmer,
    Parent B 4 — 18 retter mangler hendes svar.
    """
    if not is_on(states, E_REM_ON):
        log("påmindelser slået fra (input_boolean.mad_paamind_enabled)")
        return 0
    efter_t = num(states, E_REM_EFTER, 6)
    maks = int(num(states, E_REM_MAKS, 2))
    # 0 = send ALDRIG når man er ude (user-valg 2026-08-06). Fallback'en er
    # bevidst 0 og ikke en positiv værdi: kan vi ikke læse slideren, skal vi
    # falde tilbage til den KONSERVATIVE adfærd — en påmindelse sendt til en
    # telefon uden svar-vej er præcis den tabte stemme featuren skal forhindre.
    ude_t = num(states, E_REM_UDE, 0)
    # Efter genspørg-vinduet overtager det DAGLIGE spørgsmål selv (kan_spoerges
    # gør retten til kandidat igen) — jager vi videre her, ville de to kanaler
    # spørge om det samme, og en bunke gamle retter kunne aldrig løbe tør.
    maks_alder_t = max(1.0, num(states, E_ASK_REASK, 7)) * 24
    nu = now_local().replace(tzinfo=None)

    st = load_state()
    spurgt = st.setdefault("spurgt", {})
    paamind = st.setdefault("paamind", {})
    sidst_pers = st.setdefault("paamind_sidst", {})

    # Opløs HVER post til den ret den faktisk handler om (navnet vinder over
    # id'et) FØR vi ser på stemmer. Uden det læste vagten nabo-rettens tomme
    # felter og mindede om en ret brugeren aldrig har set — se
    # ret_bag_spoergsmaal for det målte facit 2026-08-07.
    opløst = {}
    for did, post in list(spurgt.items()):
        p = som_post(post)
        d = ret_bag_spoergsmaal(did, p.get("ret"), dishes)
        if d is None:  # ret slettet i arket
            spurgt.pop(did, None)
            paamind.pop(did, None)
            continue
        n_id = str(d["id"])
        t0 = spurgt_tidspunkt(p)
        tidl = opløst.get(n_id)
        if tidl is None:
            opløst[n_id] = (did, p, d, t0)
            continue
        # To poster peger på SAMME ret (fx spurgt igen efter en række-flytning):
        # behold den nyeste, og glem den anden så den ikke påminder dobbelt.
        nyest = t0 is not None and (tidl[3] is None or t0 > tidl[3])
        taber = tidl[0] if nyest else did
        spurgt.pop(taber, None)
        paamind.pop(taber, None)
        if nyest:
            opløst[n_id] = (did, p, d, t0)

    # --- Første levering: spørgsmål der ALDRIG blev sendt, fordi personen ikke
    # var hjemme da de blev stillet. De er ikke påmindelser — hun har ikke set
    # dem endnu — så de må hverken bruge et påmindelses-forsøg eller vente på
    # freds-vinduet. Ét ad gangen pr. kørsel, så en aftens hjemkomst ikke
    # bliver til en byge af pushes.
    pr_person = {}
    leveret = []
    for did, p, d, _t in opløst.values():
        venter = [x for x in (p.get("venter") or []) if x in PEOPLE]
        if not venter or er_afvist(d):
            continue
        m, c = stemmer(d)
        har = {"parent_a": m, "parent_b": c}
        for person in list(venter):
            if har.get(person):  # nåede at svare ad anden vej
                venter.remove(person)
                continue
            if pr_person.get(person, 0) >= PAAMIND_PR_KOERSEL:
                continue
            if not svar_vej_aaben(states, person):
                continue
            if not gate_ok(states, "mad_spoergsmaal", person):
                continue
            notify_direct(token, person, spoergsmaal_payload(person, d), dry)
            venter.remove(person)
            pr_person[person] = pr_person.get(person, 0) + 1
            # n=0: ingen påmindelse brugt. `sidst` er leverings-tidspunktet, så
            # fredsvinduet tælles fra da hun faktisk SÅ spørgsmålet.
            paamind.setdefault(did, {})[person] = {
                "n": 0,
                "sidst": now_local().isoformat(timespec="seconds"),
            }
            leveret.append(f"{PEOPLE[person]['navn']}: {d['ret']}")
        p["venter"] = venter
        spurgt[did] = p

    kandidater = []
    for did, p, d, _t in opløst.values():
        if er_afvist(d):
            paamind.pop(did, None)
            continue
        m, c = stemmer(d)
        har = {"parent_a": m, "parent_b": c}
        # Legacy-poster ved ikke hvem der fik spørgsmålet — antag begge.
        til = p.get("til") or list(PEOPLE)
        # Én der stadig står i køen har aldrig SET spørgsmålet — så er en
        # påmindelse forkert; første-leveringen ovenfor ejer dem.
        i_koe = p.get("venter") or []
        mangler = [x for x in til if x in PEOPLE and not har.get(x) and x not in i_koe]
        if not mangler:
            paamind.pop(did, None)  # færdigbesvaret → glem tælleren
            continue
        t0 = spurgt_tidspunkt(p)
        if t0 is None:
            continue
        for person in mangler:
            if PEOPLE[person].get("paamind") == "side":
                continue  # side_paamind ejer hende
            spor = som_post(paamind.get(did, {}).get(person, {}), "sidst")
            n = int(spor.get("n") or 0)
            if n >= maks:
                continue
            # Afstanden til FORRIGE kontakt (spørgsmål eller påmindelse) styres
            # af samme slider — den betyder "hvor længe får man fred".
            try:
                sidst = (
                    datetime.fromisoformat(str(spor.get("sidst"))).replace(tzinfo=None)
                    if spor.get("sidst")
                    else t0
                )
            except ValueError:
                sidst = t0
            if (nu - sidst).total_seconds() / 3600 < efter_t:
                continue
            alder_t = (nu - t0).total_seconds() / 3600
            if alder_t > maks_alder_t:
                continue
            if not svar_vej_aaben(states, person):
                # Ude: vent til de er hjemme — en påmindelse der også går tabt
                # bruger et forsøg uden at kunne indbringe et svar.
                if ude_t <= 0 or alder_t < ude_t:
                    continue
            if not gate_ok(states, "mad_spoergsmaal", person):
                continue
            kandidater.append((t0, did, person, d, n))

    # Ældste ubesvarede ret først.
    kandidater.sort(key=lambda k: k[0])
    sendt = []
    for _t0, did, person, d, n in kandidater:
        if pr_person.get(person, 0) >= PAAMIND_PR_KOERSEL:
            continue
        # Loftet gælder på tværs af KØRSLER, ikke kun inde i denne: uden det
        # ville /40-tick'en tømme hele bunken i løbet af en formiddag.
        try:
            forrige = (
                datetime.fromisoformat(str(sidst_pers.get(person))).replace(tzinfo=None)
                if sidst_pers.get(person)
                else None
            )
        except ValueError:
            forrige = None
        if forrige and (nu - forrige).total_seconds() / 3600 < efter_t:
            continue
        pr_person[person] = pr_person.get(person, 0) + 1
        stempel = now_local().isoformat(timespec="seconds")
        notify_direct(token, person, paamind_payload(person, d, n + 1, did), dry)
        paamind.setdefault(did, {})[person] = {"n": n + 1, "sidst": stempel}
        sidst_pers[person] = stempel
        sendt.append(f"{PEOPLE[person]['navn']}: {d['ret']} ({n + 1}/{maks})")

    side = side_paamind(token, states, dishes, st, dry)
    if side:
        sendt.append(side)

    if leveret:
        logbook(
            token,
            "Mad",
            "Ventende ret-spørgsmål leveret ved hjemkomst — " + ", ".join(leveret),
            dry,
        )
        log(f"leverede {len(leveret)} ventende spørgsmål: {leveret}")
    if sendt:
        logbook(token, "Mad", "Påmindelse om ubesvarede retter — " + ", ".join(sendt), dry)
        log(f"sendte {len(sendt)} påmindelse(r): {sendt}")
    if not sendt and not leveret:
        log("ingen påmindelser at sende")
    # Oprydningen (færdigbesvarede/slettede retter) skal gemmes uanset.
    save_state(st, dry)
    return len(sendt) + len(leveret)


def side_paamind(token, states, dishes, st, dry):
    """Én samlet "stem på Mad-siden" i stedet for en påmindelse pr. ret.

    Kun for personer med `paamind: "side"`. Sendes tidligst kl. E_SIDE_TID
    (automationen stopper kl. 22), kun hjemme, kun når mindst E_SIDE_MIN retter
    venter på DERES svar på siden, og højst hver E_SIDE_DAGE dag regnet fra det
    seneste af påmindelsen og deres egen seneste stemme — har hun selv stemt i
    går, er der intet at minde om. Returnerer en log-tekst, eller "".
    """
    kl = _hhmm(txt(states, E_SIDE_TID)) or 20 * 60
    nu = now_local()
    if nu.hour * 60 + nu.minute < kl:
        return ""
    dage = max(1.0, num(states, E_SIDE_DAGE, 3))
    min_retter = max(1, int(num(states, E_SIDE_MIN, 3)))
    sidst_side = st.setdefault("side_paamind", {})
    liste = stem_kandidater(dishes)
    for person, cfg in PEOPLE.items():
        if cfg.get("paamind") != "side":
            continue
        idx = 0 if person == "parent_a" else 1
        n = sum(1 for d in liste if not raa_stemmer(d)[idx])
        if n < min_retter:
            continue
        # Hendes seneste stemme = stem-holdets udløb minus holdet (sættes ved
        # HVER stemme, fra siden såvel som fra en knap).
        senest = []
        for raa in (
            sidst_side.get(person),
            som_post((st.get("stem_hold") or {}).get(person) or {}).get("til"),
        ):
            try:
                t = datetime.fromisoformat(str(raa))
            except TypeError, ValueError:
                continue
            if t.tzinfo is None:
                continue
            if raa != sidst_side.get(person):
                t -= timedelta(minutes=STEM_HOLD_MIN)
            senest.append(t)
        if senest and (nu - max(senest)).total_seconds() < dage * 86400 - 3600:
            continue
        if not svar_vej_aaben(states, person):
            continue
        if not gate_ok(states, "mad_spoergsmaal", person):
            continue
        notify_direct(
            token,
            person,
            {
                "title": f"🍽️ {n} {'ret venter' if n == 1 else 'retter venter'} på din stemme",
                "message": "Tryk her og stem på Mad-siden, så kommer dine "
                "ønsker med på indkøbslisten.",
                "data": {
                    "tag": f"mad_side_{person}",
                    "group": "mad_spoergsmaal",
                    "url": "/mad-dash/afstemning",
                    "clickAction": "/mad-dash/afstemning",
                },
            },
            dry,
        )
        sidst_side[person] = nu.isoformat(timespec="seconds")
        return f"{cfg['navn']}: Mad-siden ({n} retter)"
    return ""


FJERN_TOM = "—"


def gemte_retter(dishes, gemt):
    """Den aktuelle indkøbsliste slået op i kataloget (nøgle: rettens navn)."""
    byname = {}
    for d in dishes:
        byname.setdefault(d.get("ret", ""), d)
    return [byname[n] for n in (gemt.get("retter") or []) if n in byname]


def har_hjemme_for(st, genereret):
    """Varer vi allerede har stående — gælder KUN den liste de blev sat på.

    Uden bindingen til `genereret` ville en glemt post trække fra hver eneste
    fremtidig liste i tavshed; en ny liste får et nyt stempel og starter forfra.
    """
    return [p for p in (st.get("har_hjemme") or []) if p.get("liste") == genereret]


def opdater_historik(historik, valgt, genereret):
    """Rullende log over hvilke retter der HAR været på en indkøbsliste (1b).

    Gemmer navne, ikke opskrifter: arket er sandheden, så en rettet opskrift
    slår igennem med det samme. Dagens post overskrives (en liste kan
    genereres om / redigeres med --fjern-valgt), ældre poster beholdes.
    """
    dato = str(genereret)[:10]
    ud = [p for p in (historik or []) if p.get("dato") != dato]
    ud.append({"dato": dato, "retter": [d["ret"] for d in valgt]})
    graense = (now_local().date() - timedelta(days=HISTORIK_DAGE)).isoformat()
    return sorted([p for p in ud if p.get("dato", "") >= graense], key=lambda p: p["dato"])


def opdater_foreslaaet(foreslaaet, valgt, genereret):
    """Retter der har været vist på en KLADDE i dag — kun i dag.

    `historik` er de leverede lister og er den rigtige gentagelses-spærring.
    Denne er en anden ting: laves listen om, skal den nye kladde helst ikke vise
    de samme retter igen med det samme. Men en kasseret kladde må IKKE opbruge
    puljen (user 2026-08-20: *"de skal ikke opbruges"*) — 17 godkendte
    sommer-retter tåler ikke at tre kladder brænder 22 navne. Derfor:
    kun dagens post gemmes, og den bruges kun som tie-breaker, aldrig som
    spærring (se `vaelg_indkoeb`).
    """
    dato = str(genereret)[:10]
    navne = []
    for p in foreslaaet or []:
        if p.get("dato") == dato:
            navne = list(p.get("retter") or [])
    for d in valgt:
        if d["ret"] not in navne:
            navne.append(d["ret"])
    return [{"dato": dato, "retter": navne}]


def guide_trin(guide):
    """Fritekst-guide → nummererbare trin. Et sætningsskift kræver BÅDE '.' og
    et stort begyndelsesbogstav efter, fordi danske opskrifter er fulde af
    forkortelser ('ca. 35 minutter', '2 stk. squash') der ellers ville dele et
    trin midt over. Er guiden allerede skrevet med linjeskift, respekteres den.

    Arkets nyere trin-for-trin-format nummererer selv ('1. Forberedelse: ...').
    Numrene fjernes her, så rækkefølgen ejes af formatteren alene — ellers
    afhænger den af hvordan trinnene blev splittet."""
    tekst = (guide or "").strip()
    if not tekst:
        return []
    if "\n" in tekst:
        raa = [l.strip() for l in tekst.splitlines() if l.strip()]
    else:
        raa = [t.strip() for t in re.split(r"(?<=[.!?])\s+(?=[A-ZÆØÅ])", tekst) if t.strip()]
    trin = [re.sub(r"^(?:[-*•]\s*)?\d{1,2}\s*[.):]\s+", "", t).strip() for t in raa]
    return [t for t in trin if t]


def opskrift_md(o, d):
    """Markdown-kortet + oversigtslinjen for ÉN ret. Formatet bor her — ikke i
    dashboardets otte kort-slots, som ellers ville divergere ved første
    formatrettelse (#2). Sætter `linje` på o som sidegevinst."""
    tid = f"⏱️ **{o['tilberedningstid']} min**" if o["tilberedningstid"] else ""
    sund = f"❤️ {o['sundhed']:g}/10" if o["sundhed"] is not None else ""
    dato = f"🗓️ {o['dato'][8:10]}-{o['dato'][5:7]}" if o.get("dato") else ""
    meta = [x for x in (tid, f"{o['ikon']} {o['mad_kategori'].lower()}", sund, dato) if x]
    o["linje"] = " · ".join(x for x in (f"{o['ikon']} **{o['ret']}**", tid, sund) if x)

    varer = byg_indkoebsliste([d], False)[0] if d else []
    if not varer:
        varer = [v.strip() for v in (o["ingredienser"] or "").split(",") if v.strip()]

    ud = [f"## {o['ikon']} {o['ret']}", "", " · ".join(meta), "", "**Ingredienser**", ""]
    ud += [f"- {v}" for v in varer] if varer else ["_Ikke angivet i arket._"]
    ud += ["", "**Sådan gør du**", ""]
    trin = guide_trin(o["guide"])
    if len(trin) > 1:
        ud += [f"{i}. {t}" for i, t in enumerate(trin, 1)]
    else:
        ud += [trin[0] if trin else "_Ingen guide i arket._"]
    return "\n".join(ud)


def publish_opskrifter(token, states, dishes, historik, dry):
    """De fulde opskrifter for retterne på den AKTUELLE indkøbsliste (1b).

    Var et dato-vindue (14 dage) indtil 2026-08-20 — men et vindue og en liste
    er ikke det samme: en liste leveres hver 2. uge, så vinduet holdt forrige
    kurv i live ved siden af den nye ("ugens opskrifter fanen har retter fra en
    tidligere liste"). Nummereringen 1..8 peger desuden på faste undersider, så
    en ekstra kurv i toppen skubber dagens retter ud af deres egne kort.
    """
    byname = {}
    for d in dishes or []:
        byname.setdefault(d.get("ret", ""), d)

    poster = sorted(historik or [], key=lambda p: p.get("dato", ""))
    aktuel = poster[-1] if poster else {"dato": None, "retter": []}

    set_navne, opskrifter = set(), []
    for navn in aktuel.get("retter") or []:
        if navn in set_navne:
            continue
        set_navne.add(navn)
        d = byname.get(navn)
        o = {
            "ret": navn,
            "dato": aktuel.get("dato"),
            "guide": (d or {}).get("guide") or "",
            "ingredienser": (d or {}).get("ingredienser") or "",
            "tilberedningstid": (d or {}).get("tilberedningstid") or "",
            "mad_kategori": mad_kategori(d) if d else "Ukendt",
            "sundhed": sundhed(d) if d else None,
            "markering": godkendelse(d)["markering"] if d else "",
        }
        o["ikon"] = kategori_ikon(o["mad_kategori"])
        o["md"] = opskrift_md(o, d)
        opskrifter.append(o)

    # State er ANTALLET, ikke en sætning: Mad-siden har ét kort pr. opskrift, og
    # lovelace kan KUN skjule dem med `numeric_state` — der findes ingen
    # template-betingelse i card/section-visibility (verificeret 2026-08-17,
    # hvor en `condition: template` tavst skjulte alle otte kort). Enheden gør
    # at badges stadig læser "5 opskrifter".
    publish_sensor(
        token,
        "sensor.mad_opskrifter",
        len(opskrifter),
        {
            "friendly_name": "Mad — opskrifter (denne liste)",
            "icon": "mdi:chef-hat",
            "unit_of_measurement": "opskrifter",
            "liste_dato": aktuel.get("dato"),
            "opskrifter": opskrifter,
        },
        dry,
    )


def publish_indkoeb(token, states, valgt, dry, genereret=None, dishes=None, fjernet_tilfoej=None):
    """Sensor + gemt liste + slet-vælger. Eneste skriver af indkøbs-tilstanden.

    `fjernet` (2026-09-23, user-bug "udskift vælger den ret jeg lige slettede")
    er de retter der er taget AF DENNE liste med 🗑️/🔄. De følger listen (samme
    `genereret`) og nulstilles af en ny liste, så de kun spærrer for udskift-
    kandidaterne mens man retter DENNE liste til.
    """
    genereret = genereret or now_local().strftime("%Y-%m-%d %H:%M")
    st = load_state()
    forrige = st.get("indkoeb") or {}
    fjernet = list(forrige.get("fjernet") or []) if forrige.get("genereret") == genereret else []
    for n in fjernet_tilfoej or []:
        if n not in fjernet:
            fjernet.append(n)
    haves = har_hjemme_for(st, genereret)
    linjer, sprunget, trukket = byg_indkoebsliste(valgt, is_on(states, E_SKIP_BASIS), haves)
    ret_linjer = [
        f"{i + 1}. {d['ret']}"
        f" ({'børnevenlig' if er_boernevenlig(d) else 'voksen'}, {svaerhed(d).lower()}"
        f"{', tilbehør' if er_tilbehoer(d) else ''}"
        f", {mad_kategori(d).lower()})"
        + (f"\n   {ret_fakta(d)}" if ret_fakta(d) else "")
        + (f"\n   ⚠️ {godkendelse(d)['markering']}" if godkendelse(d)["markering"] else "")
        for i, d in enumerate(valgt)
    ]
    besked = (
        (
            "🍽️ RETTER\n"
            + "\n".join(ret_linjer)
            + "\n\n🛒 INDKØB\n"
            + "\n".join("• " + l for l in linjer)
        )
        if valgt
        else "Indkøbslisten er tom."
    )
    if sprunget:
        besked += "\n\n(basisvarer udeladt: " + ", ".join(sprunget) + ")"
    if trukket:
        besked += "\n\n(haves hjemme, trukket fra: " + ", ".join(trukket) + ")"

    publish_sensor(
        token,
        "sensor.mad_indkoebsliste",
        f"{len(valgt)} retter · {len(linjer)} varer",
        {
            "friendly_name": "Mad — indkøbsliste",
            "icon": "mdi:cart-outline",
            "retter": [
                {
                    "ret": d["ret"],
                    "id": str(d.get("id", "")),
                    "boernevenlig": d.get("boernevenlig"),
                    "svaerhedsgrad": svaerhed(d),
                    "guide": d.get("guide"),
                    "tilbehoer": er_tilbehoer(d),
                    "vaegt": kurv_vaegt(d),
                    "mad_kategori": mad_kategori(d),
                    "sundhed": sundhed(d),
                    "ikon": kategori_ikon(mad_kategori(d)),
                    "saeson": d.get("saeson") or "Hele året",
                    "tilberedningstid": d.get("tilberedningstid") or "",
                    "ingredienser": byg_indkoebsliste([d], False)[0],
                    **godkendelse(d),
                }
                for d in valgt
            ],
            "ikke_begge_ja": sum(1 for d in valgt if not godkendelse(d)["begge_ja"]),
            "varer": linjer,
            "udeladt": sprunget,
            "har_hjemme": trukket,
            "tekst": besked,
            "kurv_vaegt": round(sum(kurv_vaegt(d) for d in valgt), 1),
            "sundhed_gns": round(sum(sundhed(d) for d in valgt) / len(valgt), 1) if valgt else 0,
            "kategorier": sorted({mad_kategori(d) for d in valgt}),
            "genereret": genereret,
        },
        dry,
    )

    # Nøglen er NAVNET: arkets id-kolonne har dubletter (id 76-80 findes to
    # gange), så et id-opslag kan lande på en helt anden ret.
    st["indkoeb"] = {
        "retter": [d["ret"] for d in valgt],
        "genereret": genereret,
        "fjernet": fjernet,
    }
    st["historik"] = opdater_historik(st.get("historik"), valgt, genereret)
    st["foreslaaet"] = opdater_foreslaaet(st.get("foreslaaet"), valgt, genereret)
    st["har_hjemme"] = haves  # poster fra ældre lister ryger her
    save_state(st, dry)
    publish_opskrifter(token, states, dishes if dishes is not None else valgt, st["historik"], dry)

    if dry:
        log(f"(dry) slet-vælger = {[d['ret'] for d in valgt]}")
    else:
        ha_post(
            token,
            "/api/services/input_select/set_options",
            {"entity_id": E_FJERN, "options": [FJERN_TOM] + sorted({d["ret"] for d in valgt})},
        )
        ha_post(
            token,
            "/api/services/input_select/select_option",
            {"entity_id": E_FJERN, "option": FJERN_TOM},
        )
    return linjer, sprunget, besked


def mode_indkoeb(token, states, dishes, kilde, dry, force=False):
    if not is_on(states, E_BUY_ON):
        log("indkøbsliste slået fra")
        return
    today = now_local().date()
    naeste, ugedag, interval, anker = naeste_indkoeb(states, today)
    if not force and naeste != today:
        log(f"ikke indkøbsdag i dag (næste: {naeste})")
        return
    if not force and sprunget_i_dag(states, today):
        msg = (
            "Indkøbsliste sprunget over: du svarede i morges at køleskabet"
            " stadig er fyldt. Kadencen er urørt — næste indkøbsdag falder"
            " som normalt."
        )
        log(msg)
        logbook(token, "Mad", msg, dry)
        return

    n_min = int(num(states, E_RETTER_MIN, 3))
    n_max = max(n_min, int(num(states, E_RETTER_MAX, 4)))
    saeson = aktuel_saeson(today)
    pulje, pulje_kilde = indkoeb_pulje(dishes, n_min, saeson)
    if not pulje:
        msg = "Ingen brugbare retter (alle afvist eller katalog tomt) — ingen indkøbsliste."
        log(msg)
        logbook(token, "Mad", msg, dry)
        return

    # Målet er en VÆGT, ikke et antal (1d) — kurven kan derfor rumme flere
    # retter end n_max hvis nogle af dem er tilbehør.
    maal = random.randint(n_min, n_max)
    st = load_state()
    # Kun LEVEREDE lister spærrer. Dagens kasserede kladder er en tie-breaker,
    # ikke en spærring — ellers opbruger en "lav den om" puljen (user 08-20).
    nylige = nylige_retter(st.get("historik"))
    i_dag = str(now_local().date())
    vist_i_dag = [
        n
        for p in (st.get("foreslaaet") or [])
        if p.get("dato") == i_dag
        for n in (p.get("retter") or [])
    ]

    # Trin 1 på stigen: retter med mindst ét JA og intet NIX. De bruges KUN når
    # de godkendte friske slipper op — en frisk halv-godkendt ret slår en
    # godkendt genganger (user 2026-08-20).
    i_pulje = {id(d) for d in pulje}
    bredere = [
        d
        for d in unikke_retter(dishes)
        if id(d) not in i_pulje and not er_afvist(d) and saeson_ok(d, saeson) and har_ja(d)
    ]

    # SUPERJA (user-spec 2026-08-29): retten SKAL med på den førstkommende
    # liste. Den lægges i kurven FØR mixet vælges — hverken friskheds-stigen,
    # sæson-spærringen eller kategori-balancen må kunne skubbe den ud — og den
    # trækkes ud af alle tre kandidat-lister, så den ikke også vælges normalt.
    tvungne = [d for d in unikke_retter(dishes) if har_superja(d)]
    tvungne_navne = {normaliser_navn(d.get("ret", "")) for d in tvungne}

    def ikke_tvunget(liste):
        return [d for d in liste if normaliser_navn(d.get("ret", "")) not in tvungne_navne]

    valgt = tvungne + vaelg_indkoeb(
        ikke_tvunget(pulje),
        max(0.0, maal - sum(kurv_vaegt(d) for d in tvungne)),
        num(states, E_BV_PCT, 50),
        salat_hver=int(num(states, E_SALAT_HVER, 4)),
        sundhed_maal=num(states, E_SUNDHED, 7),
        salat_reserve=ikke_tvunget(
            [
                d
                for d in unikke_retter(dishes)
                if er_salat(d) and not er_afvist(d) and saeson_ok(d, saeson)
            ]
        ),
        saeson=saeson,
        nylige=nylige,
        bredere=ikke_tvunget(bredere),
        vist_i_dag=vist_i_dag,
    )
    nyl_stammer = [ret_stamme(n) for n in nylige]
    gengangere = sum(
        1 for d in valgt if any(naer_dublet(ret_stamme(d.get("ret", "")), t) for t in nyl_stammer)
    )
    u_godkendte = sum(1 for d in valgt if not begge_ja(d) and not har_superja(d))
    gem_forrige_liste(dry)
    linjer, sprunget, besked = publish_indkoeb(token, states, valgt, dry, dishes=dishes)

    # Pushen er en OVERSIGT, ikke selve listen (user-spec 2026-08-12: "bare en
    # linje per opskrift med navnet, ikke alt det andet tekst og detaljer").
    # Varer, fakta og ingredienser står uændret i sensorens `tekst`-attribut =
    # Mad-siden, som notifikationen linker til.
    push = "\n".join(
        f"{i + 1}. {d['ret']}" + (" ⭐" if har_superja(d) else "") for i, d in enumerate(valgt)
    )
    push += f"\n\n{len(linjer)} varer — se listen på Mad-siden."
    sj_navne = sorted({PEOPLE[d["superja"]]["navn"] for d in tvungne if d.get("superja") in PEOPLE})
    if sj_navne:
        push += f"\n(⭐ = SUPERJA fra {' og '.join(sj_navne)})"
    if pulje_kilde == "delvise svar":
        push += "\n(for få godkendte retter — valgt ud fra de svar der var)"
    elif pulje_kilde == "uden svar":
        push += "\n(ingen svar at gå efter — retterne er valgt tilfældigt)"
    if gengangere:
        push += (
            f"\n({gengangere} genganger{'e' if gengangere > 1 else ''} —"
            " puljen er for lille til en helt ny liste)"
        )
    if u_godkendte and pulje_kilde == "godkendt":
        push += (
            f"\n({u_godkendte} uden ja fra begge — valgt frem for at"
            " gentage en ret I lige har haft)"
        )
    push_notify(
        token,
        "mad_indkoeb",
        f"🛒 Indkøbsliste — {len(valgt)} retter",
        push,
        {
            "tag": "mad_indkoeb",
            "group": "mad_indkoeb",
            "url": "/mad-dash/0",
            "clickAction": "/mad-dash/0",
        },
        dry,
    )
    logbook(token, "Mad", f"Indkøbsliste sendt: {len(valgt)} retter, {len(linjer)} varer", dry)
    log(f"indkøbsliste: {[d['ret'] for d in valgt]} → {len(linjer)} varer")

    # Garantien er indfriet → stemplet må ikke tvinge retten med på næste liste
    # også. Genindlæs state: publish_indkoeb har selv skrevet `indkoeb` og
    # `historik` siden vi hentede den, og en gammel kopi ville rulle dem tilbage.
    if tvungne and not dry:
        paa_listen = {normaliser_navn(d.get("ret", "")) for d in valgt}
        st2 = load_state()
        aendret = False
        for post in (st2.get("superja") or {}).values():
            p = som_post(post)
            if normaliser_navn(p.get("ret") or "") in paa_listen and not p.get("leveret"):
                post["leveret"] = True
                aendret = True
        if aendret:
            save_state(st2)


# =============================================================================
# Morgen-spørgsmålet på indkøbsdage (2026-08-26, user-spec)
# =============================================================================
# "på indkøbsdage skal jeg om morgenen spørges om vi senere vil ha genereret en
#  liste eller om køleskabet er fyldt stadig."
#
# De tre svar rammer TRE forskellige tidshorisonter, og det er hele pointen:
#   JA     → ingen tilstand ændres; listen genereres som planlagt i eftermiddag.
#   NEJ    → `mad_indkoeb_sprunget_dato` = i dag. Springer KUN dagens liste over.
#            Kadencen er urørt, så næste indkøbsdag falder hvor den plejer.
#   SNOOZE → ankeret sættes til indkøbsdagen + 7. Det er ikke "spring over" —
#            det flytter hele rytmen en uge, præcis som user bad om ("skal
#            påvirke anker dato"). Ét skridt rykker derfor både i dag OG
#            kadencen, så ingen ekstra skip-markering er nødvendig.
#
# En markering af dagen som "sprunget" må aldrig kunne overleve til næste
# indkøbsdag: derfor sammenlignes den mod DAGENS dato, ikke mod et flag.


def sprunget_i_dag(states, today):
    """Har brugeren svaret 'køleskabet er fyldt' på netop I DAG?

    Et URØRT input_datetime med has_date står på DAGENS midnat (ikke 1970), så
    en ren dato-sammenligning ville sige ja hver eneste dag og aldrig lave en
    liste igen. Tidsdelen er sentinel'en: 00:00:00 = aldrig sat.
    """
    raw = txt(states, E_BUY_SPRUNGET, "")
    if len(raw) < 19 or raw[11:19] == "00:00:00":
        return False
    return raw[:10] == str(today)


def _saet_dato(token, entity, dato, med_tid=False, dry=False):
    """Skriv en dato. `med_tid` tilføjer et klokkeslæt der beviser at feltet ER
    sat (sentinel'en ovenfor) — og kræver at helperen har has_time: true; et
    date-only felt afviser `datetime:` med 400."""
    if med_tid:
        tid = now_local().strftime("%H:%M:%S")
        if tid == "00:00:00":  # ét sekund fra at ligne "aldrig sat"
            tid = "00:00:01"
        data = {"entity_id": entity, "datetime": f"{dato} {tid}"}
    else:
        data = {"entity_id": entity, "date": str(dato)}
    if dry:
        log(f"(dry) {entity} := {data.get('datetime', data.get('date'))}")
        return
    # set_value giver bart 400 på et has_date-felt — set_datetime er vejen.
    ha_post(token, "/api/services/input_datetime/set_datetime", data)


def mode_indkoeb_morgen(token, states, dry):
    """Spørg om morgenen, på selve indkøbsdagen, om listen skal laves i dag."""
    if not is_on(states, E_BUY_ON):
        log("indkøbsliste slået fra — intet morgenspørgsmål")
        return
    today = now_local().date()
    naeste, ugedag, interval, _anker = naeste_indkoeb(states, today)
    if naeste != today:
        log(f"ikke indkøbsdag i dag (næste: {naeste}) — intet morgenspørgsmål")
        return
    if sprunget_i_dag(states, today):
        log("dagen er allerede markeret sprunget — spørger ikke igen")
        return

    hver = "hver uge" if interval == 1 else f"hver {interval}. uge"
    besked = (
        f"Det er indkøbsdag ({ugedag.lower()}, {hver}).\n"
        "Skal jeg lave en indkøbsliste i eftermiddag, eller er køleskabet"
        " stadig fyldt?"
    )
    # Ingen `sticky`: det blev prøvet 2026-07-30b og slog appens oprydning fra,
    # så knapperne ikke kunne besvares (rullet tilbage samme dag).
    # payload ER notify-kaldets `data:` — script.push_notify sender den uændret
    # videre (`data: "{{ ndata }}"`). Et ekstra "data"-lag her gav telefonen
    # data.data.actions, og knapperne blev derfor aldrig vist (user 2026-08-30:
    # "mangler sine action knapper på min tlf. så den er ubrugelig"). Husets
    # fire øvrige push_notify-kald i denne fil er alle flade — dette var den
    # eneste afviger.
    payload = {
        "actions": [
            {"action": "MADBUY_JA", "title": "Ja, lav listen"},
            {"action": "MADBUY_NEJ", "title": "Nej, køleskabet er fyldt"},
            {"action": "MADBUY_SNOOZE", "title": "Udskyd 1 uge"},
        ],
        "tag": "mad_indkoeb_morgen",
        "group": "mad_indkoeb",
        "url": "/mad-dash/0",
        "clickAction": "/mad-dash/0",
    }
    push_notify(
        token, "mad_indkoeb_morgen", "🧊 Indkøbsdag — skal der handles?", besked, payload, dry
    )
    logbook(token, "Mad", f"Morgenspørgsmål sendt: indkøbsdag {today} ({ugedag})", dry)
    log(f"morgenspørgsmål sendt (indkøbsdag {today})")


def mode_indkoeb_svar(token, states, svar, dry):
    """Håndtér tryk på morgen-spørgsmålets tre knapper."""
    svar = (svar or "").strip().upper()
    today = now_local().date()

    if svar == "JA":
        msg = "Indkøbsdag bekræftet — listen laves som planlagt i eftermiddag."
    elif svar == "NEJ":
        _saet_dato(token, E_BUY_SPRUNGET, today, med_tid=True, dry=dry)
        msg = (
            f"Indkøbsdag {today} sprunget over (køleskabet er fyldt)."
            " Kadencen er urørt — næste indkøbsdag falder som normalt."
        )
    elif svar == "SNOOZE":
        naeste, _ug, _iv, anker = naeste_indkoeb(states, today)
        # Ankeret sættes til den udskudte dag SELV, ikke til "gammelt anker +
        # 7". De to er kun ens når man svarer PÅ selve indkøbsdagen, og et
        # anker der ligger på en indkøbsdag er per definition gyldigt (d ==
        # anker giver 0 % interval == 0, og ugedagen passer). Trykkes der på en
        # gammel notifikation dagen efter, rykker det stadig den planlagte dag
        # præcis én uge — hvor `anker + 7` dér kunne trække næste indkøb FREM.
        nyt = (naeste or today) + timedelta(days=7)
        _saet_dato(token, E_BUY_ANKER, nyt, dry=dry)
        msg = f"Indkøb udskudt 1 uge: {naeste or today} → {nyt} (anker {anker} → {nyt})."
    else:
        log(f"ukendt svar: {svar!r}")
        return

    # Ingen kvitterings-push (user 14/10) — logbogen og Mad-siden bærer svaret.
    logbook(token, "Mad", msg, dry)
    log(msg)


def gem_forrige_liste(dry):
    """Gem den aktuelle liste FØR en ny overskriver den (user-spec 2026-09-23:
    "jeg mangler en undo knap … når jeg kommer til at overskrive en
    indkøbsliste med en ny").

    Hele `historik` gemmes med, fordi en ny liste samme dag OVERSKRIVER dagens
    historik-post (opdater_historik) — en fortrydelse skal lægge præcis den
    gamle gentagelses-spærring tilbage, ikke bare listen.
    """
    st = load_state()
    nu = st.get("indkoeb") or {}
    if not nu.get("retter"):
        return
    st["indkoeb_forrige"] = {
        "retter": list(nu.get("retter") or []),
        "genereret": nu.get("genereret"),
        "fjernet": list(nu.get("fjernet") or []),
        "historik": list(st.get("historik") or []),
    }
    save_state(st, dry)


def mode_fortryd_liste(token, states, dishes, dry):
    """Byt den aktuelle liste med den forrige — et 2. tryk bytter tilbage."""
    st = load_state()
    forrige = st.get("indkoeb_forrige") or {}
    if not forrige.get("retter"):
        msg = "Der er ingen tidligere indkøbsliste at gå tilbage til."
        log(msg)
        logbook(token, "Mad", msg, dry)
        return
    nu = st.get("indkoeb") or {}
    valgt = gemte_retter(dishes, forrige)
    if not valgt:
        msg = "Den forrige liste kunne ikke slås op i kataloget — intet ændret."
        log(msg)
        logbook(token, "Mad", msg, dry)
        return
    st["indkoeb_forrige"] = {
        "retter": list(nu.get("retter") or []),
        "genereret": nu.get("genereret"),
        "fjernet": list(nu.get("fjernet") or []),
        "historik": list(st.get("historik") or []),
    }
    st["indkoeb"] = {
        "retter": forrige["retter"],
        "genereret": forrige.get("genereret"),
        "fjernet": list(forrige.get("fjernet") or []),
    }
    if forrige.get("historik") is not None:
        st["historik"] = list(forrige["historik"])
    save_state(st, dry)
    publish_indkoeb(token, states, valgt, dry, forrige.get("genereret"), dishes=dishes)
    msg = (
        f"Indkøbslisten fra {forrige.get('genereret')} er tilbage "
        f"({len(valgt)} retter). Tryk ↩️ igen for at bytte tilbage."
    )
    logbook(token, "Mad", msg, dry)
    push_notify(
        token,
        "mad_indkoeb",
        "↩️ Indkøbsliste fortrudt",
        "\n".join(f"{i + 1}. {d['ret']}" for i, d in enumerate(valgt)),
        {
            "tag": "mad_indkoeb",
            "group": "mad_indkoeb",
            "url": "/mad-dash/0",
            "clickAction": "/mad-dash/0",
        },
        dry,
    )
    log(msg)


def valgt_ret(states, gemt, slot=None):
    """Retten der skal fjernes/udskiftes: slot-nummeret fra knappen ud for
    retten (2026-09-23), ellers — gammel vej — vælgerens værdi."""
    if slot not in (None, ""):
        try:
            i = int(slot) - 1
        except ValueError:
            return ""
        retter = gemt.get("retter") or []
        return retter[i] if 0 <= i < len(retter) else ""
    return txt(states, E_FJERN, "").strip()


def meld_ingen_ret(token, handling, valg, dry):
    """Et tryk der ikke rammer en ret må ikke være TAVST (user-bug 2026-09-23:
    anden 🗑️ gjorde ingenting — vælgeren var nulstillet til '—')."""
    msg = f"Kunne ikke {handling}: ingen ret valgt ({valg or 'tom'}) — listen er uændret."
    log(msg)
    logbook(token, "Mad", msg, dry)


def mode_fjern(token, states, dishes, dry, slot=None):
    """Fjern retten (slot eller vælger) fra den aktuelle liste."""
    gemt = load_state().get("indkoeb") or {}
    valg = valgt_ret(states, gemt, slot)
    aktuel = gemte_retter(dishes, gemt)
    if not aktuel:
        log("ingen aktuel indkøbsliste at fjerne fra")
        return
    ny = [d for d in aktuel if d["ret"] != valg]
    if len(ny) == len(aktuel):
        meld_ingen_ret(token, "fjerne", valg, dry)
        return
    publish_indkoeb(
        token, states, ny, dry, gemt.get("genereret"), dishes=dishes, fjernet_tilfoej=[valg]
    )
    logbook(token, "Mad", f"Fjernet fra indkøbslisten: {valg}", dry)
    log(f"fjernede {valg!r} → {len(ny)} retter tilbage")


def mode_tilfoej(token, states, dishes, navn, dry):
    """Læg en ret tilbage på den aktuelle liste — fortryd-vejen for --fjern-valgt.

    Slår op på navnet i hele kataloget, ikke kun i den godkendte pulje: er
    retten fjernet ved et uheld, skal den kunne komme tilbage uanset hvordan
    puljen ser ud i dag.
    """
    gemt = load_state().get("indkoeb") or {}
    aktuel = gemte_retter(dishes, gemt)
    ny = next(
        (
            d
            for d in unikke_retter(dishes)
            if normaliser_navn(d.get("ret", "")) == normaliser_navn(navn)
        ),
        None,
    )
    if ny is None:
        log(f"ingen ret i kataloget der hedder {navn!r}")
        return
    if normaliser_navn(ny["ret"]) in {normaliser_navn(d["ret"]) for d in aktuel}:
        log(f"{ny['ret']!r} står allerede på listen")
        return
    publish_indkoeb(token, states, aktuel + [ny], dry, gemt.get("genereret"), dishes=dishes)
    logbook(token, "Mad", f"Tilføjet til indkøbslisten: {ny['ret']}", dry)
    log(f"tilføjede {ny['ret']!r} → {len(aktuel) + 1} retter")


def mode_har_hjemme(token, states, dishes, spec, dry):
    """'350|g|afpudsede svinekæber' — trækkes fra den AKTUELLE indkøbsliste.

    Samme format som arkets `Ingredienser_struktureret`, så varenavnet
    normaliseres præcis som i opskriften og rammer den rigtige linje.
    """
    poster = parse_struct(spec)
    if not poster:
        log(f"kunne ikke læse --har-hjemme {spec!r} (format: mængde|enhed|vare)")
        return
    st = load_state()
    gemt = st.get("indkoeb") or {}
    genereret = gemt.get("genereret")
    if not genereret:
        log("ingen aktuel indkøbsliste at trække fra")
        return
    nye = [
        {"vare": navn, "maengde": m, "enhed": enhed, "liste": genereret}
        for m, enhed, navn in poster
    ]
    navne = {p["vare"] for p in nye}
    st["har_hjemme"] = [
        p for p in har_hjemme_for(st, genereret) if normaliser_navn(p.get("vare", "")) not in navne
    ] + nye
    save_state(st, dry)
    aktuel = gemte_retter(dishes, gemt)
    if aktuel:
        publish_indkoeb(token, states, aktuel, dry, genereret, dishes=dishes)
    log("har hjemme: " + ", ".join("{maengde} {enhed} {vare}".format(**p) for p in nye))


def vaelg_erstatning(kandidater, resten, fjernet, bv_pct, sundhed_maal=7.0, saeson=None):
    """Den kandidat der passer bedst ind i den RESTERENDE liste.

    Samme fire akser som vaelg_indkoeb (kategori, sværhedsgrad, børnevenlig-
    andel, sundhed), men målt mod de retter der BLIVER på listen — plus et
    vægt-led, så et tilbehør erstattes af et tilbehør og en hovedret af en
    hovedret (ellers kunne "udskift" halvere kurvens vægt).
    """
    andel_bv = max(0.0, min(1.0, bv_pct / 100.0))
    brugt_kat, brugt_sv = {}, {}
    for d in resten:
        brugt_kat[mad_kategori(d)] = brugt_kat.get(mad_kategori(d), 0) + 1
        brugt_sv[svaerhed(d)] = brugt_sv.get(svaerhed(d), 0) + 1
    n_bv = sum(1 for d in resten if er_boernevenlig(d))
    sund_sum = sum(sundhed(d) for d in resten)
    plads = len(resten) + 1

    def score(d):
        bv_efter = (n_bv + (1 if er_boernevenlig(d) else 0)) / plads
        sund_efter = (sund_sum + sundhed(d)) / plads
        return (
            1.0 * brugt_kat.get(mad_kategori(d), 0)
            + 0.7 * brugt_sv.get(svaerhed(d), 0)
            + 2.0 * abs(bv_efter - andel_bv)
            + 0.5 * abs(sund_efter - sundhed_maal) / 10.0
            + 1.5 * abs(kurv_vaegt(d) - kurv_vaegt(fjernet))
            - (0.8 if saeson and saeson_eksplicit(d, saeson) else 0.0)
        )

    # Begge-ja først, som på selve listen (vaelg_indkoeb's styrke-trin): puljen
    # rummer også retter godkendt via svarfristen (ja + udeblevet svar).
    kort = [d for d in kandidater if begge_ja(d)] or list(kandidater)
    random.shuffle(kort)  # tilfældig rækkefølge bryder uafgjort
    return min(kort, key=score) if kort else None


def mode_udskift(token, states, dishes, dry, slot=None):
    """Udskift den valgte ret: slet den og læg en ny, godkendt ret ind i stedet.

    User-spec 2026-08-12. Samme vælger som --fjern-valgt (én liste, to knapper).
    Erstatningen tages fra samme pulje-stige som selve indkøbslisten
    (godkendte først, kravet slækkes kun hvis puljen er tom), minus alt der
    allerede står på listen — man skal ikke kunne udskifte sig til en dublet.
    """
    gemt = load_state().get("indkoeb") or {}
    valg = valgt_ret(states, gemt, slot)
    aktuel = gemte_retter(dishes, gemt)
    if not aktuel:
        log("ingen aktuel indkøbsliste at udskifte i")
        return
    fjernet = next((d for d in aktuel if d["ret"] == valg), None)
    if fjernet is None:
        meld_ingen_ret(token, "udskifte", valg, dry)
        return

    idx = aktuel.index(fjernet)
    resten = [d for d in aktuel if d["ret"] != valg]
    # 2026-09-23: også retter der er taget AF denne liste (🗑️/🔄) — målt 21/09
    # 19:54 slettet "Brændende kærlighed", 19:56 valgt som erstatning igen.
    paa_listen = {normaliser_navn(d["ret"]) for d in aktuel} | {
        normaliser_navn(n) for n in (gemt.get("fjernet") or [])
    }
    # n_min = listen + 1: stigen skal kunne levere ÉN kandidat ud over dem der
    # allerede er valgt, ellers slækkes godkendt-kravet.
    pulje, _ = indkoeb_pulje(dishes, len(aktuel) + 1, aktuel_saeson())
    kandidater = [d for d in pulje if normaliser_navn(d["ret"]) not in paa_listen]
    if not kandidater:
        msg = f"Ingen anden ret at sætte i stedet for {valg} — listen er uændret."
        log(msg)
        logbook(token, "Mad", msg, dry)
        push_notify(
            token,
            "mad_indkoeb",
            "🔄 Kunne ikke udskifte",
            msg,
            {
                "tag": "mad_indkoeb",
                "group": "mad_indkoeb",
                "url": "/mad-dash/0",
                "clickAction": "/mad-dash/0",
            },
            dry,
        )
        return

    ny = vaelg_erstatning(
        kandidater,
        resten,
        fjernet,
        num(states, E_BV_PCT, 50),
        num(states, E_SUNDHED, 7),
        saeson=aktuel_saeson(),
    )
    liste = resten[:idx] + [ny] + resten[idx:]
    publish_indkoeb(
        token, states, liste, dry, gemt.get("genereret"), dishes=dishes, fjernet_tilfoej=[valg]
    )
    logbook(token, "Mad", f"Udskiftet på indkøbslisten: {valg} → {ny['ret']}", dry)
    push_notify(
        token,
        "mad_indkoeb",
        "🔄 Ret udskiftet",
        f"➖ {valg}\n➕ {ny['ret']}",
        {
            "tag": "mad_indkoeb",
            "group": "mad_indkoeb",
            "url": "/mad-dash/0",
            "clickAction": "/mad-dash/0",
        },
        dry,
    )
    log(f"udskiftede {valg!r} → {ny['ret']!r}")


def mode_vote(token, states, dishes, kilde, args, dry):
    did, person, svar = str(args.id), args.person.lower(), args.svar.upper()
    if person not in PEOPLE or svar not in SVAR_VALG:
        raise SystemExit(f"ugyldig stemme: {person}/{svar}")
    # Notifikationen bærer ask-tidens id, og arkets id'er kan have forskudt sig
    # imens (positionel ID-kolonne). NAVNET fra `spurgt` vinder derfor over
    # id'et — samme regel som påmindelser, merge og synk-kø (fejlklasse #2).
    spurgt_om = som_post(load_state().get("spurgt", {}).get(did, {})).get("ret")
    d = ret_bag_spoergsmaal(did, spurgt_om, dishes)
    if d is None:
        if not spurgt_om:
            raise SystemExit(f"ukendt ret-id: {did}")
        # Retten findes reelt ikke længere i arket (slettet af Gemini). En
        # stemme på en ret brugeren aldrig har set forurener puljen usynligt,
        # så den kasseres — og det døde spørgsmål ryddes, så påmindelses-vagten
        # holder op med at jage det.
        nu_paa_id = next((x["ret"] for x in dishes if str(x["id"]) == did), "—")
        log(
            f"stemme afvist: id {did} er nu '{nu_paa_id}', men spørgsmålet "
            f"handlede om '{spurgt_om}', som ikke findes i arket længere"
        )
        st = load_state()
        st.get("spurgt", {}).pop(did, None)
        st.get("paamind", {}).pop(did, None)
        save_state(st, dry)
        notify_direct(
            token,
            person,
            {
                "message": f"⚠️ '{spurgt_om}' findes ikke længere i mad-arket — "
                "svaret er ikke gemt.",
                "data": {"tag": f"mad_ret_{did}_{person}", "group": "mad_spoergsmaal"},
            },
            dry,
        )
        return
    maal = str(d["id"])  # rettens id i arket NU — alt skrives herunder

    # --- SUPERJA (user-spec 2026-08-29) --------------------------------------
    # Kvote: én pr. person pr. `mad_superja_dage`. Er den brugt, bliver det et
    # helt almindeligt JA, og personen får det at vide i kvitteringen — et
    # SUPERJA må aldrig tavst blive til noget mindre.
    # Arket kender kun JA/NIX/MAASKE (VALID_VOTES i mad_sheet_api.gs), så
    # stemmen SKRIVES som JA; det er stemplet i state-filen der gør den super.
    superja, note = False, None
    if svar == "SUPERJA":
        dage = int(num(states, E_SUPERJA_DAGE, 7))
        sidst = som_post((load_state().get("superja") or {}).get(person) or {})
        brugt = parse_dato(sidst.get("dato"))
        if dage > 0 and brugt is not None and (now_local().date() - brugt).days < dage:
            svar = "JA"
            klar = brugt + timedelta(days=dage)
            note = (
                f"⚠️ Det blev et almindeligt JA — din SUPERJA gik til "
                f"'{sidst.get('ret') or '—'}' den {brugt.isoformat()}. "
                f"Næste er klar {klar.isoformat()}."
            )
        else:
            superja = True
            note = "⭐ SUPERJA brugt — retten er sikret plads på næste indkøbsliste."
    skriv_svar = "JA" if svar == "SUPERJA" else svar

    # Skriv til arket uanset hvad LÆSNINGEN kom fra: web-app'en svarer
    # sporadisk 404/429/5xx, og et hik på `dishes` gjorde før hele stemmen
    # lokal-only uden nogen vej tilbage. Fejler skrivningen alligevel, ryger
    # den i synk-køen og leveres af næste kørsel.
    skrevet = False
    if api_available():
        try:
            sheet_api("vote", dry=dry, id=maal, person=person, svar=skriv_svar, ret=d["ret"])
            skrevet = True
        except Exception as err:
            log(f"kunne ikke skrive stemmen til arket ({err}) — lagt i synk-køen")
    else:
        log("ingen skriveadgang til arket — stemmen gemmes kun lokalt")
    st = load_state()
    if not skrevet and api_available():
        koe_tilfoej(
            st, {"type": "vote", "id": maal, "ret": d["ret"], "person": person, "svar": skriv_svar}
        )
    stemmer_st = st.setdefault("stemmer", {})
    # Saml gamle poster om SAMME ret under det nye id — ellers ville den anden
    # persons tidligere svar blive hængende under et forældet id og se ud som
    # om det manglede.
    post = stemmer_st.setdefault(maal, {})
    for k in [k for k in list(stemmer_st) if k != maal]:
        gl = stemmer_st[k]
        if not isinstance(gl, dict) or not gl.get("ret"):
            continue
        if ret_bag_spoergsmaal(k, gl.get("ret"), dishes) is not d:
            continue
        for p in PEOPLE:
            if gl.get(p) and not post.get(p):
                post[p] = gl[p]
        if gl.get("svar_at") and gl["svar_at"] > (post.get("svar_at") or ""):
            post["svar_at"] = gl["svar_at"]
        stemmer_st.pop(k, None)
    # NB: `spurgt[did]` bliver liggende under ASK-tidens id med vilje — den
    # ANDENS notifikation bærer stadig det id, og det er netop dens 'ret'-navn
    # der gør deres svar opløseligt. Flyttede vi nøglen, ville deres tryk falde
    # tilbage til "hvad ligger på id'et nu" = præcis den fejl vi retter her.
    post[person] = skriv_svar
    post["ret"] = d["ret"]
    if superja:
        # `leveret` ryddes først når retten faktisk har stået på en liste —
        # kvoten er brugt ved TRYKKET, men garantien gælder til den er indfriet.
        st.setdefault("superja", {})[person] = {
            "ret": d["ret"],
            "dato": now_local().date().isoformat(),
            "leveret": False,
        }
    # Arket har ingen kolonne til HVORNÅR der blev stemt, så tidspunktet kan kun
    # bo her. Uden det måtte "seneste svar" sortere på 'Sidst spurgt' — og et
    # svar der lander fem dage efter spørgsmålet havnede så nederst på listen.
    post["svar_at"] = now_local().isoformat(timespec="seconds")
    # Stem-hold: fastfrys rækkefølgen personen SÅ (sensoren fra før trykket)
    # og forlæng den ved hver stemme — se STEM_HOLD_MIN.
    raekke = stem_hold(st, person) or [
        x.get("ret")
        for x in ((states.get(f"sensor.mad_stem_{person}") or {}).get("attributes") or {}).get(
            "poster"
        )
        or []
        if isinstance(x, dict) and x.get("ret")
    ]
    if raekke:
        st.setdefault("stem_hold", {})[person] = {
            "til": (now_local() + timedelta(minutes=STEM_HOLD_MIN)).isoformat(timespec="seconds"),
            "raekke": raekke,
        }
    save_state(st, dry)
    # Begge felter ind i den ret-liste mode_refresh straks genudgiver — ellers
    # udgives stemmen uden sit tidsstempel, og svaret rykker først til tops ved
    # næste kørsel (målt: stemme 13:17 dukkede først op efter en separat
    # --refresh).
    d[person] = skriv_svar
    d["svar_at"] = post["svar_at"]
    if superja:
        d["superja"] = person

    # Ingen kvittering (user 14/10: "send ikke svar notifikations kvitteringer
    # til os") — svaret ses på Mad-siden. Spørgsmålet tages bare ned (et tryk
    # fra Mad-siden lader det ellers ligge på telefonen). Kun en SUPERJA der
    # blev til et almindeligt JA siges højt: den må aldrig tavst blive mindre.
    tag = f"mad_ret_{did}_{person}"
    if svar == "JA" and note and note.startswith("⚠️"):
        notify_direct(token, person, kvitterings_payload(person, d, svar, did, note), dry)
    else:
        notify_direct(token, person, {"message": "clear_notification", "data": {"tag": tag}}, dry)
    if svar == "NIX":
        # Tag'et på den ANDENS telefon bærer ask-tidens id, ikke rettens id nu.
        ryd_andres_spoergsmaal(token, person, d, dry, did)
    mode_refresh(token, states, dishes, kilde, dry)
    log(f"{person} stemte {svar} på '{d['ret']}'")


def slot_ret(states, args):
    """Hvilken ret sidder i slot N på `person`s kort? ("" = tomt slot)

    Ét opslag, brugt både af den optimistiske kvittering og af selve stemmen,
    så de to ikke kan pege på hver sin ret (fejlklasse #2).
    """
    if args.person not in PEOPLE:
        raise SystemExit(f"ukendt person: {args.person}")
    try:
        slot = int(args.slot)
    except TypeError, ValueError:
        raise SystemExit(f"ugyldigt slot: {args.slot}") from None
    return str(
        (states.get(f"sensor.mad_stem_{args.person}") or {})
        .get("attributes", {})
        .get(f"ret_{slot}", "")
    ).strip()


def mode_stem_slot(token, states, dishes, kilde, args, dry):
    """Stem fra Mad-siden: knappen i slot N under den ret kortet viser.

    Findes fordi svar-knappen i notifikationen kan tabe et tryk: den skal nå
    HA over hjemme-wifi/Tailscale, appen rydder notifikationen ved tryk uanset,
    og man tror man har stemt (målt: Parent B manglede 12 svar, Parent A 1).
    Dashboardet har ikke det problem.

    Retten slås op i `sensor.mad_stem_<person>` — den SAMME kilde kortet tegner
    efter — så knap og tekst ikke kan pege på hver sin ret. Selve skrivningen
    genbruger mode_vote: ét sted der ejer ark-skrivning, synk-kø, kvittering og
    NIX-oprydning (fejlklasse #2).
    """
    navn = slot_ret(states, args)
    if not navn:
        log(f"slot {args.slot} er tomt — ingen stemme afgivet")
        return
    d = next((x for x in dishes if x.get("ret") == navn), None)
    if d is None:
        log(f"slot {args.slot} peger på '{navn}', som ikke findes i arket")
        return
    mode_vote(
        token,
        states,
        dishes,
        kilde,
        argparse.Namespace(id=d["id"], person=args.person, svar=args.svar),
        dry,
    )


def ryd_andres_spoergsmaal(token, person, d, dry=False, did=None):
    """Et NIX afviser retten alene — så den anden behøver ikke svare.

    Spørgsmålet ligger stadig på deres telefon med tre knapper der ikke betyder
    noget længere; companion-appen rydder først ved tryk, så et ubesvaret
    spørgsmål bliver hængende i timevis. `clear_notification` på samme tag
    fjerner både det oprindelige spørgsmål og en evt. påmindelse (de deler tag).
    Påmindelses-vagten holdt allerede op af sig selv (`er_afvist`) — det er kun
    den allerede leverede notifikation der manglede at blive taget ned.
    """
    andre = "parent_b" if person == "parent_a" else "parent_a"
    m, c = stemmer(d)
    if c if andre == "parent_b" else m:
        return  # de har allerede svaret — der er intet at rydde
    notify_direct(
        token,
        andre,
        {
            "message": "clear_notification",
            "data": {"tag": f"mad_ret_{str(d['id'] if did is None else did)}_{andre}"},
        },
        dry,
    )
    log(f"ryddede {andre}s spørgsmål om '{d['ret']}' (afvist af {person})")


def mode_sync_local(dishes, dry):
    """Skub lokalt gemte stemmer/stempler op i arket (efter at web-app'en kom op).

    Uden skriveadgang lander stemmerne kun i /config/.mad_planner_state.json —
    denne kørsel forener dem med arket, så intet går tabt i overgangen.
    """
    st = load_state()
    n = 0
    sprunget = []
    for did, pers in (st.get("stemmer") or {}).items():
        maal = loes_id(did, pers.get("ret"), dishes)
        if maal is None:
            sprunget.append(f"stemme {did} ({pers.get('ret') or 'uden navn'})")
            continue
        if not pers.get("ret"):
            # Legacy-post uden navn: id'et kan ikke verificeres (positionel
            # ID-kolonne). Målt 2026-08-07 er alle 11 sådanne poster allerede
            # i arket = nul at redde, men en blind skrivning kunne lande på
            # naboretten.
            sprunget.append(f"stemme {did} (uden ret-navn — kan ikke verificeres)")
            continue
        for person, svar in pers.items():
            # Stemme-dict'en bærer også en 'ret'-nøgle med rettens NAVN (gemt så
            # state-filen kan læses af et menneske). Den er ikke en stemme, og
            # web-app'en ville afvise den med "ukendt person" — men et afvist
            # kald tæller stadig i n og koster et HTTP-kald pr. ret, så filtrér
            # på de to ægte stemmere i stedet for at lade API'et rydde op.
            if person not in ("parent_a", "parent_b"):
                continue
            v = str(svar).strip().upper()
            if v not in SVAR_VALG:
                continue
            # Arket kender ikke SUPERJA (VALID_VOTES) — det er et JA plus et
            # lokalt stempel, jf. mode_vote.
            sheet_api(
                "vote",
                dry=dry,
                id=maal,
                person=person,
                svar="JA" if v == "SUPERJA" else v,
                **({"ret": pers["ret"]} if pers.get("ret") else {}),
            )
            n += 1
    # Grupperet pr. dato: 'asked' stempler ÉN dato pr. kald, og sendes de alle
    # sammen, arver hver ret dagens dato. Det skete 2026-08-05 og fladede hele
    # spørge-historikken ud — hvorefter "seneste svar" ikke kunne sortere og
    # genspørg-uret startede forfra for alle. Historikken er data, ikke pynt.
    pr_dato = {}
    ialt = 0
    for did, post in (st.get("spurgt") or {}).items():
        p = som_post(post)
        maal = loes_id(did, p.get("ret"), dishes)
        if maal is None:
            sprunget.append(f"spurgt {did} ({p.get('ret') or 'uden navn'})")
            continue
        pr_dato.setdefault(str(p.get("dato") or "")[:10], []).append(maal)
        ialt += 1
    for dato, ids in sorted(pr_dato.items()):
        sheet_api("asked", dry=dry, ids=",".join(ids), **({"dato": dato} if dato else {}))
    log(f"synkroniserede {n} stemme(r) og {ialt} 'spurgt'-stempler til arket")
    for s in sprunget:
        log(f"  sprang over: {s}")
    return n


def mode_backfill(token, dishes, dry):
    """Udled 'Ingredienser_struktureret' for rækker der mangler den."""
    mangler = [d for d in dishes if not (d.get("struct") or "").strip()]
    log(f"{len(mangler)} retter mangler struktureret ingrediensliste")
    for d in mangler:
        parsed = parse_fritekst(d.get("ingredienser", ""))
        value = ";".join(f"{m:g}|{e}|{n}" for m, e, n in parsed if n)
        if not value:
            continue
        if dry:
            print(f"{d['id']:>3} {d['ret']}\n    {value}")
            continue
        sheet_api("struct", id=d["id"], value=value)
    return len(mangler)


# =============================================================================
def main():
    ap = argparse.ArgumentParser(description="Mad-planlægning")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--ask", action="store_true")
    ap.add_argument("--indkoeb", action="store_true")
    ap.add_argument(
        "--paamind",
        action="store_true",
        help="send ubesvarede ret-spørgsmål igen (tabte svar-tryk)",
    )
    ap.add_argument("--force", action="store_true", help="ignorér indkøbs-kalenderen")
    ap.add_argument(
        "--indkoeb-morgen",
        action="store_true",
        help="morgen-spørgsmål på indkøbsdage (Ja/Nej/Udskyd)",
    )
    ap.add_argument("--indkoeb-svar", metavar="JA|NEJ|SNOOZE", help="svar på morgen-spørgsmålet")
    ap.add_argument("--vote", action="store_true")
    ap.add_argument(
        "--stem-slot",
        action="store_true",
        help="stem fra Mad-siden på retten i slot N (sensor.mad_afventer)",
    )
    ap.add_argument("--slot")
    ap.add_argument(
        "--fjern-valgt",
        action="store_true",
        help="fjern den ret der står i input_select.mad_fjern_ret",
    )
    ap.add_argument(
        "--udskift-valgt",
        action="store_true",
        help="udskift den valgte ret med en anden godkendt ret",
    )
    ap.add_argument(
        "--fortryd-liste", action="store_true", help="byt den aktuelle indkøbsliste med den forrige"
    )
    ap.add_argument(
        "--tilfoej-ret", metavar="NAVN", help="læg en ret tilbage på den aktuelle liste (fortryd)"
    )
    ap.add_argument(
        "--har-hjemme",
        metavar="MÆNGDE|ENHED|VARE",
        help="træk varer vi allerede har fra den aktuelle liste",
    )
    ap.add_argument("--id")
    ap.add_argument("--person")
    ap.add_argument("--svar", help="JA|SUPERJA|NIX (MAASKE kun legacy)")
    ap.add_argument("--backfill-struct", action="store_true")
    ap.add_argument(
        "--sync-local",
        action="store_true",
        help="skub lokalt gemte stemmer op i arket (engangs, efter setup)",
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    dry = args.dry_run

    token = ha_secrets.get(TOKEN_KEY)
    states = ha_get_states(token)
    # Svar-fristen skal stå FØR første klassifikation (merge_local_state og
    # alt hvad der kalder stemmer()) — ellers ville kørslen bruge default'en.
    global SVAR_TIMEOUT_DAGE
    SVAR_TIMEOUT_DAGE = int(num(states, E_SVAR_TIMEOUT, 7))

    # Morgen-spørgsmålet rører hverken retter eller ark — så det skal heller
    # ikke betale fetch_dishes' 3-8 s. Svar-vejen er et knaptryk brugeren
    # venter på kvittering for; den skal være hurtig.
    if args.indkoeb_svar:
        mode_indkoeb_svar(token, states, args.indkoeb_svar, dry)
        return
    if args.indkoeb_morgen:
        mode_indkoeb_morgen(token, states, dry)
        return

    # Kvittér på skærmen FØR arket hentes: fetch_dishes er 3-8 s mod Apps
    # Script, og indtil da så et tryk på Mad-siden ud som om intet skete.
    # Stemmen selv skrives længere nede ad den normale vej.
    if args.stem_slot:
        stem_navn = slot_ret(states, args)
        if stem_navn:
            optimistisk_fjern(token, states, args.person, stem_navn, str(args.svar).upper(), dry)
    dishes, kilde = fetch_dishes()
    dishes = merge_local_state(dishes, load_state())
    log(f"{len(dishes)} retter hentet (kilde: {kilde})")
    # Ryd synk-køen FØR dagens arbejde: /40-tick'en (--paamind) er den hyppigste
    # kørsel, så en fejlet skrivning står højst 40 min i kø i stedet for at
    # afvente en manuel --sync-local.
    flush_usynket(dishes, dry)

    if args.sync_local:
        mode_sync_local(dishes, dry)
        return
    if args.backfill_struct:
        mode_backfill(token, dishes, dry)
        return
    if args.vote:
        mode_vote(token, states, dishes, kilde, args, dry)
        return
    if args.stem_slot:
        mode_stem_slot(token, states, dishes, kilde, args, dry)
        return
    if args.ask:
        mode_ask(token, states, dishes, kilde, dry)
    if args.paamind:
        mode_paamind(token, states, dishes, dry)
    if args.fjern_valgt:
        mode_fjern(token, states, dishes, dry, slot=args.slot)
    if args.udskift_valgt:
        mode_udskift(token, states, dishes, dry, slot=args.slot)
    if args.fortryd_liste:
        mode_fortryd_liste(token, states, dishes, dry)
    if args.tilfoej_ret:
        mode_tilfoej(token, states, dishes, args.tilfoej_ret, dry)
    if args.har_hjemme:
        mode_har_hjemme(token, states, dishes, args.har_hjemme, dry)
    if args.indkoeb:
        mode_indkoeb(token, states, dishes, kilde, dry, args.force)
    mode_refresh(token, states, dishes, kilde, dry)


DETACH_LOG = "/config/.mad_planner_detach.log"


def detach_and_exit():
    """--detach (2026-10-06): HA dræber en shell_command efter 60 s, og en kørsel
    tager 11-60+ s når Apps Script er langsom — målt 10-06 11:59:22 og 12:00:22:
    to stemmer dræbt og TABT (ingen lokal skrivning nåede at ske). Forælderen
    starter sig selv igen i en ny session med log til fil og returnerer straks;
    barnet kører færdigt uden stopur. Mønster: scripts/apollo_kalib_capture.py.
    Fejl står derfor i DETACH_LOG, ikke i HA-loggen."""
    import subprocess

    args = [a for a in sys.argv[1:] if a != "--detach"]
    try:
        if os.path.getsize(DETACH_LOG) > 1_000_000:
            os.replace(DETACH_LOG, DETACH_LOG + ".1")
    except OSError:
        pass
    logf = open(DETACH_LOG, "a", encoding="utf-8")
    logf.write(f"{datetime.now().isoformat(timespec='seconds')} start {' '.join(args)}\n")
    logf.flush()
    subprocess.Popen(
        [sys.executable, os.path.abspath(__file__), *args],
        stdin=subprocess.DEVNULL,
        stdout=logf,
        stderr=logf,
        start_new_session=True,
        env={**os.environ, "MAD_DETACHED": "1"},
    )
    sys.exit(0)


if __name__ == "__main__":
    if "--detach" in sys.argv:
        detach_and_exit()
    _laas = state_lock(vent="--paamind" not in sys.argv)
    try:
        main()
    finally:
        _laas.close()
