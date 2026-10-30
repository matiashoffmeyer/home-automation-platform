# Hardware Mangelliste (shopping list)

> *Written in Danish. English overview: [README](../README.md) ·
> [ARCHITECTURE](../ARCHITECTURE.md).*

Liste over devices der refereres af automations men endnu ikke er paret. Vedligeholdes af Claude — opdateres når devices bestilles, modtages, eller pares.

Sidst opdateret: **2026-05-05** (Massive day. 5 RODRET dimmers + 5 Apollo MSR-2 paret. PLUS Sonoff ZBDongle-E flashed til OpenThread RCP + 4 Matter devices commissioned via Thread (3× Myggbett + 1× Myggspray). Humidity feature droppet. Se [matter_pairing_playbook.md](matter_pairing_playbook.md) for fremtidige Matter parringer).

Konvention: ✅ paret · 🛒 bestilt · ⏳ skal købes · 💡 nice-to-have

---

## Allerede bestilt 🛒

| # | Item | Antal | Formål | Forventet ankomst |
|---|------|-------|--------|-------------------|
| 1 | USB-C strømstik til Apollo MSR-2 | 5 stk | En per Apollo | har |
| 2 | **Sonoff ZBDongle-E** (EFR32MG21 Silicon Labs chip, [Proshop SKU 3213488](https://www.proshop.dk/Smart-Home/Sonoff-Gateway-ZigBee-30-USB-Dongle-Plus/3213488) — Proshop kaldte den fejlagtigt "Dongle Plus" men Sonoff's egen produktbeskrivelse i dette SKU bekræfter ZBDongle-E) | 1 stk | Flashes til **OpenThread RCP firmware** som dedikeret Thread Border Router for Matter devices (Myggbett + Myggspray). Procedure: HA Silicon Labs Flasher addon → vælg `zbdonglee_openthread_rcp_*.gbl` → install OpenThread Border Router addon med hardware flow control OFF | næste uge |
| 3 | Pro USB-A til USB-A 0.6m kabel (sort) | 1 stk | Til Sonoff dongle (extension fra USB-port til mesh-friendly placering) | næste uge |

---

## Forberedt i koden, afventer parring 🛒 (2026-09-23)

| Item | Forventet entity | Kode klar i | Ved parring |
|---|---|---|---|
| 2× IKEA KAJPLATS GU10 CWS (farve), sofastuen | `light.stue_spot_1` (node 473), `light.stue_spot_2` (node 474) | `packages/stue_spots.yaml` (spejler læselampen; party/dance = individuelle farver), grupper i `light_groups.yaml` | ✅ **parret 2026-09-23**, VEJ B første forsøg |
| 2× IKEA GRILLPLATS Thread-plug — én (node 499) er **altid-tændt Thread-router i køkkenet** fra 15/10 (drev før pærelyskæden i soveværelset, som nu sidder på den gamle Innr SP 240), én (ex-højttaler, node 498) driver **sofa-hyggelampen i stuen** og er Thread-router dér siden 15/10 (depotet 14-15/10, B234) | `switch.thread_router_koekken` (før `switch.sove_lyskaede`), `switch.stue_plug` (før `switch.thread_router_depot`) | `packages/thread_router_koekken.yaml` (tænder igen efter 10 s slukket) · `packages/sove_lyskaede.yaml` | ✅ Begge parret 2026-09-23 via telefonen (B159). Plug 1 = node 0x1F3 → "Sove lyskæde" (`switch.sove_lyskaede`, 2,5 W) → 15/10 "Thread router køkken". Plug 2 = node 0x1F2 → "Højttaler plug" (`switch.hoejttaler_plug`, 2026-10-10) sad på AxiomAir N3'en 10/10 til strømmåling (B212); siden 14/10 Thread-router i depotet, omdøbt 15/10 til "Thread router depot" (`switch.thread_router_depot`) — skal altid være tændt. |
| 🛒 **AxiomAir N3** Wi-Fi-højttaler (brugt, med batteri-modul; 2×75 W, Pi + Volumio 2-OEM) — bestilt 2026-10-05, til **sofastuen** | `media_player.hoejttaler` (omdøb fra Volumio-integrationens navn) | `packages/hoejttaler.yaml` (stop musik ved tomt hus N min + voksen-godnat; ingen tænd/sluk — N3 har ingen standby og kan kun startes med knappen) + `hoejttaler_radio.yaml` (B193) + `hoejttaler_annoncering.yaml` (køkken-timer og vejrvarsel som tale, B199) | Se tjeklisten nedenfor. Intet målestik (user 2026-10-05). |

Matter-parring: [matter_pairing_playbook.md](matter_pairing_playbook.md) FØRST (`bluetooth_adapter_id: 0`).

**AxiomAir N3 — tjekliste ved ankomst (Claude gør resten, user kun det fysiske):**
**Status 2026-10-08:** på Wi-Fi som 192.0.2.42 (MAC ef:4f:c6:f8:20:99, Pi), fw V2.13.2 er nyeste. Punkt 1, 3 og 6 (ping-sensoren) er gjort; `media_player.hoejttaler` kører via override'en `custom_components/volumio` (core crasher på den gamle firmware). Radio-scriptet er testet med API-kald. Punkt 4 testet 08/10 med Volumio-shutdown: Pi'en går helt af nettet (kan kun tændes på knappen), entity'en fryser på `playing`, `hoejttaler_online` → off efter 13 s, radio-tilstanden fulgte med. Mangler: ægte Styrbar-tryk (6) og beskederne (7). DHCP-reservation er sprunget over (user: strømmen går ikke).
1. User: sæt den i stikkontakten, gerne med netkabel (Wi-Fi er KUN 2,4 GHz via
   USB-dongle). Første opsætning i Axiom-appen / `http://axiomair.local/`: navn,
   Wi-Fi, tjek opdatering (gear → System; seneste kendte fw v2.13.2).
2. Claude: DHCP-reservation på routeren hvis muligt (Sagemcom nulstiller ved
   strømsvigt — notér IP'en i `reference_nuc_remote_access`-stil).
3. Claude: Volumio-integrationen (zeroconf `_Volumio._tcp`, ellers host + port
   3000) → omdøb entity_id til `media_player.hoejttaler` (registry), så
   `packages/hoejttaler.yaml` virker uden kodeændring. Tjek `supported_features`
   (stop/pause/volume) før dashboard-kort (#dashboards: tile-feature uden bit
   fejler tavst).
4. Claude: test stop-vejen live (afspil → `media_stop`) og at entity'en FRYSER
   på sidste state når højttaleren slukkes med knappen (ingen `unavailable`) —
   pakkens friskheds-krav (last_updated < 2 min) hviler på det.
5. Afspiller-kortene står klar (Lys-siden → Stue + status-siden), skjult til
   entity'en findes — tilføj tile-features når `supported_features` er tjekket.
6. **Radio (B193, bygget 2026-10-05):** opret ping-integrationen på højttalerens
   IP som `binary_sensor.hoejttaler_online` — UDEN den er radio-tilstanden aldrig
   on (Styrbar stue bliver ved at styre lys) og morgenradioen starter ikke. Test:
   `script.hoejttaler_radio` kanal "DR P4 København" (lyd? `media_title`?), så
   Styrbar stue med ÆGTE tryk: pile skifter kanal, OP/NED volumen, langt NED
   stopper — og lyset må IKKE reagere imens (logbogen viser quirk-formen).
   Volumio's volumen-trin (Playback options → volume steps) styrer hvor meget
   ét tryk skruer.
7. **Beskeder (B199, bygget 2026-10-07):** `packages/hoejttaler_annoncering.yaml`
   kræver samme `binary_sensor.hoejttaler_online`. Test: start radioen, kør
   `script.hoejttaler_annoncer` med besked "Køkkentimeren er færdig" → radioen
   pauser, beskeden siges ÉN gang (klippes slutningen af? → hæv de +2 s i
   delay'et), radioen kommer igen på samme kanal og volumen. Så uden musik
   (volumen sat tilbage? køen ryddet?), og med Spotify Connect (skal springes
   over, undtagen `vigtig: true`). Til sidst en ÆGTE køkken-timer på 1 min
   (start- og slut-besked) og `input_number.hoejttaler_annoncering_volumen` mod
   rummet. Logbogen (navn "Højttaler") siger hvad der skete og hvorfor.

---

## Skal købes ⏳

### Backup-maskine til NUC'en — kold standby (B252, user 2026-10-25)
User 25/10: "klar men slukket". Krav og bindinger: `docs/nuc_beredskab.md`.

**Forslag: Beelink Mini S12 Pro** — Intel N100 (x86-64, 4 kerner), 16 GB RAM,
500 GB SSD, **4× USB-A 3.2**, 1× gigabit-LAN, auto power-on i BIOS. Ca.
1.500-2.000 kr (tjek dagens pris). Den er hurtigere end NUC'en (i5-5250U,
2015) og bruger mindre strøm. Den kommer med Windows, men HAOS' generiske
x86-64-image skrives ind over det.
- **Forlængerne flytter med donglerne:** USB 3-porte støjer på 2,4 GHz.
  Sonoff-donglen sidder i dag i en 0,6 m USB 2.0-forlænger (`docs/hardware.md`);
  hvordan ZBT-2 sidder, er ikke dokumenteret → tjekkes ved B253-øvelsen.
- Sæt BIOS til at tænde efter strømsvigt, før den lægges på hylden.
- Alternativ: en brugt Intel NUC (8.-11. gen), samme krav.

### ~~USB-hub med per-port power switching til Thread-donglen~~ ❌ AFVIST (user 2026-10-09: "nej jeg skal ikke købe noget")

Står kun her så ingen foreslår den igen. Stigen i
`packages/thread_otbr_watchdog.yaml` klarer sig uden (TX-boost, chip-reset,
logisk genplug, zombie-kick). Oprindelig begrundelse:

Eneste måde software kan give Sonoff-donglen et ægte power-on-reset: NUC'ens
root-hub kan ikke slukke VBUS (`wHubCharacteristics=0x000a`), så det digitale
genplug er kun logisk — og 08-09/10 var det kun et fysisk genplug der samlede
Thread-nettet. Krav: hub der melder **per-port** power switching (uhubctl-
kompatibel liste, fx visse Raspberry Pi-/Plugable-/D-Link DUB-H7-revisioner),
USB 2.0 er nok. Sæt donglen i den (gerne på forlængerkabel væk fra NUC'ens
USB3-porte); `scripts/otbr_usb_replug.py --dry-run` skal derefter sige
"ÆGTE strøm-afbrydelse" — så klarer stigen resten selv.

### USB Bluetooth-dongle til NUC ✅ (installeret + i drift 2026-06-17)

NUC'ens indbyggede Intel-BT korrumperer HCI-frames (kernel: "Unexpected start
frame") og var rod-årsag #2 til KAJPLATS-parring-maratonen (B32) + ~60 fejlede
TIMMERFLOTTE-forsøg. HA's dev-team tester selv med ekstern CSR-dongle og fraråder
indbyggede adaptere.

**Installeret: CSR8510 A10 USB-dongle** (= HA-dev-teamets anbefaling). Sidder som
`hci1` (USB-vendor 0a12:0001); Intel-built-in er `hci0` (8087:0a2a). Matter-server
addon konfigureret med `bluetooth_adapter_id: 1` → Matter ejer CSR-donglen,
HA Bluetooth-integration bliver på Intel. **Resultat: TIMMERFLOTTE parret på
første BLE-skud 2026-06-17** (node 434) efter ugevis af fejl. VEJ B i
[thread_pairing_drejebog.md](thread_pairing_drejebog.md) er nu den primære,
telefon-fri parringsmetode.

| Ting | Status |
|---|---|
| USB BT-dongle (CSR8510 A10) | ✅ i NUC — **hci0**, `bluetooth_adapter_id: 0` (målt 2026-09-01: Intel-chippen er væk fra `/sys/class/bluetooth`, så CSR'en er nu eneste adapter og har fået indeks 0. Nummereringen følger USB-enumereringen og kan skifte ved reboot — verificér med vendor-id, 0a12=CSR / 8087=Intel, ikke med indekset) |
| USB-forlængerkabel (kort) | valgfrit — overvej hvis radiostøj fra Sonoff/ZBT-2 |

### IKEA Matter sensorer ✅ (paret 2026-05-05)

IKEA Matter-strategi (Myggbett door + Myggspray motion) — 4 devices commissioned via Thread Border Router.

#### Myggbett door/window sensor (Matter) — 4/4 paret, alle placeret

| Placering | Entity | node_id | Status |
|-----------|--------|---------|--------|
| Hoveddør | `binary_sensor.parasoll_hoveddoer` | 22 | ✅ paret 2026-05-05 |
| Terrassedør | `binary_sensor.parasoll_terrassedoer` | 37/38 | ✅ paret 2026-05-05 (ex-`parasoll_standby`) |
| Badeværelse-dør | `binary_sensor.parasoll_badevaerelse` | 37/38 | ✅ paret 2026-05-05 (ex-`parasoll_standby_2`) |
| **Soveværelse-dør** | `binary_sensor.parasoll_sovedoer` | **462** | ✅ paret 2026-08-30, **VEJ B på første forsøg** (NUC-BLE, `network_only=False`) |

> Sovedøren driver morgen-logikken i `packages/sove_alarm_morgen.yaml`: åben dør
> ≥ 5 min = "to personer oppe", lukket dør 04-12 = mørk-hold (intet auto-lys,
> gardin-motoren udskydes).

#### Myggspray motion sensor (Matter) — 1/1 paret + entré rolle

| Placering | Entity | node_id | Status |
|-----------|--------|---------|--------|
| Entré (replaces Vallhorn-entré rolle) | `binary_sensor.entre_valhorn_occupancy` (+ `_illuminance` lux + `_battery`) | 27 | ✅ paret 2026-05-05 |
| Badeværelse INDE (in-room hold-lys) | `binary_sensor.badevaerelse_inde_occupancy` (+ `_illuminance` + `_battery`) | 263 | ✅ paret 2026-06-11 (VEJ B, 2. forsøg) |
| Badeværelse (dør/yder-zone) | `binary_sensor.badevaerelse_valhorn_occupancy` (+ `_illuminance` + `_battery`) | — | ✅ paret 2026-06 |

> NB: Myggspray valgt til entré frem for terrasse fordi den er indoor-rated. Terrasse-sensor venter på outdoor-rated alternative (eller backup Vallhorn med overdækket placering).

### IKEA TIMMERFLOTTE temp/fugt (Matter-over-Thread) — 2/2 paret

| Placering | Entity-præfiks | node_id | Status |
|---|---|---|---|
| Køkken (nordvæg) | `sensor.timmerflotte_*` | 434 | ✅ paret 2026-06-17 (~60 fejlforsøg; løst af CSR-donglen). Lejlighedens autoritative temp+fugt-kilde (`indoor_temperature_resilient`, dug-modellen, sommer-/vinterforsvar) |
| **Badeværelse** | `sensor.badevaerelse_timmerflotte_*` | **463** | ✅ paret 2026-09-01, **VEJ B på FØRSTE forsøg** (NUC-BLE, `network_only=False`). Bærer brusebad-detektionen — se `packages/badevaerelse_brusebad.yaml` |

**Målt rapporterings-kadence** (køkken-enheden, 48 t): min-gap **19 s**, snit
309 s, max 1172 s. Den rapporterer kun hurtigt når værdien faktisk bevæger sig
— rigeligt til at se et brusebad, men aldrig hurtigt nok til at en enkelt
sample-kant kan bruges som signal. Mål altid i vinduer.

**Opskriften der virkede begge gange** (5 min, ingen telefon): restart
matter-server-addon (frisk BlueZ) → push Thread-creds (de wipes ved restart;
TLV hentes med `docker exec app_core_openthread_border_router ot-ctl dataset
active -x`) → `commission_with_code` UDEN `network_only` mod
`ws://172.30.32.1:5580/ws`. Kræver `pip3 install --break-system-packages
websockets` på HAOS-hosten (wipes ved hver reboot).

### IKEA Vallhorn (Zigbee, post-flyt rolle)

✅ Vallhorn (IEEE fd:00:ad:46:6a:93:29:a8) — pre-paret, planlagt depot rolle post-flyt → entity `binary_sensor.depot_valhorn_occupancy`

### Gardin-motorer (planen nedenfor er delvist overhalet af virkeligheden)

**Status 2026-07-28 — hvad der FAKTISK findes i HA:**

**4 gardiner i alt — listen er komplet** (user-spec 2026-07-28). Verdenshjørne
står med, fordi sommer-/vinterforsvaret grupperer efter sol-side.

| Placering | Entity | Side | Hardware | Status |
|---|---|---|---|---|
| Soveværelse | `cover.gardin_sovevaerelse` | **syd** | **Tuya TS0601 rullegardin-motor på ZHA** (`_TZE284_3mzb0sdz`, 2× AA) | ✅ monteret + limits kalibreret 2026-07-28 |
| Stue syd (sofa) | `cover.gardin_stue_syd` | syd | Somfy RTS via Broadlink RM4 Pro | ✅ 2026-06-11 |
| Stue vest (sofa) | `cover.gardin_stue_vest_1` | vest | Somfy RTS via Broadlink | ✅ 2026-06-11 |
| Spisestue vest | `cover.gardin_spisestue_vest` | vest | Somfy RTS via Broadlink | ✅ |

**Droppet 2026-07-28 (user-spec):** børneværelset får ALDRIG gardin-motor —
`cover.gardin_boernevaerelse` er slettet fra hele kodebasen (mørklægning dér =
lyset holdes slukket). Et 5. gardin `cover.gardin_stue_vest_2` var kun et
plan-artefakt og er ligeledes fjernet fra docs.

**Sove-motorens kalibrering** (gentag ved re-montering/`delete_all_limits`):
retning = `select.gardin_sovevaerelse_motor_direction` → **`Back`** (med
`Forward` kører `open_cover` NED, og motoren registrerer "lower limit" som
øvre grænse); kør helt ned → `button…set_lower_limit` (= position 0), kør helt
op → `button…set_upper_limit` (= 100). Position rapporteres først korrekt når
BEGGE grænser sidder (før: fast 50). Motoren melder mål-position med det samme,
så `opening`/`closing` ses aldrig undervejs.

Den oprindelige plan (5× IKEA Matter curtain motors, fx Praktlysing) er
afsluttet — **intet gardin-hardware mangler**. Skal en motor udskiftes, så bevar
det eksakte entity_id, ellers går automations i stykker:

| Placering | Entity_id (skal bevares) | Driver automations |
|-----------|------------------|-----|
| Stue syd | `cover.gardin_stue_syd` | winter/summer_defense (syd), somrig_stue_curtain (smart-klik-RODRET), Dark Mode — egen syd-RODRET omkodet til gæste-knap 2026-09-27 |
| Stue vest 1 | `cover.gardin_stue_vest_1` | winter/summer_defense (vest), somrig_stue_curtain, RODRET, Dark Mode |
| Spisestue vest | `cover.gardin_spisestue_vest` | winter/summer_defense (vest), morning_curtains, putte-glare |
| Soveværelse | `cover.gardin_sovevaerelse` | summer_defense (**syd**), winter_defense, godnat/godmorgen, vækning, Dark Mode, Somrig sove |

**Pairing playbook (Matter — kun relevant ved fremtidig udskiftning):**
1. Pre-flight: `./scripts/matter_preflight.sh` (verify stack health)
2. Per device: `./scripts/matter_commission.sh "MT:QR-code" "gardin_sovevaerelse"`
3. Auto-renamer device + entities. Total ~3-4 min per curtain.

Detaljer: [`entities/covers/covers.yaml`](../entities/covers/covers.yaml) + [`docs/matter_pairing_playbook.md`](matter_pairing_playbook.md)

### IKEA Somrig E2213 (dual-button)

✅ Sove Somrig paret 2026-05-04 (IEEE b3:47:dd:fa:8c:68:31:05)
🛒 5 nye Somrig pares 2026-05-05 (har dem allerede):
- Sove gardin (`somrig_sove_curtain`)
- Stue gardin (`somrig_stue_curtain`)
- Børn gardin (`somrig_boern_curtain`)
- Entré super-remote (4 actions)
- Børneværelse kalde-knap (`somrig_7`) — quick tap = "kalde mor/far" → rødt nat-lys

### IKEA Tradfri E27 hvid dimmable bulbs

🛒 5 stk pares 2026-05-05 (har dem allerede). På standby uden socket-assignment.

### IKEA KAJPLATS E27 CWS globe — entré-loft ✅ (paret 2026-08-21, Matter node 461)

Erstattede `IKEA TRADFRI bulb E27 WS globe 1055lm` i entré-loftet. Samme
entity_id (`light.entre_loft`) — den gamle ZHA-node blev omdøbt til
`light.entre_loft_tradfri_udgaaet` og er en orphan indtil pæren fysisk fjernes
fra ZHA. **To grunde til skiftet:** (1) den er FARVE, så entréen kan være med i
festlys/dance-events + gæste-fanfaren; (2) den er mains-drevet Matter/Thread og
bliver husets **fjerde Thread-router** — badets tre spots var eneste routere, og
falder de, kaskaderer halvdelen af Matter-nettet. Router-rollen er **verificeret**
(`read_attribute 0/53/1` = 5), ikke antaget.

NB pæren sidder på en **vægkontakt**: slukkes den fysisk, forsvinder routeren
igen — og værre, den kan tabe sin fabric. Det skete allerede første dag: node
438 kom aldrig tilbage på mesh'et efter strømtabet og begyndte at BLE-annoncere
som uparret (Google Home tilbød at tage den). Den blev fjernet og pæren paret
forfra som **node 461**. Skal det ske igen, se
[matter_pairing_playbook.md](matter_pairing_playbook.md) — og lad være med at
acceptere Google Homes tilbud, det ville lægge den i Googles fabric.

Den gamle TRADFRI-pære er dermed **udgået af drift** — huset har nu kun ÉN pære
med `E27 WS globe`-quirken (2 %-bug ved bri+ct+transition i samme kald):
`light.depot_loft_ikea`.

---

## Allerede ejer ✅ (men ikke paret endnu)

### Broadlink RM4 Pro + 2× Somfy RTS gardiner ✅ (sat op 2026-06-11)

- **RM4 Pro**: 192.0.2.87 (mac d5:4e:b8:af:bd:dd), `remote.broadlink_rm4_pro`
  + bonus temp/fugt-sensorer. Provisioneret app-/cloud-frit (AP-mode +
  python-broadlink fra NUC-WiFi). USB på NUC er KUN strøm.
  **Står i DEPOTET** (2026-10-15). Temp/fugt er reserve for køkkenets
  TIMMERFLOTTE i `sensor.inde_absolut_fugt` + `sensor.indoor_humidity_resilient`
  (depot = køkken + 0,52 g/m³; får bad-dampen → 30-min-middel).
- **Somfy-gardiner**: `cover.gardin_stue_syd` + `cover.gardin_stue_vest_1`
  (packages/broadlink_gardiner.yaml) — RF-koder fanget på FAST 433.42 MHz
  (auto-sweep virker ALDRIG mod Somfy RTS). Replay-verificeret begge veje.
  RODRETs/defense/godnat-automationer virker via de planlagte entity-navne.
- Fjernbetjeningen har 4 kanaler + alle: kanal syd + kanal vest er fanget;
  2 kanaler ledige til fremtidige gardiner (gen-fang ved behov).

### Chromecast / streaming-stick til projektor

- **Status:** Bruger har Chromecast Google TV — skal pares som ESPHome/Google Cast i HA + omdøbes til `media_player.stue_chromecast`
- **Formål:** Cinema mode tænder/slukker projektor via HDMI CEC. Pt. kommenteret ud i scene_cinema indtil paret.

---

## Nice-to-have 💡

Disse er ikke i koden endnu, men vil enable features fra audit-runde 2026-04-29:

### Smart Zigbee wall-switch til bath + sove (O1)

- **Formål:** Eliminerer ~1 min Styrbar-delay efter wall-switch on. Mekaniske wall-switches kutter strøm til Innr-pærene — hver power-cycle = mesh-disturbance + ZHA queue flush + bulb mesh re-routing. Smart switch bevarer strøm og sender Zigbee-commands → bulb power-cycler aldrig → mesh stabil.
- **Driver:** Daglig UX. Hver gang familien bruger wall-switch (måske 5-10 gange/dag) er der 30-60 sek hvor Styrbar ikke virker. Med smart switch: instant Styrbar response.
- **Type:** Zigbee in-line switch (bag eksisterende kontakt) eller wall-switch insert. Eksempler: Aqara H1 (modular, kræver neutral), Sonoff ZBMINI L2 (no-neutral version findes), Shelly Plus 1 (WiFi alternativ men kompatibel via integration).
- **Antal:** 2 stk (1 til bath, 1 til sove)
- **Kompleksitet:** Kræver el-installation (livefremme work). ~600 kr i hardware + ~1-2 timer elektriker.
- **Sidegevinst:** Hvis valgt med dimming-funktion kan switch'en også være dim-control (men Styrbar dækker det allerede).

### Smart switch til badeværelse-ventilator

- **Formål:** Auto-trigger ventilator når SCD40 humidity > 75% under/efter brusebad. Stop ved < 60%.
- **Driver:** Forhindrer mug og kondens. Audit gap #3.
- **Type:** Zigbee in-line switch der kan klare 230V relay til ventilator-motor.

### Smart siren / klokke til alarmer

- **Formål:** Eskaleret signal ved vandlæk + indbrud. Pt. har vi kun rødt blink + persistent notification.
- **Driver:** [water_leak_alarm.yaml](../automations/water_leak_alarm.yaml) + [security.yaml](../automations/security.yaml).
- **Type:** Zigbee siren (fx Aqara, Heiman). Tjek at den er HØJ nok til at vække fra dyb søvn.

### Parent B telefon — Companion app

- **Formål:** Personlig presence-tracking + push-notifications.
- **Status:** Parent A telefon er paret 2026-04-28. Parent B afventer.
- **Type:** HA Companion app installeret på Parent B's telefon, logget ind som `parent_a` shared user. Person entity `person.parent_b` skal oprettes separat.

### Apple home hub (HomePod mini / Apple TV) — til Parent B's geofence

- **Formål:** Lade iOS eje geofencen for Parent B i stedet for HA Companion-appen. Hjem-appen trykker på `input_boolean.parent_b_hjemme_ios` via HA's HomeKit Bridge (se `packages/parent_b_ios_geofence.yaml`).
- **Driver:** 2026-08-14 satte iOS appen ned til "Authorized when in use" → `device_tracker` frøs på `home` og huset troede hun var hjemme mens hun var ude. Appens "Altid"-adgang udløser de pop-ups der før eller siden bliver klikket væk; en iOS-ejet geofence gør ikke.
- **Status:** Huset har pr. 2026-08-14 hverken Apple TV, HomePod eller HomeKit-bridge (verificeret mod `core.config_entries` + `/api/states`). **Uden hub er Automatik-fanen i Hjem-appen slet ikke tilgængelig** — Apple Home-ruten er derfor blokeret på hardware.
- **Alternativ uden køb:** Genveje-appen (personlig automatik "Når jeg ankommer/forlader"). Men forlad-kaldet sker efter hun er af hjemme-wifi og afhænger derfor af Tailscale på hendes telefon. Hub-ruten er mere robust, netop fordi hub'en står hjemme på LAN'et og selv sender beskeden.
- **Type:** HomePod mini (billigst) eller Apple TV 4K. iPad duer ikke længere som hub.

### Aqara T1 outdoor motion sensor (IP65-rated)

- **Formål:** Hvis terrasse Myggspray viser sig at være for skrøbelig udendørs (Myggspray er indoor-rated, IP20).
- **Driver:** Backup hvis Myggspray dør pga regn/temperatur. Aqara T1 er IP65 og overlever vejret.
- **Type:** Aqara FP1 (mmWave) eller T1 (PIR), Zigbee. Indtil Matter-versionen kommer.

---

## Roadmap-overblik

**Pre-flytte (2026-05-05 — i morgen):**
- [x] 5× Apollo MSR-2 (har)
- [x] 5× IKEA Tradfri hvid bulbs (har)
- [x] 5× IKEA Somrig (har)
- [x] 1× IKEA Vallhorn (har, til entré)
- [ ] Pair Chromecast til HA (allerede ejet)

**Post-2026-05-05 (Matter migration):**
- [ ] **Modtag Sonoff ZBDongle-P** (næste uge) — flash til OpenThread RCP for Thread BR
- [ ] 3× Myggbett (Matter door sensors — hoveddør + altandør + bad)
- [ ] 1× Myggspray (Matter motion — terrasse)
- [ ] Setup Matter integration i HA
- [ ] Pair Myggbett/Myggspray via Matter QR-code

**Post-flytte (2026-06-01+):**
- [ ] Smart Zigbee wall-switch til bath + sove (O1) — eliminerer 1-min delay daglig UX issue
- [ ] Smart switch til bad-ventilator
- [ ] Smart siren

**Apollo MSR-2 spare-strategi (per Apollo support 2026-05-19):**
- ⏸️ **VENT med spare-Apollos.** DPS310 (pressure+temp chip) er **discontinued**
  af manufacturer. Current production MSR-2 ships uden pressure sensor.
- Apollo planlægger transition til **DPS368** (successor) når ESPHome support
  er bekræftet — pressure feature returnerer da i nye units.
- **Anbefaling:** Køb først nye Apollos efter Apollo officielt har shipperet
  DPS368-version. Tjek deres changelog / firmware-releases periodisk.
- Boern Apollo's DPS310 er død (B17) — accepteres som permanent loss af pressure
  på den unit indtil hele unit udskiftes med DPS368-version. Temp fallback via
  `indoor_temperature_resilient` chain dækker.
- [ ] Parent B phone setup
- [ ] Aqara T1 outdoor (kun hvis Myggspray fejler udendørs)

---

## Diskontinuerede produkter (FYI)

IKEA's gamle smart-line erstattes af Matter:

| Gammel (Zigbee) | Ny (Matter/Thread) | Status |
|---|---|---|
| Parasoll door/window | Myggbett | Parasoll udgået, Myggbett er erstatning |
| Vallhorn motion | Myggspray | Vallhorn udgået for nye køb. Eksisterende Vallhorn (depot + kommende entré) fungerer indtil de dør. |
| Tradfri WS bulb | (TBD — IKEA migrerer langsomt) | Hvide bulbs kan stadig købes som Tradfri Zigbee |
| Styrbar 4-button | (uændret indtil videre) | Stadig Zigbee, ikke udgået |
| Somrig 2-button | (uændret indtil videre) | Stadig Zigbee, ikke udgået |

---

## Bath spots pairing (sprint 2026-05-10 — code-ready, awaiting hardware)

5 nye spots installeres i bath. Code er **fuldt klar** — alle entities, groups, automations, scenes, recovery, og firmware-defaults venter på pairing.

### Hardware

| Slot | Model | Type | Status |
|---|---|---|---|
| Spot 1 | IKEA KAJPLATS GU10 CWS 470lm | Matter/Thread (node 75) | ✅ PARET 2026-06-10 |
| Spot 2 | IKEA KAJPLATS GU10 CWS 470lm | Matter/Thread (node 206) | ✅ PARET 2026-06-11 |
| Spot 3 | IKEA KAJPLATS GU10 CWS 470lm | Matter/Thread (node 234) | ✅ PARET 2026-06-11 |
| Spot 4 | Innr RS 242 C GU10 (03:6c:40:7c:f3:dd:e8:02) | RGBW Zigbee/ZHA | ✅ PARET 2026-06-10 |
| Spot 5 | Innr RS 242 C GU10 (d5:17:f0:5b:a9:b1:0e:84) | RGBW Zigbee/ZHA | ✅ PARET 2026-06-10 |

### Pairing-procedure (gentag for hver spot)

1. **Pair via ZHA UI:**
   - HA → Settings → Devices & Services → ZHA → Add Device
   - Skru bulb i (= power on)
   - Vent 30 sek for ZHA discovery
   - Accept device

2. **Rename til konventionen:**
   - Klik på det nye device → tandhjul (settings) → Device name
   - Sæt til **"Badevaerelse Spot 1"** (eller _2, _3, _4, _5)
   - Accept "Update N entity IDs" prompt
   - Resulterende entity_id: `light.badevaerelse_spot_1` → matcher kode

3. **Note IEEE:**
   - Kopiér device IEEE (vises i settings)
   - Hvis Innr RS 242 C GU10 (spot 1+2): opdater `automations/bulb_firmware_defaults.yaml`
     → find `name: bath_spot_1` (eller _2) → erstat `ieee: "00:00:00:00:00:00:00:00"` med faktisk IEEE
   - Hvis spot 3-5 og non-Innr: tilføj NEW entry i `bulb_configs:` blok
     (copy bath_spot_1 template, opdater IEEE + name + cluster_768 baseret på model)

4. **Update device_inventory.yaml:**
   - Find `innr_badevaerelse_spot_1` (eller `badevaerelse_spot_3` etc)
   - Opdater `ieee:` field + `paired:` date

5. **Commit + deploy:**
   - `git add ... && git commit -m "Bath spot N paret" && git push --no-verify`
   - `bash scripts/ha_deploy.sh`

### Hvad sker automatisk efter pairing (ingen kode-ændring)

✅ `light.badevaerelse_all` group inkluderer den nye spot
✅ `light.alle_indvendige` + `alle_lys` includes new spot (Dormant Off, snapshots)
✅ Styrbar bath actions controllerer spot via `light.badevaerelse_all`
✅ presence_badevaerelse tænder/slukker spot sammen med loft
✅ Scenes (zen, party, blue, etc.) target spot via group
✅ AirBnB lockdown + Dormant slukker spot via group
✅ Water leak alarm flasher spot rødt
✅ Terrace presence sluk inkluderer spot

### Specielle tilfælde for spot 3-5 (TBD type)

Hvis du vælger:
- **Innr RGBW** (samme som spot 1+2): tilføj entry i bulb_firmware_defaults med `cluster_768: true`
- **Tradfri WW** (white-only): tilføj entry med `cluster_768: false` (matcher tradfri_white_1-5 pattern)
- **Anden RGBW model**: tjek om `cluster_768` (color cluster) er supporteret. Innr-pattern virker for de fleste RGBW

For 100% behavior-match med eksisterende bath_loft: Innr RGBW er det rette valg (samme firmware-default brightness pattern, samme adaptive sun-bracket logik virker out-of-the-box).

## Stuen: en lux-måler ved sofaen (2026-09-30, lux-audit)

Stue-Apolloens LTR390 døde 2026-05-05 (B111) — `sensor.stue_apollo_lux` har
ikke leveret én måling i 14 døgn. Stuen gater derfor på `sensor.open_plan_lux`,
der måles ved spisestue-vinduet og i køkkenet. Auditten 30/9: user tændte selv
stuen tre gange (17/9 17:22, 24/9 18:19, 27/9 17:40) mens open plan målte
43-230 lx — sofa-hjørnet er mørkere end kanalen der skal repræsentere det.
**Forslag:** en IKEA VALLHORN (lux + bevægelse, samme model som entré/depot)
ved sofaen, eller en ny LTR390-breakout i Apolloen. Når den findes: stuens
tænd-vej skal læse dens tal mens stue-lyset er SLUKKET (ren kanal), ikke
open_plan_lux.
