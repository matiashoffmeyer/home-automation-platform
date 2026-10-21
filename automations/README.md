# automations/ — index

> *Written in Danish. English overview: [README](../README.md) ·
> [ARCHITECTURE](../ARCHITECTURE.md).*

Hver fil er et tematisk bundt af automations. Loaded af HA via `automation: !include_dir_merge_list automations/` i [configuration.yaml](../configuration.yaml).

**Last reviewed: 2026-05-08** efter sprint sequence (kids_home v2 + putning auto-detect + global tuning sliders + morning sanity-check + kalde sove blink).

**📋 For cross-cutting concerns + "hvor lever X" map:** se [docs/cross_cutting_map.md](../docs/cross_cutting_map.md).

---

## Lys-styring (presence-drevet)

Phase 2.2 (2026-05-05) splittede `presence_lights.yaml` til per-rum filer:

| Fil | Beskrivelse | Antal |
|---|---|---|
| **[presence_stue.yaml](presence_stue.yaml)** ⭐ | Open-plan stue tænd (lux<40, godnat-aware). 20 min absence-fade. | 2 |
| **[presence_koekken.yaml](presence_koekken.yaml)** ⭐ | Open-plan koekken tænd (følger stue/spisestue Apollo). 20 min fade. | 2 |
| **[presence_sovevaerelse.yaml](presence_sovevaerelse.yaml)** ⭐ | Sove tænd via radar still_target. 5 min absence-fade. Auto dim 35/22/12% per LUX-bracket. | 2 |
| **[presence_boernevaerelse.yaml](presence_boernevaerelse.yaml)** ⭐ | Boern tænd: før sengetid (lux-adaptive varm hvid), efter sengetid med børn hjemme puttelys-udseendet (fase 1 uden flag). | 2 |
| **[presence_badevaerelse.yaml](presence_badevaerelse.yaml)** ⭐ | Bath tænd. Sun-aware brightness. 30s/90s godnat timeout. | 2 |
| **[presence_lights.yaml](presence_lights.yaml)** | Reactive LUX automations (cross-room) + scene-restore. (Per-rum lys flyttet til filer ovenfor; boern aftendaempning pensioneret 2026-06-12/B20.) | 7 |
| **[entre_motion.yaml](entre_motion.yaml)** | Entré Vallhorn motion → bright lys (lampeskaerm-bumped 100/85/65/50%) + nat-mode 23-06h dim warm. | 3 |
| **[depot_harry_potter.yaml](depot_harry_potter.yaml)** | Depot Vallhorn → varm 2000K Harry Potter-glow. Pre-flyt: depot Vallhorn ikke paret. | 2 |
| **[terrace_presence.yaml](terrace_presence.yaml)** | Altandør åben → terrasse welcome lys + dim indendørs. | 4 |
| **[light_power_recovery.yaml](light_power_recovery.yaml)** | Innr-bulb mesh-flicker → fade til target (LUX/sun/godnat-aware). 4 brightness-trigger ranges. | 2 |
| **[bulb_firmware_defaults.yaml](bulb_firmware_defaults.yaml)** | Adaptive NVRAM updates per sun-bracket + godnat. 8 paerede bulbs (bath, sove, boern + 5 Tradfri WW). Skip-unavailable A2 fix. | 1 |

## Knap-styring

| Fil | Beskrivelse | Antal |
|---|---|---|
| **[styrbar_rooms.yaml](styrbar_rooms.yaml)** ⭐ | Universal Styrbar-handler: 1 instant-actions + 1 hue-scroll + 5 per-rum lr_grace. Dækker alle 5 paerede Styrbars via IEEE→rum mapping. | 7 |
| **[somrig_buttons.yaml](somrig_buttons.yaml)** | RODRET remotes (4 stk): sove + stue-smart + stue-syd = gardin op/ned/stop; **boern = 🎬 Dark Mode toggle** (2026-07-27, mørklægning i packages/dark_mode.yaml). | 16 |
| **[entre_somrig.yaml](entre_somrig.yaml)** | RODRET entré exit/enter (top=welcome lux+godnat-aware, bund=vi-gaar). | 5 |
| **[styrbar_battery_refresh.yaml](styrbar_battery_refresh.yaml)** | F1 fix sprint 1: ZCL ReadAttribute pulls battery på alle 5 Styrbars + Somrig ved HA start + 08:55 + 18:55 daily. | 1 |

## Mode-flow (godnat / godmorgen / wakeup / putning)

Modular godnat-state-machine med union sensor `binary_sensor.godnat_any_active`
(sprint 2026-05-05). Use union, ikke kun master flag.

**🔗 Single-source-of-truth pattern (sprint 2026-05-08):** ALLE entry-points
sætter blot `godnat_boern_active=on`. Cascading actions (slukke + gardin) sker
via `automation.godnat_boern_active_on_actions` i godnat_night.yaml. Se
[docs/cross_cutting_map.md](../docs/cross_cutting_map.md) #6 for full chain.

| Fil | Beskrivelse | Antal |
|---|---|---|
| **[godmorgen_godnat.yaml](godmorgen_godnat.yaml)** ⭐ | Sove Somrig: kort-ned=voksen-godnat, kort-op=godmorgen. Plus auto-detect, godnat_full_activate, weekend gardin, kids morning. | 8 |
| **[godnat_night.yaml](godnat_night.yaml)** ⭐ | Kalde-knap kort-OP (kalde event: stue/koekken steady red 8% + sove BLINK red 8% i 30s, sprint 2026-05-08) + kalde kort-NED (start putning) + voksen nat-tur. **NEW: godnat_boern_active_on_actions** (single source of truth for slukke + gardin). | 7 |
| **[putning_auto_detect.yaml](putning_auto_detect.yaml)** ⭐ NEW (2026-05-07/08) | 2 triggers (bath visit ≥3min OR boern still_target ≥10min). Sets godnat_boern_active=on. Cascades til godnat_boern_active_on_actions. Gated på kids_home + auto_putning_enabled + tidsvinduer 18:30-20:30 / 19:30-21:00. | 2 |
| **[boern_ankomst_detekter.yaml](boern_ankomst_detekter.yaml)** ⭐ NEW (2026-07-30) | Ankomst = 4. auto-signal i `binary_sensor.kids_home` (de tre andre kræver at børnene har været her i timevis). Sammenhængende børneværelses-ophold ≥ slider (12 min, kalibreret mod 14 dage: voksen-dage maks 7,0 min) → `boern_aktivitet_detekteret` + bekræftelses-push; ro ≥ 120 min → selv-rydning; "❌ Nej" rydder + pauser 6 t. Begge tilstands-automations har /15-backstop. | 3 |
| **[godnat_subflag_safety.yaml](godnat_subflag_safety.yaml)** | Safety-clear stuck sub-flags (09:00 daily + 2h-after-master-off + HA start). A19 weekend early-clear (sove tom + lux>30). | 2 |
| **[godnat_auto_declare.yaml](godnat_auto_declare.yaml)** | Auto-declare godnat efter 2t kun sove-presence efter 21:00. | 1 |
| **[wakeup_alarm_driven.yaml](wakeup_alarm_driven.yaml)** | Sunrise-style ramp 30 min før phone-alarm (sensor.phone_a_next_alarm = Parent A). 5%→40%→80% over 30 min. ⚠️ Kun Parent A's phone — Parent B har ingen equivalent (backlog F2/B17). | 1 |
| **[wakeup_post_sluk.yaml](wakeup_post_sluk.yaml)** | F5 (B13) fix: 15 min efter wakeup → smart LUX-aware fade off (lux>15) eller dim-down (lux<15). A6+A7+A11+A12 hardening. | 1 |
| **[wakeup_adults.yaml](wakeup_adults.yaml)** | LEGACY 05:55 hverdage (DISABLED — replaced af wakeup_alarm_driven). Beholdt som re-enable fallback. | 1 |
| **[wakeup_kids.yaml](wakeup_kids.yaml)** | 06:05 hverdage + 07:30 weekend gradvis fade børneværelse. **STRENGT GATED (sprint 2026-05-08):** kids_home=on + boern overnight motion + godnat_boern_active=off. | 2 |
| **[morning_lights_sanity_check.yaml](morning_lights_sanity_check.yaml)** ⭐ NEW (2026-05-08) | Auto-off boern (06-12) + sove (07-12) hvis (lux>50 i 5min) ELLER (occupancy off i 10min). Skip-betingelser: cinema/cirkus/godnat_any_active. | 2 |
| **[init_user_preferences.yaml](init_user_preferences.yaml)** ⭐ NEW (2026-05-07) | HA start fresh-install protection: sets defaults for tunable input_numbers HVIS værdi er på min + last_changed <60s. 13 helpers initialiseret. | 1 |
| **[legetoejsdag.yaml](legetoejsdag.yaml)** NEW (2026-06-12) | Første ikke-lukkedags-fredag i måneden: 10 sek diskolys (stue+spisestue+køkken+bad) ~10s efter morgen-vejrvarslerne = "Child A skal ha legetøj med". Arbejdsdag + lukkedags-liste (grundlovsdag m.fl.) + måneds-markør. | 1 |

## Aktivitets-bevidst (intelligent gating)

| Fil | Beskrivelse | Antal |
|---|---|---|
| **[activity_aware.yaml](activity_aware.yaml)** ⭐ | Auto-set guest_mode ved social activity 30 min (10 for party). Bedroom-only winddown. Terrasse-only winddown. M3+A5 fixes for godnat_any_active gating. | 7 |
| **[room_drift_back.yaml](room_drift_back.yaml)** ⭐ | State-triggered drift Manual → Auto. Sensor off+for=20min trigger drifter ALTID ved tomt rum (uanset tændt lys, 2026-07-25) + 15-min backup-tick for occupied-fallback (room_manual_on_hold_hours; sove/bad egne tider) + 24h backstop. only_on re-apply. | 1 |
| **[manual_override.yaml](manual_override.yaml)** ⭐ NEW (2026-06-10) | App-justeringer (context.user_id) på rum-lys → Manual mode + last_press stamp, så auto-tænd blokeres og 3h-hold gælder (spejler Styrbar-adfærd). | 1 |
| **[mood_flag_safety.yaml](mood_flag_safety.yaml)** | Auto-clear cinema_active/cirkus_active hvis stuck >4h + stue tom 30 min. | 2 |

## Modes / states

| Fil | Beskrivelse | Antal |
|---|---|---|
| **[dormant_schedule.yaml](dormant_schedule.yaml)** ⭐ NEW (2026-06-10) | Skema-drevet Dormant: hverdage kl 09:30 (veto: aktivitet 08:45-09:30) + weekend 60-min "stearinlys"-counter 09:31-15:00. Occupancy-on veto i begge. | 2 |
| **[airbnb_mode.yaml](airbnb_mode.yaml)** ⭐ | house_mode → AirBnB lockdown: disable 30+ automations, force-clear flags, privacy-purge 14-day history (15+ entity_globs incl. scenes/kalde/styrbar pattern). Resume reactivate alle ved skift tilbage Normal. | 6 |
| **[arrival.yaml](arrival.yaml)** | Hoveddør åben → entré + welcome lys. A22: godnat-aware dim mode (entre 8% / stue 12% / sove+boern dark). | 2 |

## Klima / sikkerhed

| Fil | Beskrivelse | Antal |
|---|---|---|
| **[climate_control.yaml](climate_control.yaml)** | Bath humidity high-warning, post-shower reminder, kids-room cold, lejlighed varm. Mute'd i guest_mode + bath_visit + nat. | 4 |
| **[security.yaml](security.yaml)** | Hoveddør/altandør glemt åben, dor-åbnet under Dormant. | 4 |
| **[water_leak_alarm.yaml](water_leak_alarm.yaml)** | Badring water leak → rødt blink + persistent + mobile push. Auto-clear ved sensor reset. | 2 |
| **[summer_defense.yaml](summer_defense.yaml)** | Sommer Dormant + varmt → per-room close (B6.3: stue, boern bruger egen lux-sensor). | 1 |
| **[winter_defense.yaml](winter_defense.yaml)** | Vinter Dormant → per-room close. Solar-gain åben syd-gardin på solskin <20°C. Cold-snap force-luk under -2°C. | 4 |

## System / vedligehold

| Fil | Beskrivelse | Antal |
|---|---|---|
| **[backup_schedule.yaml](backup_schedule.yaml)** | Daglig backup.create_automatic kl 02:00 (F4 fix: modern API, opdaterer sensors). Retention 7 dage via UI config. | 1 |
| **[battery_alerts.yaml](battery_alerts.yaml)** | <15% warning + <5% kritisk for alle Styrbar/Somrig/Vallhorn/Badring batterier. Mute'd i guest_mode + nat. | 2 |
| **[device_health_check.yaml](device_health_check.yaml)** | HA start + dagligt 09:00 → tjek alle kendte entities er available. Notification ved degradation. | 1 |
| **[zha_auto_config.yaml](zha_auto_config.yaml)** | Ved device-pair: anvend model-specifikke defaults via script.<model>_defaults. | 1 |
| **[styrbar_battery_refresh.yaml](styrbar_battery_refresh.yaml)** | F1 fix sprint 1: ZCL ReadAttribute pulls battery på alle 5 Styrbars + Somrig ved HA start + 08:55 + 18:55 daily. | 2 |
| **[mad_planlaegning.yaml](mad_planlaegning.yaml)** NEW (2026-07-29) | 🍽️ Mad: dagens ret-spørgsmål til begge telefoner + indkøbsliste hver N. ugedag + stemme-handler (`mobile_app_notification_action`, person kodet i action-id) + sensor-refresh ved HA-start/slider-ændring. Se [docs/mad_planlaegning.md](../docs/mad_planlaegning.md). | 4 |

---

## ⭐ = "skal kende" — gå hertil først ved spørgsmål

- **presence_<room>.yaml** (5 filer) = per-rum lys-tænd-logik
- **styrbar_rooms.yaml** = universal knap-håndtering
- **godmorgen_godnat.yaml** = sove Somrig + auto-detect + commit-flow
- **activity_aware.yaml** = intelligent gating
- **airbnb_mode.yaml** = lockdown + privacy-purge

---

## Critical gotchas (sprint-learned)

- **`godnat_any_active` (sprint 2026-05-06)**: Brug union sensor for godnat-aware
  gating. Master `godnat_active` sættes KUN ON når BÅDE voksne+boern aktive.
  Voksen-only godnat (somrig kort-ned) → kun voksne_active=on, master OFF.
  Conditions der gateder på master flag MISSEDE voksen-only godnat indtil A1+A4+A5+A8+A9 fix.
- **State-triggers `to: off for: 5min`**: kræver state TRANSITION on→off. Hvis
  state allerede var off pre-trigger, automation FYRER ALDRIG. A27 fix tilfojede
  `time_pattern` fallback til godnat_adult_nightwalk_off for arrival-orphan-bug.
- **Apollo lux dependency**: B12 stue Apollo's LTR390 chip defekt. Brug
  `sensor.open_plan_lux` (template m/ fallback chain). Hver per-room lux check
  bør have `unavailable` fallback (jf A26 fix).
- **AirBnB lockdown completeness**: vokser ikke automatisk. Hver ny family-
  automation skal eksplicit registreres i lockdown + resume lists.

## Trigger-typer

Mange automations bruger forskellige trigger-platforme. Quick reference:

- **`platform: state`** — fyrer ved entity state-ændring (kræver TRANSITION!)
- **`platform: event`** med `event_type: zha_event` — fyrer ved Zigbee-knap-tryk
- **`platform: time`** — fyrer på specifik klokkeslæt
- **`platform: time_pattern`** — fyrer periodisk (state-history-uafhængig)
- **`platform: numeric_state`** — fyrer ved numerisk værdi-tærskel (lux, temp)
- **`platform: homeassistant`** med `event: start` — fyrer ved HA boot
- **`platform: template`** — fyrer ved boolean template-evaluering

---

## Gates der ofte ses

```yaml
# Master gate (skip pre-flyt + sensor-failure)
- condition: state
  entity_id: binary_sensor.presence_sensors_available
  state: "on"

# Godnat gate — USE UNION SENSOR (sprint 2026-05-06)
- condition: state
  entity_id: binary_sensor.godnat_any_active
  state: "off"  # eller "on" for godnat-only automations

# Mood-mode skal være OFF
- condition: state
  entity_id: input_boolean.cinema_active
  state: "off"
- condition: state
  entity_id: input_boolean.cirkus_active
  state: "off"

# House aktiv
- condition: state
  entity_id: input_select.house_state
  state: "Active"

# Time-window (B5.3 — bruger time_window_* template_sensors fra constants.yaml)
- condition: state
  entity_id: binary_sensor.time_window_active_hours
  state: "on"  # 05-23
```
