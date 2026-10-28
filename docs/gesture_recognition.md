# Hånd-gestus i køkkenet — implementeringsplan

> *Written in Danish. English overview: [README](../README.md) ·
> [ARCHITECTURE](../ARCHITECTURE.md).*

**Status 2026-09-14: HELE KÆDEN ER LIVE OG VERIFICERET MED EN ÆGTE HÅND.**
Kamera → shim → MediaPipe → MQTT → timer. Kl. 17:06:58 gav tre frames
`open_palm` en 5-minutters timer. Det eneste der udestår er endelig montering af
kameraet; se "Status" nederst.

Grænsefladen mellem kamera og hus er to HA-**events**, ikke MQTT:

```
event: koekken_gestus_start    data: {minutter: 1..10}
event: koekken_gestus_kvitter  (ingen data)
```

Kameraet taler altså aldrig med lyset — det fyrer kun de to events. Det er
grunden til at `packages/koekken_gestus_timer.yaml` (1-10 minutter, rød
blink-alarm på lyskæden indtil nogen kvitterer, 15-min selv-stop) kunne bygges
og live-verificeres 09-12, længe før hardwaren fandtes. Samme indgang bruges af
ti tal-knapper på Lys-siden og ti telefon-widget-scripts
(`script.koekken_timer_<N>_min`), som derfor stadig virker uafhængigt af
kameraet.

**Læringen værd at tage med:** delt op sådan var kamera-forsinkelsen aldrig en
blokering for 90 % af arbejdet — og da hardwaren kom, var der intet at
integrere, kun at tilslutte.

Verificeret 2026-09-11 mod add-on'ets kildekode
(`benja-opazo/home-assistant-hand-recognition`, v0.3.27), ikke mod dokumentation.

---

## ⚠️ AirBnB: kameraet skal være fuldstændigt deaktiveret (user-spec 2026-09-11, juridisk krav)

**User-beslutning: under AirBnB deaktiveres kameraet fuldstændigt.** Designet
herunder behandler det som et lovkrav, ikke som en præference — det betyder at
det skal være **bevisbart**, **fail-safe** og skal holde også når HA er nede.

**Én ting skal siges rent:** deaktivering dækker det juridiske (samtykke/GDPR),
men **Airbnbs egen policy er strengere end lovkravet.** Siden 30/4 2024 er alle
indendørs kameraer forbudt i listings — uden undtagelse for fællesrum, for
oplysning i annoncen, eller for at enheden er slukket. Policyen rammer
*tilstedeværelsen*, ikke driften. Deaktivering fjerner altså den juridiske
eksponering, men ikke risikoen for at annoncen suspenderes hvis en gæst
anmelder enheden. Det er en forretningsrisiko, og den er users at tage.

### Lagene, svagest først

| Lag | Beskytter mod | Holder hvis HA er nede? |
|---|---|---|
| Automations-gate på `house_mode` | at gestus *reagerer* | nej |
| Shim stoppet | at RTSP-strømmen *åbnes* | ja (forbliver stoppet) |
| Add-on stoppet (`hassio.addon_stop`) | at billeder *behandles* | ja (forbliver stoppet) |
| Privacy-mode via Tapo-integration | at linsen *optager* | nej |
| Strøm afbrudt (plug eller hånd) | at enheden *kører* | ja |
| **Kameraet fysisk pakket væk** | **alt, inkl. tilstedeværelsen** | **ja** |

Kun det nederste lag er et ægte kill-switch — og det er det eneste lag ingen
maskine kan udføre.

**Plug-designet blev forkastet på sin egen præmis.** Planen indtil 09-12 var en
smart plug som "det autoritative lag", men policyen rammer *tilstedeværelsen*,
ikke driften (se ovenfor): en strømløs Tapo der ligger på bordpladen er stadig
et kamera i lokalet. Plug'en kunne altså ikke opfylde det krav den var tegnet
til at opfylde. Den er aldrig købt, og kameraet sidder i en almindelig
stikkontakt.

**I stedet er ankeret en menneske-kvittering:**
`packages/kamera_airbnb_vagt.yaml`. Ved skift til AirBnB varsles user om at
trække stikket **og pakke kameraet væk**, og først hans tryk på
`KAMERA_PAKKET_VAEK` skriver `input_text.kamera_airbnb_status`. Ingen sensor
kan bevise "pakket væk" — derfor er kvitteringen ikke en nødløsning, men det
eneste mulige bevis.

### Konkret

1. **Varsel ved entry**, gentaget indtil der kvitteres. Asymmetrien er bevidst:
   status nulstilles til `staar_fremme` ved skift **væk** fra AirBnB, aldrig
   den anden vej — et lovkrav skal fejle mod at varsle.
2. **Add-on-lagene stoppes** som dybde, ikke som erstatning. Både shimmen og
   `hand_recognition`; shimmen er den vigtigste af de to, da det er den der
   faktisk åbner RTSP-forbindelsen.
3. **`input_text`, ikke `input_boolean`** — husets eneste gratis helper-reload,
   så vagten kunne deployes uden restart. Fasen kodes som `<fase>:<epoch>`.
4. **Denne ene push sendes også i AirBnB** (user-spec 2026-09-11). Den er
   undtagelsen der bekræfter reglen nedenfor: varslet rammer user i det sekund
   *han selv* flipper mode, altså mens telefonen beviseligt er i hans hånd.

### Der varsles bevidst IKKE

Huset sender ingen push i AirBnB-mode (user-spec 2026-07-13, telefonen kan være
i gæstens hænder) — og her er undtagelsen ekstra rigtig: **en notifikation om at
kameraet stadig kører ville netop afsløre at der ér et kamera.**

Compliance-tjekket hører derfor i **`./scripts/ha_health.sh`**, ikke i en
notifikation — samme løsning som blindheds-målingen i sprint 09-09f, hvor et
varsel uden en modtager blev rullet tilbage til ren diagnostik.

**`./scripts/ha_health.sh kamera`** (kører også i `all`) — bygget 09-12
hardware-agnostisk, udvidet 09-14 da hardwaren kom. Under AirBnB tjekker den
fem lag: kvitteringen, evt. kamera-plug, **shimmen**, `hand_recognition`, og
`camera.*`-entities.

To ting værd at vide, før du retter i den:

- **Shimmen var oprindeligt usynlig for tjekket.** Den ledte kun efter
  `hand_recognition` — men det add-on henter bare JPEGs fra shimmen, så gestus
  kunne være stoppet, tjekket meldt compliant, og huset stadig trække video ud
  af køkkenet. Kigger du efter "behandler vi billeder?", så husk at spørge
  "hvem holder forbindelsen?" først.
- **Netværks-proben er bevidst ensrettet.** Svarer kameraets RTSP-port, er den
  strømførende — det falsificerer kvitteringen. Tavshed beviser derimod intet
  (forkert DHCP-lease, wifi nede), så proben kan kun *tilføje* en fejl, aldrig
  frikende. Adressen hentes fra shimmens egne add-on-options, så der ikke er to
  steder at rette den; kun host+port forlader parseren, da RTSP-URL'en bærer
  kamera-kontoens kodeord.

⚠️ En evt. plug findes via en **navne-heuristik** (`switch.*kamera*` /
`light.*kamera*`). Der er ingen i dag; pares en under et andet navn, er den
usynlig for tjekket.

---

## Hvad Geminis oplæg fik galt

Tre af antagelserne er bærende, og alle tre holder ikke:

**1. Add-on'et kan ikke læse RTSP. Overhovedet.**
Der er ingen RTSP-input. `frigate_client.py` henter udelukkende JPEG over HTTP:

```
{frigate_url}/api/{camera}/latest.jpg          # mode: latest_frame
{frigate_url}/api/events/{event_id}/snapshot.jpg  # mode: event
```

Kravet om "kun at fodre sub-streamen til MediaPipe" kan derfor ikke opfyldes som
beskrevet — MediaPipe ser aldrig en stream, kun enkeltbilleder. Lav opløsning
opnås i stedet via den kilde der *serverer* billedet.

**2. Der findes ingen JSON-config at indsætte.**
Add-on'ets HA-options-skema er i sin helhed:

```json
{ "web_ui_port": 8099, "debug_mode": false }
```

Alt det interessante — MQTT-credentials, billedkilde, backend, gestus-liste —
lever i `/data/config.yaml` inde i add-on'ets egen datamappe og skrives via dets
web-UI. **Det er ikke i git og overlever ikke en afinstallation.** Skal værdierne
snapshottes, skal det gøres separat.

**3. Hele mellemlaget mangler i huset.**
Hverken Mosquitto, MQTT-integrationen, Frigate eller et kamera findes. Målt
2026-09-11: `ha addons` viser 6 add-ons, ingen broker; `/api/states` har nul
`camera.*`-entities.

---

## Hardware-virkeligheden på NUC'en

| | Målt |
|---|---|
| CPU | Intel i5-5250U — Broadwell, **2 kerner / 4 tråde**, 1,6 GHz |
| RAM | 7,8 GB, ~6 GB available |
| iGPU | `/dev/dri/renderD128` findes (HD 6000, Gen8) |
| Coral TPU | ingen |

Den tunge del er **ikke** MediaPipe — det er Frigate. Frigates CPU-detector
frarådes eksplicit af projektet selv, og OpenVINO's GPU-plugin understøtter fra
Gen9 (Skylake) og opefter; Broadwell er Gen8 og falder derfor tilbage på CPU.
Det ville lægge en konstant objekt-detektion oven på de 2 kerner der allerede
kører Matter-server, OTBR, ZHA og recorder.

VAAPI-*afkodning* virker fint på Gen8 og hjælper på ffmpeg-delen, men det er
detektionen der koster.

---

## Anbefalet arkitektur: spring Frigate over

Frigates eneste rolle her er "opdag et menneske, tag så et snapshot". **Det rum
har allerede en bedre sensor end en CPU-sulten personde­tektor: køkkenets Apollo
MSR-2 radar** (`binary_sensor.koekken_apollo_radar_moving_target`).

Add-on'et understøtter det direkte. Fra `mqtt_listener.py`:

```python
def _extract_event_info(payload):
    """Extract (event_id, camera, score) from both frigate/events and flat payloads."""
```

Et **fladt payload** er altså en førsteklasses, understøttet vej — ikke et hack.
Både emnet (`mqtt_topic`) og filtrene (`topic_filters`) er frit konfigurerbare.

```
Apollo radar (moving_target)
        │
        ▼
Home Assistant  ──MQTT──▶  hand_recognition add-on
                                   │
                                   │ GET /api/koekken/latest.jpg
                                   ▼
                           frame-shim (ffmpeg/go2rtc → JPEG fra RTSP-substream)
                                   │
                                   ▼
                           MediaPipe (landmarks)
                                   │
                                   └──MQTT──▶ hand-recognition/koekken ──▶ automation
```

Fordelen: **nul CPU når køkkenet er tomt.** MediaPipe kører på ét JPEG ad gangen,
kun når radaren siger der er en krop i bevægelse.

Prisen: `frame-shim` er kode vi selv skal vedligeholde. Den mapper
`/api/<navn>/latest.jpg` til et enkeltbillede fra Tapo'ens **sub-stream**
(`rtsp://<bruger>:<pass>@<ip>:554/stream2` — stream1 er main, stream2 er lav
opløsning). Det er dér lav-ressource-kravet reelt indfries.

**Shimmen er skrevet og testet:** `addons/gesture_frame_shim/`. Den holder kun
ffmpeg i live mens der faktisk hentes frames, så et tomt køkken koster nul; inden
for en byge er streamen allerede varm, så frame 2-5 slipper for RTSP-connect og
keyframe-ventetid igen.

Verificeret 11/9 mod en fake-ffmpeg (intet kamera nødvendigt): 5 unikke frames i
en byge på 5 kald med 1 s mellemrum, ffmpeg ryddes ved idle og genstarter på
næste kald, ukendt kameranavn og path-traversal giver 404, og RTSP-adgangskoden
optræder aldrig i loggen.

To ting der blev fundet ved netop den test, og som begge ville have været usynlige
indtil kameraet sad på væggen:
- `proc.stdout.read(n)` **blokerer** til bufferen er fuld. Ved 4 fps og ~30 kB
  pr. frame ville shimmen have hængt i flere sekunder pr. kald. Skal være `read1`.
- Et cachet frame må kun genbruges i ca. to frame-intervaller. Med en løsere
  tolerance ville en byge servere det samme billede flere gange — og gestussen er
  netop forbigående.

Installation: kopiér mappen til `/addons/` (findes allerede og er tom), hvorefter
add-on'et dukker op under **Local add-ons**. RTSP-URL'en sættes i add-on'ets
options og er markeret som `password`, så den ikke vises i UI'et.

```bash
cp -r /homeassistant/addons/gesture_frame_shim /addons/
```

**Alternativet** er den kedelige, understøttede vej: installér Frigate, peg den
på sub-streamen, accepter CPU-detectoren — eller køb en Coral USB TPU (~500 kr.),
som gør Frigate triviel på denne maskine.

---

## Add-on-opsætning

Repo tilføjes under **Indstillinger → Add-ons → Add-on Store → ⋮ → Repositories**:
`https://github.com/benja-opazo/home-assistant-hand-recognition`

> Bygges lokalt ved installation. På denne NUC tager det et stykke tid.

HA-options (det eneste der sættes i selve add-on-panelet):

```json
{
  "web_ui_port": 8099,
  "debug_mode": false
}
```

Resten sættes i add-on'ets web-UI. Værdier for den Frigate-frie vej:

| Felt | Værdi | Hvorfor |
|---|---|---|
| `mqtt_host` | `core-mosquitto` | intern add-on-DNS |
| `mqtt_port` | `1883` | |
| `mqtt_username` / `_password` | `gestus` + genereret | **login i Mosquitto, ikke en HA-bruger** — se nedenfor |
| `frigate_url` | `http://local-gesture-frame-shim:8090` | trods navnet: bare en base-URL |
| `frigate_snapshot_mode` | `latest_frame` | rammer `/api/{camera}/latest.jpg` |
| `frigate_snapshot_height` | `0` | substreamen er allerede lav |
| `frigate_snapshot_crop` | `false` | virker kun i event-mode med Frigate |
| `mqtt_topic` | `house/gesture/scan` | vores eget emne |
| `topic_filters` | tomt | vi publicerer kun når vi mener det |
| `snapshot_mode` | `continuous` | se fælden nedenfor |
| `continuous_snapshot_count` | `7` | 2026-10-11 (før 5) — bygen skal være kortere end scan-løkkens 5 s |
| `continuous_snapshot_interval` | `0.5` | 2026-10-11 (før 1): målt ~0,62 s pr. billede → ~3,8 s pr. byge |
| `recognizer_backend` | `landmarks` | `three_fingers` findes kun her |
| `output_topic_template` | `hand-recognition/{camera}` | |
| `max_snapshots` | `10` | 2026-10-28 (før 100), B273: hvert billede gemmes som jpg, og med 10 slettes det efter ~7 s — før kernen skriver det til disken (30 s) → ~4 KiB pr. billede mod 134. **Aldrig 0:** crasher (`popleft` på tom deque) |

HA publicerer så et fladt payload til `house/gesture/scan`:

```json
{ "camera": "koekken", "id": "radar-trigger", "score": 1 }
```

**Fælde — et tredjeparts-add-on får INGEN MQTT-credentials fra supervisoren.**
Auto-discovery udsteder kun til supervisorens egne integrationer, så
`hand_recognition` fik `MQTT connection failed with code 5` (not authorised).
Løsningen er en dedikeret `gestus`-bruger i Mosquitto-add-on'ets `logins[]` —
ikke en HA-bruger, som README'en antyder. Brugernavn/kodeord ligger i
`secrets.yaml` (gitignored), fordi add-on-options ikke er i git og ikke
overlever en afinstallation. Bekræft blast-radius før du genstarter brokeren;
her var der **0 MQTT-entities** i registry'et, så genstarten var gratis.

**Fælde — gestussen er øjeblikkelig, triggeren er det ikke.** Add-on'et tager ét
billede pr. event i `normal`-mode. Rammer snapshottet ikke præcis det øjeblik
hånden holdes op, ser det ingenting. Derfor `continuous`: en byge på 5 billeder
over 5 sekunder giver et vindue at ramme indenfor. Nye events ignoreres mens en
byge kører, så det bliver ikke en løkke.

**Målt 2026-09-14** (varm stream): bygen tager **4,25 s** — første billede efter
53 ms, derefter **1,05 s** mellem hvert. Kold start er 2,6-13,3 s, fordi
shimmen lukker ffmpeg ned efter `idle_timeout`; rammer man den, timeouter det
første snapshot på 10 s og bliver til en 503. Det selv-heler inden for en
episode, da scan-løkkens 6 s-interval holder strømmen varm.

**Bemærk uenighed mellem README og kode:** README opgiver `sigmoid k = 4.0` og
`score threshold = 0.6`; `config_default.yaml` har **10.0** og **0.7**. Koden
vinder. Kalibrér selv mod ægte billeder via **Reclassify**-knappen i UI'et —
📏-reglen gælder også her.

---

## Automationen

**Læs dette først:** hele timer- og alarm-kæden findes allerede og kører
(`packages/koekken_gestus_timer.yaml`, live 2026-09-12). Automationen herunder
er derfor **kun en oversætter**: MQTT-payload → antal fingre → `koekken_gestus_start`.
Den må ALDRIG selv starte en timer, tænde lys eller sende en notifikation —
så ville husets timer-regel være kodet to steder og drive fra hinanden (#2).

**Deployet 2026-09-12 som `automations/gestus_koekken.yaml`** — læs koden dér.
Der stod tidligere en fuld kopi her; den er fjernet, fordi den nåede at blive
forældet inden for samme døgn (den viste stadig `mode: single` og den
dedupe-condition hold-to-confirm krævede fjernet). En kode-kopi i et dokument er
fejlklasse #2 med ekstra skridt.

Formen i korte træk: MQTT-trigger på `hand-recognition/koekken` → `variables:`
udleder `gestures` (begge hænder) og `fingre` (summen af `finger_count`, så
6-10 kan vises med to hænder) → `choose:` med to grene, `thumbs_up` →
`koekken_gestus_kvitter` og 1-10 fingre → `koekken_gestus_start` med
`minutter`. Hold-to-confirm-laget er beskrevet nedenfor.

**Hold-to-confirm er bygget (2026-09-12).** En hånd der føres op i billedet
passerer gennem 1, 2, 3 fingre, og add-on'et publicerer for HVER frame — så en
hånd på vej op ville starte en 1-minuts timer. Timeren startes derfor først når
det samme fingertal har stået i **3 frames i træk**.

Bufferen er `input_text.koekken_gestus_pending` med formatet
`<antal>:<epoch>:<frames>:<sidst_fyret_epoch>`:

- **Samme tal + frisk buffer** (< 10 s siden sidste frame) → `frames + 1`.
- **Andet tal, eller for gammel buffer** → `frames = 1`. Det er dét der dræber
  hånden på vej op: 1 → 2 → 3 er tre forskellige tal og når aldrig op på 3.
- **`frames >= 3`** → `koekken_gestus_start` fyres, og bufferen nulstilles til
  `0:0:0:<nu>` — fyrings-stemplet beholdes, så resten af bygen ikke starter en
  timer mere (cooldown 60 s).
- **Tommel op** har med vilje **intet** hold-krav. En misset kvittering
  efterlader lyskæden blinkende rødt indtil 15-min-cappen, så den vej skal fejle
  mod at reagere; et falsk positiv koster ingenting når der ikke er nogen alarm.

To detaljer der ikke er valgfri:

- Automationen er **`mode: queued`**, ikke `single`. Hvert frame er et
  læs-ret-skriv på den samme `input_text`. `single` ville droppe hele byger
  lydløst, så holdet aldrig blev opfyldt; `parallel` ville lade to frames læse
  den samme værdi og skrive det samme tal tilbage.
- Den gamle 60-sekunders `last_triggered`-dedupe i `conditions:` er **fjernet**.
  Den afviste frame nr. 2 og frem og gjorde dermed hold-to-confirm umulig — der
  fandtes aldrig to frames at sammenligne. Gentagelses-beskyttelsen ligger nu på
  selve affyringen og bruger et **skrevet** stempel, fordi `last_triggered`
  sættes efter conditions men før action-body'en og derfor ville læse sit eget
  stempel (09-09e).

Verificeret 12/9 over ægte MQTT: 1 → 2 → 3 fingre gav **ingen** timer; tre
frames med samme tal startede en 3-minutters timer; de næste tre frames i samme
byge startede **ikke** en timer mere.

**De 3 frames var et skøn — 09-14 er kadencen målt, og skønnet holdt.**
Add-on'et leverer et resultat hvert **1,05 s**, så 3 frames svarer til et
bevidst hold på ca. **3,2 s**. Det er langt nok til at et tilfældigt håndtegn
under madlavning ikke rammer tre gange i træk, og kort nok til at kunne holdes
uden at føles som en straf. Går kravet under ~3 s bliver det uopnåeligt i
praksis og ligner "kameraet kan ikke se mig" (B133 lukket).

### Valg der afviger fra oplægget — og hvorfor

**AirBnB-gaten ligger i PAKKEN, ikke i oversætteren.** Oplægget havde ingen gate
overhovedet; uden den kan enhver gæst der løfter fingre i køkkenet starte husets
lysalarm. Den står nu som `house_mode in ['Normal','Home Vacation']` på
`koekken_gestus_start_timer` — altså ét sted, hvor den også dækker
dashboard-knapperne og enhver fremtidig kilde (🏡 #1, fejlklasse #21).

**Dedupe tilføjet.** Add-on'et publicerer **for hvert behandlet snapshot**, også
når resultatet er `unknown`. I `continuous`-mode er det 5 beskeder pr. episode.
Uden dedupe ville den samme hånd sende 5 identiske events; pakken ville ganske
vist bare overskrive sin egen timer hver gang, men den (dengang blå, nu grønne) kvitterings-flash
ville blinke 5 gange og se ud som en fejl.

**Ingen lampe-styring i oversætteren.** Oplæggets "tænd en lampe i 3 minutter"
kolliderer med husets egen lysstyring: køkkenlyset har allerede med-ejere
(enforcer, lux-gates, `room_mode_koekken`), så et fremmed hold ville enten blive
overskrevet eller selv overskrive dem (#1). Pakken bruger Apolloens onboard-RGB
til kvitteringen (fortilfælde: `packages/apollo_rgb_varsel.yaml`) og rører kun
lyskæden når alarmen faktisk går — og dér er enforceren eksplicit gatet fra.
**Caveat:** ringen lyser ind i Apolloens egen LTR390, så kvitteringen
kontaminerer `koekken_apollo_lux` i sine 2 sekunder. Adfærds-logik læser
`sensor.koekken_lux_reel`/`koekken_dagslys_lx` og er upåvirket.

**Ingen `delay` i oversætteren.** En `delay` overlever ikke en HA-restart, og
oplæggets 3-minutters ophold ville efterlade ringen tændt for evigt ved uheldig
timing. Pakken bruger en rigtig `timer`-entity med `restore: true` i stedet.

## Status — hele kæden er live 2026-09-14

Intet af det krævede en core-restart.

1. ~~Smart plug først.~~ **Forkastet** — se "Plug-designet blev forkastet på sin
   egen præmis" ovenfor. Ankeret er menneske-kvitteringen i
   `packages/kamera_airbnb_vagt.yaml`.
2. ~~Mosquitto.~~ **GJORT 09-12, rettet 09-14:** `logins[]` er ikke længere tom —
   den har en dedikeret `gestus`-bruger, fordi tredjeparts-add-ons ikke får
   supervisorens auto-credentials.
3. ~~Tapo C210.~~ **GJORT 09-14.** Fast IP, kamera-konto oprettet i Tapo-appen
   (den konto RTSP bruger — ikke TP-Link-cloud-loginet). Begge streams svarer
   `RTSP/1.0 200 OK`.
4. ~~Shimmen.~~ **GJORT.** Verificeret med 5 unikke JPEGs, 1280×720, 2,2 s kold
   og <0,2 s varm.
5. ~~Hand Recognition.~~ **GJORT.** v0.3.27, forbundet til MQTT, abonnerer på
   `house/gesture/scan`.
6. ~~Publisheren.~~ **GJORT 09-14** — `gestus_koekken_scan_puls`. Den manglede
   helt: hele kæden var bygget, men *ingen* publicerede til
   `house/gesture/scan`, så den var færdig og strukturelt ude af stand til at
   fyre én eneste gang.

7. ~~Fingertallet.~~ **GJORT 09-14.** Oversætteren læste et `finger_count`-felt
   der ikke findes i payloaden; tallet udledes nu af gestus-navnet.
8. ~~Live-verifikation med en ægte hånd.~~ **GJORT 09-14 kl. 17:06:58.** Tre
   frames `open_palm` (score 0,97-0,99, 1 s mellem hver) → `timer.koekken_gestus`
   `active`, `0:05:00`. Flad hånd = 5 fingre = 5 minutter, hele vejen fra linse
   til timer.
9. ~~Kvitterings-vejen og fingertal nr. 2.~~ **GJORT 09-14.** User kørte selv
   videre end der var bedt om, og dækkede dermed tre veje mere: `peace` → 2 min
   (17:10:48), `thumbs_up` → `koekken_gestus_kvitter` som annullerede timeren og
   afleverede lyskæden tilbage (17:10:26 og 17:12:32), og lyskæden holdt tændt +
   pulsede under nedtællingen og stod korrekt `off` efter afleveringen.
   **60-sekunders-cooldownen blev målt i den positive retning samtidig:** to
   fyringer 17:10:48 → 17:11:49 = 61 s, altså først tilladt lige efter vinduet.
   Selve alarmen ved udløb er derfor stadig kun verificeret fra 09-12 — han
   kvitterede hver gang inden timeren nåede at løbe ud.

10. ~~Fysisk montering.~~ **GJORT 09-15.** Kameraet sidder over komfuret. Se
    "Den kontrollerede kalibrering" nedenfor for hvad vinklen koster og hvorfor
    den ikke må ændres.

**Kalibrering af `landmark_score_threshold` (live 0.7) er UAFKLARET og kræver en
kontrolleret test.** Her stod en overgang at den var *aflyst*, fordi de 90
sekunder før første fyring viste fingertallet skifte mellem frames 1 sekund fra
hinanden ved score 0,90-0,99 — hvad der lignede en klassifikator der flipper
mellem nabo-tal ved fuld selvsikkerhed. User oplyste derefter at han skiftede
gestus **med vilje**, lige efter hinanden.

**Det er værd at huske som metode-fejl, ikke kun som en rettelse:** i en
ukontrolleret demo er menneskets bevidste variation og sensorens støj den samme
kurve, og de kan ikke skilles ad bagefter — informationen om hvad hånden faktisk
gjorde findes kun hos mennesket. En stabilitets-måling kræver derfor **én
gestus, holdt ubevægelig, i en kendt periode**, med hvad der blev holdt noteret
på forhånd. Indtil den test er kørt (efter monteringen over komfuret) ved vi
ikke om score kan skelne et hold fra et skift.

Det der står tilbage som målt: `hold_frames: 3` tillod et ægte hold at fyre, og
nulstillede når fingertallet skiftede. Det sidste er nu bekræftet som tilsigtet
adfærd ved kendt input — ikke som støjfiltrering.

---

## Den kontrollerede kalibrering — kørt 2026-09-15

Kameraet er nu monteret over komfuret, og **vinklen er bevidst høj: den holder
børnene ude af billedet** (user-spec 15/9). Den må derfor ikke vippes ned for at
forbedre genkendelsen — det er en fast randbetingelse, ikke et kompromis der
kan forhandles.

Metoden var dét forrige afsnit efterlyste: **én gestus ad gangen, holdt
ubevægeligt i 25 sekunder, med facit noteret på forhånd.** Klassifikatoren blev
holdt varm ved selv at publicere `house/gesture/scan` hver 4,5 s, så vi målte
hånden og ikke radarens kadence. Billeder blev gemt side om side med svarene, så
facit kom fra at SE hånden — ikke fra at antage at brugeren gjorde som aftalt.

### Hovedresultat: det er den mindste hånd der tabes

| Vist | Sammensætning | Resultat |
|---|---|---|
| 2 | peace alene | **12 svar i træk**, 0,88-0,98 ✓ |
| 4 | four_fingers alene | solid ✓ |
| 5 | open_palm alene | solid ✓ |
| **7** | **4 + 3** | **9 i træk**, 0,89-0,99 ✓ |
| 8 | 5 + 3 | 8 i træk ✓ |
| 9 | 5 + 4 | 6 i træk ✓ |
| 10 | 5 + 5 | 6 i træk ✓ |
| 7 | 5 + 2 | ✗ peace-hånden set 3 af 20 gange |
| 6 | 5 + tommel | ✗ set 1 af 18; læst som **10** fem gange |
| 3 | three_fingers alene | ✗ læst som `four_fingers` i **to uafhængige forsøg** |
| 1 | pointing alene | ✗ 1 af 23 (hånden var sunket ud af billedet) |

**Reglen der falder ud af det: sammensæt 6-10 af to STORE, åbne hænder.** Når to
hænder er oppe, ses den store hver gang og den lille kun sjældent. Derfor virker
5+3, 5+4, 5+5 og 4+3, mens 5+2 og 5+tommel ikke gør.

Tommelen skal helt ud af vokabularet: den blev læst som `open_palm` med score
**0,99**, så et 6-forsøg startede en 10-minutters timer.

### Tre ting der IKKE virkede som man skulle tro

1. **Score kan ikke skelne rigtigt fra forkert.** En korrekt `four_fingers`
   scorede 0,90 mens to beviseligt forkerte aflæsninger scorede 0,89 og 0,91. En
   forkert `four_fingers` nåede 0,96. `landmark_score_threshold` kan altså ikke
   kalibreres til at redde os — spørgsmålet fra forrige afsnit er hermed besvaret
   med et nej.
2. **Et forkert tal kan holdes stabilt.** `3` blev læst som `four_fingers` ni
   frames i træk. Hold-kravet beskytter mod flimmer, ikke mod en model der er
   konsekvent forkert — så `3` som enkelt hånd er ikke brugbar i denne vinkel.
3. **Højde i billedet er nødvendig, men ikke tilstrækkelig.** En hånd der synker
   ned mod underkanten bliver ikke genkendt (det dræbte `1`), men at løfte `3`
   helt over hovedet ændrede ikke dens fejlaflæsning.

### Præfiks-fejlen — den dyreste, og den eneste der er kodefikset

Under et 7-forsøg (5+2) svarede klassifikatoren `open_palm + unknown` = **5** i
13 af 20 svar, heraf **5 frames i træk inden peace-hånden var set én eneste
gang**. Med `hold_frames: 3` er det rigeligt til at fyre: huset ville have
startet en 5-minutters timer mens brugeren stadig var i gang med at vise 7.

`4` og `5` er præfikser for alle to-hånds-tallene, og de er de eneste koder en
to-hånds-gestus kan degradere TIL, fordi det altid er den lille hånd der tabes.
Derfor fik de først deres eget hold på 6 frames, mens 1, 2 og 3 beholdt 3.

### Den utilsigtede fyring — hvorfor 3 frames var målbart for lavt

15/9 kl. 12:55:31 og 13:00:50 startede huset to timere som ingen havde bedt om
(begge 2 min). Parent B bevægede sig bare i køkkenet. Begge var **kode 2**
(peace), og begge ramte **præcis 3 frames** — nøjagtig kravet.

Fordelingen af stribe-længder (samme kode i træk) over **93 striber** den dag:

| Population | Længste stribe |
|---|---|
| Kontrolleret kalibrering 07:11-07:42 (bevidste hold) | ≥ 4 |
| Alt efter 08:00 — tilfældige køkken-hænder | **3** |

Koderne `4`/`5` er det rene kontrol-eksperiment: deres krav var allerede 6 fra
07:46, så deres striber blev aldrig afkortet af en fyring — og de oversteg
alligevel aldrig 3 frames tilfældigt. 6 ligger altså over **hele** den
utilsigtede population, ikke bare over de to der nåede at fyre.

**16/9 blev 6 derfor kravet for alle fingertal.** `hold_praefiks` findes ikke
længere — `hold_frames: 6` dækker begge grunde, og kun knytnæven har stadig sit
eget, kortere hold (2 frames: den skal kunne stoppe en 15-sekunders alarm).

### 2026-09-25: `3` er IKKE et vinkel-problem — det er add-on'ets tabel

User viste 3 fingre to gange 24/9: 18:18:23 blev læst som `3`, 18:22:07 som
`four_fingers` i 3 frames i træk (bufferen `input_text.koekken_gestus_pending`
viser 4-4-4-4 uden et eneste 3-frame imellem). Add-on-loggen roterer efter få
timer, så scorerne var væk — men koden i `hand_recognizer.py` (v0.3.27,
github.com/benja-opazo/home-assistant-hand-recognition) forklarer det
deterministisk. Gestus-tabellen er `[tommel, pege, lang, ring, lille]`:

| Mønster | Navn |
|---|---|
| `T T T F F` | `three_fingers` = **tommel + pege + lang** |
| `F T T T T` | `four_fingers` |
| `F T T T F` (pege + lang + ring) | **findes ikke** |

`_match_gesture` vælger det mønster flest fingre er enige med. Pege+lang+ring
er uenig med `four_fingers` i ÉN finger (lillefingeren) og med `three_fingers`
i TO (tommel + ring) → den læses altid som `four_fingers`, med en score der
typisk ligger over tærsklen 0,7. README'en påstår "index, middle, ring" — koden
siger tommel. Kalibreringens "3 læst som four_fingers i to uafhængige forsøg"
(15/9) var altså sandsynligvis samme fejl, ikke kameravinklen.

Konsekvens: **`3` virker kun som tommel + pege + lang** (den danske tælle-
måde), og kun når tommelen ses — hvilket vinklen gør ustabilt (tommel-læsninger
ovenfor). En rigtig rettelse kræver en lokal fork af add-on'et med et ekstra
mønster `F T T T F → three_fingers` (og evt. finger-scorerne i payloaden, så HA
kan afgøre det selv) — prisen er at en `4` hvis lillefinger scores krøllet så
bliver `3`.

### 2026-10-05: afstand kræver en MÅLT hånd-størrelse — `PalmGate` i shimmen

User: *"tapo registrerer igen finger gestures på alt for lang afstand. dem i dag
var utilsigtet på 1.5m afstand. det troede jeg vi havde fixet?"*

**Hvad der skete.** Fixet 24/9 (`gestus_haand_skala_pct` 65 %) blev rullet
tilbage 28/9 (→ 100 %, så en knytnæve på 50 cm kunne ses), og holdet blev sat
3 → 2 frames 4/10. Begge værn var altså væk. Add-on-loggen (hentet før den
roterede) viser tre affyringer fra én venstre hånd:

| Tid | Frames | facing / rotation | score | Udfald |
|---|---|---|---|---|
| 15:02:03-04 | 2 × `four_fingers` | away / −46…−38° | 0,86-0,89 | 4-min-timer startet |
| 15:03:30-32 | 2 (+1 `unknown` 0,699) | away / −49…−58° | 0,76-0,80 | genstartet |
| 15:04:17-18 | 2 | away / −36° | 0,77-0,82 | blokeret af 60-s-pausen |
| ec:09:9b-6a:c0:11 | **6 i træk** | camera→away / −5…−16° | **0,90-0,94** | genstartet 15:05:56 |
| 15:06:07-10 | 3 × `fist` | camera | 0,94-0,96 | annulleret (bevidst) |

Træneren spurgte 15:06:08, user svarede `utilsigtet`.

**Hvorfor ingen af de gamle knapper kan det.** Seks frames i træk med score
0,9 og håndfladen mod linsen er umulige at skille fra en bevidst fagt på hold
eller score. Og skalaen virker kun hvis detektionen afgøres af størrelsen —
men palme-detektoren finder en ÅBEN hånd let selv langt væk, mens en
KNYTNÆVE (ingen strakte fingre, knoerne mod linsen) er dens svære tilfælde:
28/9-sweepet så knytnæven på 50 cm i 3/14 frames ved 100 % og 0/14 ved 70 %.
En global skala skærer altså knytnæven væk før den fjerne åbne hånd.

**Fixet (shim 0.16.0).** Shimmen kører add-on'ets EGEN palme-detektor
(`palm_detection_full.tflite`, byte-identisk med den i mediapipe 0.10.14-
wheelen, via `cv2.dnn.readNetFromTFLite` — NCHW-input, ellers en
konvolutions-assertion i OpenCV 4.10) på hvert billede `/api/koekken/latest.jpg`
serverer. Hver palme hvis boks er smallere end
`input_number.gestus_min_haand_px` får MediaPipes egen hånd-ROI (2,6 × boksen,
skubbet en halv boks mod fingrene) malet sort, så add-on'ets landmark-trin intet
har at se på. Nære hænder der overlapper en fjern ROI beholder deres pixels.
Gaten **fejler åben** (ingen model / fejl / 0 = uændret billede).

**Shim 0.16.1 — sløring i stedet for sort (B235).** 15/10 20:42 læste
add-on'et knivmagneten som `four_fingers` (rotation −115°) i 6 min, selvom
gaten maskerede den ~60 px palme der i HVERT frame: en sort rombe med
knivblade stikkende ud er selv en hånd-silhuet. Nu erstattes ROI'en af en
kraftig sløring af sig selv (box-blur 45 px ×2 ≈ 90 px trekant-kerne) med
en blød kant (Gauss 31 px), så masken ingen kanter har at finde fingre i.
Nære hænder (`keep`) og alt uden for ROI'en er bit-identiske; ~18 ms
median pr. frame (kun beskæringen sløres). Offline: 0 detektioner på 600
slørede køkken-frames med add-on'ets egen `HandRecognizer`. **Ikke bevist:**
falsk-palmen opstod kun under den lyserøde `light.koekken_lyskaede` og
kunne ikke genskabes offline — om hånden var maskens form eller knivpixels
uden for ROI'en er åbent. Rotations-gaten i `automations/gestus_koekken.yaml`
(`input_number.gestus_max_rotation_grader`) er det egentlige værn.

**Shim 0.16.2 — kun de nære hænder overlever (B235).** 16/10 06:26 startede
en OPREJST hånd ~2 m væk (palme 51 px, rotation −8…+1°, score 0,90-0,99) en
4-min-timer, selvom shimmen maskerede den i alle 7 frames i burstet:
add-on'et fandt `four_fingers` i det slørede område. Siden 0.16.1 kom
**alle 6** add-on-detektioner fra frames med KUN maskerede palmer, 0 fra
nære. Rotations-gaten kunne ikke se det (hånden var oprejst). Nu vendes
masken om: så snart én palme < `min_px` er i billedet, ser add-on'et KUN de
nære hænders ROI (blød kant, Gauss 31 px) og fladt grå (128) resten; kun
fjerne palmer → helt gråt frame. Frames uden fjern palme (også uden palme
overhovedet) er urørte, så fejl-åben-garantien for den nære knytnæve står.
Pris: en nær hånd shimmen IKKE fandt, i et frame hvor den fandt en fjern,
forsvinder (annullér findes også i app/stemme).

**Fælde undervejs — opencv_zoo's palme-ONNX er LITE-modellen.** Add-on'et
kører FULL (`model_complexity: 1`). Reviewet viste at ONNX'en matcher
`palm_detection_lite.tflite` til 2e-4, og at den på køkken-billedet missede
30 af 61 palmer under 50 px som full fandt — præcis de fjerne. "Samme
model-familie" er ikke samme model; tjek sha256 mod det add-on'et faktisk
kører.

**Offline-bevis** (Docker: add-on'ets præcise kode + mediapipe 0.10.14 som
orakel; gaten i shimmens rigtige Alpine-billede; 507 kompositter af
MediaPipes test-hænder i 8 størrelser × 3 positioner i det ægte
køkken-billede, 209 hænder orakelet så):

| | Resultat |
|---|---|
| Gaten fandt samme hånd som orakelet | 207/209 (lite: 199/209) |
| Palme-boks / håndled→langfinger-knoe | åben 1,07 · knytnæve 1,12 (median) |
| Palme-boks / hånd-højde | åben 0,58 · knytnæve 0,83 |
| Små hænder (< tærskel) set af orakelet EFTER maskering | 0 ved 60 / 100 / 120 / 150 |
| Store hænder tabt eller ny fagt efter maskering | 0 ved alle fire |
| To hænder (nær + fjern) i samme billede | 49/50 rigtige; undtagelsen er en fjern hånd INDE i den nære hånds ROI (den nære vinder bevidst) |
| Tid pr. billede (i5-1135G7, Docker) | 36 ms uden hånd, 41 ms med (p95 63) |

**Kalibrering.** Startværdien 120 px er geometri, ikke måling af ægte fagter:
24/9 målte en bevidst nær hånd ~400 px høj (→ boks ~230) og et krukke-greb
~100 px (→ ~58); billedet selv giver f ≈ 1000 px (køleskab 60 cm = 290 px,
krukker ~10 cm = 55 px), dvs. en hånd på 1,5 m ≈ 70 px, en knytnæve på 50 cm
≈ 210 px, og 120 px ≈ 85 cm. Valget holder for f mellem 800 og 1200. Hver palme
logges med boks-px, håndled→langfinger-knoe, score, position og om den blev
maskeret til `/share/gesture_frame_shim/palms.jsonl` (roteres ved 4 MB) og
live på `http://local-gesture-frame-shim:8090/haand`. Stil tærsklen efter
fordelingen af HVERDAGENS hænder (krukke-greb, madlavning — alle utilsigtede)
mod de bevidste fagter user bekræfter i træneren, ikke efter en poseret
sweep. B194.

### Åbent

`1`, `3` og `6` er stadig ikke pålidelige. Den oplagte næste vej er at lade
shimmen beskære sit JPEG til det område hænderne faktisk er i, så hånden fylder
mere af de pixels MediaPipe ser — shimmen ejer kropsdetektionen selv, så
`/api/<kamera>/latest.jpg` bruges KUN af hand_recognition og kan beskæres uden at
røre #9/#10. Beskæring fjerner desuden billedindhold i stedet for at tilføje
det, så den rører ikke ved børne-randbetingelsen.

---

## Fremtid: pan/tilt og mikrofon

C210 har motoriseret pan/tilt og mikrofon. Begge dele styres via HACS-integrationen
[`JurajNyiri/HomeAssistant-Tapo-Control`](https://github.com/JurajNyiri/HomeAssistant-Tapo-Control),
som giver preset-positioner, privacy-mode og bevægelsesdetektion som entities —
uafhængigt af gestus-stakken. Mikrofonen er lyd-optagelse indendørs og falder
under præcis samme AirBnB-forbud som linsen.
