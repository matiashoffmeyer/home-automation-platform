---
paths:
  - "packages/*gardin*.yaml"
  - "automations/*gardin*.yaml"
  - "packages/*curtain*.yaml"
  - "automations/*curtain*.yaml"
  - "packages/mosbillede_*.yaml"
  - "packages/dark_mode.yaml"
  - "packages/projektor_predark.yaml"
  - "packages/putte_vest_glare.yaml"
  - "packages/*_morgen_beskyttelse.yaml"
  - "automations/somrig_buttons.yaml"
  - "automations/{summer,winter}_defense.yaml"
  - "automations/wakeup_alarm_driven.yaml"
  - "entities/covers/**"
---

> *Danish. A path-scoped rule file: Claude Code loads it the first time a
> file matching `paths:` is read. See
> [docs/methodology.md](../../docs/methodology.md).*

# Gardiner og sol

Path-scopet fra CLAUDE.md (Permanente fakta) — loades når du læser en fil
der matcher `paths:`. Samme genkendelses-lag: regel, signatur, entity-navn.
Den lange version (måledata, incidents): `docs/permanente_fakta.md`
(`grep -n "<nøgleord>"`). Ændrer virkeligheden sig, ret BEGGE lag.

- **`sun.sun`s azimut/elevation opdateres kun hvert 4. min over 10° (2 min
  under), og recorderen gemmer dem ikke** → en sol-regulering handler på en
  gammel sol: fremskriv (`sensor.mosbillede_solindfald_cm`); historik = regn.
- **En `platform: time`-trigger på en `sun.sun`-afledt timestamp fyrer ALDRIG**,
  og sun-triggerens `offset:` kan ikke templates → slider-styret offset kræver
  et VINDUE-flag (`binary_sensor.sove_gardin_aftenluk_vindue`).
- **Auto-åbnere af gardiner deler ét hold-anker:** `sensor.gardiner_manual_hold`.
- **De tre open-plan-gardiners position er en ANTAGELSE, ikke en måling**
  (envejs RF), og restaureres ikke: efter hver restart `unknown`. Sove-gardinet
  er IKKE ramt. Gates på position/`open`/`closed` er stumme efter restart (#9).
- **Terrassedøren har INTET gardin** (user 2026-10-07) → en åben terrassedør må
  aldrig spærre et gardin (en spærre på stue vest blev bygget og fjernet igen
  samme dag). **Stue vest må højst 85 % ned — der står ting under:** close =
  NED → `input_number.gardin_vest_ned_sekunder` → stop, målt fra TOP. Derfor er
  vest-luk IKKE idempotent: et 2. luk uden åbning imellem kører i bund. Re-home
  (op først) som `script.gardin_film_luk`, eller luk kun fra kendt top.
- **`sensor.gardiner_manual_hold` har TO lister: `held` = auto-ÅBN-blokliste
  (bærer AirBnB-tæppet: alle fire permanent), `held_luk` = auto-LUK-blokliste
  (samme minus tæppet).** **Signatur: en LUK-vej der læser `held` kan aldrig
  lukke for en gæst** (sept.: sove-gardinet 100 % oppe i 6½ nat, B123). → nyt
  ejer-flag IND i ankeret (alle tre renderinger, #2 — åbnerne arver gratis);
  LUK-veje læser `held_luk`, og om de kører i AirBnB er deres EGEN mode-gate.
- **Sol-indtrængnings-dybde = `(brystning+højde)/tan(elev) × cos(azimut−normal)`,
  men den formel ALENE lyver ved strøjflys:** `1/tan` → ∞ gange `cos(Δ)` → 0
  giver et plausibelt mellemtal uden lys i. **Signatur: stor dybde ved elevation
  under ~3°.** → kræv `cos(elev)·cos(Δ) ≥ 0,25` INDE i dybde-sensoren (#2), og
  FÅ RUMMETS MÅL FØR du modellerer — gæt aldrig hvilken væg, hvor langt,
  hvor højt. Spisestuen: vinduet vender **333°** (user, professionelt kompas =
  source of truth), mosbilledet på den parallelle væg 250 cm overfor, sydkant i
  flugt med vinduets nordkant (foto 30/9); gardinet aldrig under 50 % åben
  (user). Den SETE eftermiddagssol på billedet (az 244-248°) kan 333° ikke
  forklare → empirisk strejflys-boks (`packages/mosbillede_solbeskyttelse.yaml`).
  **Signatur: en observation modellen ikke kan forklare → spørg om målet. Et
  MÅLT tal slår omtrentlige ord ("nord-syd-vægge") og din egen slutning; dæk
  observationen empirisk, fit ALDRIG en vinkel til den.** Glasset er 55-228 cm.
