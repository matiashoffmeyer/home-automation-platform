#!/usr/bin/env python3
"""Himmelfænomen-varsler for København — aurora, planeter, lysende natteskyer.

Kører én gang hver aften (shell_command, se packages/sky_notifications.yaml) og
sender ÉN samlet notifikation til notify.mobile_app_phone_a (Parent A's telefon) —
men kun hvis mindst ét af tre fænomener er reelt synligt i nat:

  1) NORDLYS: forventet Kp (NOAA SWPC 3-døgns forecast) ≥ AURORA_KP_TRIGGER OG
     et GRADERET mørkt nok vindue (Kp 5-6 kræver astronomisk mørke -18°, Kp ≥7
     kun nautisk -12° — kraftig storm ses i lysere himmel) OG skydække ≤
     CLOUD_OK_MAX. Valgfri: core Aurora-integration (NOAA Ovation) giver en lokal
     synligheds-% der filtrerer svage storme uden reel projektion over DK.
     Sæson-gate falder ud af astronomien: i Kbh-sommeren (~apr–aug) når solen
     ikke dybt nok om natten → ingen falske sommer-nordlys-varsler.
  2) PLANET-ALIGNMENT: 2+ frie-øje-planeter (Merkur/Venus/Mars/Jupiter/Saturn)
     samtidig over PLANET_MIN_ALT° mod NORD/VEST/SYD i et mørkt vindue, og kun
     hvis skydække ≤ CLOUD_OK_MAX på det bedste tidspunkt. Planetpositioner
     beregnes i ren Python (Schlyter low-precision, ~1 bueminut — rigeligt).
  3) LYSENDE NATTESKYER (NLC): NLC-sæson (maj–aug) OG et dybt tusmørke-vindue
     (sol mellem -16° og -4°) OG skydække ≤ CLOUD_OK_MAX mod nord OG nordenvind
     (bearing ≥315° ell. ≤45° = vind fra nord = bedste chance). Bedste tidspunkt
     ~sol-midnat, lavt mod nord/nordvest.

LIVE-VAGT (--live, B228 2026-10-12): kører hvert kvarter om aftenen og varsler
"nordlys NU" når det sker — Kp for de seneste ~3-6 t (observeret/estimeret) +
Ovation-% NU + mørke NU + OBSERVERET skydække (DMI Kastrup, 10-min) i stedet for
met.no-prognosen. Lørdag 10/10-26 (Kp 7, Ovation 14 %) missede 21:30-prognosen:
met.no sagde 83-98 % skyer, Kastrup målte 0-25 % kl. 22:10-00:00. Egen dedup
(én live-besked pr. nat), uafhængig af aften-prognosen.

Alle tærskler er konstanter nedenfor (samme stil som scripts/plant_notify.py).
Dedup: /config/.sky_notify_state.json — én prognose- og én live-besked pr. nat.

Kun stdlib. Test lokalt:  python3 scripts/sky_notify.py --dry-run
(viser sol/planet-tabel + den besked der ville blive sendt; sender intet).
"""

import functools
import json
import math
import os
import sys
import urllib.request
from datetime import datetime, timedelta

import ha_secrets

try:
    from zoneinfo import ZoneInfo

    TZ = ZoneInfo("Europe/Copenhagen")
    UTC = ZoneInfo("UTC")
except Exception:  # pragma: no cover
    TZ = None
    UTC = None


# --- Lokation (HA home) -------------------------------------------------------
# Samme home_latitude/home_longitude som configuration.yaml giver HA — ét sted,
# ikke i git. Læses først når en beregning skal bruge dem.
@functools.cache
def home_location():
    """(lat, lon) for husets home-zone, fra secrets.yaml."""
    return float(ha_secrets.get("home_latitude")), float(ha_secrets.get("home_longitude"))


# --- HA-adgang ---------------------------------------------------------------
STATE_FILE = "/config/.sky_notify_state.json"
HA_URL = "http://127.0.0.1:8123"
# 2026-07-12: routet via central dispatch script (notif_id nordlys). Telefon-
# valg + master + tidsvindue styres fra 🔔 Notifikationer-fanen (packages/
# notifikationer.yaml). NOTIF_ID skal matche en notif_<id>_*-helper-gruppe.
NOTIFY_SERVICE = "script/push_notify"
NOTIF_ID = "nordlys"
WEATHER_ENTITY = "weather.forecast_home"
KP_FORECAST_URL = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json"

# --- Tærskler (juster her efter behov) ---------------------------------------
AURORA_KP_TRIGGER = 5.0  # forventet Kp ≥ dette → reel nordlys-chance på 55°N
AURORA_KP_STRONG = 7.0  # Kp ≥ dette = kraftig storm → synlig i lysere (nautisk) himmel
# Graderet mørke-krav (fix 2026-07-04): den gamle -6° (civil) fyrede falske
# sommer-varsler — i juli når Kbh-solen kun ~-11° og himlen er aldrig mørk nok
# til nordlys. Svagt nordlys kræver nu ægte astronomisk mørke; kraftig storm
# ses i lysere nautisk tusmørke. Sæson-gaten falder naturligt ud af astronomien:
AURORA_SUN_FAINT = -18.0  # svagt nordlys (Kp 5-6): astronomisk mørke (blokerer ~20. apr–22. aug)
AURORA_SUN_STRONG = -12.0  # kraftigt nordlys (Kp ≥7): nautisk mørke nok (blokerer ~21. maj–24. jul)
AURORA_OVATION_ENTITY = ""  # core Aurora-integration; "" = auto-discover sensor.*aurora* med %
AURORA_OVATION_MIN = 5.0  # % lokal Ovation-chance: under dette + kun moderat Kp = for lav → skip
CLOUD_OK_MAX = 40.0  # % skydække: over dette regnes himlen som for dækket
# Live-vagt: observeret skydække (DMI metObs, keyless, 10-min). Kastrup ~4 km fra huset.
DMI_OBS_URL = (
    "https://opendataapi.dmi.dk/v2/metObs/collections/observation/items"
    "?stationId=06180&parameterId=cloud_cover&period=latest-hour"
)
DMI_OBS_MAX_AGE_MIN = 40  # ældre observation = ukendt → fald tilbage til met.no
PLANET_MIN_ALT = 8.0  # ° over horisont før en planet regnes "synlig"
PLANET_SUN_MAX = -4.0  # sol-højde der definerer "mørkt nok til planeter"
NLC_MONTHS = {5, 6, 7, 8}  # lysende natteskyer-sæson (maj–aug)
NLC_SUN_HI = -4.0  # NLC-tusmørke: sol mellem NLC_SUN_LO og NLC_SUN_HI
NLC_SUN_LO = -16.0
# NLC ses lavt mod nord; user-spec 2026-07-10: varsl KUN ved nordenvind (vinden
# KOMMER fra nord = klarest/bedst chance mod nordhimlen). wind_bearing = retning
# vinden kommer FRA (met.no, N=0°). Nordlig sektor NV→N→NØ = bearing ≥315° ell. ≤45°.
NLC_WIND_FROM_MIN = 315.0
NLC_WIND_FROM_MAX = 45.0
SAMPLE_MIN = 15  # sampling-opløsning i minutter over natten

RAD = math.pi / 180.0
DEG = 180.0 / math.pi
CARDINALS = ["N", "NØ", "Ø", "SØ", "S", "SV", "V", "NV"]


def log(msg):
    print(f"[sky_notify] {msg}", file=sys.stderr)


def now_local():
    return datetime.now(TZ) if TZ else datetime.now()


# =============================================================================
# Astronomi (Paul Schlyter, "Computing planetary positions", low precision)
# =============================================================================
def _rev(x):
    return x % 360.0


def day_number(dt_utc):
    """Dage siden 2000-01-00 00:00 UT (inkl. brøkdel fra UT)."""
    Y, M, D = dt_utc.year, dt_utc.month, dt_utc.day
    ut = dt_utc.hour + dt_utc.minute / 60.0 + dt_utc.second / 3600.0
    d = 367 * Y - (7 * (Y + ((M + 9) // 12))) // 4 + (275 * M) // 9 + D - 730530
    return d + ut / 24.0


def _eccentric_anomaly(M, e):
    M = _rev(M)
    E = M + e * DEG * math.sin(M * RAD) * (1 + e * math.cos(M * RAD))
    for _ in range(8):
        dE = (E - e * DEG * math.sin(E * RAD) - M) / (1 - e * math.cos(E * RAD))
        E -= dE
        if abs(dE) < 1e-6:
            break
    return E


def sun_ecliptic(d):
    """Returnér (lon_sun_deg, r_sun, xs, ys) i geocentrisk ekliptik (z=0)."""
    w = 282.9404 + 4.70935e-5 * d
    e = 0.016709 - 1.151e-9 * d
    M = _rev(356.0470 + 0.9856002585 * d)
    E = _eccentric_anomaly(M, e)
    xv = math.cos(E * RAD) - e
    yv = math.sqrt(1 - e * e) * math.sin(E * RAD)
    v = _rev(math.atan2(yv, xv) * DEG)
    r = math.sqrt(xv * xv + yv * yv)
    lon = _rev(v + w)
    xs = r * math.cos(lon * RAD)
    ys = r * math.sin(lon * RAD)
    return lon, r, xs, ys, M, w


def obliquity(d):
    return 23.4393 - 3.563e-7 * d


# Orbital-elementer som funktioner af d (deg / AU). M reduceres mod 360.
PLANETS = {
    "Merkur": dict(
        N=(48.3313, 3.24587e-5),
        i=(7.0047, 5.00e-8),
        w=(29.1241, 1.01444e-5),
        a=0.387098,
        e=(0.205635, 5.59e-10),
        M=(168.6562, 4.0923344368),
    ),
    "Venus": dict(
        N=(76.6799, 2.46590e-5),
        i=(3.3946, 2.75e-8),
        w=(54.8910, 1.38374e-5),
        a=0.723330,
        e=(0.006773, -1.302e-9),
        M=(48.0052, 1.6021302244),
    ),
    "Mars": dict(
        N=(49.5574, 2.11081e-5),
        i=(1.8497, -1.78e-8),
        w=(286.5016, 2.92961e-5),
        a=1.523688,
        e=(0.093405, 2.516e-9),
        M=(18.6021, 0.5240207766),
    ),
    "Jupiter": dict(
        N=(100.4542, 2.76854e-5),
        i=(1.3030, -1.557e-7),
        w=(273.8777, 1.64505e-5),
        a=5.20256,
        e=(0.048498, 4.469e-9),
        M=(19.8950, 0.0830853001),
    ),
    "Saturn": dict(
        N=(113.6634, 2.38980e-5),
        i=(2.4886, -1.081e-7),
        w=(339.3939, 2.97661e-5),
        a=9.55475,
        e=(0.055546, -9.499e-9),
        M=(316.9670, 0.0334442282),
    ),
}


def planet_equatorial(name, d, xs, ys, ecl):
    """Geocentrisk RA/Dec (deg) for en planet."""
    el = PLANETS[name]
    N = el["N"][0] + el["N"][1] * d
    i = el["i"][0] + el["i"][1] * d
    w = el["w"][0] + el["w"][1] * d
    a = el["a"]
    e = el["e"][0] + el["e"][1] * d
    M = _rev(el["M"][0] + el["M"][1] * d)
    E = _eccentric_anomaly(M, e)
    xv = a * (math.cos(E * RAD) - e)
    yv = a * (math.sqrt(1 - e * e) * math.sin(E * RAD))
    v = _rev(math.atan2(yv, xv) * DEG)
    r = math.sqrt(xv * xv + yv * yv)
    # Heliocentrisk ekliptik
    vw = (v + w) * RAD
    Nr = N * RAD
    ir = i * RAD
    xh = r * (math.cos(Nr) * math.cos(vw) - math.sin(Nr) * math.sin(vw) * math.cos(ir))
    yh = r * (math.sin(Nr) * math.cos(vw) + math.cos(Nr) * math.sin(vw) * math.cos(ir))
    zh = r * (math.sin(vw) * math.sin(ir))
    # Geocentrisk ekliptik (+ solens geocentriske vektor)
    xg = xh + xs
    yg = yh + ys
    zg = zh
    # Roter til ækvator
    er = ecl * RAD
    xe = xg
    ye = yg * math.cos(er) - zg * math.sin(er)
    ze = yg * math.sin(er) + zg * math.cos(er)
    ra = _rev(math.atan2(ye, xe) * DEG)
    dec = math.atan2(ze, math.sqrt(xe * xe + ye * ye)) * DEG
    return ra, dec


def lst_hours(d, sun_M, sun_w, dt_utc):
    """Lokal siderisk tid (timer) for hjemmets længdegrad."""
    ut = dt_utc.hour + dt_utc.minute / 60.0 + dt_utc.second / 3600.0
    Ls = _rev(sun_M + sun_w)
    gmst0 = (Ls + 180.0) / 15.0  # timer
    return (gmst0 + ut + home_location()[1] / 15.0) % 24.0


def altaz(ra, dec, lst_h, lat=None):
    """Topocentrisk (alt, az) i grader. az fra nord, med uret (N=0,Ø=90,S=180,V=270)."""
    if lat is None:
        lat = home_location()[0]
    ha = lst_h * 15.0 - ra  # timevinkel i grader
    har = ha * RAD
    decr = dec * RAD
    latr = lat * RAD
    x = math.cos(har) * math.cos(decr)
    y = math.sin(har) * math.cos(decr)
    z = math.sin(decr)
    xhor = x * math.sin(latr) - z * math.cos(latr)
    yhor = y
    zhor = x * math.cos(latr) + z * math.sin(latr)
    az = _rev(math.atan2(yhor, xhor) * DEG + 180.0)
    alt = math.atan2(zhor, math.sqrt(xhor * xhor + yhor * yhor)) * DEG
    return alt, az


def sun_altitude(dt_utc):
    d = day_number(dt_utc)
    lon, r, xs, ys, M, w = sun_ecliptic(d)
    ecl = obliquity(d)
    # Solens ækvatoriale koordinater (geocentrisk, z=0)
    er = ecl * RAD
    xe = xs
    ye = ys * math.cos(er)
    ze = ys * math.sin(er)
    ra = _rev(math.atan2(ye, xe) * DEG)
    dec = math.atan2(ze, math.sqrt(xe * xe + ye * ye)) * DEG
    lst = lst_hours(d, M, w, dt_utc)
    alt, az = altaz(ra, dec, lst)
    return alt, az


def cardinal(az):
    return CARDINALS[int((az + 22.5) // 45) % 8]


def in_allowed_sector(az):
    """Nord/vest/syd (ekskl. øst 45–135°)."""
    return not (45.0 <= az < 135.0)


# =============================================================================
# Data: Kp-forecast + skydække
# =============================================================================
def fetch_kp_forecast():
    """Returnér liste af (utc_naive_datetime, kp_float, is_predicted)."""
    req = urllib.request.Request(KP_FORECAST_URL, headers={"User-Agent": "ha-sky-notify/1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    out = []
    for row in data:
        if isinstance(row, dict):
            tt, kp, obs = row.get("time_tag"), row.get("kp"), row.get("observed")
        else:  # ["time_tag","kp","observed",...] header + rows
            if row and row[0] == "time_tag":
                continue
            tt, kp = row[0], row[1]
            obs = row[2] if len(row) > 2 else None
        try:
            dt = datetime.strptime(tt[:19], "%Y-%m-%dT%H:%M:%S")
            if UTC:
                dt = dt.replace(tzinfo=UTC)
            out.append((dt, float(kp), str(obs) == "predicted"))
        except ValueError, TypeError:
            continue
    return out


def get_token():
    return ha_secrets.get(ha_secrets.HA_API_TOKEN)


def get_hourly_forecast(token):
    body = json.dumps({"type": "hourly", "entity_id": WEATHER_ENTITY}).encode("utf-8")
    req = urllib.request.Request(
        f"{HA_URL}/api/services/weather/get_forecasts?return_response",
        data=body,
        method="POST",
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        resp = json.load(r)
    return resp["service_response"][WEATHER_ENTITY]["forecast"]


def build_cloud_map(forecast):
    """{ (local-date, hour) : cloud% }."""
    cm = {}
    for h in forecast or []:
        try:
            dt = datetime.fromisoformat(h["datetime"])
            if TZ:
                dt = dt.astimezone(TZ)
            cm[(dt.date(), dt.hour)] = float(h.get("cloud_coverage") or 0.0)
        except ValueError, KeyError, TypeError:
            continue
    return cm


def cloud_at(cm, local_dt):
    return cm.get((local_dt.date(), local_dt.hour))


def build_wind_map(forecast):
    """{ (local-date, hour) : wind_bearing° } — retning vinden KOMMER fra (N=0)."""
    wm = {}
    for h in forecast or []:
        try:
            dt = datetime.fromisoformat(h["datetime"])
            if TZ:
                dt = dt.astimezone(TZ)
            wb = h.get("wind_bearing")
            if wb is not None:
                wm[(dt.date(), dt.hour)] = float(wb)
        except ValueError, KeyError, TypeError:
            continue
    return wm


def wind_at(wm, local_dt):
    return wm.get((local_dt.date(), local_dt.hour))


def is_northerly(bearing):
    """True hvis vinden kommer fra nordlig sektor (NV→N→NØ). None hvis ukendt."""
    if bearing is None:
        return None
    return bearing >= NLC_WIND_FROM_MIN or bearing <= NLC_WIND_FROM_MAX


def get_ovation_pct(token):
    """Core Aurora-integrationens lokations-synligheds-% (NOAA Ovation).

    Auto-discover: hvis AURORA_OVATION_ENTITY er sat bruges den, ellers findes
    en sensor hvis entity_id indeholder 'aurora' med en numerisk 0–100 %-state
    ('visibility' i navnet foretrækkes). Returnér None hvis integrationen ikke
    er installeret (så scriptet kører videre på ren Kp — graceful).
    """
    req = urllib.request.Request(
        f"{HA_URL}/api/states", headers={"Authorization": "Bearer " + token}
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        states = json.load(r)
    by_id = {s.get("entity_id"): s for s in states}

    def pct(s):
        if not s:
            return None
        try:
            v = float(s["state"])
        except ValueError, KeyError, TypeError:
            return None
        return v if 0.0 <= v <= 100.0 else None

    if AURORA_OVATION_ENTITY:
        v = pct(by_id.get(AURORA_OVATION_ENTITY))
        if v is not None:
            return v
    best = None  # ((rank, v), v)
    for eid, s in by_id.items():
        if not eid or not eid.startswith("sensor.") or "aurora" not in eid:
            continue
        v = pct(s)
        if v is None:
            continue
        rank = (1 if "visibility" in eid else 0, v)
        if best is None or rank > best[0]:
            best = (rank, v)
    return best[1] if best else None


def send_notify(token, title, message):
    body = json.dumps({"notif_id": NOTIF_ID, "title": title, "message": message}).encode("utf-8")
    req = urllib.request.Request(
        f"{HA_URL}/api/services/{NOTIFY_SERVICE}",
        data=body,
        method="POST",
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status


def publish_sensor(token, state, attrs):
    body = json.dumps({"state": state, "attributes": attrs}).encode("utf-8")
    req = urllib.request.Request(
        f"{HA_URL}/api/states/sensor.sky_tonight",
        data=body,
        method="POST",
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
    )
    urllib.request.urlopen(req, timeout=30)


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


# =============================================================================
# Hoved-logik
# =============================================================================
def night_samples(base_local):
    """Sampling fra kl 21:00 i aften til 05:00 i morgen (local)."""
    start = base_local.replace(hour=21, minute=0, second=0, microsecond=0)
    if base_local.hour < 12:  # kørt om morgenen → nat var i går
        start -= timedelta(days=1)
    samples = []
    t = start
    end = start + timedelta(hours=8)
    while t <= end:
        utc = t.astimezone(UTC) if UTC else t
        alt, _ = sun_altitude(utc)
        samples.append((t, utc, alt))
        t += timedelta(minutes=SAMPLE_MIN)
    return samples


def fmt(t):
    return t.strftime("%H:%M")


def assess_aurora(samples, kp_rows, cm, ovation=None):
    if not samples or not kp_rows:
        return None
    # Kp over natten (hele sample-spændet — storm-styrken, ikke synligheden).
    # Kp-rækkerne er 3-t-bins stemplet med STARTEN: 18 UTC-bin'en dækker 20-23
    # lokal og hører med, selvom den starter før kl. 21 (missede Kp 6,7 10/10).
    night_start_utc, night_end_utc = samples[0][1], samples[-1][1]
    kp_night = [
        kp
        for (dt, kp, pred) in kp_rows
        if night_start_utc - timedelta(hours=3) < dt <= night_end_utc
    ]
    if not kp_night:
        return None
    kp_max = max(kp_night)
    if kp_max < AURORA_KP_TRIGGER:
        return None
    # Graderet mørke-krav: kraftig storm ses i lysere himmel end svag. Er der
    # intet vindue mørkt nok = ikke nordlys-sæson i Kbh → intet varsel.
    required = AURORA_SUN_STRONG if kp_max >= AURORA_KP_STRONG else AURORA_SUN_FAINT
    dark = [(t, u, a) for (t, u, a) in samples if a < required]
    if not dark:
        return None
    # Lokal Ovation-chance (core Aurora-integration): filtrér svage storme uden
    # reel projektion over DK. Kraftige storme (≥ strong) slipper altid igennem.
    if ovation is not None and ovation < AURORA_OVATION_MIN and kp_max < AURORA_KP_STRONG:
        return None
    # bedste vindue = mørke timer med lavest skydække
    best = min(dark, key=lambda s: cloud_at(cm, s[0]) if cloud_at(cm, s[0]) is not None else 100)
    cl = cloud_at(cm, best[0])
    if cl is not None and cl > CLOUD_OK_MAX:
        # B228 (user-valg b, 12/10): en kraftig storm varsles alligevel —
        # met.no er for høj om natten (lørdag 10/10: 83-98 % lovet, 0-25 % målt).
        if kp_max < AURORA_KP_STRONG:
            return None
        return (
            f"🌌 Nordlys: kraftig storm — forventet Kp ~{kp_max:.0f}, men prognosen "
            f"siger skydække ~{cl:.0f}%. Hold øje med huller i skyerne "
            f"{fmt(dark[0][0])}–{fmt(dark[-1][0])} lavt mod NORD — "
            f"live-vagten pusher hvis DMI måler klart."
        )
    chance = "god" if kp_max >= 6 else "moderat"
    ov_txt = f", lokal-chance ~{ovation:.0f}%" if ovation is not None else ""
    return (
        f"🌌 Nordlys: {chance} chance — forventet Kp ~{kp_max:.0f}{ov_txt}. Bedst "
        f"{fmt(dark[0][0])}–{fmt(dark[-1][0])} lavt mod NORD"
        + (f" (skydække ~{cl:.0f}%)." if cl is not None else ".")
    )


def kp_recent(kp_rows, now_utc):
    """Max Kp for bin'en der dækker NU + den forrige (Kp er et 3-t-bagudblik)."""
    vals = [kp for (dt, kp, pred) in kp_rows if now_utc - timedelta(hours=6) < dt <= now_utc]
    return max(vals) if vals else None


def fetch_dmi_cloud(now_utc):
    """Seneste observerede skydække (%) fra DMI Kastrup, eller None hvis for gammel."""
    req = urllib.request.Request(DMI_OBS_URL, headers={"User-Agent": "ha-sky-notify/1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    best = None
    for f in data.get("features", []):
        p = f.get("properties", {})
        try:
            t = datetime.fromisoformat(p["observed"].replace("Z", "+00:00"))
            v = float(p["value"])
        except KeyError, ValueError, TypeError:
            continue
        if best is None or t > best[0]:
            best = (t, v)
    if best is None or now_utc - best[0] > timedelta(minutes=DMI_OBS_MAX_AGE_MIN):
        return None
    return best[1]


def assess_aurora_live(now_local_dt, kp_rows, ovation, cloud_obs, cm):
    """Nordlys NU: storm i gang + mørkt NU + klart NU. Samme gates som prognosen."""
    now_utc = now_local_dt.astimezone(UTC) if UTC else now_local_dt
    kp = kp_recent(kp_rows, now_utc)
    if kp is None or kp < AURORA_KP_TRIGGER:
        return None
    if ovation is not None and ovation < AURORA_OVATION_MIN and kp < AURORA_KP_STRONG:
        return None
    required = AURORA_SUN_STRONG if kp >= AURORA_KP_STRONG else AURORA_SUN_FAINT
    alt, _ = sun_altitude(now_utc)
    if alt >= required:
        return None
    cl, src = cloud_obs, "målt Kastrup"
    if cl is None:
        cl, src = cloud_at(cm, now_local_dt), "prognose"
    if cl is not None and cl > CLOUD_OK_MAX:
        return None
    ov_txt = f", lokal-chance ~{ovation:.0f}%" if ovation is not None else ""
    cl_txt = f" Skydække ~{cl:.0f}% ({src})." if cl is not None else ""
    return (
        f"🌌 Nordlys NU: Kp ~{kp:.0f}{ov_txt}. Kig lavt mod NORD, væk fra "
        f"lys — kameraet ser mere end øjet.{cl_txt}"
    )


def assess_planets(samples, cm):
    best = None  # (count, sum_alt, local_t, visible_list)
    for t, u, sun_alt in samples:
        if sun_alt >= PLANET_SUN_MAX:
            continue
        cl = cloud_at(cm, t)
        if cl is not None and cl > CLOUD_OK_MAX:
            continue
        d = day_number(u)
        lon, r, xs, ys, M, w = sun_ecliptic(d)
        ecl = obliquity(d)
        lst = lst_hours(d, M, w, u)
        vis = []
        for name in PLANETS:
            ra, dec = planet_equatorial(name, d, xs, ys, ecl)
            alt, az = altaz(ra, dec, lst)
            if alt >= PLANET_MIN_ALT and in_allowed_sector(az):
                vis.append((name, alt, az))
        if len(vis) >= 2:
            score = (len(vis), sum(v[1] for v in vis))
            if best is None or score > best[0]:
                best = (score, t, cl, vis)
    if not best:
        return None
    _, t, cl, vis = best
    parts = [
        f"{n} {a:.0f}° i {cardinal(z).lower()}" for (n, a, z) in sorted(vis, key=lambda v: -v[1])
    ]
    return (
        f"🪐 Planeter: {len(vis)} synlige sammen ~{fmt(t)} — "
        + ", ".join(parts)
        + (f" (skydække ~{cl:.0f}%)." if cl is not None else ".")
    )


def assess_nlc(samples, cm, wm, month):
    if month not in NLC_MONTHS:
        return None
    window = [(t, u, a) for (t, u, a) in samples if NLC_SUN_LO <= a <= NLC_SUN_HI]
    if not window:
        return None
    # bedste chance ~sol-midnat (dybeste tusmørke)
    deepest = min(window, key=lambda s: s[2])
    cl = cloud_at(cm, deepest[0])
    if cl is not None and cl > CLOUD_OK_MAX:
        return None
    # user-spec 2026-07-10: varsl KUN ved nordenvind (bedst chance). Ukendt
    # vind (None) blokerer ikke — graceful, som skydække.
    wb = wind_at(wm, deepest[0])
    if is_northerly(wb) is False:
        return None
    wind_txt = f", nordenvind {wb:.0f}°" if wb is not None else ""
    return (
        f"🌙 Lysende natteskyer: gode betingelser ~{fmt(deepest[0])} lavt mod "
        f"NORD/NORDVEST (dyb tusmørke, sol {deepest[2]:.0f}°"
        + (f", skydække ~{cl:.0f}%" if cl is not None else "")
        + wind_txt
        + ")."
        + " Kig efter sølvblå, bølgede skyer på den lyse nordhimmel."
    )


def main():
    dry = "--dry-run" in sys.argv
    no_notify = "--no-notify" in sys.argv  # publicér sensor, send IKKE notifikation
    live = "--live" in sys.argv  # live-vagt: kun "nordlys NU"
    base = now_local()
    night_key = (base if base.hour >= 12 else base - timedelta(days=1)).date().isoformat()
    samples = night_samples(base)

    token = None
    if not dry:
        token = get_token()

    # Skydække + vind
    cm = {}
    wm = {}
    try:
        fc = get_hourly_forecast(token) if token else None
        if dry and fc is None:
            fc = get_hourly_forecast(get_token())
        cm = build_cloud_map(fc)
        wm = build_wind_map(fc)
    except Exception as e:
        log(f"skydække/vind utilgængelig: {e}")

    # Kp
    kp_rows = []
    try:
        kp_rows = fetch_kp_forecast()
    except Exception as e:
        log(f"Kp-forecast utilgængelig: {e}")

    # Ovation lokal-synligheds-% (core Aurora-integration, valgfri)
    ovation = None
    try:
        ov_token = token or get_token()
        ovation = get_ovation_pct(ov_token)
    except Exception as e:
        log(f"Ovation-opslag fejlede: {e}")

    if dry:
        log("--- sol-højde over natten ---")
        for t, _u, a in samples[::2]:
            log(f"  {fmt(t)}  sol={a:5.1f}°  cloud={cloud_at(cm, t)}")
        log(f"Ovation lokal-chance = {ovation}")

    if live:
        return run_live(base, night_key, token, dry, kp_rows, ovation, cm)

    aurora = assess_aurora(samples, kp_rows, cm, ovation)
    planets = assess_planets(samples, cm)
    nlc = assess_nlc(samples, cm, wm, base.month)

    lines = [x for x in (aurora, planets, nlc) if x]
    summary = (
        " + ".join(s for s, x in (("Nordlys", aurora), ("Planeter", planets), ("NLC", nlc)) if x)
        or "Intet i nat"
    )

    attrs = {
        "friendly_name": "Himmelfænomener i nat",
        "icon": "mdi:weather-night",
        "updated": base.strftime("%Y-%m-%d %H:%M"),
        "nordlys": aurora or "",
        "planeter": planets or "",
        "natteskyer": nlc or "",
        "nat": night_key,
    }

    if dry:
        log("=== ville sende ===" if lines else "=== intet at sende ===")
        if lines:
            log("🌌 Himmelfænomener i nat")
            for l in lines:
                log("  " + l)
        log(f"sensor.sky_tonight = {summary!r}")
        return 0

    try:
        publish_sensor(token, summary, attrs)
    except Exception as e:
        log(f"sensor-publish fejlede: {e}")

    if no_notify:
        log("--no-notify: sensor opdateret, springer notifikation over")
        return 0

    if not lines:
        log("intet synligt i nat — ingen besked")
        return 0

    state = load_state()
    if aurora and state.get("live_sent_night") == night_key:
        # live-vagten har allerede sagt "nordlys NU" i aften — gentag det ikke
        lines = [x for x in lines if x is not aurora]
        if not lines:
            log("nordlys allerede live-varslet i aften — ingen besked")
            return 0
    if state.get("sent_night") == night_key:
        log(f"allerede sendt for nat {night_key} — skipper")
        return 0

    msg = "\n".join(lines)
    try:
        send_notify(token, "🌌 Himmelfænomener i nat", msg)
        state["sent_night"] = night_key
        save_state(state)
        log(f"sendt ({len(lines)} fænomen(er)) for nat {night_key}")
    except Exception as e:
        log(f"notify fejlede (prøver igen næste kørsel): {e}")
        return 1
    return 0


def run_live(base, night_key, token, dry, kp_rows, ovation, cm):
    now_utc = base.astimezone(UTC) if UTC else base
    cloud_obs = None
    try:
        cloud_obs = fetch_dmi_cloud(now_utc)
    except Exception as e:
        log(f"DMI-skydække utilgængelig: {e}")
    line = assess_aurora_live(base, kp_rows, ovation, cloud_obs, cm)
    if dry:
        log(
            f"live: Kp(seneste)={kp_recent(kp_rows, now_utc)} ovation={ovation} "
            f"sol={sun_altitude(now_utc)[0]:.1f}° skyer(DMI)={cloud_obs} "
            f"skyer(prognose)={cloud_at(cm, base)}"
        )
        log(f"live: {line or 'intet nu'}")
        return 0
    if not line:
        return 0
    state = load_state()
    if state.get("live_sent_night") == night_key:
        log(f"live allerede sendt for nat {night_key}")
        return 0
    try:
        send_notify(token, "🌌 Nordlys lige nu", line)
        state["live_sent_night"] = night_key
        save_state(state)
        log(f"live sendt for nat {night_key}: {line}")
    except Exception as e:
        log(f"live notify fejlede (prøver igen næste kvarter): {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
