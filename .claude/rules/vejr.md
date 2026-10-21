---
paths:
  - "packages/dmi_*.yaml"
  - "packages/dug_*.yaml"
  - "packages/weather_*.yaml"
  - "packages/regn_*.yaml"
  - "automations/rain_warning.yaml"
  - "*/sky_notifications.yaml"
  - "scripts/sky_notify.py"
  - "scripts/plant_notify.py"
  - "packages/plant_notifications.yaml"
---

> *Danish. A path-scoped rule file: Claude Code loads it the first time a
> file matching `paths:` is read. See
> [docs/methodology.md](../../docs/methodology.md).*

# Vejr (DMI, met.no, REST)

Path-scopet fra CLAUDE.md (Permanente fakta) — loades når du læser en fil
der matcher `paths:`. Samme genkendelses-lag: regel, signatur, entity-navn.
Den lange version (måledata, incidents): `docs/permanente_fakta.md`
(`grep -n "<nøgleord>"`). Ændrer virkeligheden sig, ret BEGGE lag.

- **DMI lever på ÉN host, `opendataapi.dmi.dk`, med TO versioner:** prognose =
  `/v1/forecastedr`, observationer = `/v2/metObs` (begge **keyless**).
  Versionen hører til PRODUKTET. Legacy-hosten er DNS-nedlagt; NXDOMAIN giver
  `curl` HTTP 000 på ~1 ms, hvilket ligner en sandbox-blokade.
- **En REST-sensor med `this.state`-fallback bliver ALDRIG `unavailable` — den
  fryser på sidste værdi og lyver med fuld selvsikkerhed. Signatur:
  `last_changed` er timer gammel mens virkeligheden beviseligt har ændret sig.**
  Verificér på `last_attempt_ok` + `observed`, aldrig på state alene.
- **met.no's `cloud_coverage` er systematisk for HØJ om natten**, og bias'en
  rammer præcis udstrålings-nætterne → korrigér ved INPUTTET
  (`dug_metno_sky_bias_pct`), ikke i fysikken der forbruger tallet.
