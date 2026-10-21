---
paths:
  - "packages/cykel_lader*.yaml"
  - "packages/energy_*.yaml"
  - "packages/elpris_*.yaml"
  - "packages/setup_cost.yaml"
  - "packages/robot_lade*.yaml"
  - "packages/luksus_besparelse.yaml"
  - "packages/lys_kpi.yaml"
  - "packages/*plug*.yaml"
  - "dashboards/forbrug.yaml"
---

> *Danish. A path-scoped rule file: Claude Code loads it the first time a
> file matching `paths:` is read. See
> [docs/methodology.md](../../docs/methodology.md).*

# Energi, plugs og elpris

Path-scopet fra CLAUDE.md (Permanente fakta) — loades når du læser en fil
der matcher `paths:`. Samme genkendelses-lag: regel, signatur, entity-navn.
Den lange version (måledata, incidents): `docs/permanente_fakta.md`
(`grep -n "<nøgleord>"`). Ændrer virkeligheden sig, ret BEGGE lag.

- **Effekt-plugs er delta-rapporterede**: et sample-hul betyder "uændret",
  aldrig "nul", og de hænger på sidste værdi ~15-20 s efter sluk.
- **De to cykelbatterier er ens, men LADERNE er ikke** (hans plateau er ~2,4×
  Parent B's) → effekt-niveauet på `sensor.entre_cykel_lader_effekt` fortæller
  HVIS batteri der sidder på den fælles plug. **Historik (fra 10-05): kun
  `sensor.cykel_lader_effekt_ren`** — den rå er ekskluderet fra recorderen.
- **Energi Data Service' `raw_today[].price` er allerede inkl. nettarif +
  afgifter** (ex moms) — læg aldrig tariffer til igen.
- **Højttaleren (AxiomAir N3) kører på KONSTANT strøm** (pluggen fjernet 10/10,
  B212 droppet) — batteriet holder kun ~1,5-1,8 t og niveauet kan IKKE aflæses
  (ingen fuel gauge på I2C, ingen power_supply). Forbrug målt ~10,6 W døgn-snit
  (≈ 93 kWh / ~180 kr om året) → `input_number.cost_hoejttaler_watt` i setup-kosten.
  Kører den på batteri og går offline, afgør LED'en (ingen = slukket, blå/rød
  blink = egen hotspot, grøn = hængt). SD-backup: `/share/axiomair_n3_backup/`.
