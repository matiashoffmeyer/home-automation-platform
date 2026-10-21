#!/usr/bin/env bash
# ha_health.sh: the house's standing health checks, in one place.
#
# Replaces a 47-line shell block that used to live in CLAUDE.md. Commands in a
# file that is run cost no context, while commands in an instruction file are
# read in every session. Output is deliberately short: counts and deviations,
# not dumps. Dig afterwards if something shows up.
#
# Runs on the Home Assistant host and uses $SUPERVISOR_TOKEN.
#
#   ./scripts/ha_health.sh              # everything (weekly check)
#   ./scripts/ha_health.sh deploy       # after a deploy: automations that failed
#                                       #   validation (failure class #22) + blind
#   ./scripts/ha_health.sh blind        # blind presence channels; read this FIRST
#                                       #   when explaining presence behaviour
#   ./scripts/ha_health.sh kamera       # guest-mode camera compliance (a legal
#                                       #   requirement); deliberately not notified
#   ./scripts/ha_health.sh log [n]      # the last n lines of the core log (200)
#   ./scripts/ha_health.sh flags|lights|noisy|zha|docs|backup|sys

set -uo pipefail
API="http://supervisor/core/api"
AUTH=(-H "Authorization: Bearer ${SUPERVISOR_TOKEN:?SUPERVISOR_TOKEN mangler}")
DB=/config/home-assistant_v2.db

api() { curl -s -m 30 "${AUTH[@]}" "$API/$1"; }
hdr() { printf '\n=== %s ===\n' "$1"; }

# Fejlklasse #22: en automation i unavailable er valideringsfejlet og STUM.
# Skal køres efter HVER deploy. Skelner ægte fejl fra registry-orphans:
# orphans bærer restored: true, ægte fejl gør ikke.
check_deploy() {
  hdr "Fejlede automations (fejlklasse #22)"
  api states | python3 -c '
import json,sys
bad=[s for s in json.load(sys.stdin)
     if s["entity_id"].startswith("automation.") and s["state"]=="unavailable"
     and not s["attributes"].get("restored")]
print(f"{len(bad)} valideringsfejlet")
for s in bad: print("  FEJL:", s["entity_id"])
if bad: print("  -> aarsag: ./scripts/ha_health.sh log | grep validat")
'
  hdr "Template-fejl i loggen (sidste 200 linjer)"
  local n; n=$(curl -s -m 30 "${AUTH[@]}" "http://supervisor/core/logs?lines=200" 2>/dev/null \
    | grep -ciE "could not be validated|TemplateError") || true
  echo "${n:-0} linjer med validerings-/template-fejl"
}

check_blind() {
  # Blinde presence-kanaler forklarer en MASSE adfaerd: `unavailable` laeses som
  # `off` overalt (fejlklasse #9), saa et doedt instrument svarer "her er tomt"
  # med fuld selvsikkerhed. Naesten altid fordi en vaegkontakt er slukket —
  # normal brug, ikke en fejl, og derfor varsles der ikke om det (09-09f).
  # Staar her saa enhver session ser det UDEN at vide at den skulle spoerge.
  hdr "Presence-blindhed (laes FOER du forklarer presence-adfaerd)"
  api states | python3 -c '
import json,sys
d={s["entity_id"]:s for s in json.load(sys.stdin)}
c=d.get("sensor.presence_signal_confidence")
b=d.get("binary_sensor.presence_kanaler_blinde")
if not c: print("konfidens-sensor mangler"); raise SystemExit
a=c["attributes"]; n=int(a.get("blinde_antal") or 0)
print("konfidens", c["state"], "% |", n, "blinde kanaler")
if n:
    print("  blinde:    ", a.get("blinde"))
    if b: print("  forklaret: ", b["attributes"].get("forklaret"),
                " (vaegkontakt slukket = normalt)")
    print("  -> presence-logik i DISSE rum svarer tomt uanset virkeligheden")
'
}

# AirBnB-kamera-compliance. Kameraet i koekkenet (gestus-stakken) SKAL vaere
# fuldstaendigt deaktiveret under AirBnB — det er et lovkrav, ikke en praeference.
# Tjekket bor HER og ikke i en notifikation, fordi en push om at kameraet stadig
# koerer netop ville afsloere at der ER et kamera (docs/gesture_recognition.md).
# Samme loesning som blindheds-maalingen i 09-09f: et varsel uden en modtager
# blev rullet tilbage til ren diagnostik.
#
# Lagene er IKKE ligevaerdige. Kun mennesket kan bevise "pakket vaek" — en
# stroemloes Tapo der ligger paa bordpladen er usynlig for enhver maaling, og
# DET er grunden til at kvitteringen i packages/kamera_airbnb_vagt.yaml er
# ankeret. Alt herunder kan kun FALSIFICERE den kvittering, aldrig erstatte den.
check_kamera() {
  hdr "AirBnB-kamera-compliance (lovkrav)"
  local addons; addons=$(curl -s -m 30 "${AUTH[@]}" "http://supervisor/addons" 2>/dev/null)
  api states | ADDONS="$addons" python3 -c '
import json,re,socket,sys,os,urllib.request
st=json.load(sys.stdin)
d={s["entity_id"]:s for s in st}
mode=(d.get("input_select.house_mode") or {}).get("state","?")

kameraer=[s["entity_id"] for s in st if s["entity_id"].startswith("camera.")]
# Plug-heuristik: kameraet sidder (09-14) i en almindelig stikkontakt uden
# plug-styring, saa listen er tom. Pares der en plug, skal den hedde noget med
# "kamera" — ellers er den usynlig her.
plugs=[s for s in st if s["entity_id"].split(".")[0] in ("switch","light")
       and "kamera" in s["entity_id"]]
try:
    ad=json.loads(os.environ.get("ADDONS") or "{}")
    lst=ad["data"]["addons"] if isinstance(ad.get("data"),dict) else (ad.get("data") or [])
except Exception:
    lst=[]
def har(a,*ord_):
    s=(a.get("slug","")+" "+a.get("name","")).lower()
    return all(o in s for o in ord_)
hr=[a for a in lst if har(a,"hand","recognition")]
# Shimmen er den der FAKTISK aabner RTSP-forbindelsen; hand_recognition henter
# kun JPEGs fra den. Kigger man kun efter gestus-add-on\x27et, overser man altsaa
# praecis det lag der traekker video ud af kameraet.
shim=[a for a in lst if har(a,"frame","shim")]

print(f"house_mode={mode} | {len(kameraer)} camera-entities | "
      f"{len(plugs)} kamera-plug | {len(shim)} frame-shim | {len(hr)} hand-recognition")

if not kameraer and not plugs and not hr and not shim:
    print("  intet at haandhaeve — kamera-stakken findes ikke i huset endnu")
    raise SystemExit

if mode != "AirBnB":
    print("  ikke AirBnB — ingen restriktion aktiv")
    raise SystemExit

def sup(path):
    req=urllib.request.Request("http://supervisor"+path,
        headers={"Authorization":"Bearer "+os.environ.get("SUPERVISOR_TOKEN","")})
    with urllib.request.urlopen(req,timeout=15) as r: return json.load(r)["data"]

def kamera_endpoints():
    """host:port fra shimmens egne options — ét sted at vedligeholde IP\x27en.

    RTSP-URL\x27en baerer kamera-kontoens kodeord, saa kun host og port maa
    forlade denne funktion; resten af strengen roeres aldrig.
    """
    ud=set()
    for a in shim:
        try: opts=sup("/addons/%s/info" % a["slug"]).get("options") or {}
        except Exception: continue
        for cam in opts.get("cameras") or []:
            m=re.match(r"rtsps?://(?:[^@/]*@)?([^/:]+)(?::(\d+))?", cam.get("rtsp_url") or "")
            if m: ud.add((m.group(1), int(m.group(2) or 554)))
    return ud

# Under AirBnB skal ALLE lag vaere nede.
fejl=[]
kvit=(d.get("input_text.kamera_airbnb_status") or {}).get("state","")
if not kvit.startswith("pakket_vaek"):
    fejl.append("IKKE KVITTERET: mennesket har ikke bekraeftet pakket vaek (%s)" % (kvit or "tom"))
for p in plugs:
    if p["state"] == "on": fejl.append("PLUG TAENDT: " + p["entity_id"])
for a in shim:
    if a.get("state") == "started": fejl.append("SHIM KOERER — aabner RTSP: " + str(a.get("slug")))
for a in hr:
    if a.get("state") == "started": fejl.append("ADD-ON KOERER: " + str(a.get("slug")))
for k in kameraer:
    if d[k]["state"] not in ("unavailable","off","idle"): fejl.append("KAMERA AKTIVT: " + k)
# Ensrettet bevis: svarer den, er den stroemfoerende. Tavshed betyder derimod
# INTET (forkert DHCP-lease, wifi nede), saa proben maa kun kunne tilfoeje en
# fejl — aldrig frikende. Derfor staar den efter kvitterings-tjekket.
for host,port in sorted(kamera_endpoints()):
    try:
        with socket.create_connection((host,port),timeout=2): pass
        fejl.append("KAMERA SVARER PAA %s:%d — den er STROEMFOERENDE" % (host,port))
    except OSError:
        pass
if fejl:
    print("  ⛔ IKKE COMPLIANT under AirBnB:")
    for f in fejl: print("    ", f)
    print("    -> traek stikket FOERST (juridisk lag), derefter shim + add-on")
else:
    print("  ✅ compliant: kvitteret, add-ons nede, kameraet svarer ikke")
'
}

check_flags() {
  # Kun TILSTANDS-flag. De ~150 konfig-flag (*_enabled, notif_*, *_spot_N) er
  # on by design og drukner signalet — de er ikke "stuck", de er indstillinger.
  hdr "Stuck-kandidater: tilstands-flag der staar on"
  api states | python3 -c '
import json,sys,re,datetime
skip=re.compile(r"_enabled$|^notif_|^dance_room_|_spot_\d+$|^user_prefs_")
now=datetime.datetime.now(datetime.timezone.utc)
rows=[]
for s in json.load(sys.stdin):
    if not s["entity_id"].startswith("input_boolean.") or s["state"]!="on": continue
    n=s["entity_id"][14:]
    if skip.search(n): continue
    age=(now-datetime.datetime.fromisoformat(s["last_changed"])).total_seconds()/3600
    rows.append((age,n))
print(len(rows),"tilstands-flag on (konfig-flag filtreret fra)")
for age,n in sorted(rows,reverse=True):
    print(f"  {age:6.1f} t  {n}" + ("   <-- gammelt, tjek" if age>36 else ""))
'
}

check_lights() {
  hdr "Lys taendt af automations seneste 24 t"
  local start; start=$(date -u -d '24 hours ago' '+%Y-%m-%dT%H:%M:%S')
  api "logbook/$start" | python3 -c '
import json,sys,collections
try: ev=json.load(sys.stdin)
except Exception: print("logbook tomt/fejl"); raise SystemExit
c=collections.Counter(e.get("context_name","?") for e in ev
    if str(e.get("entity_id","")).startswith("light.")
    and e.get("context_event_type")=="automation_triggered")
for name,n in c.most_common(12): print(f"  {n:4d}x {name}")
'
}

check_noisy() {
  hdr "Mest skiftende entities (24 t) — stoej/flap-jagt"
  sqlite3 "$DB" "SELECT sm.entity_id, COUNT(*) c FROM states_meta sm
    JOIN states s ON sm.metadata_id = s.metadata_id
    WHERE s.last_updated_ts > strftime('%s','now','-1 day')
    GROUP BY sm.entity_id ORDER BY c DESC LIMIT 15;" 2>/dev/null \
    || echo "  (DB laast — HA skriver; proev igen)"
}

check_zha() {
  hdr "Utilgaengelige devices (batteri/mesh)"
  api states | python3 -c '
import json,sys
u=[s["entity_id"] for s in json.load(sys.stdin)
   if s["state"]=="unavailable" and not s["attributes"].get("restored")
   and s["entity_id"].split(".")[0] in ("light","binary_sensor","sensor","cover","switch")]
print(len(u),"unavailable")
for e in sorted(u)[:20]: print("  ",e)
'
}

# Rum-dossiers + dependency_map er genererede; er de stale, svarer de FORKERT.
# (entity_catalog.md er vaek 2026-10-05: "hvor bruges X" = `hq.py where X`,
# som scanner LIVE og derfor aldrig er stale.)
check_docs() {
  hdr "Auto-docs friskhed"
  local cat=docs/auto/dependency_map.md
  [ -f "$cat" ] || { echo "  MANGLER: $cat -> python3 scripts/gen_docs.py"; return; }
  local nyest; nyest=$(find automations packages dashboards -name '*.yaml' -newer "$cat" 2>/dev/null | wc -l)
  echo "$nyest yaml-filer er nyere end dependency_map.md"
  if [ "$nyest" -gt 0 ]; then echo "  -> python3 scripts/gen_docs.py && git add docs/auto"; fi
}

check_backup() { hdr "Backups"; ls -1t /backup/ 2>/dev/null | head -5; }
check_sys()    { hdr "Ressourcer"; free -h | head -2; df -h /config | tail -1; uptime; }

case "${1:-all}" in
  deploy) check_deploy; check_blind ;;
  blind)  check_blind ;;
  kamera) check_kamera ;;
  flags)  check_flags ;;
  lights) check_lights ;;
  noisy)  check_noisy ;;
  zha)    check_zha ;;
  docs)   check_docs ;;
  backup) check_backup ;;
  sys)    check_sys ;;
  log)    curl -s -m 30 "${AUTH[@]}" "http://supervisor/core/logs?lines=${2:-200}" ;;
  all)    check_deploy; check_blind; check_kamera; check_flags; check_lights; check_noisy; check_zha; check_docs; check_backup; check_sys ;;
  *)      sed -n '2,18p' "$0"; exit 1 ;;
esac
