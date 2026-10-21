#!/usr/bin/env python3
"""Plante-notifikationer — poll Google Sheet + vejr, send beskeder til telefon.

Kører én gang i døgnet (shell_command, se packages/plant_notifications.yaml) og
laver to slags notifikationer (via script.push_notify, notif_id `planter`):

1) GØDNING (frekvens-model, user-spec 2026-07-29: "vi dropper brugen af
   Sidst Gødet-kolonnen, det er for besværligt"). Sæsonen vælger
   `Gødningsfrekvens <sæson> per måned` → interval = ~30/frekvens dage.
   Scriptet HUSKER SELV næste dato (`fert_next:<ID>` i state-filen); arkets
   `Sidst Gødet` læses IKKE. Alle forfaldne planter samles i ÉN push: arket har
   44 planter med samme startdato, så per-plante-pushes gav ~30 beskeder på én
   morgen (07-29). freq 0 for sæsonen → ingen gødning den sæson.

   KVITTERING (user-spec 2026-10-05: "der skal være action knap 'Done' på
   gødningsnotifikation og hvis jeg ikke trykker done skal den komme igen
   dagen efter"): en påmindelse er IKKE længere baseline. `fert_next` står
   stille indtil ✅ Gødet (knap på pushen eller på Planter-siden) — så er
   planten stadig forfalden næste morgen, og 08:00-kørslen sender den igen.
   ✅ lægger næste dato et interval frem fra KVITTERINGS-dagen. Batchen
   (`_fert_last`) huskes efter kvitteringen, så Planter-siden kan vise
   "sidste gang bad jeg dig gøde disse" (user: "in case jeg glemmer det").
   Højst én gødnings-push pr. dag: HA genstarter flere gange dagligt, og
   start-triggeren må ikke gentage en ukvitteret push samme dag.

2) VEJR-ADVARSLER (forecast-baseret, met.no daily):
   - Meget regn på vej (sum mm over RAIN_DAYS ≥ RAIN_MM) → "flyt krukke-planter i ly".
   - Varmt + solrigt på vej (≥ HEAT_MIN_DAYS dage med max ≥ HEAT_TEMP og sol) →
     "vand ekstra / skyg". Begge har cooldown så de ikke gentages dagligt.

VANDING pushes IKKE længere (user-spec 2026-07-29: "du behøver ikke give
notifikationer om vanding, det skal jeg nok selv gøre"). Arkets `Næste
HA-notifikation`/`Næste HA-besked` bruges kun til plante-dashboardets
"kommende vanding"-liste (sensor.plant_overview).

Dedup/hukommelse: state-fil /config/.plant_notify_state.json.
  gødning -> "fert_next:" + plante-ID -> næste forfaldsdato (ISO)
             "fert_sidst:" + plante-ID -> sidst kvitteret gødet (ISO)
             "_fert_last" -> seneste push-batch: planter, sendt, status
  vejr    -> nøgle = "_rain_warn"/"_heat_warn" -> sidst-advaret dato (cooldown)

Gødnings-push-knapper: ✅ Gødet / 📅 +1 uge, gældende ALLE planter i beskeden.
Telefonens tryk lander som mobile_app_notification_action →
notif_action_plant_fert (packages/notif_actions.yaml) →
script.planter_goedning_kvitter → `--fert-action {done|snooze7}` her. Samme
script bag Planter-sidens knapper. `snooze1` (gammel 😴-knap) virker stadig
for pushes der lå på telefonen før 2026-10-05.

Kun stdlib. Test lokalt:  python3 scripts/plant_notify.py --dry-run
(vejr-delen kræver HA-adgang + token og springes over lokalt uden secrets.)
"""

import csv
import io
import json
import os
import sys
import urllib.request
from datetime import date, datetime, timedelta

import ha_secrets

try:
    from zoneinfo import ZoneInfo

    TZ = ZoneInfo("Europe/Copenhagen")
except Exception:  # pragma: no cover - tzdata altid til stede på HAOS core
    TZ = None

# Arkets id står i secrets.yaml (plant_sheet_id), ikke i git: CSV-eksporten
# er en læse-nøgle til arket.
SHEET_ID_KEY = "plant_sheet_id"
STATE_FILE = "/config/.plant_notify_state.json"
HA_URL = "http://127.0.0.1:8123"
# 2026-07-12: routet via central dispatch script (notif_id planter). Telefon-
# valg + master + tidsvindue styres fra 🔔 Notifikationer-fanen (packages/
# notifikationer.yaml).
NOTIFY_SERVICE = "script/push_notify"
NOTIF_ID = "planter"
WEATHER_ENTITY = "weather.forecast_home"

# 'Sidst Gødet' læses bevidst IKKE (user-spec 2026-07-29 — se modulets docstring).
COL_NOTIF = "Næste HA-notifikation"
COL_BESKED = "Næste HA-besked"
COL_ID = "ID"
COL_NAVN = "Kaldenavn"
COL_PLACERING = "Placering"
COL_FREQ = {
    "sommer": "Gødningsfrekvens sommer per måned",
    "forår": "Gødningsfrekvens forår per måned",
    "vinter": "Gødningsfrekvens vinter per måned",
    "efterår": "Gødningsfrekvens efterår per måned",
}

# Maks. antal plante-navne i gødnings-pushen (resten vises som "+ N flere" —
# beskeden skal kunne læses på en låseskærm; hele listen står på Planter-siden).
FERT_MAX_NAVNE = 24
FERT_TAG = "plant_fert"

# --- Vejr-advarsler (forecast-baseret). Juster her efter behov. ---
RAIN_DAYS = 3  # kig N dage frem for regn
RAIN_MM = 20.0  # samlet mm over vinduet → advarsel
HEAT_DAYS = 4  # kig N dage frem for varme
HEAT_TEMP = 26.0  # °C max-temp der tæller som "varm"
HEAT_MIN_DAYS = 2  # mindst M varme+solrige dage → advarsel
SUNNY_CONDS = {"sunny", "clear", "clear-night", "partlycloudy"}
WARN_COOLDOWN_DAYS = 2  # vent mindst N dage før samme vejr-advarsel gentages
# Krukke-planter der kan flyttes i ly (placering indeholder et af disse ord).
MOVABLE_HINTS = ("terrasse", "altan")


def log(msg):
    print(f"[plant_notify] {msg}", file=sys.stderr)


def now_local():
    return datetime.now(TZ) if TZ else datetime.now()


def parse_dt(s):
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(tzinfo=TZ) if TZ else dt
        except ValueError:
            continue
    log(f"uparsebar dato: {s!r}")
    return None


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError, json.JSONDecodeError:
        return {}


def save_state(state):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)
    os.replace(tmp, STATE_FILE)


def fetch_rows():
    url = f"https://docs.google.com/spreadsheets/d/{ha_secrets.get(SHEET_ID_KEY)}/export?format=csv"
    req = urllib.request.Request(url, headers={"User-Agent": "ha-plant-notify/1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read().decode("utf-8")
    return list(csv.DictReader(io.StringIO(data)))


def get_token():
    return ha_secrets.get(ha_secrets.HA_API_TOKEN)


def send_notify(token, title, message, payload=None):
    doc = {"notif_id": NOTIF_ID, "title": title, "message": message}
    if payload:
        doc["payload"] = payload
    body = json.dumps(doc).encode("utf-8")
    req = urllib.request.Request(
        f"{HA_URL}/api/services/{NOTIFY_SERVICE}",
        data=body,
        method="POST",
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status


def get_state(token, entity_id):
    req = urllib.request.Request(
        f"{HA_URL}/api/states/{entity_id}",
        headers={"Authorization": "Bearer " + token},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r).get("state")


def _hhmm(s):
    # input_datetime-state = "HH:MM:SS" -> minutter siden midnat.
    try:
        h, m, *_ = str(s).split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return None


def deliverable_now(token):
    """True hvis en planter-push RENT FAKTISK ville blive leveret/køet lige nu.

    B66-fix: script.push_notify returnerer HTTP 200 SELV når dens gate_ok-
    condition STOPPER sekvensen (uden for tidsvindue / master-off / type-off /
    ingen telefon valgt) — en haltet HA-condition er ikke en fejl. send() må
    derfor kun markere et varsel 'sendt' når gaten reelt leverer, ellers tabes
    det stille (dedup springer det over næste scan).

    SPEJL af gate_ok + targets for notif_id=planter i
    packages/notifikationer.yaml (script.push_notify). HOLD I SYNC dermed.
    Fejl/uvished -> True (fail-open: fixet må aldrig gøre det VÆRRE end før —
    kun droppe mark-sent når vi POSITIVT ved at gaten dropper).
    """
    try:
        if get_state(token, "input_boolean.notifikationer_master_enabled") != "on":
            return False
        if get_state(token, "input_boolean.notif_planter_enabled") != "on":
            return False
        if (
            get_state(token, "input_select.house_mode") == "AirBnB"
            and get_state(token, "input_boolean.notif_planter_airbnb") != "on"
        ):
            return False
        # mindst én telefon valgt (ellers har push_notify ingen target).
        if (
            get_state(token, "input_boolean.notif_planter_parent_a") != "on"
            and get_state(token, "input_boolean.notif_planter_parent_b") != "on"
        ):
            return False
        # tidsvindue (samme midnats-wrap-logik som gate_ok).
        s = _hhmm(get_state(token, "input_datetime.notif_planter_start"))
        e = _hhmm(get_state(token, "input_datetime.notif_planter_slut"))
        if s is None or e is None or s == e:
            return True
        n = now_local().hour * 60 + now_local().minute
        return (s <= n < e) if s < e else (n >= s or n < e)
    except Exception as ex:
        log(f"deliverability-tjek fejlede ({ex}) — fail-open, sender som før")
        return True


def get_daily_forecast(token):
    body = json.dumps({"type": "daily", "entity_id": WEATHER_ENTITY}).encode("utf-8")
    req = urllib.request.Request(
        f"{HA_URL}/api/services/weather/get_forecasts?return_response",
        data=body,
        method="POST",
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        resp = json.load(r)
    return resp["service_response"][WEATHER_ENTITY]["forecast"]


def keymatch(keys, want):
    for k in keys:
        if k and k.strip() == want:
            return k
    return None


def season_of(month):
    if 3 <= month <= 5:
        return "forår"
    if 6 <= month <= 8:
        return "sommer"
    if 9 <= month <= 11:
        return "efterår"
    return "vinter"


def fnum(s):
    if s is None or s == "":
        return 0.0
    if isinstance(s, (int, float)):
        return float(s)
    try:
        return float(str(s).replace(",", ".").strip() or 0)
    except ValueError:
        return 0.0


def parse_iso_date(s):
    try:
        return date.fromisoformat(s) if s else None
    except ValueError, TypeError:
        return None


def fert_interval(freq):
    """Dage mellem gødninger ved `freq` gange pr. måned."""
    return max(1, round(30.4 / freq))


def fert_next(state, pid, interval, today):
    """Næste gødningsdato for planten (og persistér den hvis den mangler).

    Datoen står stille til user kvitterer ✅ (apply_fert_action) — en ukvitteret
    plante er derfor stadig forfalden næste morgen. Mangler den:
      • gammel model kørte -> `fert:<ID>` var cyklussen vi sidst mindede om
        → næste ligger et interval derefter (ingen dobbelt-påmindelse ved
        opgraderingen).
      • ellers (ny plante / sæson hvor freq lige er blevet > 0) -> baseline i
        dag, så første påmindelse kommer om et interval. Ville vi i stedet
        melde "forfalden nu", ville alle 44 planter blaste ved første kørsel.
    """
    key = "fert_next:" + pid
    nd = parse_iso_date(state.get(key))
    if nd is None:
        old = parse_iso_date(state.get("fert:" + pid))
        nd = (old + timedelta(days=interval)) if old else (today + timedelta(days=interval))
        state[key] = nd.isoformat()
    return nd


def due_fertilizer(rows, cols, state, today):
    """[(pid, navn, placering, interval)] for planter der skal gødes i dag
    (inkl. dem der har ventet på ✅ siden en tidligere dag)."""
    fcol = cols.get(COL_FREQ[season_of(today.month)])
    if not fcol:
        log("gødnings-frekvens-kolonne mangler — springer gødning over")
        return []
    out = []
    for r in rows:
        pid = (r.get(cols[COL_ID]) or "").strip()
        if not pid:
            continue
        freq = fnum(r.get(fcol))
        if freq <= 0:
            continue  # ingen gødning denne sæson
        interval = fert_interval(freq)
        if fert_next(state, pid, interval, today) > today:
            continue
        out.append(
            (
                pid,
                (r.get(cols[COL_NAVN]) or f"Plante {pid}").strip(),
                (r.get(cols[COL_PLACERING]) or "").strip(),
                interval,
            )
        )
    return out


def dk_dato(iso):
    """'2026-10-02' -> '2/10' (samme form i pushen og på Planter-siden)."""
    d = parse_iso_date(iso)
    return f"{d.day}/{d.month}" if d else ""


def migrate_legacy_batch(state, rows, cols):
    """Engangs-migrering fra modellen 'påmindelsen ER baseline' (til 2026-10-05).

    Den gamle model skubbede fert_next frem i det sekund pushen gik og huskede
    kun listen i `_fert_sent_ids`. Den push blev aldrig kvitteret — knappen
    fandtes ikke — så den genopstår som AFVENTER: datoen stilles tilbage til
    push-dagen, og næste kørsel i notif-vinduet spørger igen med ✅-knappen."""
    ids = state.pop("_fert_sent_ids", None)
    sent = state.pop("_fert_sent_date", None)
    if "_fert_last" in state or not ids or not parse_iso_date(sent):
        return
    by_id = {(r.get(cols[COL_ID]) or "").strip(): r for r in rows}
    fcol = cols.get(COL_FREQ[season_of(parse_iso_date(sent).month)])
    planter = []
    for pid in ids:
        r = by_id.get(pid)
        if r is None:
            continue  # slettet fra arket siden
        freq = fnum(r.get(fcol)) if fcol else 0.0
        planter.append(
            {
                "id": pid,
                "navn": (r.get(cols[COL_NAVN]) or f"Plante {pid}").strip(),
                "plac": (r.get(cols[COL_PLACERING]) or "").strip(),
                "iv": fert_interval(freq) if freq > 0 else 30,
            }
        )
        state["fert_next:" + pid] = sent
    state["_fert_last"] = {
        "sendt": sent,
        "foerst": sent,
        "antal": 1,
        "planter": planter,
        "status": "afventer",
    }
    log(f"migrering: push fra {sent} ({len(planter)} planter) står nu som afventer ✅")


def apply_fert_action(act, today=None, state=None):
    """✅ Gødet / 📅 +1 uge — fra pushen eller Planter-siden (via
    script.planter_goedning_kvitter). Gælder ALLE planter i den seneste
    gødnings-push; den er samlet, så der er ikke ét plante-ID.

    ✅ lægger næste runde et interval frem fra I DAG (kvitterings-dagen), ikke
    fra forfaldsdagen: blev planten først gødet tre dage for sent, er den også
    gødet tre dage senere. En batch der allerede er lukket en tidligere dag,
    røres ikke — Planter-sidens knapper står der altid (Lovelace kan ikke
    skjule et kort på en attribut), og et tryk på en gammel batch ville
    ellers flytte en dato ingen har bedt om at flytte. Samme dag må man gerne
    ombestemme sig (✅ fra siden efter 📅 på telefonen)."""
    if act not in ("done", "snooze1", "snooze7"):
        log(f"ukendt fert-action: {act!r}")
        return 1, state
    own_state = state is None
    if own_state:
        state = load_state()
    today = today or now_local().date()
    last = state.get("_fert_last") or {}
    planter = last.get("planter") or []
    lukket_foer = (
        last.get("status") in ("gødet", "udskudt") and last.get("kvitteret") != today.isoformat()
    )
    if not planter or lukket_foer:
        log(f"fert-action {act}: ingen åben gødnings-push at kvittere")
        return 0, state
    for p in planter:
        pid = p["id"]
        if act == "done":
            iv = int(p.get("iv") or 30)
            state["fert_next:" + pid] = (today + timedelta(days=iv)).isoformat()
            state["fert_sidst:" + pid] = today.isoformat()
        else:
            dage = 1 if act == "snooze1" else 7
            state["fert_next:" + pid] = (today + timedelta(days=dage)).isoformat()
    last["kvitteret"] = today.isoformat()
    if act == "done":
        last["status"] = "gødet"
        last.pop("udskudt_til", None)
    else:
        last["status"] = "udskudt"
        last["udskudt_til"] = state["fert_next:" + planter[0]["id"]]
    state["_fert_last"] = last
    if own_state:
        save_state(state)
    log(f"fert-action {act}: {len(planter)} planter → {last['status']}")
    return 0, state


# --- de to notifikations-typer -----------------------------------------------


def process_fertilizer(rows, cols, state, today, send):
    due = due_fertilizer(rows, cols, state, today)
    if not due:
        return
    last = state.get("_fert_last") or {}
    # Højst én gødnings-push pr. dag: start-triggeren kører ved HVER HA-genstart
    # (flere gange dagligt), og fert_next står nu stille indtil ✅ — uden denne
    # ville hver genstart i notif-vinduet gentage den ukvitterede push.
    if last.get("sendt") == today.isoformat() and last.get("status") == "afventer":
        return
    season = season_of(today.month)
    # Er det den SAMME ukvitterede opgave igen (eller en udskudt der er forfalden
    # på ny)? Så bærer pushen "venter siden" fra første gang den blev sendt.
    aaben = last.get("status") in ("afventer", "udskudt")
    gammel_ids = {p.get("id") for p in (last.get("planter") or [])}
    gentaget = aaben and any(pid in gammel_ids for pid, *_ in due)
    foerst = (last.get("foerst") or last.get("sendt")) if gentaget else today.isoformat()
    # Grupperet efter placering: det er sådan man går rundt med kanden.
    grupper = {}
    for pid, navn, plac, _iv in due[:FERT_MAX_NAVNE]:
        grupper.setdefault(plac or "Uden placering", []).append(f"#{pid} {navn}")
    linjer = [f"**{plac}:** " + ", ".join(navne) for plac, navne in grupper.items()]
    rest = len(due) - FERT_MAX_NAVNE
    if rest > 0:
        linjer.append(f"+ {rest} flere (se Planter-siden)")
    hvad = f"{len(due)} planter" if len(due) > 1 else due[0][1]
    title = f"🌿 Stadig ikke gødet: {hvad}" if gentaget else f"🌿 Gød {hvad} i dag"
    msg = "\n".join(linjer)
    if gentaget:
        msg += f"\n\nVenter siden {dk_dato(foerst)}."
    msg += (
        "\n\nTryk ✅ Gødet når det er gjort — ellers minder jeg dig igen i "
        f"morgen. Næste runde følger {season}-frekvensen (~hver "
        + "/".join(str(i) for i in sorted({d[3] for d in due}))
        + " dage)."
    )
    payload = {
        "tag": FERT_TAG,
        "actions": [
            {"action": "PLANT_FERT_DONE", "title": "✅ Gødet"},
            {"action": "PLANT_FERT_SNOOZE7", "title": "📅 +1 uge"},
        ],
    }
    if send(title, msg, payload):
        # fert_next røres IKKE her — kun ✅/📅 flytter den (apply_fert_action).
        state["_fert_last"] = {
            "sendt": today.isoformat(),
            "foerst": foerst,
            "antal": (int(last.get("antal") or 1) + 1) if gentaget else 1,
            "planter": [
                {"id": pid, "navn": navn, "plac": plac, "iv": iv} for pid, navn, plac, iv in due
            ],
            "status": "afventer",
        }


def _cooldown_ok(state, key, today):
    last = state.get(key)
    if not last:
        return True
    try:
        return (today - date.fromisoformat(last)).days >= WARN_COOLDOWN_DAYS
    except ValueError:
        return True


def process_weather(rows, cols, state, today, send, fc):
    if not fc:
        log("vejr-forecast utilgængelig — springer vejr-advarsler over")
        return
    # markør så vi kan bekræfte at forecast-fetch lykkedes (debug/observability)
    state["_weather_checked"] = today.isoformat()
    movable = [
        (r.get(cols[COL_NAVN]) or "").strip()
        for r in rows
        if (r.get(cols[COL_ID]) or "").strip()
        and any(h in (r.get(cols[COL_PLACERING]) or "").lower() for h in MOVABLE_HINTS)
    ]
    n_mov = len([m for m in movable if m])

    # --- Regn-advarsel ---
    rain_sum = sum(fnum(d.get("precipitation")) for d in fc[:RAIN_DAYS])
    if rain_sum >= RAIN_MM and _cooldown_ok(state, "_rain_warn", today):
        title = "🌧️ Meget regn på vej"
        msg = (
            f"~{rain_sum:.0f} mm forventet over {RAIN_DAYS} dage. "
            f"Overvej at flytte de {n_mov} krukke-planter på terrasse/altan i ly "
            f"(eller tjek dræn)."
        )
        if send(title, msg):
            state["_rain_warn"] = today.isoformat()

    # --- Varme/sol-advarsel ---
    hot = [
        d
        for d in fc[:HEAT_DAYS]
        if fnum(d.get("temperature")) >= HEAT_TEMP
        and str(d.get("condition", "")).lower() in SUNNY_CONDS
    ]
    if len(hot) >= HEAT_MIN_DAYS and _cooldown_ok(state, "_heat_warn", today):
        maxt = max(fnum(d.get("temperature")) for d in hot)
        title = "☀️ Varmt og solrigt på vej"
        msg = (
            f"{len(hot)} varme, solrige dage forude (op til {maxt:.0f}°C). "
            f"Vand ekstra og skyg følsomme planter — krukker tørrer hurtigt ud."
        )
        if send(title, msg):
            state["_heat_warn"] = today.isoformat()


def sidste_goedning(state, today):
    """Planter-sidens "sidste gødnings-påmindelse": hvem pushen bad om, og om
    den er kvitteret. Teksten bygges HER (testbart) frem for i Jinja."""
    last = state.get("_fert_last") or {}
    planter = [
        {"id": p.get("id"), "navn": p.get("navn"), "plac": p.get("plac")}
        for p in (last.get("planter") or [])
    ]
    status = last.get("status")
    if not planter:
        tekst = ""
    elif status == "gødet":
        tekst = f"✅ Gødet {dk_dato(last.get('kvitteret'))}"
    elif status == "udskudt":
        tekst = f"📅 Udskudt til {dk_dato(last.get('udskudt_til'))}"
    else:
        antal = int(last.get("antal") or 1)
        tekst = f"⏳ Venter på ✅ — spurgt {dk_dato(last.get('foerst'))}" + (
            f", {antal}× i alt" if antal > 1 else ""
        )
    return {
        "status": status or "",
        "status_tekst": tekst,
        "sendt": last.get("sendt") or "",
        "planter": planter[:40],
    }


def publish_overview(rows, cols, state, today, fc, get_tok, dry):
    """Publicér sensor.plant_overview (kommende vandinger + gødninger + vejr) så
    plante-dashboardet kan vise 'upcoming varsler'. Sættes via REST API; gen-
    populeres ved hver daglig kørsel + HA-start (automationens start-trigger)."""
    season = season_of(today.month)
    fcol = cols.get(COL_FREQ[season])
    watering, fert, n_plants = [], [], 0
    for r in rows:
        pid = (r.get(cols[COL_ID]) or "").strip()
        if not pid:
            continue
        n_plants += 1
        navn = (r.get(cols[COL_NAVN]) or f"Plante {pid}").strip()
        plac = (r.get(cols[COL_PLACERING]) or "").strip()
        wdt = parse_dt(r.get(cols[COL_NOTIF]))
        besked = (r.get(cols[COL_BESKED]) or "").strip()
        if wdt and besked:
            d = wdt.date()
            dage = (d - today).days
            # 2026-06-17 (user-spec): forældede (forfaldne i fortiden) events vises
            # ikke på plantesiden — brugeren tikker ikke tasks af, så past-due ville
            # ellers hænge som "X d forsinket". Kun i dag + fremtid medtages.
            if dage >= 0:
                watering.append(
                    {
                        "id": pid,
                        "navn": navn,
                        "plac": plac,
                        "dato": d.isoformat(),
                        "dage": dage,
                        "besked": besked,
                    }
                )
        if fcol:
            freq = fnum(r.get(fcol))
            if freq > 0:
                nd = fert_next(state, pid, fert_interval(freq), today)
                dage = (nd - today).days
                # Forfaldne (dage < 0) = venter på ✅ fra en tidligere dag, eller
                # pushen kunne ikke leveres endnu (uden for notif-vinduet) —
                # vis dem som "i dag".
                fert.append(
                    {
                        "id": pid,
                        "navn": navn,
                        "plac": plac,
                        "dato": nd.isoformat(),
                        "dage": max(dage, 0),
                    }
                )
    watering.sort(key=lambda x: x["dato"])
    fert.sort(key=lambda x: x["dato"])
    rain_mm, hot_days, maxt = 0.0, 0, None
    if fc:
        rain_mm = round(sum(fnum(d.get("precipitation")) for d in fc[:RAIN_DAYS]), 1)
        hotd = [
            d
            for d in fc[:HEAT_DAYS]
            if fnum(d.get("temperature")) >= HEAT_TEMP
            and str(d.get("condition", "")).lower() in SUNNY_CONDS
        ]
        hot_days = len(hotd)
        if hotd:
            maxt = max(fnum(d.get("temperature")) for d in hotd)
    due_w = sum(1 for w in watering if w["dage"] <= 0)
    # fert_next står stille til ✅, så "forfalden" = "ikke kvitteret endnu" —
    # siden og pushen kan ikke længere sige hver sit (jf. 2026-08-13).
    due_f = sum(1 for f in fert if f["dage"] <= 0)
    attrs = {
        "friendly_name": "Plante-oversigt",
        "icon": "mdi:sprout",
        "updated": now_local().strftime("%Y-%m-%d %H:%M"),
        "antal_planter": n_plants,
        "forfaldne_vanding": due_w,
        "forfaldne_goedning": due_f,
        "vanding": watering[:20],
        "goedning": fert[:20],
        "sidste_goedning": sidste_goedning(state, today),
        "regn_3d_mm": rain_mm,
        "varme_dage": hot_days,
        "varme_maxtemp": maxt,
    }
    log(
        f"oversigt: {n_plants} planter, {due_w} vanding/{due_f} gødning forfaldne, "
        f"regn3d={rain_mm}mm, varme={hot_days}d"
    )
    if dry:
        return
    body = json.dumps({"state": f"{due_w + due_f} forfaldne", "attributes": attrs}).encode("utf-8")
    req = urllib.request.Request(
        f"{HA_URL}/api/states/sensor.plant_overview",
        data=body,
        method="POST",
        headers={"Authorization": "Bearer " + get_tok(), "Content-Type": "application/json"},
    )
    urllib.request.urlopen(req, timeout=30)


def load_sheet():
    """(rows, cols) — eller (None, None) hvis arket ikke kan bruges."""
    try:
        rows = fetch_rows()
    except Exception as e:
        log(f"CSV-hentning fejlede: {e}")
        return None, None
    if not rows:
        log("ingen rækker i arket")
        return None, None
    keys = list(rows[0].keys())
    cols = {
        name: keymatch(keys, name)
        for name in [COL_NOTIF, COL_BESKED, COL_ID, COL_NAVN, COL_PLACERING, *COL_FREQ.values()]
    }
    # ID + mindst én frekvens-kolonne er alt gødningen behøver; vandings-
    # kolonnerne bruges kun til dashboard-listen og må gerne mangle.
    if not (cols[COL_ID] and any(cols.get(c) for c in COL_FREQ.values())):
        log(f"påkrævede kolonner mangler. fandt: {keys}")
        return None, None
    return rows, cols


def main():
    dry = "--dry-run" in sys.argv
    today = now_local().date()

    # Push-knap-mode (✅/📅 fra telefonen eller Planter-siden): kvittér, gem, og
    # genudgiv oversigten MED DET SAMME — ellers stod siden på "venter" til
    # næste 08:00-kørsel, selvom brugeren lige har trykket.
    if "--fert-action" in sys.argv:
        try:
            act = sys.argv[sys.argv.index("--fert-action") + 1]
        except ValueError, IndexError:
            log("brug: --fert-action {done|snooze7}")
            return 1
        rc, state = apply_fert_action(act)
        if rc or state is None:
            return rc
        rows, cols = load_sheet()
        if rows:
            fc = None
            try:
                fc = get_daily_forecast(get_token())
            except Exception as e:
                log(f"forecast utilgængelig: {e}")
            try:
                publish_overview(rows, cols, state, today, fc, get_token, dry)
            except Exception as e:
                log(f"plante-oversigt publish fejlede: {e}")
            if not dry:
                save_state(state)  # fert_next() kan have sat baseline for nye planter
        return 0

    state = load_state()
    rows, cols = load_sheet()
    if rows is None:
        return 1
    migrate_legacy_batch(state, rows, cols)

    box = {"token": None, "sent": 0, "deliver": None}

    def get_tok():
        if box["token"] is None:
            box["token"] = get_token()
        return box["token"]

    def send(title, message, payload=None):
        log(f"NOTIFY: {title} -> {message!r}")
        if dry:
            box["sent"] += 1
            return True
        # B66-fix: markér KUN sendt hvis push_notify's gate reelt leverer nu.
        # Uden for gaten (fx HA-restart før 08:00-vinduet) droppes pushen stille
        # men returnerer 200 -> uden dette tjek ville item dedup'es væk = tabt.
        # Ikke-leverbar -> returnér False -> item forbliver pending -> leveres
        # ved næste in-window scan (08:00-daglig eller HA-start i vindue).
        if box["deliver"] is None:
            box["deliver"] = deliverable_now(get_tok())
        if not box["deliver"]:
            log(f"UDSKUDT (uden for planter-gate, forbliver pending): {title!r}")
            return False
        try:
            send_notify(get_tok(), title, message, payload)
            box["sent"] += 1
            return True
        except Exception as e:
            log(f"notify fejlede (prøver igen næste scan): {e}")
            return False

    # Forecast hentes én gang (bruges af både vejr-advarsler og plante-oversigt).
    fc = None
    try:
        fc = get_daily_forecast(get_tok())
    except Exception as e:
        log(f"forecast utilgængelig: {e}")

    process_fertilizer(rows, cols, state, today, send)
    process_weather(rows, cols, state, today, send, fc)
    try:
        publish_overview(rows, cols, state, today, fc, get_tok, dry)
    except Exception as e:
        log(f"plante-oversigt publish fejlede: {e}")

    if not dry:
        save_state(state)
    log(f"færdig. sendt={box['sent']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
