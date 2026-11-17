# Health — trænings-, vægt- og kostprogram i Home Assistant

En side i Home Assistant med fem faner:

- **I dag:** vej dig, se dagens pas, og giv knæet en score en gang om ugen.
- **Træning:** dagens øvelser med billeder, *hvordan* og *hvorfor*. Du logger med + / − og Done.
- **Kost:** dagens kalorie- og proteinmål. Det justerer sig selv efter vægt-trenden. Under målet står måltiderne, og hvert måltid har knapperne Spist/Halvt.
- **Statistik:** vægtkurve mod den forventede kurve, knæ-score, træning pr. uge, styrke-fremgang, kropsmål og en ugentlig vurdering.
- **Historik:** spørgsmål du svarer på, kropsmål med målebånd og dine egne noter.

Telefonen giver dig påmindelser med knapper. Det gælder vejning (svar med tallet), dagens program, træning ("Klaret som anbefalet" / "Udsæt 1 time"), knæ-scoren søndag og målebåndet hver 4. uge.

Programmet er bygget til **vægttab med et knæ, der skal skånes**:

- Styrke 3 dage om ugen, aldrig to dage i træk. Ben-øvelserne er knævenlige: squat til en kasse, kort benpres, lavt step-up og rumænsk dødløft.
- Knæ-basis hver dag i ca. 12 minutter: lårspænd, benløft, hofte, vægsiddning og læg. Dertil en gåtur.
- Kondition uden stød: cykel, crosstrainer, bakke-gang og svømning. Lang gåtur i weekenden.
- Vægtene stiger af sig selv, når du når toppen af spændet. Bliver knæ-scoren højere, tager programmet automatisk en **skånsom uge**.

> ⚠️ **Ikke lægefagligt.** Har du en diagnose eller er opereret, så vis `helbred/program.yaml` til en fysioterapeut, før du starter. Hævet knæ, et knæ der låser eller svigter, eller smerte der bliver værre fra uge til uge betyder: stop og få det undersøgt.

---

## Uden Home Assistant

Vil du bare have programmet på papir, så udfyld `helbred/profil.yaml` og kør:

```bash
HELBRED_DIR=./helbred python3 scripts/helbred.py program > mit_program.md
```

Det kræver Python 3.11+ og `pyyaml`.

---

## Installation i Home Assistant

Du skal bruge Home Assistant OS eller Supervised og et add-on, der giver adgang til filerne, fx **File editor**, **Studio Code Server** eller **Samba**. Til trin 6 skal du også bruge **Terminal & SSH**.

### 1. Kopiér filerne til `/config`

| Fra pakken | Til |
|---|---|
| `scripts/helbred.py`, `scripts/oevelse_billeder.py` | `/config/scripts/` |
| `packages/helbred.yaml` | `/config/packages/` |
| `dashboards/helbred.yaml` | `/config/dashboards/` |
| `www/helbred-card.js` og mappen `www/oevelser/` | `/config/www/` |
| mappen `helbred/` | `/config/helbred/` |

### 2. `configuration.yaml`

Tilføj følgende. Har du allerede en `homeassistant:`, `lovelace:` eller `recorder:` sektion, så flet linjerne ind i den.

```yaml
homeassistant:
  packages: !include_dir_named packages

lovelace:
  dashboards:
    helbred-dash:                 # navnet bruges af pushene — behold det
      mode: yaml
      filename: dashboards/helbred.yaml
      title: Health
      icon: mdi:heart-pulse
      show_in_sidebar: true
      require_admin: true

recorder:
  exclude:
    entity_globs:
      - sensor.helbred_*          # helbredsdata skal ikke også ligge i HA's database
```

### 3. Kortet som ressource

Gå til **Indstillinger → Dashboards → ⋮ → Ressourcer → Tilføj ressource**. Udfyld:

- URL: `/local/helbred-card.js?v=1`
- Type: JavaScript-modul

Ændrer du senere i filen, så hæv tallet (`?v=2`).

### 4. Token

Gå til din profil (nederst i venstre side) → **Sikkerhed** → **Langtidsgyldige adgangstokens** → **Opret token**. Kopiér det, og gem det som eneste linje i en ny fil: `/config/helbred/.token`.

Del aldrig filen. Tokenet giver fuld adgang til dit Home Assistant.

Scriptet bruger tokenet til at sende push og læse kontakten "påmindelser".

### 5. Udfyld din profil

Åbn `/config/helbred/profil.yaml` og udfyld alt der står **UDFYLD**:

- fødselsår, højde, vægt i dag og målvægt
- startdato
- telefonens notify-navn: i HA-appen gå til **Udviklerværktøjer → Handlinger** og søg `notify.mobile_app_`

Ret gerne `fitness_dage`. Det er de dage, du træner i fitnesscenter. De andre dage viser siden hjemme-udgaven.

### 6. Tjek og genstart

I **Terminal**-add-on'et:

```bash
python3 /config/scripts/helbred.py tjek       # skal svare "ok"
```

Mangler yaml-modulet i terminalen, så kør `apk add py3-yaml` først. Home Assistant har det selv.

Genstart derefter Home Assistant. **Health** kommer frem i sidemenuen. Slå **Påmindelser på telefonen** til på *I dag*-fanen.

---

## Gør det til dit eget

Alle filerne i `/config/helbred/` er almindelig tekst. Ret dem frit, og kør `tjek` bagefter.

- **`program.yaml`:** øvelser, sæt, reps, startvægte, hvilke øvelser der hører til hvilket pas, og reglerne.
  - Startvægtene er sat lavt med vilje. Programmet bygger selv op.
  - Gør en øvelse ondt, så slet den fra passet, eller skift den ud med en fra listen.
  - Hver øvelse skal have et `hvorfor:`. Det er hele idéen, at man ved, hvorfor man gør det.
- **`kost.yaml`:** måltiderne er skrevet til ca. 2 100-2 200 kcal. Skriv dem om til det, du faktisk spiser, og behold kcal og protein nogenlunde.
  - Kalorie-målet regnes ud fra din vægt (`kcal: auto`).
  - Taber du dig for langsomt over 2 uger, går målet 150 kcal ned. Taber du dig for hurtigt, går det op.
- **`spoergsmaal.yaml`:** spørgsmålene på Historik-fanen. Svarene gemmes og vises nederst.
- **`historik.md`:** dine egne noter, fx diagnose, mål og hvad der er sket undervejs.

Dine logs ligger i `/config/helbred/log/*.jsonl`, én linje pr. registrering. Tag dem med i din backup.

Billederne er fra [free-exercise-db](https://github.com/yuhonas/free-exercise-db) (Unlicense). Se `www/oevelser/KILDE.md`.
