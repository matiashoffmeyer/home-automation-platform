---
paths:
  - "packages/*lux*.yaml"
  - "packages/activity_state.yaml"
  - "packages/koekken_lyskaede.yaml"
  - "packages/koekken_cooking.yaml"
  - "packages/morgen_opstigning_rampe.yaml"
  - "packages/mosbillede_solbeskyttelse.yaml"
  - "packages/natlys_sol.yaml"
  - "packages/sensor_snapshots.yaml"
  - "automations/presence_*.yaml"
  - "automations/morning_lights_sanity_check.yaml"
  - "automations/{summer,winter}_defense.yaml"
  - "script_pkg/room_logic.yaml"
---

> *Danish. A path-scoped rule file: Claude Code loads it the first time a
> file matching `paths:` is read. See
> [docs/methodology.md](../../docs/methodology.md).*

# Lux og dagslys (Apollo LTR390)

Path-scopet fra CLAUDE.md (Permanente fakta) — loades når du læser en fil
der matcher `paths:`. Samme genkendelses-lag: regel, signatur, entity-navn.
Den lange version (måledata, incidents): `docs/permanente_fakta.md`
(`grep -n "<nøgleord>"`). Ændrer virkeligheden sig, ret BEGGE lag.

- **Apollo MSR-2'ens onboard SK6812-RGB lyser ind i sin EGEN LTR390.**
  Adfærds-logik læser `sensor.<rum>_lux_reel`, **aldrig** `*_apollo_lux`.
- **LTR390'en rapporterer kun ved ændring ≥ ~20 lx** → under ~20 lx er en
  aflæsning det SIDSTE trin, ikke en måling. **Signatur: en lux-sensor der står
  på samme decimal-tal hele aftenen gennem solnedgang og lys-skift.** En gate
  under ~20 lx kan ikke afgøres af kanalen alene (sove-fixet: sol < −6° +
  aflæsning < gate + 20 = mørkt).
- **RUMMETS EGNE LAMPER lyser også ind i LTR390'en — en lux-gate der kan
  evalueres mens vores eget lys er tændt, måler sig selv** og bliver
  selvopfyldende. **SVARET er et FASTHOLDT RENT SAMPLE, ikke et fradrag**
  (`binary_sensor.<rum>_lys_rent` → `sensor.<rum>_dagslys_sample`): et fradrag
  skal ramme farve-regime, over-/under-fradrag og fade-kurve rigtigt SAMTIDIG,
  et gemt sample skal ramme nul af dem. Reglerne der følger med:
  - Gate-kilder: `sensor.koekken_dagslys_lx`, `sensor.open_plan_lux`,
    `sensor.entre_lux_reel`. **Entré duer som RETNING, ikke NIVEAU** (open plan
    median 2,26× lysere) → skaleres med
    `input_number.open_plan_entre_fallback_faktor`. **Et fallback-led vurderes
    på om det måler det SAMME, ikke kun på om det svarer.**
  - **Et for gammelt eller lånt sample lander i DØDBÅNDET mellem tænd- og
    sluk-gaten — så fyrer INGEN vej, og lyset brænder i timevis** (18b).
    **Om aftenen er retningen kendt** → fremskriv ad solhøjden HELE aftenen med max(bånd-median, dagens egen rate
    `k_idag`) (under 3° falder
    spisestuen ≥ ×e^−0,59 pr. grad i ALLE målte par), fald aldrig tilbage til en
    kontamineret fallback (`spisestue_dagslys_lx`; `open_plan_lux` under 11° sol
    siden 30/9 — samme bånd-tabel, ret begge). **Kun sikkert for LYS-gates:
    en solbeskyttelse ser ikke sol der bryder igennem** → rå minus målt
    lampelys (`sensor.mosbillede_lux_maalt`). `open_plan_lux` har et SOL-LOFT
    på begge grene (morgen og aften har HVER sin målte kurve — morgenen er langt
    mørkere ved samme elevation).
  - **Et gemt sample er et LOFT, ikke et facit** → `min(sample, rå
    *_apollo_lux)` — rå, ALDRIG `*_lux_reel`. Børneværelsets er upålidelig →
    `sensor.boernevaerelse_lux_reel` er **afledt** af open-plan × 35 %.
  - **Et fradrag er ALTID for smalt i et åbent rum. Signatur: time-medianer
    HØJERE om aftenen end midt på dagen.** → loft af `sensor.open_plan_lux`.
  - **Et fradrag STØRRE end den rå måling er ikke 0 lux — det beviser at modellen
    er for stor**, men `max(…, 0)` gør det til en påstand om kulsort (og `min`
    kan kun mørkne). **Signatur: dagslys-sensor klistret på 0,0 mens den rå
    kanal måler 70-noget.**
  - **Kontaminationen er SELV-KORRIGERENDE hvis tænd/sluk-parret er bredere end
    den:** tænd-gaten evalueres mens lampen er slukket (ren kanal), sluk-gaten
    mens den lyser (biased OPAD) — og opad peger mod at slukke kunstigt lys = den
    sikre retning. → vælg en VINDUESNÆR kilde + et målt bånd (køkken→spisestue
    3,37×, par ≥ 56 lx), ikke en fradrags-model.
  - **Et rent sample kræver mørke LÆNGE nok** (`open_plan_lys_rent.delay_on` =
    6 min) **mens enforceren tænder igen efter 27 s** → dagslys-probens 45-min
    cooldown er BÆRENDE: fjern den, og open-plannet flimrer hvert 5. minut.
  - **Kanalen er ubrugelig i sekunderne omkring vores EGET skift** (målt
    125,6 → 47,6 → 124,8 på fire sekunder, fordi fradraget ikke følger fade'en)
    → læs gaten FØR lys-handlingen og bær dommen med. **Og en lux-gates
    off→on-flanke er oftest vores EGEN sluk** (kædens lux_ok 10-16: 33/74
    < 60 s efter) → aldrig en re-arm på den.
  - Skal du alligevel fradrage: gang med den hvide kanals andel (`1 - sat/100`),
    skeln `off_with_transition`/`off_brightness`, fade-kurven er **kvadratisk**.
    **En slukket lampe har ingen farve** → bær den fra sidste tændte render
    (`this`) og brug kaldets egen transition; ellers tænd/sluk-løkke.
