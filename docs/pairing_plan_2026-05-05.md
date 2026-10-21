# Pairing Slagplan — 2026-05-05 @ FRB

> *Written in Danish. English overview: [README](../README.md) ·
> [ARCHITECTURE](../ARCHITECTURE.md).*

13 nye Zigbee/WiFi devices skal pares + integreres. Estimeret tid: 2-3 timer
fokuseret arbejde.

## Hardware oversigt

| Type | Antal | Teknologi | Pre-flyt rolle |
|---|---|---|---|
| **Tradfri E27 hvid dimmable** | 5 | Zigbee | Standby — pair only, ingen room-assign endnu |
| **Vallhorn motion** | 1 ny + 1 paret (depot) | Zigbee | Ny → entré (`binary_sensor.entre_valhorn_occupancy`) |
| **Apollo MSR-2 multi-sensor** | 5 | WiFi/ESPHome | sove + boern + stue + spisestue + bad |
| **IKEA Somrig dual-button** | 5 | Zigbee | 3 gardin (sove/stue/boern) + 1 entré super-remote + 1 kalde-knap |

**Allerede paret (skipper):**
- Sove Somrig: IEEE `b3:47:dd:fa:8c:68:31:05` (godnat-knap)
- Bath bulb: color (badevaerelse_loft)
- Sove bulb: color (sovevaerelse_loft)
- Sove Styrbar, bath Styrbar
- Terrasse_lyskaede (RGB-strip), terrasse_paerelyskaede (warm-white pearl-chain)
- Depot Vallhorn (`binary_sensor.depot_valhorn_occupancy`)

---

## Phase 0: Pre-arrival prep (Claude før user kommer)

- [ ] **Backup current /config** — safety net før mass changes
  ```bash
  ssh ha "ha backups new --name 'pre-pairing-2026-05-05'"
  ```
- [ ] **Verify ZBT-2 alive** + paret count baseline
  ```bash
  ssh ha "python3 -c '...zha/devices count...'"
  ```
- [ ] **Tjek ZHA pair-mode tilgængeligt**
- [ ] **Snapshot kendte IEEE** så vi ser nye

## Phase 1: Bulbs (5 Tradfri hvid) — ~20 min

### Per bulb (gentag 5x):

1. **Setup**: Skru bulb i en tilfældig socket der har strøm. Kan også bruge en testlampe.
2. **Sæt i pair mode**: 6× hurtige tænd/sluk på væg-switch (1 sek mellem hver). Bulb begynder at fade.
3. **HA Settings → Devices → ZHA → Add Device → Search**
4. **Vent 30-60 sek** til ZHA detekterer
5. **Note IEEE** (Claude logger)
6. **Rename** device i HA UI til `tradfri_white_<n>` (1-5)
7. **Test**: Toggle on/off via Developer Tools → Services → light.toggle

### Efter alle 5:

- [ ] **Update `packages/light_groups.yaml`**: tilføj 5 entities til relevant placeholder gruppe (eller midlertidig "standby_lights")
- [ ] **Skip bulb_firmware_defaults_dispatcher** — disse er warm-white-only (ingen CT-cluster, ingen RGB-cluster). Kun start_up_current_level (cluster 8) er relevant.
- [ ] **Optional**: Run `script.tradfri_white_bulb_defaults` (ny script — TBD om vi skal lave en)
- [ ] **Verify**: 5 nye `light.tradfri_white_*` entities synlige + responsive

## Phase 2: Somrigs (5) — ~30 min

### Pair-procedure per Somrig:

1. **HA Settings → Devices → ZHA → Add Device**
2. **Pair-tryk på Somrig**: hold begge knapper (top+bund) samtidig i 10 sek til LED blinker hvidt. Slip.
3. **Vent på detect** (30-60 sek)
4. **Note IEEE**
5. **Rename** per rolle:
   - Curtain sove → `somrig_sove_curtain`
   - Curtain stue → `somrig_stue_curtain`
   - Curtain boern → `somrig_boern_curtain`
   - Entré super-remote → `somrig_entre`
   - Kalde-knap → `somrig_kalde`
6. **Test events**: monitor zha_event for IEEE → press alle knapper (top/bund × short/long)

### Pair rækkefølge (anbefalet):

1. Entré super-remote (mest kompleks — 4 actions)
2. Kalde-knap (1 action — kalde_on)
3. Curtain sove
4. Curtain stue
5. Curtain boern

### Efter alle 5:

- [ ] **Update `automations/entre_somrig.yaml`**: replace IEEE `00:00:00:00:00:00:00:00` (3 steder: top quick, top long, bund quick, bund long, undo grace) med ny IEEE
- [ ] **Update `automations/somrig_buttons.yaml`**: replace `PLACEHOLDER_SOMRIG_SOVEVAERELSE`, `PLACEHOLDER_SOMRIG_STUE`, `PLACEHOLDER_SOMRIG_BOERNEVAERELSE` med faktiske IEEE
- [ ] **Update `automations/godnat_night.yaml`**: replace IEEE for kalde-knap (somrig_7)
- [ ] **Update `automations/godmorgen_godnat.yaml`**: tilføj somrig_4 IEEE (boern bedtime button — hvis vi VIL have boern-godnat. NB: ikke i scope tomorrow per user-spec, så skip)
- [ ] **Update `entities/device_inventory.yaml`** med alle 5 IEEE
- [ ] **Reload automations** + verify hver Somrig fyrer korrekt automation via event monitor

## Phase 3: Vallhorn (1 ny) — ~5 min

1. **HA Settings → Devices → ZHA → Add Device**
2. **Pair-tryk på Vallhorn**: hold reset-knap i 10 sek til LED blinker
3. **Note IEEE**
4. **Rename**: `entre_valhorn` → entity bliver `binary_sensor.entre_valhorn_occupancy`
5. **Verify**: walk past sensor, se occupancy state flip on/off

### Efter pair:

- [ ] **Update `entities/device_inventory.yaml`** med IEEE
- [ ] **Verify entity_id** matcher `binary_sensor.entre_valhorn_occupancy` (used by airbnb_dormant_to_active_entre, godnat_voksen_start wait_template, godnat_auto_declare, m.fl.)

## Phase 4: Apollo MSR-2 (5) — ~30-60 min

**Apollo er ESPHome WiFi, IKKE Zigbee!**

### Per Apollo (gentag 5x):

1. **Strøm**: USB-C kabel til hver Apollo
2. **Første gang setup** (kun hvis ikke pre-flashed):
   - Apollo skaber midlertidigt WiFi access point `apollo-msr-2-XXXXXX`
   - Connect din phone til det AP
   - Browse til `http://192.168.4.1` → indtast home WiFi credentials
   - Apollo reboot, joiner home WiFi
3. **HA auto-discovery** via mDNS — ESPHome integration popper en notification
4. **Click "Configure" i HA → indtast API-key** (typisk auto-detected, kan også blank)
5. **Rename device** per rum:
   - `apollo-msr-2-XXXXXX` → `sovevaerelse_apollo` etc.
   - 5 rum: sove, boern, stue, spisestue, bad
6. **Verify entities**: brightness, motion, mmwave, lux, temp, humidity (~30 entities per Apollo)

### Pre-flyt limitation:

Apollo entities heter `binary_sensor.<rum>_apollo_occupancy`. Code bruger DENNE convention. Verify renaming matcher.

### Efter alle 5 paret:

- [ ] **Verify presence_sensors_available = on** (template_sensor checker hvis ALLE Apollo+Vallhorn responder)
- [ ] **Test occupancy detection** ved at gå ind i hvert rum, se entity flip
- [ ] **Verify lux readings** (hvis Apollo i rum med vindue)
- [ ] **Update `packages/recorder.yaml`** (configuration.yaml exclude filter) — tjek at noisy entities filtreres

## Phase 5: Codebase updates — ~30 min

Mange filer skal opdateres med nye IEEE:

- [ ] `entities/device_inventory.yaml` — alle 13 nye devices
- [ ] `automations/entre_somrig.yaml` — entré Somrig IEEE
- [ ] `automations/somrig_buttons.yaml` — 3 curtain Somrig IEEE
- [ ] `automations/godnat_night.yaml` — kalde-knap IEEE
- [ ] `packages/light_groups.yaml` — 5 nye bulbs til standby gruppe
- [ ] `automations/bulb_firmware_defaults.yaml` — IKKE add hvide bulbs (cluster_768 false, kun cluster 8 brightness)
- [ ] `CLAUDE.md` — update pre-flyt setup note med ny hardware

Alle commits via:
```bash
git add . && git commit -m "feat: pair 5 bulbs + 5 Somrig + 1 Vallhorn + 5 Apollo (FRB test)"
git push origin main
ssh ha "cd /config && git fetch origin && git reset --hard origin/main && zsh -lc 'ha core restart'"
```

## Phase 6: HA restart + verification — ~10 min

```bash
ssh ha "zsh -lc 'ha core restart'"
```

Vent på boot. Verify:

- [ ] Alle 5 nye `light.tradfri_white_*` synlige + on/off virker
- [ ] Alle 5 nye Somrig fyrer events ved tryk (event monitor)
- [ ] Entré Vallhorn occupancy state ændrer ved bevægelse
- [ ] 5 Apollo: alle entities responder
- [ ] `binary_sensor.presence_sensors_available` = ON
- [ ] Eksisterende automations stadig fungerer (sove godnat-tryk, wakeup, scenes)

## Phase 7: Integration tests — ~30 min

### Test 1: AirBnB welcome (entré Somrig nu live)
1. Skift `house_mode → AirBnB` i HA UI
2. Tap entré Somrig TOP quick
3. Verify: entré + stue + køkken + spisestue tænder lux-baseret
4. Tap entré Somrig BUND quick → alt slukker
5. Skift tilbage til `Normal`

### Test 2: Auto-godnat (post 2t bedroom-only)
1. Sæt `godnat_auto_enabled = on` (default)
2. Gå i sove-rum og bliv der i 2 timer (eller manipuler Apollo state via Developer Tools)
3. Verify `script.godnat` fyrer + flags settes

### Test 3: AirBnB no-presence 60min
1. AirBnB mode active
2. Forlad alle rum i 60 min
3. Verify alt slukker + house_state Dormant

### Test 4: Wakeup-driven alarm
- Allerede testet 2026-05-04 ✓

### Test 5: Curtain Somrigs (limited pre-flyt)
- Pair OK, events fyrer OK, men ingen Aqara curtain motors paret pre-flyt → cover.* services fejler silent
- Post-flyt: curtain motors pares, så bliver functional

## Risici + rollback

**Risiko**: Mass-pairing kan stresse Zigbee mesh. ZBT-2 kan timeout under høj device-discovery load.
**Mitigation**: Pair én ad gangen, vent for full integration før næste.

**Rollback**: Backup taget i Phase 0. Hvis noget breaker → restore backup via `ha backups restore`.

**Risiko**: Apollo WiFi-config fejler hvis pre-flyt WiFi krediteringer er ukendte.
**Mitigation**: Sørg user har FRB WiFi password klar.

**Risiko**: IEEE-IDs vil være ukendte indtil pairing → koden er PLACEHOLDER. Codebase updates kan først ske POST-pairing.
**Mitigation**: Phase 5 (codebase) sker EFTER Phase 1-4. Ingen pre-emptive YAML edits.

## Tidsestimat samlet

| Phase | Estimat |
|---|---|
| 0 - Prep | 5 min |
| 1 - Bulbs (5) | 20 min |
| 2 - Somrig (5) | 30 min |
| 3 - Vallhorn (1) | 5 min |
| 4 - Apollo (5) | 30-60 min |
| 5 - Codebase | 30 min |
| 6 - Restart + verify | 10 min |
| 7 - Integration tests | 30 min |
| **Total** | **~3 timer** |
