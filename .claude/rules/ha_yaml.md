---
paths:
  - "automations/**/*.yaml"
  - "packages/**/*.yaml"
  - "script_pkg/**/*.yaml"
  - "entities/**/*.yaml"
  - "configuration.yaml"
---

> *Danish. A path-scoped rule file: Claude Code loads it the first time a
> file matching `paths:` is read. See
> [docs/methodology.md](../../docs/methodology.md).*

# HA-YAML og Jinja: platform-fælder når du SKRIVER konfiguration

Path-scopet fra CLAUDE.md (Permanente fakta, flyttet 2026-10-07) — loades når
du læser en YAML-fil under automations/, packages/, script_pkg/ eller
entities/. Kun det man skal vide for at SKRIVE korrekt står her; det
husdækkende diagnose-lag (restart, template.reload, segfault, last_changed)
blev i CLAUDE.md. Den lange version: `docs/permanente_fakta.md` og
`grep -n "Jinja-gotchas" docs/fejlklasser.md`. Ændrer virkeligheden sig, ret
BEGGE lag.

## HA-platformen

- **Huset har INGEN `sensor.uptime` for HA selv** → fang boot-tidspunktet i
  `variables:` FØR en `delay`.
- **`initial:` RESTORER IKKE — den PÅTVINGER** ved hver HA-start. Skal en værdi
  overleve: udelad `initial:` helt, og kør aldrig `input_boolean.reload` for én
  ny helper. **Gratis helper-reloads: `input_text`, `input_number` og `input_datetime`**
  (sidstnævnte målt 10-28: stempler med `initial:` urørte; `input_number`
  målt 10-05: 0/778 ændret — tjek først at alle med `initial:` står PÅ den). Ny
  slider = reload + API-set (den starter på `min`), ingen restart.
- **HA springer SELV `unavailable` entities over i service-kald** → døde pærer
  er et SYNLIGHEDS-problem, aldrig et performance-problem.
- **Et Styrbar-tryk sætter selv rummet i Manual** → skal en anden automation
  sætte Auto på samme tryk, skal den vente ~2 s.
- **`delay_on` + `delay_off` på SAMME template-udtryk bevogter kun ÅBNINGEN.**
  **Signatur:** en sensor hvis `last_changed` er mange gange ældre end dens
  `delay_off`, mens state-templaten renderer False. → split i BEVIS-sensor
  (`delay_on`, intet `delay_off`) + HOLD-sensor. NB templated `delay_off` skal
  være SEKUNDER som skalar.
- **Et `statistics`-vindue over en sensor der kun rapporterer ved ÆNDRING mister
  sin bund når værdien har stået stille længere end `max_age`** — præcis i
  hvilen før hændelsen. **Signatur: en stigning der måles fra hændelsens FØRSTE
  sample, ikke fra hvilen.** → bær forrige sample med (`sensor.badevaerelse_fugt_forrige`).
- **En `history_stats` hvis `start:` er en entitets `last_changed` er STALE i
  netop den flankes sekund** (genberegnes først ved næste minut-tick) → en regel
  der trigger på flanken læser det GAMLE vindue. **Signatur: en "efter N min"-
  handling der fyrer 0,1 s efter flanken.** → kræv også `now() - last_changed ≥ N`.
- **Et urørt `input_datetime` med `has_date: true` står på DAGENS midnat** →
  guard på `states(x)[11:] == '00:00:00'`. Sæt med **`set_datetime`**.
- **`as_timestamp(states('input_datetime.X'), 0)` er FORKERT** (naiv lokal
  streng parset som UTC) → brug **`state_attr(x, 'timestamp')`**. **Signatur:**
  et "aldrig sat"-stempel ser friskt ud mellem 02:00-02:02; fejlen bliver **+1 t
  ved vintertid** i stedet for at forsvinde. Huset er ryddet (B121+B127).
- **En urørt `input_text` står på `'unknown'`, som er truthy** — test eksplicit;
  `| default('', true)` redder den ikke.
- **`last_triggered` sættes FØR action-body'en fejler** → frisk stempel + nul
  side-effekter = action'en aborterer. Duer derfor heller ikke som dedupe inde i
  automationens egen `choose:` (den læser sit eget stempel) → hører i
  `condition:`.
- **HA-slugify:** ø→o. **Entity_id'et afledes af `name:`, ALDRIG af
  `unique_id:`** — rammer du forkert, fejler intet: sensoren findes, forbrugeren
  læser tomt, og guarden returnerer false for evigt. Slå sluggen op i
  `/api/states` efter første restart. Entity_ids er danske alias-slugs — list
  dem (`hq.py find`), gæt aldrig.
- **`!include` af en MANGLENDE eller ugyldig fil sender HELE HA i recovery mode;
  `!include_dir_named` på en manglende mappe giver bare `{}`** (målt 2026.9.2).
  En fil HA læser og et script skriver → afledt, kun-tal, atomisk, `merge=binary`
  i `.gitattributes` (`config_snapshots/fresh_install/`).
- **En `template:`-blok er ALT-ELLER-INTET pr. fil:** én ugyldig sensor dræber
  HELE `template:`-nøglen, mens filens `automation:`/`input_*:` loader normalt.
  **Signatur:** entities der hverken er `unavailable` eller i registry
  (= fraværende ≠ stale reference). Log-grep: `template|package` +
  `error|invalid`, ikke entity-navnet.
- **`parallel:`-grene DELER variabel-scope** — en `variables:` i gren 2
  overskriver gren 1's (målt 12/10: begge ild-grene skrev til spot 2).
  **Signatur:** én af N parallelle løkker "fryser", mens trace viser lige mange
  kald i hver gren. → én løkke der skifter mål, eller unikke navne pr. gren.
- **En trigger-template-sensor på `unknown`/`unavailable` ved restart får IKKE
  sine attributter gendannet** (`template/entity.py`) → en akkumulator i en
  attribut skal have en state der aldrig er `none`.

## Jinja-gotchas

- En `variables:` der renderer bar `false`/`true` bliver en truthy STRENG →
  skriv `{{ false }}` (harmløst i `value_template`; `| default(false, true)`
  redder det IKKE).
- **Et SCRIPT-FELT der ikke sendes med i kaldet er UDEFINERET**, og `| int(0)`
  redder det ikke — hele automationen aborterer med `UndefinedError` →
  `| default(x) | int(x)` på ethvert valgfrit felt.
- **`{{ trigger.id | default('x', true) }}` redder IKKE en automation kaldt via
  `automation.trigger`** — opslaget på det udefinerede `trigger` kaster FØR
  filteret griber; kun `{{ trigger.id if trigger is defined else 'x' }}` virker
  (samme gælder ethvert `trigger.<felt>`).
- **`| string` gør INTET ved et StrEnum** (`color_mode`, attribut-nøglerne
  `icon`/`friendly_name`) — en dict-variabel med et enum bliver en repr-STRENG;
  brug `'' ~ x` og byg dicts af kendte nøgler.
- **Et rå `states()`-opslag der RENDER som et unparenthesized tal-komma
  (`"255,168,89"`) er gyldig Python tuple-syntaks** — giver man den sin EGEN
  `variables:`-nøgle, native-parser HA den til en `TupleWrapper` (ingen
  `.split()`, aborterer med `UndefinedError: ... has no attribute 'split'`). →
  split ALTID i SAMME Jinja-blok som opslaget (internt `{% set %}`), aldrig en
  separat raw-string-variabel (ramt i `packages/stue_spots.yaml`).
- **`repeat.index0` findes IKKE** (kun `repeat.index`, 1-baseret).
- Et ukendt attribut bliver Undefined og maskeres af forbrugerens `| int(0)`.
- Ingen list-comprehensions · foldet `{% %}`-blok = streng · template-sensor
  name-slug SKAL matche unique_id · `%` skal IKKE escapes · ingen `exp()`, men
  konstanten `e` og `**` virker.
- `{# #}` kan ikke ligge inde i `{{ }}`, og et literal `#}` i kommentar-TEKSTEN
  lukker kommentaren for tidligt.
