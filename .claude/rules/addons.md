---
paths:
  - "addons/**"
---

> *Danish. A path-scoped rule file: Claude Code loads it the first time a
> file matching `paths:` is read. See
> [docs/methodology.md](../../docs/methodology.md).*

# Lokale add-ons

Path-scopet fra CLAUDE.md (Permanente fakta) — loades når du læser en fil
der matcher `paths:`. Samme genkendelses-lag: regel, signatur, entity-navn.
Den lange version (måledata, incidents): `docs/permanente_fakta.md`
(`grep -n "<nøgleord>"`). Ændrer virkeligheden sig, ret BEGGE lag.

- **Lokale add-ons deployes fra `/addons/<slug>/`, ikke fra git-kopien i
  `/config/addons/<slug>/`** — to uafhængige filtræer. **Signatur: rebuild
  svarer `{"result":"ok"}`, alt ser rigtigt ud, og `info` melder stadig den
  GAMLE `version`.** → `cp` FØRST, så `/store/reload`, så **`update` UDEN body**.
  Verificér på `version` i `/addons/<slug>/info`, aldrig på et sundt log.
- **Et add-on's host-port er en dør UDEN login på LAN + tailnet** — ingress
  beskytter kun UI-vejen, og add-ons taler sammen over Docker-nettet
  (`core-mosquitto`, `local-gesture-frame-shim:8090`). **Signatur: en `ports:`-
  linje som ingen enhed uden for NUC'en forbinder til** → `null` (8090, 8099 og
  MQTT lukket 25/10, B251: kamera-billeder + MQTT-password lå åbne).
- **Music Assistant (`d5369777_music_assistant`) kræver login; boot er `manual`,
  og `input_boolean.hoejttaler_spotify_via_ha` ejer start/stop** (B204). API'et
  kaldes med `scripts/ma_api.py` (password i secrets, printes aldrig). Streams-
  `bind_ip` = LAN-IP'en, ellers annoncerer Spotify Connect Tailscale-adressen
  først. **Signatur: "Højttaler via HA" ses, men forbinder aldrig.** Under DLNA er
  Volumios metadata stale → kilden læses i MPD (`kilde=ha`), også når strømmen
  er SLUT (Volumio bliver stående på `play`). Shell_command-svar med JSON-
  `true` native-parses ikke → `| from_json` (B205).
- **Pause fra Spotify-appen på "Music Assistant Playback" (MA's soloist) når
  ikke højttaleren. MA springer til næste nummer efter ~20 s stall, og Connect-
  pluginnets dealer hænger for evigt.** → `scripts/ma_watch.py` (daemon i
  SSH-add-on'en) oversætter begge fra MA's DEBUG-log (B207). Appens play virker
  kun ~20 s efter pausen (så lukker soloisten); kø-nummeret står i
  `media_item.uri`, IKKE `current_item.uri`.
