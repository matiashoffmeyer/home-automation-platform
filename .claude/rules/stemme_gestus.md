---
paths:
  - "packages/koekken_gestus*.yaml"
  - "packages/koekken_stemme*.yaml"
  - "packages/koekken_kamera*.yaml"
  - "packages/voice_commands.yaml"
  - "packages/tapo_tuning.yaml"
  - "automations/gestus_*.yaml"
  - "addons/gesture_frame_shim/**"
  - "scripts/stemme_replay.py"
  - "scripts/assist_expose.py"
  - "docs/gesture_recognition.md"
---

> *Danish. A path-scoped rule file: Claude Code loads it the first time a
> file matching `paths:` is read. See
> [docs/methodology.md](../../docs/methodology.md).*

# Stemme, gestus og køkken-kamera

Path-scopet fra CLAUDE.md (Permanente fakta) — loades når du læser en fil
der matcher `paths:`. Samme genkendelses-lag: regel, signatur, entity-navn.
Den lange version (måledata, incidents): `docs/permanente_fakta.md`
(`grep -n "<nøgleord>"`). Ændrer virkeligheden sig, ret BEGGE lag.

- **Køkken-kameraets KONTROL-API er død — kun RTSP virker, og højttaleren findes
  KUN bag kontrol-API'en** (nonce-handshake som `pytapo` ikke kan; alle målte
  credentials afvist, også den der autentificerer RTSP fejlfrit). Højttaleren
  kan heller ikke nås via go2rtc — **MIKROFONEN kan** (RTSP-lydtrack). **Spørg
  altid hvilken RETNING lyden løber.** Ikke installér igen: `grep "B146" BACKLOG.md`.
- **"Spiller højttaleren?" afgøres IKKE af kamera-mikrofonens NIVEAU** (radio på
  25 % og stilhed måler begge ~−57 dB) — kun af KORRELATION mod selve streamen:
  `scripts/hoejttaler_lyttetest.py` (spiller 0,23-0,69 ved lag 0,3-0,8 s; stoppet ≤ 0,12).
- **hand_recognition's `three_fingers` = TOMMEL + pege + lang** (README'en lyver);
  pege + lang + ring har intet mønster og læses deterministisk som
  `four_fingers`. **Signatur: et fingertal der er konsekvent én for højt, ikke
  flimrende** — hold-kravet hjælper ikke.
- **En fjern hånd kan IKKE skilles fra en nær med hold-krav eller billed-skala**
  — palme-detektoren finder en ÅBEN hånd på 1,5 m let (10-05: `four_fingers` i
  6 frames i træk, score 0,9), men en KNYTNÆVE på 50 cm kun i fuldt billede
  (3/14). Formen afgør detektionen, ikke størrelsen. **Signatur: utilsigtede
  timere med lange, stabile striber og høj score.** → størrelsen måles
  direkte: shimmens `PalmGate` finder palmer under
  `input_number.gestus_min_haand_px` (palme-boksen er næsten ens for
  knytnæve og åben hånd), og er én i billedet, ser add-on'et KUN de nære
  hænders ROI — at skjule den fjerne (sort, sløret) lækkede begge gange, B235. Fordelingen: `/share/gesture_frame_shim/palms.jsonl`,
  live på shimmens `/haand`.
- **Speech-to-Phrase er en FAST-SÆTNINGS-MATCHER uden "ved det ikke"-udgang** —
  hver ytring snappes til nærmeste trænede sætning, og grafen bygges af de
  entities der er EKSPONERET TIL ASSIST. **Signatur: en misset stemme-kommando
  står i loggen som en ANDEN ægte HA-kommando** ('pause', 'what is CO2'). → skru
  ned for konkurrencen i eksponeringen (`scripts/assist_expose.py`), ikke i
  shimmens tærskler; kræver add-on-genstart (ingen config entry, træner kun ved
  opstart). Nye entities eksponeres SELV (#16). **MEN færre sætninger hjælper en
  ÆGTE kommando igennem og gør samtidig STØJ værre** — mængden er en
  skraldespand der opsuger klirren. Transcript-eventet bærer **ingen
  confidence**, så støj og tale er samme streng → falske positiver kan kun
  bekæmpes UDEN FOR lyden: en HOLDT hånd eller et BLIK armerer mikrofonen i 12 s
  (`packages/koekken_stemme_arm.yaml`; `ArmGate`/`GazeWatcher` fejler LUKKET og
  skriver SAMME stempel). **Kameraet hænger 30 cm over users hoved → et bevidst
  kig læses 14-29°**; et blik MENS man taler armerer derfor med løsere vinkel.
  **Tal: -teen/-ty forveksles akustisk** (fifteen→50, sixteen→60; 8 kHz) —
  replay med pad/norm ændrer intet → dobbelt vink ved tvetydige tal. Mishør?
  Klippene ligger i `/share/gesture_frame_shim/clips` → `scripts/stemme_replay.py`.
- **En NATIV Android-timer (`SET_TIMER`) kan HA ikke fjerne igen — OnePlus' Ur
  ignorerer `DISMISS_TIMER`, og der er ingen kvittering** (HTTP 200 = kun "FCM
  tog imod"). Køkkenets lyd er derfor en HA-ejet TTS-løkke på telefonens
  `alarm_stream` (`script.koekken_gestus_telefon_alarm`, B149): HA ejer både
  start og stop. Stop midt i en sætning = `message: command_stop_tts`.
- **`binary_sensor.koekken_kamera_krop` er frame-til-frame-BEVÆGELSE, ikke
  tilstedeværelse** — en voksen der står stille ved komfuret er lige så tavs som
  et barn under billedet, så kamera-tavshed beviser aldrig "lav krop" (10-05: 24
  lave passager på 70 min med kun voksne hjemme; user-svar 1 ja/3 nej).
  **Signatur: "kameraet tavst i 1000+ s" mens køkken-radaren ser passager hvert
  minut.** → featuren er slået fra (`koekken_lav_krop_boern_enabled`); et
  barne-signal herfra ville kræve en PERSON-detektor, ikke en tærskel.
