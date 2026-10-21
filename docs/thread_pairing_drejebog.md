# 🎯 Thread/Matter Parring — Den Skudsikre Drejebog

> *Written in Danish. English overview: [README](../README.md) ·
> [ARCHITECTURE](../ARCHITECTURE.md).*

**Skrevet 2026-06-10** efter KAJPLATS-maratonen (1 succes / ~90 fejl — se
felt-rapporten i [matter_pairing_playbook.md](matter_pairing_playbook.md)).
Designet ud fra princippet: **al friktion fjernes FØR parringsdagen.** Gør
Del 0 én gang i ro og mag — derefter er hver parring 5 minutter.

> **⚠️ 2026-09-23 — DEN EGENTLIGE ROD-ÅRSAG TIL TELEFON-FEJLENE:** husets router
> videresender ikke OTBR'ens IPv6-RA fra kabel til Wi-Fi, så telefonen kan
> aldrig RUTE til Thread-nettet efter BLE-fasen ("Unable to connect", HA ser
> intet kald). URL-bug #6367 er ægte, men ikke nok. **Før et telefon-forsøg:**
> OTBR `backbone_interface: wlp2s0` + restart, og verificér fra PC'en på Wi-Fi at
> der findes en rute til `fd6d:ac87:0485:1::/64` (og at en Thread-node kan
> pinges). Derefter parrede IKEA GRILLPLATS — som NUC-BLE aldrig kunne — på
> første forsøg. Detaljer: `grep -n "Telefon-commissioning" docs/permanente_fakta.md`.

## ✅ VEJ A, som den faktisk virkede (GRILLPLATS ×2, 2026-09-23)

**Claude (NUC):**
1. OTBR-options: `backbone_interface: wlp2s0` (resten af options uændret —
   POST hele objektet) → restart addon → vent til `ot-ctl state` = `leader`.
2. Verificér FRA EN WI-FI-KLIENT (PC'en): `Get-NetIPAddress -AddressFamily IPv6`
   viser en `fda4:…`-adresse, `Get-NetRoute` har `fd6d:ac87:0485:1::/64`, og
   `ping -6 <en Thread-nodes fdb8-adresse fra ot-ctl srp server service>` svarer.
   Uden det: STOP — telefonen vil fejle med "Unable to connect".
3. HA-core `external_url` = `http://192.0.2.151:8123` (WS `config/core/update`).

**User (telefon):**
4. HA-app → Indstillinger → Companion app → serveren: BÅDE Home Assistant URL
   og intern URL = `http://192.0.2.151:8123`. Tailscale FRA. Wi-Fi fra/til
   (henter ruten straks).
5. Kun én uparret enhed med strøm; frisk strøm (10 s ud) eller fabriksreset.
6. Tilføj enhed → Tilføj Matter-enhed → "Nej, den er ny" → scan QR.
   Undervejs ses enheden i SRP først på Googles fabric (`A360F32F…`) + et
   `_matterc`, derefter som `BB335B2CA03048E7-…` (HA) — Matter-loggen siger
   `Commissioned peerN as @1:<node>`.

**Bagefter (Claude):** omdøb device + entities via WS
(`config/device_registry/update` `name_by_user`, `config/entity_registry/update`
`new_entity_id` — **stigende WS-id'er**, ellers fejler kaldet), test on/off med
kvittering i Matter-loggen, sæt backbone tilbage til `enp0s25` og
`external_url` tilbage til `http://198.51.100.101:8123`. User: app-URL + VPN tilbage.

---

## Hvorfor det fejlede for os (de 3 rod-årsager, nu med eksterne beviser)

1. **Android-appens URL-bug (åben bug [home-assistant/android#6367](https://github.com/home-assistant/android/issues/6367)):**
   Appens Matter-commissioning-service bruger den **EKSTERNE URL** til
   websocket-forbindelsen — selv når telefonen står hjemme på WiFi. Vores
   eksterne URL er Tailscale-adressen → uden VPN er den uopnåelig →
   **"Can't reach device" hver gang**, mens pæren imens blev fanget på
   Googles fabric. Bekræftet workaround fra issue'et: *sæt begge URL'er til
   den interne under parring.*

2. **NUC'ens Intel-BT-chip er uegnet til Matter-BLE:** kernel-fejl
   ("Unexpected start frame"), BlueZ-objekter der rådner, GATT-fejl. HA's
   egne udviklere [anbefaler eksterne USB-dongler](https://www.home-assistant.io/integrations/bluetooth/)
   (de tester selv med Feasycom FSC-BP119/CSR8510A10) og advarer generelt
   mod indbyggede adaptere. Virker kun pålideligt ~40 min efter frisk boot.

3. **To kommissionér-stakke sloges om pæren:** Googles stack på telefonen
   prikkede til pæren over BLE (1 forbindelses-slot) samtidig med NUC'en,
   og diagnose-scans med `bluetoothctl` gjorde pæren usynlig for
   Matter-serverens scanner (BlueZ-cache).

---

## 🌐 URL/Tailscale/Termius-redegørelsen (én gang for alle)

Tre HELT adskilte systemer der bruger adresser — bland dem aldrig sammen:

| System | Bruger adresse | Rolle | Påvirker parring? |
|---|---|---|---|
| **Companion app — Intern URL** | `http://192.0.2.151:8123` (eller homeassistant.local) | Appens forbindelse når du er HJEMME (matcher WiFi SSID) | **JA — kritisk** |
| **Companion app — Ekstern URL** | Tailscale `http://198.51.100.101:8123` | Appens forbindelse når du er UDE | **JA — pga. bug #6367 bruger commissioning DENNE** |
| **Termius/SSH** | `homeassistant.local:22` / LAN / Tailscale | Kun terminal-adgang (Claude/dig). | **NEJ — totalt irrelevant for parring** |

**Reglerne:**
- **Intern URL** skal ALTID være `http://192.0.2.151:8123`, og hjemme-WiFi'ens
  SSID (`ExampleHome`) skal stå på appens WiFi-liste (Indstillinger →
  Companion app → din server → Internal connection URL + SSIDs).
- **Ekstern URL** må gerne være Tailscale i hverdagen — MEN på parringsdage
  sættes den MIDLERTIDIGT til samme som den interne (bug-workaround), og
  sættes tilbage bagefter. Dette er punkt P4 i tjeklisten herunder.
- **Tailscale-VPN på telefonen: ALTID FRA under parring.** Selv med korrekt
  URL kan en aktiv VPN-tunnel sende lokal trafik forkert.
- **Termius-rod:** SSH-adgang har INTET med parring at gøre. Hvis Termius
  ikke kan forbinde er det SSH-addon'en der er stoppet (B29) — fix:
  `hassio.addon_start` via REST API eller HA UI → Add-ons. Det blokerer
  aldrig en parring.

---

## 🛒 Del 0A — Indkøb (én gang, ~150 kr, fjerner rod-årsag #2 permanent)

| Ting | Hvorfor | Status |
|---|---|---|
| **USB Bluetooth-dongle** (anbefalet af HA-dev-teamet: Feasycom FSC-BP119; alternativ: TP-Link UB500/ASUS USB-BT500) | Erstatter NUC'ens defekte Intel-BT til Matter-BLE-commissioning. CSR-chippen har hurtigste connect-tider, ingen drivere nødvendige | → på hardware_shopping.md |
| **Kort USB-forlængerkabel** (har vi måske) | HA-docs: forlænger væk fra USB3/metal forbedrer BT/Zigbee-radioer markant. Skal også ADSKILLE donglen fra Sonoff/ZBT-2 (de støjer på hinanden) | tjek skuffen |

Efter donglen er i: NUC-BLE-vejen (VEJ B) bliver pålidelig og kan bruges som
primær — helt uden telefon.

## 📱 Del 0B — Telefon-forberedelse (én gang, 10 min, rolig aften)

- [ ] **P1:** HA-app opdateret fra Play Store (fuld version) + Google Play
      Services opdateret
- [ ] **P2:** App-tilladelse **Lokation = "Tillad hele tiden"** (Android
      nægter ellers SSID-adgang til baggrundsservices → commissioning fejler;
      officielt HA-krav)
- [ ] **P3:** Intern URL = `http://192.0.2.151:8123` + hjemme-SSID på listen
- [ ] **P4 (parringsdags-workaround for bug #6367):** Notér nuværende
      eksterne URL ét sted (det er Tailscale-adressen). På parringsdagen:
      sæt ekstern URL = intern URL. Efter parring: sæt tilbage.
- [ ] **P5:** Synk Thread-creds til telefonen: HA-app → Indstillinger →
      Companion app → Fejlfinding → **"Sync Thread credentials"**
- [ ] **P6:** Verificér preferred network: HA UI → Indstillinger → Enheder →
      Thread → Konfigurer → HA-logoet skal stå under **"Preferred network"**
      (ext_pan `a40cd73932141520`) → tryk **"Send credentials to phone"**.
      Driller det: ryd Google Play Services-data og gentag (kendt fix).

## 🏠 Del 0C — Netværk/HA-forberedelse (én gang, 15 min)

- [ ] **N1:** HA: Indstillinger → System → Netværk → **IPv6 = Automatic**
      (officielt krav for Thread)
- [ ] **N2:** Router: **IGMP snooping / multicast-filtrering FRA** (officiel
      HA-anbefaling — blokerer ellers mDNS-discovery). Tjek routerens
      trådløse indstillinger.
- [ ] **N3:** Ingen VLAN'er / gæstenetværk mellem telefon, NUC og enheder —
      alt på samme flade 2.4GHz-kompatible WiFi
- [ ] **N4:** Begge radio-dongler i NUC (Sonoff=Thread, ZBT-2=Zigbee) med
      indbyrdes afstand, OTBR addon boot=auto, watchdog on

---

## 🚀 Selve parringen (parringsdag, ~5 min per device)

### Preflight (kør altid, 2 min)

```bash
bash scripts/matter_preflight.sh   # alle checks grønne, ellers STOP
```

Plus tjeklisten:
- [ ] Kun ÉN uparret Matter-enhed med strøm (discriminator-kollision —
      KAJPLATS-koderne deler short disc!)
- [ ] Telefon: VPN FRA, hjemme-WiFi, Bluetooth TIL, ekstern URL = intern (P4)
- [ ] Ingen `bluetoothctl scan` undervejs — ALDRIG (cache-forgiftning)
- [ ] Enheden fysisk < 3 m fra telefonen (BLE-fasen)

### VEJ A — Telefonen (primær; officielt supporteret flow)

1. Factory reset enheden (KAJPLATS/IKEA-pære: 6× sluk/tænd i 1-sek-takt,
   slut tændt, **vent på fade-kvittering** — ingen fade = intet reset).
   Fabriksnye enheder: bare strøm på, intet reset.
2. HA-app → Indstillinger → Enheder → **Tilføj enhed → Matter** → scan
   QR / indtast kode.
3. Lad flowet køre HELT færdigt uden at røre noget. Med P1-P6 + N1-N3 på
   plads og ekstern URL = intern er bug #6367 neutraliseret — handoveren
   til HA går nu over den interne URL og virker.
4. Fejler den alligevel: tag screenshot af fejlen, annullér, og gå til VEJ B
   — **lav IKKE 5 gentagne telefon-forsøg** (hver fejl efterlader enheden
   på Googles fabric og kræver nyt reset).

### VEJ B — NUC-BLE ("det magiske kald"; primær når USB-donglen er købt)

Krav: USB-BT-dongle installeret, ELLER kør indenfor 40 min efter NUC-reboot.

> **2026-06-17: CSR8510-donglen ER nu installeret** (hci1, USB 0a12:0001).
> Matter-server addon option `bluetooth_adapter_id` er sat til **1** så Matter
> bruger CSR-donglen i stedet for Intel-built-in (hci0, 8087:0a2a). Med
> separate adaptere er HA's Bluetooth-integration (på Intel) IKKE i vejen
> længere → **trin 2 nedenfor (disable BT-integration) er ikke længere
> nødvendigt**, og WiFi behøver ikke slukkes. TIMMERFLOTTE blev parret på
> første skud med denne opsætning. Verificér adapteren efter NUC-reboot:
> `ls -l /sys/class/bluetooth` + USB-vendor (0a12=CSR=ønsket, 8087=Intel).

```bash
# 1. (kun før dongle) Frisk BT: reboot NUC eller restart Matter-server
# 2. Deaktivér HA's Bluetooth-integration midlertidigt (UI → Integrationer
#    → Bluetooth → Deaktivér) — Matter-serveren skal have adapteren alene
# 3. Kør commission (pusher selv Thread-creds — de wipes ved server-restart):
./scripts/matter_commission.sh "<kode eller MT:QR>" "<entity_prefix>"
# 4. Telefonen er HELT slukket/væk under dette
# 5. Reset enheden FØRST når scriptet/loopet kører (15-min annonceringsvindue)
# 6. Genaktivér Bluetooth-integrationen bagefter
```

3 forsøg uden held → stop, lav frisk Matter-server-restart, prøv 3 til.
Stadig nej → VEJ C.

### VEJ C — Google Home multi-admin (sidste udvej, virker altid men 2 apps)

1. Telefon-BT til, accepter Google Homes "ny enhed"-prompt → parring til
   Google Home gennemføres (Googles stack bruger HA's Thread-net via de
   synkede creds fra P5/P6).
2. Google Home → enheden → ⚙️ → **"Tilknyttede Matter-apps og -tjenester"**
   → **Tilknyt Home Assistant** → handover sker over Thread/IP (ingen
   NUC-BLE, ingen URL-bug — det er en in-app intent).
3. Bagefter kan enheden evt. fjernes fra Google Home (den bliver på HA's
   fabric — multi-admin er uafhængige links).

### Efter succes (uanset vej)

- [ ] Omdøb device + entities til konventionen (`matter_commission.sh` gør
      det selv; ellers manuelt i UI eller bed Claude)
- [ ] Opdater `packages/light_groups.yaml`-kommentar + fjern entity fra
      `scripts/ha_validate_whitelist.txt`
- [ ] Opdater `docs/hardware_shopping.md` status-tabel
- [ ] **Sæt ekstern URL tilbage til Tailscale** (P4 revert!)
- [ ] Genaktivér HA Bluetooth-integration hvis VEJ B blev brugt

---

## 🏆 FACIT 2026-06-11 — den opskrift der faktisk virkede (3/3 succeser)

Spot 1 (node 75), spot 2 (node 206) og spot 3 (node 234) blev alle parret med
**VEJ B fra NUC'ens normale plads** — ingen flytning, ét forsøg for 2+3:

1. `matter-server addon restart` (frisk BlueZ-session)
2. **Deaktivér HA's Bluetooth-integration** (UI → Integrationer → Bluetooth)
   — DEN afgørende ingrediens; Matter-serveren skal have adapteren ALENE
3. Re-push Thread-creds (wipes ved restart)
4. **Telefonens Bluetooth: HELT SLUKKET** (Google-stacken prikker ellers til
   pæren og stjæler dens ene BLE-slot)
5. Armér auto-retry-loop (commission_with_code UDEN network_only, 8 forsøg)
6. FØRST DEREFTER: 6× reset af pæren (fade-kvittering obligatorisk)
7. Hænderne væk → loopet fanger pæren → omdøb → genaktivér BT-integration

**Aflivede teorier (spar tiden næste gang):**
- ❌ VEJ C / Google Home-link: kræver fysisk Google-hub (Nest) til
  Thread-opsætning — "You need a hub" er en hård stopklods uden.
- ❌ "Google-hub-skærmen efterlader pæren på Thread med åbent vindue":
  nej — Google tjekker hub-kravet FØR den rører pæren. 50 net-kast, nul bid.
- ❌ Takeover-kald (network_only) timet efter telefon-fejl: vinduet lukker
  på sekunder; selv et konstant kørende fangstnet fangede aldrig noget,
  fordi HA-app-flowet commissioner til Googles TEMP-fabric og lukker
  vinduet rent. Telefon-vejen er strukturelt upålidelig på Android pt.

## Hurtig fejlfinding

| Symptom | Betydning | Handling |
|---|---|---|
| App: "Can't reach device" | URL-bug #6367 (ekstern URL brugt) eller mDNS blokeret | Tjek P4 + N2; gå evt. VEJ B |
| App: hænger på "Checking network connectivity" | Forkert WiFi-bånd/SSID eller lokationstilladelse | Tjek P2 + N3 |
| Enheden annoncerer ikke (ingen Google-prompt, intet fund) | Ikke i pairing-mode (fanget på et fabric) | 6× reset MED fade-kvittering |
| NUC-BLE: "Discovery timed out" + 0 fund | Enheds-vindue udløbet ELLER bluetoothctl-cache | Reset enheden; aldrig scanne manuelt |
| NUC-BLE: GDBus/"Method Connect doesn't exist" | BlueZ-session rådden | Restart Matter-server + re-push creds |
| PASE crypto-fejl | Forkert pære svarede (discriminator-kollision) | Kun én uparret enhed med strøm |
| Alt fejler, alle veje | 2.4GHz-støj / multicast-filter / IPv6 av | Gennemgå Del 0C igen |

---

## Kilder

- [home-assistant/android#6367 — commissioning bruger ekstern URL (åben bug + workaround)](https://github.com/home-assistant/android/issues/6367)
- [HA Matter-integration docs — krav: IPv6, mDNS/multicast, ingen VLAN, telefonkrav](https://www.home-assistant.io/integrations/matter/)
- [HA Bluetooth docs — anbefalede USB-adaptere (Feasycom FSC-BP119), forlængerkabel-rådet](https://www.home-assistant.io/integrations/bluetooth/)
- [HA Thread docs — preferred network + send credentials to phone](https://www.home-assistant.io/integrations/thread/)
- [Community: Matter Pairing/Commissioning hints — same-SSID-krav, faseopdelt fejlsøgning, BT-eksklusivitet](https://community.home-assistant.io/t/matter-pairing-commissioning-hints/750938)
- Egen felt-rapport 2026-06-10: [matter_pairing_playbook.md](matter_pairing_playbook.md) (8 regler + fejltabel)
