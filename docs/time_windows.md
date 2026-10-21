# Time-Window Mapping Audit (A21 sprint 2026-05-06)

> *Written in Danish. English overview: [README](../README.md) ·
> [ARCHITECTURE](../ARCHITECTURE.md).*

Standardiserede time-windows defineret i `packages/constants.yaml`:

| Window | Range | Use case |
|---|---|---|
| `time_window_night` | 23:00 - 05:00 | Deep-sleep, kun nightwalk + kalde |
| `time_window_early_morning` | 05:00 - 09:00 | Wakeup-flow, godnat-clear, kids op |
| `time_window_day` | 09:00 - 21:00 | Presence_lights normal |
| `time_window_evening` | 21:00 - 23:00 | Winddown, dim-down |
| `time_window_active_hours` | 05:00 - 23:00 | Bredt vindue (= early_morning + day + evening) |

## Cross-check: existing `condition: time` blocks

| File:line | Current threshold | Maps cleanly to | Status |
|---|---|---|---|
| `entre_motion.yaml:46` | after 06:00 before 23:00 | `active_hours` (05-23) | ✅ MIGRATED A20 — 1h tidligere åbning OK |
| `entre_motion.yaml:143-144` | after 23:00 before 06:00 | `night` (23-05) | Kunne migrere — 1h tidligere lukning |
| `presence_sovevaerelse.yaml:39` | after 06:00 | `active_hours` | ⏳ Kan migreres — 1h tidligere |
| `presence_boernevaerelse.yaml:53` | after 06:00 | `active_hours` | ⏳ Kan migreres — 1h tidligere |
| `presence_lights.yaml:190, 233` | after 06:00 | `active_hours` | ⏳ Kan migreres |
| `godmorgen_godnat.yaml:505` | after 06:00 | `active_hours` | ⏳ Kan migreres |
| `godmorgen_godnat.yaml:661-662` | after 06:00 before 09:00 | `early_morning` (05-09) | ⚠️ 1h tidligere åbning — verify intent |
| `godnat_subflag_safety.yaml:137-138` | after 06:00 before 12:00 | Ingen clean match | ❌ Brug eksisterende time-block |
| `wakeup_post_sluk.yaml:53-54` | after 04:00 before 12:00 | Ingen clean match | ❌ Brug eksisterende time-block |
| `wakeup_alarm_driven.yaml:57-58` | after 04:00 before 10:00 | Ingen clean match | ❌ Brug eksisterende time-block |
| `activity_aware.yaml:105-106` | after 21:00 before 07:00 | Approximerer `evening + night + early_morning` | ❌ Brug eksisterende |
| `godnat_auto_declare.yaml:65-66` | after 21:00 before 07:00 | Approximerer | ❌ Brug eksisterende |
| `summer_defense.yaml:43-44` | after 09:00 before 20:00 | `day` slut 21:00 — 1h forskel | ⏳ Kan migreres med 1h justering |
| `battery_alerts.yaml:44-45` | after 07:00 before 19:00 | Ingen clean match | ❌ Brug eksisterende |
| `entre_motion.yaml night-mode` | after 23:00 before 06:00 | `night` (23-05) | ⏳ 1h forskel for åbning |

## Migration strategi

**Migrer hvis:**
- Threshold matcher en time_window EKSAKT (eller 5-9, 9-21, 21-23, 23-5)
- 1h forskel kan accepteres som UX-forbedring
- Automation bruges af mange scenarios → konsistens vigtig

**Behold `condition: time` hvis:**
- Threshold er specifik til automation's domæne (eg. battery alerts 07-19 = quiet hours)
- Threshold ville kræve > 1h justering
- Automation er one-off med ikke-aspirational threshold

## Anbefaling

**Næste sprint:** Migrer 4-6 automations til time_window (lav-risk, høj konsistens):
- presence_sovevaerelse, presence_boernevaerelse, presence_lights → `active_hours`
- godmorgen_godnat:505 → `active_hours`
- godmorgen_godnat:661-662 → `early_morning` (verify intent)

**Behold som er:**
- battery_alerts (quiet hours = domain-specific)
- wakeup_* (lange windows = catch edge cases)
- godnat_subflag_safety (06-12 fanger morning specifik)
- activity_aware bedroom_only (21-07 = whole-night specifik)
- godnat_auto_declare (21-07 = same)


---

## ⏰ Morning Timeline — orden af tidstriggers (B5.1)

Flyttet hertil fra CLAUDE.md 2026-08-15 (auto-load-budget). Tabellen er
hånd-kurateret og kan drifte — verificér mod `automations/` ved tvivl.

Conditions guarder mod race-conditions, men hvis fejl observeres i morgenrutine
tjek denne timeline. Per audit-runde 16: vi accepterer denne cluster — har
ikke set faktisk failure pre-flyt. Post-flyt + Apollo: monitor.

| Tid | Automation | Hvad | Conditions blocker hvis |
|---|---|---|---|
| 02:00 | backup_schedule | hassio.backup_full | (ingen) |
| 05:55 | vakning_voksne_kl_05_55_hverdage | Sove dim 5%→40%→80% over ~8 min | weekend, ikke arbejdsdag, AirBnB mode, godnat_active=off |
| 06:00 | godnat_auto_clear (time-trigger) | Clear godnat flags + open curtains | godnat_active=off, ingen presence |
| 06:00 | (presence_lights conditions) | Various — `after 06:00` gates | n/a |
| 06:05 | vakning_pigerne_kl_06_00_hverdage | Boern dim 5%→30%→50%→70% over 15 min | weekend, ikke arbejdsdag, AirBnB |
| 07:00 | activity_aware bedroom_winddown_clear | Clear bedroom_only_winddown flag | flag=off |
| 07:30 | vakning_pigerne_weekend_ferie | Soft sunrise boern på weekend | hverdag, AirBnB |
| 09:00 | godnat_subflag_safety | Auto-clear stuck godnat sub-flags | ingen sub-flag stuck |
| 09:00 | godmorgen_weekend_sovevaerelse_gardin | Open sove gardin (sleep-in protection) | hverdag, ikke Active |

**Race-vinduer (lav risiko):**
- 05:55 vakning_voksne (Phase 1) overlapper 06:00 godnat_auto_clear → wakeup clearer flags først, godnat_auto_clear no-op'er.
- 09:00 har 2 fires same minute — uafhængige, ingen reel konflikt.

**Hvad skal monitoreres efter post-flyt + Apollo parring:**
- Stue-light tilstand kl 06:00 efter wakeup_voksne — burde være ON (presence) eller dimmed
- Boern wakeup forløb — observer Phase 1→2→3→4 over ~15 min uden afbrydelse
- godnat-flags status kl 09:01 — alle 3 sub-flags burde være OFF
