---
paths:
  - "packages/presence.yaml"
  - "packages/parent_b_*.yaml"
  - "packages/gps_*.yaml"
  - "automations/presence_gps_stale.yaml"
  - "automations/arrival.yaml"
  - "packages/departure_*.yaml"
  - "automations/boern_ankomst*.yaml"
  - "automations/wakeup_*.yaml"
  - "packages/notif*.yaml"
  - "scripts/notif_queue.py"
  - "packages/sove_alarm_morgen.yaml"
---

> *Danish. A path-scoped rule file: Claude Code loads it the first time a
> file matching `paths:` is read. See
> [docs/methodology.md](../../docs/methodology.md).*

# Personer, telefoner og notifikationer

Path-scopet fra CLAUDE.md (Permanente fakta) — loades når du læser en fil
der matcher `paths:`. Samme genkendelses-lag: regel, signatur, entity-navn.
Den lange version (måledata, incidents): `docs/permanente_fakta.md`
(`grep -n "<nøgleord>"`). Ændrer virkeligheden sig, ret BEGGE lag.

- **`sensor.phone_a_next_alarm` (Android) melder UTC**; Parent B's melder lokal
  offset. `unavailable` = "ingen alarm sat", ikke en defekt sensor.
- **`input_boolean.<person>_home` er en GPS-FRISKHEDS-degraderet proxy** — en
  stille iPhone er tavs i op til 17 t.
- **En iOS Companion-app uden `Authorized Always` kan ALDRIG melde et
  zone-skift** — tavsheden har nul informationsindhold, så en
  staleness-tærskel er kun en forsinket løgn (`binary_sensor.parent_b_gps_baggrund_ok`).
  **Parent B's presence er HELT væk fra GPS:** spørg
  `binary_sensor.parent_b_hjemme_anker`, aldrig device_trackeren.
- **Kun `zone.home` giver tracker-state `'home'`** (#17).
- **Notifikations-KNAPSVAR kræver netværk til HA** (leveringen går via FCM/APNS
  og virker overalt, men SVARET er et HTTP-kald) → manglende svar ≠ ignoreret.
