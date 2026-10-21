---
paths:
  - "scripts/**/*.py"
  - "scripts/*.sh"
  - "packages/*notifications*.yaml"
---

> *Danish. A path-scoped rule file: Claude Code loads it the first time a
> file matching `paths:` is read. See
> [docs/methodology.md](../../docs/methodology.md).*

# Scripts, REST og recorder

Path-scopet fra CLAUDE.md (Permanente fakta) — loades når du læser en fil
der matcher `paths:`. Samme genkendelses-lag: regel, signatur, entity-navn.
Den lange version (måledata, incidents): `docs/permanente_fakta.md`
(`grep -n "<nøgleord>"`). Ændrer virkeligheden sig, ret BEGGE lag.

- **Recorderens `context_user_id` er TOM** — brugeren står i
  **`context_user_id_bin`** → `*_bin` + `hex()`, ellers ligner hvert fingertryk
  en automation.
- **"Blev B forårsaget af A?" besvares af `parent_id`, ALDRIG af `context.id`**
  (ULID med millisekund-prefix: afkortede ID'er matcher altid falsk, fulde
  aldrig). **Signatur:** et replay der siger "din nye regel gør ingenting".
- **`/api/template` bruger den fulde HA-template-env** → gyldigt orakel for
  "findes dette filter?".
- **`/api/history/period/{start}` defaulter `end_time` til start + 1 DØGN** —
  længere forespørgsler trunkeres TAVST uden `&end_time=`.
- **En entity der KUN skabes af `POST /api/states` er FRAVÆRENDE efter hver
  genstart** — ikke `unavailable`, men ikke-eksisterende (`states[x]` er `none`,
  dashboardet siger "entity not found"). → stil en YAML-defineret template-sensor
  som facade foran den (`sensor.koekken_stemme_sidst`) og whitelist den i
  `scripts/ha_validate_whitelist.txt`.
- **HA Core's shell_command-subproces HAR en `SUPERVISOR_TOKEN`, men supervisor-
  proxyen afviser den (401) for `/core/api`** — kun add-ons med homeassistant_api må.
  **Signatur:** et script der virker fra SSH-add-on'et men aldrig leverer fra en
  automation, og som er startet `--detach` (stderr i /dev/null = tavs død). → brug
  `ha_api_token` via `scripts/ha_secrets.py` + `127.0.0.1:8123` (som plant_notify/
  notif_queue/sky_notify) og log `--detach`-børn til fil. Fanget i `apollo_kalib_capture.py` (B182).
- **Scripts læser secrets.yaml KUN via `scripts/ha_secrets.py`** — en ny nøgle skal stå i
  `secrets.example.yaml`, ellers afviser `scripts/secrets_contract.py` committen.
