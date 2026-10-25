---
paths:
  - "packages/*otbr*.yaml"
  - "packages/thread_*.yaml"
  - "scripts/otbr_*"
  - "scripts/matter_*"
  - "docs/matter_pairing_playbook.md"
  - "docs/thread_pairing_drejebog.md"
  - "docs/otbr_rcp_recovery.md"
  - "docs/zigbee.md"
  - "docs/hardware.md"
---

> *Danish. A path-scoped rule file: Claude Code loads it the first time a
> file matching `paths:` is read. See
> [docs/methodology.md](../../docs/methodology.md).*

# Thread, Matter og parring

Path-scopet fra CLAUDE.md (Permanente fakta) — loades når du læser en fil
der matcher `paths:`. Samme genkendelses-lag: regel, signatur, entity-navn.
Den lange version (måledata, incidents): `docs/permanente_fakta.md`
(`grep -n "<nøgleord>"`). Ændrer virkeligheden sig, ret BEGGE lag.

- **Husets Thread-routere (09/10, 8 stk): badets KAJPLATS-spots, entré-loftet,
  stue-spotsene og GRILLPLATS-pluggene
  (`switch.thread_router_koekken` i køkkenet, altid tændt — før sove-lyskæden;
  hyggelampens `switch.stue_plug` i stuen; begge fra 15/10).** Stue-spotsene er BROEN mellem OTBR'en
  og badet: trækkes de ud, falder badet af (08/10 20:38 → 20:56). Gen-verificér
  rollerne med `ot-ctl router table` (extended MAC ↔ matter-nodens `0/51/0`).
- **Zombie-router: står i `router table` med Age < 30 s men er døv for ping/
  Matter** → HA `unavailable`, pæren hænger i sin sidste tilstand. Kur:
  `ot-ctl releaserouterid <id>` på lederen; automatiseret i
  `scripts/thread_zombie_kick.py` (daemon-loopet, 6 min hold, 30 min cooldown).
- **Et Thread partition-split heler IKKE altid sig selv** (03/09: 21 min;
  08-09/10: OTBR'en ensom leder i 9 t, og hver OTBR-restart/pin-reset lavede
  bare en NY ensom partition — kun et fysisk genplug samlede nettet).
  **Signatur:** `sensor.otbr_routere` = 1 mens Thread-enheder er unavailable.
  → `binary_sensor.thread_border_router_nede` + stigen i
  `thread_otbr_watchdog.yaml` (TX-boost → chip-reset → USB-genplug, for evigt).
  **NUC'ens root-hub har ingen port-strømstyring → software kan IKKE give
  donglen et power-on-reset**, og user køber ikke en hub (9/10). Udløseren
  08/10 var stue-spots trukket ud + den gamle vagts pin-reset — ikke donglen.
- **NUC'en har TO BLE-adaptere, og indekserne er omvendt af hvad man gætter:**
  `hci0` = USB-donglen (virker), `hci1` = Intel (duer IKKE) →
  `bluetooth_adapter_id: 0`. **Signatur:** parringen dør konsekvent på
  `SendPAICertificateRequest` — ligner en upparret pære, og fabriksreset er den
  forkerte konklusion. [docs/matter_pairing_playbook.md](../../docs/matter_pairing_playbook.md) FØRST.
- **IKEA GRILLPLATS (Thread-plug) kan IKKE parres fra NUC'en — hverken matter.js
  eller CHIP-SDK, hverken CSR- eller Intel-adapter.** **Signatur:** BLE-connect +
  BTP-håndtryk lykkes (`656c04f10005`), så `Acknowledgement … not received` /
  `PASESession timed out … message type was 33`. Ikke afstand, ikke reset.
  Upstream: matterjs-server #929. **Vejen der VIRKER: HA-appens Android-flow**
  — begge parret 2026-09-23 efter fixet i næste bullet.
- **Telefon-commissioning kræver at Wi-Fi-klienter kan RUTE til Thread — og
  husets router videresender IKKE OTBR'ens IPv6-RA fra kabel til Wi-Fi** (den
  leverer ingen IPv6 selv). **Signatur:** pluggen dukker op i SRP på Googles
  fabric `A360F32F…`, telefonen siger "Unable to connect", HA ser NUL kald. →
  Parringsdag: OTBR `backbone_interface: wlp2s0` (drift: `enp0s25`) + begge
  app-URL'er = LAN-IP (bug #6367) + VPN fra. Opskrift: toppen af
  [docs/thread_pairing_drejebog.md](../../docs/thread_pairing_drejebog.md).
- **Sonoff-donglens RCP kan hard-hænge** → RCP-reset kurerer KUN et wedget
  addon (`state: error`), aldrig en pære der er faldet af mesh'et — og på et
  raskt net (`sensor.otbr_routere` > 1) gør den skade (ny ensom partition).
- **RCP-resets skalerer med Matter-kald-raten til stue-spotsene (~1 % pr.
  kommando).** **Signatur:** et Matter-kald der hænger ~5 s, samtidig på alle
  Thread-pærer, og `radio tx timeout → RCP failure` i otbr-loggen i samme
  sekund. Årsag: ZBDongle-E kører 460800 baud UDEN hardware flow control (har
  ingen) → tabte serial-bytes (addons#4856). Ingen RCP-firmware løser det (B232).
  **Trappe 17/10:** ≤ 0,5 kald/s rent, 1 kald/s = reset-byge efter ~3 min;
  en KAJPLATS-OTA koster ~3 resets (`grep -n "Trappe-test" docs/permanente_fakta.md`).
- **OTBR-add-on'et nulstiller TX-power til 6 dBm ved hver start** → daemonens
  `txhold` holder 17 dBm hvert tick (B234). Svag sendestyrke = de fjerne
  stue-spots (path cost 4-5) falder af. Tjek: `ot-ctl txpower`.
- **Thread-helbred som tal: `sensor.otbr_rcp_resets_1t`** (daemonen, hvert
  2. min via eventet `otbr_rcp_stats` → trigger-sensor). Ild-trafikken
  pauser over `input_number.stue_spots_ild_rcp_loft`/t og i 30 min efter en
  byge (≥ `stue_spots_ild_rcp_byge` på 10 min, 17/10) — crashet kommer som en
  byge, timeloftet når det for sent. Byg aldrig ny
  Matter-trafik med > ~1 kommando/5 s pr. pære uden at måle den her.
  **Festlys deler samme vagt** (`binary_sensor.stue_spots_ild_thread_pause`).
- **Budgettér HUSETS sum, ikke pr. pære (25/10, B260):** halloween sendte ~0,67
  kommandoer/s pr. Matter-pære = ~2/s i alt og fældede OTBR'en (06:21, alle
  Thread-enheder væk ~3 min); hvert test-løb 24/10 kostede 3-5 RCP-resets.
  **Signatur:** KLYNGER af RCP-resets (3+ inden for 30 s) i takt med festlys-
  events, OTBR hard-hang lige efter et låst event — enkelt-resets ~1,8/t er
  baggrund (B232). → ét fælles gitter for alle Thread-pærer på et absolut ur
  (`custom_templates/festlys.jinja`, `input_number.festlys_thread_skrivninger`
  pr. minut, default 8 ≈ 0,27 kommandoer/s), skriv kun når udseendet skifter.
  **Diagnose-trafik tæller også:** `meshdiag` spørger hver router over luften
  → Thread-kortets måle-interval er `input_number.thread_kort_maaling_minutter` (4 min fra 15/10; RCP-resets/t var ens ved 2 og 30 min).
- **Entré-loftet + stue-spotsene er husets SKRØBELIGSTE Thread-led (user-spec
  15/10: "meget forsigtige med at belaste dem")** — indtil 15/10 18:51 nåede
  stuen kun OTBR'en via entré-loftet (74-92 % frame-fejl på stue→entré).
  **Fra 15/10 har køkken-routeren (GRILLPLATS node 499) LQ 3 til OTBR'en,
  stue spot 1 og Stue Plug** = en vej uden om entré (meshdiag 19:19; spot 2
  linker også, men med 24 % fejl). Gen-mål før du antager den ene eller anden vej. → ny kode der skriver til en af de tre (eller meshdiag/ping
  over dem) kræver et målt kommando-budget FØR deploy; entré-faden er skåret
  31 → 10 kommandoer, og `thread_zombie_kick.py` kicker aldrig entré
  (`BRO_NODER`). **Signatur:** stue-spot `unavailable` mens den står i
  `router table` med frisk Age — subscriptionen dør på broen, ikke radioen.
- **Tæl udvekslinger, ikke kommandoer: en Matter-pære SVARER med rapporter**
  (målt entré-loftet 15/10): CurrentLevel for hver ~50 trin ændring (uanset
  overgangens længde), + 2× RemainingTime når `transition` > 0, + OnOff ved
  tænd/sluk. Et blødt lysstyrke-skift ≈ 4-5 udvekslinger; et øjeblikkeligt ≈ 2.
  Budgettér i udvekslinger — rapporterne fra stue-spotsene går også gennem entré.
- **Split-signatur: `Different partition (peer:X` i otbr-loggen + NoAck** →
  enheden sidder i sit eget net og fletter ALDRIG selv; kun genplug af den.
  `binary_sensor.thread_enheder_vaek` pusher hvilken (30 min, 1 pr. 12 t).
  **Er det en ø af FLERE routere, er genplug af én ikke nok** — den finder
  sine gamle naboer og genskaber øen → sluk ALLE øens medlemmer samtidig,
  tænd én ad gangen (B234, 15/10). At OTBR'en flytter med over i en
  genopstået partition (`BetterPartition`) er en fletning, ikke en fejl.
- **OTBR'en er altid leder (15/10): `leaderweight 128`** (andre 64-65; vægten
  sammenlignes FØR størrelse) holdt af `thread_zombie_kick.py`, som også kører
  `state leader` efter ≥ 6 min som router. **Signatur på det det forhindrer:**
  `leaderdata` peger på en router der ikke svarer på meshdiag → ingen nye
  router-ID'er (REED'er hænger som børn), halvdøde routere ryddes aldrig.
