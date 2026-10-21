---
paths:
  - "scripts/nemlig*"
  - "packages/nemlig*.yaml"
  - "*/mad_planlaegning.yaml"
  - "scripts/mad_planner.py"
  - "dashboards/mad.yaml"
  - "docs/nemlig_kurv.md"
  - "docs/mad_*.md"
---

> *Danish. A path-scoped rule file: Claude Code loads it the first time a
> file matching `paths:` is read. See
> [docs/methodology.md](../../docs/methodology.md).*

# Nemlig og madplan

Path-scopet fra CLAUDE.md (Permanente fakta) — loades når du læser en fil
der matcher `paths:`. Samme genkendelses-lag: regel, signatur, entity-navn.
Den lange version (måledata, incidents): `docs/permanente_fakta.md`
(`grep -n "<nøgleord>"`). Ændrer virkeligheden sig, ret BEGGE lag.

- **Nemligs søgning er IKKE ascii-foldende** — det der SENDES skal staves med
  danske bogstaver. **Signatur: et helt almindeligt ord finder kun sodavand.**
- **Nemligs søgesvar har et 3-niveau VARETRÆ, og bladet (`ProductSubGroupName`)
  ER varearten**; `Favorite` = "købt før" (dækker næsten alle varianter), og en
  multipak prissættes PR. STYK. → `nemlig_api.taksonomi()`; mål enhver
  matcher-ændring med `nemlig_selftest.py --offline --diff` + en audit af VALGENE.
