---
paths:
  - "packages/light_*.yaml"
  - "automations/light_*.yaml"
  - "automations/bulb_*.yaml"
  - "automations/zha_auto_config.yaml"
  - "script_pkg/bulb_defaults.yaml"
  - "script_pkg/scene*.yaml"
  - "packages/stue_spots.yaml"
  - "packages/stue_spots_ild.yaml"
  - "packages/stue_plug.yaml"
  - "packages/sove_lyskaede.yaml"
  - "packages/lys_kpi.yaml"
  - "packages/luksus_lys.yaml"
  - "automations/godnat_night.yaml"
  - "entities/device_inventory.yaml"
  - "entities/lights/**"
  - "dashboards/lights.yaml"
  - "docs/hardware_shopping.md"
  - "docs/hardware.md"
---

> *Danish. A path-scoped rule file: Claude Code loads it the first time a
> file matching `paths:` is read. See
> [docs/methodology.md](../../docs/methodology.md).*

# Pærer og lys-hardware

Path-scopet fra CLAUDE.md (Permanente fakta) — loades når du læser en fil
der matcher `paths:`. Samme genkendelses-lag: regel, signatur, entity-navn.
Den lange version (måledata, incidents): `docs/permanente_fakta.md`
(`grep -n "<nøgleord>"`). Ændrer virkeligheden sig, ret BEGGE lag.

- **Legacy `light: - platform: group` refresher kun ved RESTART.**
- **`IKEA TRADFRI bulb E27 WS globe 1055lm` lander på 2 %** hvis ét
  `light.turn_on` indeholder brightness + color_temp + transition > 0 samtidig.
  Husets eneste: `light.depot_loft_ikea` → split i to, eller
  `script.tradfri_ws_bri_fix` efter gruppe-kald.
- **`brightness: 1` via ZHA er et SLUK på Innr og Hue** (move_to_level_with_on_off
  rammer min-niveauet → pæren melder `off`). **Signatur:** et dæmp-script
  efterlader en pære slukket, og en "kun hvis den stadig lyser"-guard
  gendanner den aldrig. → gulv på 3 (`halloween_stemning_paere`).
- **En RGBW-strip kan ikke crossfade mellem RGB-motoren og sin hvide kanal** —
  bliv i ÉT color_mode; oversæt kelvin til RGB (`script.boern_natlys_set`).
- **En pære med `power_on_behavior = Off` er usynligt død fra vægkontakten.**
  **Signatur:** masser af `off→on` i history, men **nul `unavailable→on`**.
- **Stuen har fire fysiske lys:** to Thread-spots (`light.stue_spot_1/2`),
  `light.stue_plug` (effektmålt, som sove-lyskæden — resten er estimat) og
  `light.stue_laesehygge` (vægkontakt ⇒ dens unavailable-andel er
  brugeren). De tre øvrige er pærer i et skab, bevidst bevaret i rosters (B132).
  **Generelt: en permanent død entity er ubrugelig som BEVIS** — mål
  unavailable-andelen over 14 døgn før du vælger kanariefugl eller gate-kilde.
  **Signatur: en test der kun kan fejle.**
- **Sofa-spotsene og `light.stue_room`/`light.stue_all` er IKKE i recorderen**
  (B227, ild-faderne ≈ 10k rækker/t) → `hq.py hist|who|flanks` er tomme på dem.
  Brug `light.stue_laesehygge`, `input_select.room_mode_stue` eller et trace;
  net-status (væk/forbundet) står i `sensor.thread_routere_vaek` (attribut `routere`).
- **En firmware-OTA slutter med en device-reboot, hvor enheden anvender sin
  `power_on_behavior` — ikke sin sidste state.** Forudsigeligt: læs
  `select.<device>_power_on_behavior` før du flasher. Ryd op på **switch-laget**,
  ikke på template-wrapperen (den står i `manual_override.yaml`s rum-map, #11).
- **En pære der falder af radionettet MENS den lyser, bliver stående fysisk
  tændt — og `unavailable` gør den usynlig for hver eneste sluk-vej.** Enhver
  "alt lys er slukket"-påstand skal tælle dem med:
  `input_text.godnat_uopnaaelige_lys` + `sensor.lys_spoegelser`.
  **Undtagelse: `light.terrasse_paerelyskaede`s `on → unavailable` er næsten
  altid user der slukker stikkontakten** — intet vidne, så den står i
  spøgelses-tallet med vilje.
