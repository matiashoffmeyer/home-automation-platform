# Spotify-bro (B237) — AKTIVERET 17/10, husets Spotify-vej (myair fra)

> *Written in Danish. English overview: [README](../../README.md) ·
> [ARCHITECTURE](../../ARCHITECTURE.md).*

Spotify Connect-modtager på NUC'en der afspiller på N3'en som en almindelig
HTTP-radiostrøm. Installeret som `local_spotify_bro`. Live-test 3 (17/10) ✅
med begge konti og Jam. User 17/10: "implementer fuldt ud, vi kører med det her
setup uden myair" → limen er lavet (tjeklisten nedenfor), myair står fra.
HA-siden: `packages/spotify_bro.yaml`.

## Live-test 1 (16/10) → 0.1.2

| Fund | Årsag | Rettet i 0.1.2 |
|---|---|---|
| Appen blev pauset lige efter start | Volumio meldte P4 et øjeblik; broen tog det som radio-overtagelse | en anden kilde/stop/pause skal holde i `confirm_s` (2,5 s) og læses igen før appen pauses; højttaleren startes først på `playing`, ikke `will_play` |
| ~6 s latens | broen selv: backlog 3,0 s + lead 0,5 s; resten er MPD/Volumios buffer | `backlog_s` 0,5, `lead_ms` 300, og `start_hold_s`: daemonen holdes, til MPD henter strømmen, så starten ikke tabes |
| Volumen hoppede 49↔50 | Volumio melder float (49,99924), `int()` kappede | afrunding + ±1 ekko-tolerance |
| Appen sagde "Connecting" efter Tailscale til/fra på telefonen | telefonen gentog zeroconf-login hvert ~33 s; broen loggede ind og registrerede sig hver gang, men Spotifys sky sendte aldrig en transfer. Telefonens net var også væk → telefonens sky-vej | kur: tving Spotify-appen lukket eller slå wifi fra og til (IKKE Tailscale). Broen: go-librespot 0.10.5 |
| Stilhed der stod som "playing" | go-librespot bygger en NY session ved hver zeroconf-login, uden et event | log-linjen "accepted zeroconf" og et `/status`-backstop (`reconcile_s`) slipper højttaleren; tælles i `session_nulstillet` |

## Live-test 2 (16/10 aften) → 0.1.3/0.1.4

| Fund | Årsag | Rettet i 0.1.3 |
|---|---|---|
| "Connecting" igen, også for en frisk test-modtager | telefonens Connect-stak hang efter net-skiftet: zeroconf-login hvert ~33 s, broens connect-state 200, ingen transfer. Tving-stop af appen hjalp ikke, genstart af telefonen gjorde | ikke broen. Næste gang: wifi fra/til før genstart (utestet) |
| Latens ~4 s (MPD `elapsed` bag librespots position, målt) | MPD/Volumios buffer | uændret; N3-bufferen skal måles før noget røres |
| "Skiftede sang selv midt i en sang" | sangen sluttede rigtigt (appen havde spolet til 1:33). Men go-librespot melder et nummer-skift som `stopped` → `playing`, og broen stoppede Volumio med det samme → de sidste ~4 s i MPD's buffer blev klippet, og næste nummer ventede på en ny forbindelse | `stop_grace_s` (2 s): højttaleren stoppes først hvis librespot stadig er stoppet bagefter. Målt hullet stopped → playing: 0,26-0,63 s (5 skift, 1 skip + 4 naturlige slut, 0,25 s-sampling) |
| (0.1.4, code-review) to hurtige skip | det første skips stop-ur ramte det andet skips hul | ét stop-ur ad gangen, aflyses af `playing`/`paused`; før stop spørges go-librespot selv (tabt `playing`-event) |
| Ejerskabs-race (fundet i testen) | en `speaker_play` der holdt låsen satte `owns` igen efter et stop | `speaker_stop` nulstiller `owns` inde i låsen |

## Hvorfor (rodårsagerne fra B202/B204/B207/B233)

| Forsøg | Hvad gik galt | Rodårsag |
|---|---|---|
| N3'ens egen librespot ("myair", B202) | forsvinder, kan ikke stoppes/pauses fra HA, genstarter spontant | firmware-librespot 0.1.0 uden API, ingen SSH, kan kun genoplives med reboot af hele højttaleren |
| Music Assistant "Højttaler via HA" (B204) | appen hænger på "Connecting", play efter radio gav Volumios kø, HA-stop kappede kun DLNA | MA læser go-librespots stdout KUN mens der streames → når strømmen rives ned blokerer skrivningen, dealer-pong'en udebliver, og release-flowet deadlocker. Derudover DLNA-resume uden ny URI |
| App-pause via MA (B207) | pause nåede ikke højttaleren; play kun i ~20 s | soloisten lukker; pause skulle oversættes fra MA's log (`ma_watch.py`) |

## Design

`go-librespot 0.10.5` (0.9.0 = MA's binær indtil 16/10; 0.10.x gen-sender tabt
connect-state og opgiver et hængende AP-handshake; state-formatet i `/data` er
uændret) med pipe-output → `bro.py`, som:

- **altid dræner** daemonens stdout i realtid, med eller uden lytter. Det fjerner
  dealer-hænget. Målt i testen: den længste enkelt-skrivning var 0,34 s, mens
  strømmen blev revet ned midt i en sang. I MA blokerer den samme skrivning
  for evigt.
- serverer `http://192.0.2.151:8098/spotify.l16` (PCM, eller `.flac`) med
  ICY-titel, og beder Volumio afspille den som webradio (`replaceAndPlay`). Det
  er samme vej som vores radio, som Volumio 2 håndterer stabilt.
- holder sangens start (`start_hold_s`), til MPD har forbundet, og lægger
  derefter højst `backlog_s` + `lead_ms` (0,8 s) oven i MPD's egen buffer.
- styrer højttaleren via MPD/Volumio i begge retninger:
  - app-pause → MPD `pause 1`, og app-play → `pause 0`. Ingen
    DLNA-resume-fælde.
  - HA/knap-pause eller -stop på højttaleren → appen pauses. Radioen tager over
    → appen pauses, og broen slipper højttaleren. Alle tre skal holde i
    `confirm_s`, før de tæller.
  - volumen synkroniseres begge veje (ekko-dedupe 3 s, ±1). Sessionens
    start-volumen fra appen flytter IKKE rummet; højttalerens volumen vinder.
- eksponerer `/status` og `/cmd/*` til HA (`packages/spotify_bro.yaml`), og beder selv HA om
  `update_entity` ved hver ændring.
- genstarter daemonen med backoff (2→60 s) hvis den dør. Højttaleren genstartes
  aldrig.

Kendt pris:

- Kontoen skal være Premium (Spotify Connect-modtagere kræver det).
  UBEKRÆFTET: en påstand om at konti oprettet efter dec. 2024 ikke virker,
  er ikke målt. Afgøres ved live-testen med Parent B's konto.
- UBEKRÆFTET: om broen skifter pænt mellem to konti (zeroconf `addUser` fra
  en anden telefon, mens en anden konto er gemt med `persist_credentials`).
- Start/skip-latens afhænger af MPD's buffer. Det er ikke målt på den ægte
  N3 endnu.

## Filer

| Fil | Indhold |
|---|---|
| `config.yaml`, `build.yaml`, `Dockerfile`, `run.sh` | add-on'en (Debian bookworm-base, go-librespot hentet med sha256-tjek pr. arch) |
| `bro.py` | broen (aiohttp, ~860 linjer) |
| (HA-siden) | `packages/spotify_bro.yaml`: `sensor.spotify_bro`, `binary_sensor.spotify_bro_spiller`, `rest_command.spotify_bro_cmd`. Knappen `input_boolean.hoejttaler_spotify_bro` + start/stop-automationen i `packages/hoejttaler.yaml` |
| `tests/test_bro.py` + `tests/fake_librespot.py` | 23 offline-trin mod en falsk N3 (Volumio REST + socket.io + MPD) og en falsk go-librespot med blokerende stdout |

Køres med `python3 tests/test_bro.py` (kræver aiohttp; `flac` for flac-trinnet).
Resultat 16/10 (0.1.4): 26/26 i venv. (0.1.2: 23/23.) 0.1.0: 16/16 både i venv og i det byggede image (Python 3.11 /
aiohttp 3.8). Den ægte go-librespot accepterede broens config i imaget
(API oppe på 127.0.0.1:38950). Den døde kun på apresolve, fordi testen var
uden net.

## Aktiverings-tjekliste — udført 17/10

1. ✅ (16/10) `cp -r /config/addons/spotify_bro /addons/` → `/store/reload` → install
   `local_spotify_bro`. Ved ny version: `cp` → `/store/reload` → `update` uden body. Verificér `version` i `/addons/local_spotify_bro/info`
   (`.claude/rules/addons.md`).
2. ✅ `packages/spotify_bro.yaml`: rest-sensoren (flyttet fra
   `stue_spots_spotify.yaml`; uden `position_s`/`events`, der skifter ved hvert
   push), `rest_command.spotify_bro_cmd`, `binary_sensor.spotify_bro_spiller`
   (playing OG `ejer_hoejttaler` — sand fra broens replaceAndPlay, før Volumio
   skifter uri — eller `hoejttaler == 'spiller'`). `ha_pakke.yaml` slettet.
3. ✅ Kilde-proben: `mpd_kilde()` → `'bro'` (`:8098/spotify.`).
4. ✅ Ankrene: `anden_kilde` (spotify_bro_spiller ELLER Volumio spiller
   broens URL), `spotify_aktiv`; `spiller_reelt` virker uændret (MPD-kilde).
5. ✅ Overtageren: trigger `bro` (off→on) → volumen op fra standby, radio-flaget ryddet.
6. ✅ Genopliv: kræver allerede `input_boolean.hoejttaler_myair` on → inert.
7. ✅ Volumio-overriden: `_er_spoegelse` undtager broen; pause/stop/play/
   næste/forrige går til broens `/cmd/` når Volumio står på broens URL
   (stop = pause; play = resume). `play_media` (radioen) pauser IKKE broen
   selv — broens takeover-tjek gør det (2,5 s).
8. ✅ Annoncering: springer over via `anden_kilde`; sangen også via
   `spotify_bro_spiller`, og en sang afbrydes når broen tager over.
   Radio-adopteren spørger broen frisk (update_entity) før den sætter flaget.
9. ✅ myair fra (`input_boolean.hoejttaler_myair` off, 17/10).
10. ✅ Dashboards: Lys-sidens højttaler-linje, `sensor.spotify_bro` på status,
    Indstillinger-tekster. `triggers.yaml`: intet nyt (broen rører ingen lys
    ud over Spotify-farverne, der står der i forvejen).
11. ✅ AirBnB: intet at rydde — broen virker neutralt for gæster på wifi, og
    knappen ryddes ikke. `bruger` (Spotify-id) står i sensor-attributten.
12. Live-verifikation efter deploy (se BACKLOG B237); konto-skift midt i en
    session og 30 min med `tabte_bidder` = 0 står stadig åbent.

## Åbne beslutninger (user)

- ~~myair: pensionér eller behold?~~ Pensioneret 17/10 (står fra, kan slås til i Indstillinger).
- Enhedsnavn i appen: "Højttaler" (default i `config.yaml`)?
- Login: INGEN kopi af MA's go-librespot-credentials (`spotify_connect_up26491670`).
  Første gang nogen vælger "Højttaler" i Spotify-appen på wifi, afleverer
  telefonen selv adgangen (zeroconf), præcis som med myair. Begrundelse:
  - begge konti skal kunne bruge broen;
  - MA's `state.json` bærer MA's device-id, så en kopi giver to enheder med
    samme id, hvis MA's Connect-plugin tændes igen;
  - credentials skal ikke flyttes mellem containere uden grund.
  (Afklaret med user 16/10.)
- Rapportér MA's release-deadlock upstream?
