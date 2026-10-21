# volumio — override af core-integrationen (2026-10-08)

> *Written in Danish. English overview: [README](../../README.md) ·
> [ARCHITECTURE](../../ARCHITECTURE.md).*

Kopi af `homeassistant/components/volumio` fra HA 2026.9.2. Den skal bruges
fordi højttaleren (AxiomAir N3, `media_player.hoejttaler`) kører Volumio 2-OEM
V2.13.2 (2020): her findes kun getState/listplaylists/commands over REST.
Core crasher derfor (`KeyError: 'hardware'`), og `play_media` gør tavst ingenting.

Rettelserne er markeret i koden:
- `__init__.py`: system-info hentes via socket.io, når REST giver `{}`
- `media_player.py`: `uid` falder tilbage på entry_id, entity'en bliver `unavailable` når højttaleren ikke svarer (core fryser på sidste state), og `play_media` går via
  socket.io `replaceAndPlay` (`legacy.py`)
- `media_player.py` (alle firmwares): poller hurtigt i ~15 s efter hvert kald
  (ellers så knapperne døde ud til næste 10-s-poll), 8 s timeout på pollet, og
  `supported_features` følger det der spiller — webradio skjuler
  pause/forrige/næste/shuffle/repeat, en tom playliste-liste skjuler kilde-valget
- `media_play` på Music Assistants DLNA-strøm (`:8097/flow/<session>/<queue_id>/`)
  genoptager MA-køen via `scripts/ma_api.py` (Volumio kan ikke selv genstarte
  en udløbet flow-URL); fejler det → radio-favoritten (`script.hoejttaler_radio`).
  Fra standby (volumen 0) sættes start-volumen først
- mediebrowseren går via socket.io `getBrowseSources`/`browseLibrary`
  (`legacy.Library`) — REST-browse gav "Unknown error"

Fjern mappen og genstart, hvis core en dag får en fallback, eller hvis
højttaleren skiftes ud. Entity'en bevarer sit navn, men `play_media` dør igen,
så test radioen bagefter. HA logger "custom integration volumio overrides core" ved
hver start; det er forventet.
