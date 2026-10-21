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
