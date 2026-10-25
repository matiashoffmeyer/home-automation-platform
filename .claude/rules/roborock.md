---
paths:
  - "packages/roborock*.yaml"
  - "packages/robot_*.yaml"
  - "dashboards/stoevsug.yaml"
  - "packages/maaltid_detektion.yaml"
---

> *Danish. A path-scoped rule file: Claude Code loads it the first time a
> file matching `paths:` is read. See
> [docs/methodology.md](../../docs/methodology.md).*

# Roborock

Path-scopet fra CLAUDE.md (Permanente fakta) — loades når du læser en fil
der matcher `paths:`. Samme genkendelses-lag: regel, signatur, entity-navn.
Den lange version (måledata, incidents): `docs/permanente_fakta.md`
(`grep -n "<nøgleord>"`). Ændrer virkeligheden sig, ret BEGGE lag.

- **Roborock sug + mop er ÉN tilstand:** enhver mop-skrivning sætter sugestyrken
  ned → sug skrives SIDST. Kraftigst: `max` + `extreme` + `standard`.
- **Roborock:** statussen kommer fra deres SKY, ½-2½ min EFTER robottens egen
  start; kun `sensor.s8_maxv_ultra_status` skelner varianterne. **Robotten ER
  den bevægelse Apollo'erne ser** → `binary_sensor.roborock_zone_maskering` kan
  kun trække estimatet til 1, aldrig til 0.
- **Forhindringer + fotos registreres KUN under rengøring** — goto (`app_goto_target`)
  og fjernstyring ser intet og kører ind i ting. Spejder-tur = en rigtig clean.
  Forsigtig kørsel = `set_collision_avoid_status` **2** (appens værdi, 22/10).
- **Spejdertur (mild mop, ingen sug) kører KUN i tomt hus**, foran hel-hus-
  kørslerne (`script.roborock_start_med_spejder`) og hver segment-vej — rum-kø,
  let stue-tur, måltid — via `script.roborock_spejdertur_rum`, der SVARER
  `koer`/`spejd`/`vent` (response_variable). Tilstand i
  `input_text.roborock_spejder_fase` (`<fase>:<epoch>:<script>:<profil>[:<seg-seg>]`).
  Dens rengørings-post genkendes på start ≈ epoch → tæller ALDRIG som rengøring.
  En ny segment-vej uden spejder-kaldet er en regression (`grep spejdertur_rum`).
- **I SmartPlan (alle tre koder `smart_mode`) AFVISER robotten løse profil-
  skrivninger** (`Error while calling SET_MOP_MODE`) — kun det atomiske
  `set_clean_motor_mode` kommer ud. **Signatur: en kø/start der aborterer på
  sin første select-skrivning lige efter en SmartPlan-tur.** → enhver
  profil-vej kalder `script.roborock_forlad_smartplan` FØRST (`grep forlad_smartplan`).
