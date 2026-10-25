---
paths:
  - "packages/dance_mode.yaml"
  - "packages/fest_*.yaml"
  - "script_pkg/vejr_varsel_blink.yaml"
  - "automations/rain_warning.yaml"
  - "packages/weather_warning.yaml"
  - "packages/roegalarm.yaml"
  - "packages/alert_*.yaml"
  - "packages/apollo_rgb_varsel.yaml"
  - "packages/koekken_gestus_timer.yaml"
  - "automations/legetoejsdag.yaml"
  - "script_pkg/house_routines.yaml"
  - "automations/godnat_night.yaml"
  - "automations/presence_badevaerelse.yaml"
  - "packages/badevaerelse_*.yaml"
  - "packages/entre_fade_ud.yaml"
  - "packages/light_groups.yaml"
---

> *Danish. A path-scoped rule file: Claude Code loads it the first time a
> file matching `paths:` is read. See
> [docs/methodology.md](../../docs/methodology.md).*

# Lys-effekter, fades og protokol

Path-scopet fra CLAUDE.md (Permanente fakta) — loades når du læser en fil
der matcher `paths:`. Samme genkendelses-lag: regel, signatur, entity-navn.
Den lange version (måledata, incidents): `docs/permanente_fakta.md`
(`grep -n "<nøgleord>"`). Ændrer virkeligheden sig, ret BEGGE lag.

- **Et `light.turn_on` med N pærer returnerer først når den LANGSOMSTE har
  svaret** (`spisestue_loft` hænger 5,5 s hvert 6.-8. kald) → en hurtig effekt
  må aldrig være ét gruppe-kald pr. frame; brug én løkke pr. pære på et fælles
  ur (`script.dance_event_bulb`). **Signatur:** en effekt der varer mange gange
  sin designede tid og fryser ~5 s ad gangen på ALLE pærer.
- **Matter-pærer deler ÉN flaskehals: ~0,1-0,15 s × antal Matter-pærer pr.
  kommando, et farvet turn_on = 2 kommandoer, og 2-3 % gensendes med ~5,2 s
  hæng** (normalt, ikke et sygt net). **Signatur:** Matter-pærer ude af takt i
  en hurtig effekt mens ZHA-naboen holder den. → **de danser slet ikke med i
  koreografien (25/10, B260):** festlys skriver kun til Thread-pærerne på deres
  plads i husets fælles gitter (`custom_templates/festlys.jinja`,
  `input_number.festlys_thread_skrivninger` pr. minut for ALLE tilsammen) — et
  tempo-gulv pr. pære (det gamle `inv`) holdt ikke HUSETS sum nede.
- **Et FARVET `light.turn_on` er TO zigbee-frames pr. pære**, et `turn_off` én
  (målt 2:1) → i en blink-løkke: sæt farven ÉN gang før løkken, rene niveau-kald
  i den. **Et blink hvis ON-fase er kortere end bølgen kan ALDRIG se synkront
  ud** — gulv ≈ 3× målt p90, med mindre målet er en ægte ZHA-gruppe.
- **Huset har ÉN ægte ZHA-gruppe:** `light.zbt_2_vejrvarsel_morgen` (`_aften`
  faldt væk 2026-09-23: ZHA laver ingen gruppe-entity under 2 medlemmer). Ét groupcast-frame ⇒ ingen bølge, men **ingen APS-ACK pr. pære**.
  To fælder: en ZHA-gruppe markerer sig med **`group_entities`**, ikke
  `entity_id` (en guard der kun tester `entity_id` kan groupcast'e et sluk); og
  **ZHA skriver ANTAGET state på medlemmerne**, så recorderen ikke kan bevise
  synkronitet.
- **HA's state er IKKE et referat af hvad du sendte til en Matter-enhed** (~1
  rapport/sek, Level og Color uafhængigt) → skal du bevise at N hurtige kald
  landede, gør hver skrivning **identificerbar**.
- **Recorderen gemmer INGEN lys-attributter ud over `friendly_name`** →
  **history kan ALDRIG bevise hvilken farve eller lysstyrke en pære havde**; kun
  live-polling. Og en Matter-pære rapporterer LANGSOMMERE fra slukket end når
  den allerede lyser. **Signatur:** "pæren blev ikke rød", hvor dit eget
  måle-interval er kortere end koldstarten.
- **En lang `transition` på ét `light.turn_on` køres i PÆRENS firmware**
  (lineær `MoveToLevel`, mens lysopfattelse er logaritmisk). **Signatur: en fade
  der hakker mod slutningen, og en history med kun TO rækker.** → lad HA drive
  rampen i **geometriske** trin (`godnat_fuld`).
- **HA's Matter-light videregiver ALDRIG `transition` til `turn_off`**, mens ZHA
  honorerer det ⇒ **en blandet lysgruppe slukker i to tempi**. **Signatur:**
  state-rækker inden for 0,2 s, hvor de sene pærer har `off_with_transition`. →
  fix ÉT sted, på gruppens `→ off`-flanke
  (`badevaerelse_spots_confirm_off`): gør de LANGSOMME hurtige.
