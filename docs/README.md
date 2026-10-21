# docs/ — index

> *Written in Danish. English overview: [README](../README.md) ·
> [ARCHITECTURE](../ARCHITECTURE.md).*

| Fil | Formål |
|---|---|
| **[cross_cutting_map.md](cross_cutting_map.md)** ⭐ NEW (2026-05-08) | **"Hvor lever koncept X på tværs af filer?"** Single document mapping 15 cross-cutting concerns + ⚠️ flagger farlige steder (light_groups templated refs, godnat flag chain, kids_home v2, putning chain, etc.). LÆS HER FØR du editor cross-cutting kode. |
| **[architecture.md](architecture.md)** ⭐ | System-design overblik. Holy Grail-filosofi, room mode state machine, activity-state tree, mode-flag interactions, sensor-gate, scene-system. Læs FØRST hvis du vil forstå hvordan det hele hænger sammen. |
| **[state_machine.md](state_machine.md)** ⭐ | Mermaid-diagrams over state machines (house, mode-toggle, activity, godnat, mode-flag interactions, sensor flow, hardware stack). Visual reference til architecture.md. |
| **[hardware.md](hardware.md)** | Host-niveau hardware: Intel NUC, HAOS-version, Bluetooth + Zigbee + Thread coordinator. |
| **[hardware_shopping.md](hardware_shopping.md)** | Mangelliste — hvad skal købes / paret / dropped. Vedligeholdes af Claude. |
| **[zigbee.md](zigbee.md)** | Dual-radio setup: ZBT-2 (Zigbee) + ZBDongle-E (Thread). Mesh-fejl recovery decision tree. |
| **[apollo_calibration.md](apollo_calibration.md)** | Per-room Apollo MSR-2 radar gate thresholds. Re-calibration procedure. Diagnostic queries. |
| **[matter_pairing_playbook.md](matter_pairing_playbook.md)** | Step-by-step procedure for Matter-over-Thread commissioning. Magic-trick (mobile + NUC fallback). 4 devices commissioned 2026-05-05. |
| **[time_windows.md](time_windows.md)** | B5.3 standardiserede `binary_sensor.time_window_*` sensors (early_morning/day/evening/night/active_hours) + cross-check audit af eksisterende `condition: time` blocks. |
| **[mad_planlaegning.md](mad_planlaegning.md)** NEW (2026-07-29) | 🍽️ Mad-planlægning: daglige ret-afstemninger + samlet indkøbsliste hver N. ugedag. Ark-skema, Apps Script-opsætning (skriveadgang), formatet for den strukturerede ingrediens-kolonne + instruktionen Gemini skal følge. |
| **[konsolidering.md](konsolidering.md)** ⭐ NEW (2026-10-04) | 🧱 **Konsoliderings-indsatsen (B188):** commit-evidensen for hvilke løsninger der oftest går i stykker, de tre offline-beviser (`scripts/ha_offline.py` check/equiv/staging + refs) og den prioriterede plan P1-P9. **Læs §3 hvis du er den lokale session der skal verificere branchen.** |
| **[fejlklasser.md](fejlklasser.md)** ⭐ NEW (2026-08-15) | 🧠 **Den lange version af fejlklasse-listen** i CLAUDE.md: det konkrete incident, måledata og fuld begrundelse bag hver af de 24 klasser. CLAUDE.md bærer genkendelses-laget (signatur → metode) — læs denne når du genkender en signatur og vil vide præcis hvordan fejlen så ud. **Auto-loades ikke — `grep -n "#20"`.** |
| **[auto/](auto/)** | Auto-genereret af `scripts/gen_docs.py` — dependency_map.md + 12 per-room dossiers i rooms/. Re-genereret per sprint. |

⭐ = "skal kende"

---

## Når jeg vil...

| Spørgsmål | Læs |
|-----------|-----|
| Forstå hvordan systemet er bygget | [architecture.md](architecture.md) |
| Tune en magic-number værdi | [system_design.md](../system_design.md) (hvilken slider ejer den), så slider-kommentaren og `hq.py hist <entity> --stats` (CLAUDE.md 📏) |
| Lave hardware-køb | [hardware_shopping.md](hardware_shopping.md) |
| **Parre et Thread/Matter device (skudsikkert)** | [thread_pairing_drejebog.md](thread_pairing_drejebog.md) ⭐ — forberedelse, URL-bug-workaround, 3 veje |
| Recovery efter Zigbee-mesh fejler | [zigbee.md](zigbee.md) "Mesh-fejl recovery decision tree"-sektion |
| Forstå hvad et OPEN backlog-item handler om | [../CLAUDE.md](../CLAUDE.md) |
| Få fast-path navigation som AI | [../AGENTS.md](../AGENTS.md) |

---

## Doc-konventioner

- **Sprog:** Dansk i prosa, engelsk i kode/identifiers (matcher HA-konvention)
- **Format:** GitHub-flavored Markdown
- **Indhold der hører hjemme her:** alt der ikke er live HA-config (loaded af HA). Designdoks, runbooks, roadmaps, decision-rationale.
- **Indhold der IKKE hører hjemme her:** YAML-config der HA loader (skal i automations/, packages/, scripts.yaml, etc.). Per-fil-dokumentation hører i den relevante README.md (automations/README.md, packages/README.md).
