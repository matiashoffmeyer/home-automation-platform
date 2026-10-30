# Offline-audit — lys og radio uden internet (B254)

> *Written in Danish. English overview: [README](../README.md) ·
> [ARCHITECTURE](../ARCHITECTURE.md).*

**Målt 2026-10-26, kun ved at læse koden og core 2026.9.2's kilde** (ingen test
endnu). Rammer (user 23/10): lys og radio er det vigtige og skal bare virke.
Nød-radioen er familiens egen FM-radio uden for HA (B255 droppet). Spørgsmålet
er derfor: **kan en cloud-kilde der dør låse en lys-vej?** `unavailable` er
hverken on eller off (#9).

## Konklusion

**Ingen lys-gate fejler lukket.** Alle cloud-afledte værdier, som en lys-vej
læser, falder tilbage til neutral eller "tænd alligevel". Ingen kode skal
ændres før testen. Det eneste der rigtig går tabt, er alt der skal ud af huset:
push, TTS-beskeder, netradio og Spotify.

## Cloud-kilderne og deres vej ind i lyset

Fundet ved at slå `iot_class` op for alle config entries (`manifest/list`) og
grep'e efter eksterne hosts i YAML. Bagefter blev template-entities, der læser
kilderne, fulgt fire led ud, ind i de filer der kalder `light.turn_*`.

| Kilde | Uden net | Lys-vej | Udfald |
|---|---|---|---|
| **Nord Pool** (spotpris) | Har den dagens priser, bruger den dem (`_async_update_data` stopper tidligt). Ellers `UpdateFailed` → `unavailable` | `elpris_spot_aktuel` → `elpris_dim_factor` → `global_brightness_factor` (næsten alle lys), `luksus_lys_elpris_block`, `roborock_elpris_block` | De rigtige timepriser i ~1-2 døgn. Derefter er prisen `unavailable`, hvilket giver `p = -999`, så faktoren bliver **1.0** og blokken **off** = neutral |
| **Energi Data Service** | `unknown`/`unavailable` | kun omkostnings- og lader-sensorer, ingen lys-gate | — |
| **met.no** (`weather.forecast_home`) | `unavailable` efter ca. 1 t (målt 21/10 03:46-04:42) | `terrasse_regn_aktiv` (vådt nu), regn-varslets blink | Ikke vådt, så terrasse-pluggen bliver på (bevidst fail-safe). Blinket udebliver |
| **DMI** (REST, `this`-fallback) | beholder sidste værdi (forældet) | `terrasse_regn_aktiv` via `mm_next3h` | Alders-guard på 3 t, så værdien udløber af sig selv |
| `sensor.udetemp` (met.no) | kortvarige `unavailable` | ingen lys-vej (gardiner, fugt, `activity_state`-fallback `float(8)`) | — |
| **Roborock** | integrationen kan miste robotten | `roborock_blokerer_lys` (alle presence-veje) | `unavailable` er ikke `cleaning`, så lyset tænder (fail-open, bevidst). Ulempe: tænder robotten lys i et Dormant hus, holdes det ikke tilbage |
| Aurora, HACS, analytics | fejl i loggen | ingen | — |

Lokale og dermed uberørte: ZHA, Matter/Thread (OTBR), Hue, ESPHome
(Apollo'erne), Broadlink, Volumio, Cast, `sun.sun` (beregnet), lux
(Apollo LTR390), people/presence.

## Det der går tabt — og om det fejler pænt

- **Push** (`script.push_notify` → `notify.mobile_app_*`): mobile_app fanger
  selv fejlen fra relayet og logger den (`_async_send_remote_message_target`,
  `asyncio.timeout(10)`). Den der kalder **afbryder altså ikke**, men venter
  højst ~10 s pr. telefon. 45 filer kalder blokerende. Ingen af dem mister en
  handling, men en besked kommer op til 20 s senere end den ville. Beskeden er
  tabt, medmindre telefonen har local push på hjemme-wifi'en. Knapsvar virker
  hjemme, fordi de går til `internal_url`.
- **TTS** (Google Translate): `tts_url.py` fejler inden for ≤ 50 s, og så
  laver `script.hoejttaler_annoncer` en logbook-linje og `stop`. Alle callers
  bruger `script.turn_on`, så ingen venter. Timer- og vejr-beskeder bliver
  bare væk. **B258's beskeder skal derfor ligge som færdige lydfiler** (står i
  B258).
- **Radio og Spotify**: DR's streams og Spotify er cloud og spiller ikke.
  `hoejttaler_spotify_genopliv` læser mDNS og librespot `getInfo` (lokalt), så
  den burde ikke genstarte højttaleren hvert 2. time uden net. Det bekræftes i
  testen.
- **Fjernadgang** (Tailscale) er væk. Hjemme virker app og browser via LAN.

## Netværket

- DNS: HA → Supervisor-DNS → routeren, med fallback. Husets egne mål er
  IP-adresser, og `*.local` går over mDNS → lokale navne virker uden WAN.
- NTP: ikke målt. Et kort udfald er harmløst, da NUC'ens ur kører videre.
- **Huset ved ikke selv, at det er offline**: der er ingen `ping`-sensor mod
  internettet. Det er ikke et problem for lyset, men B256 må ikke tolke et
  langt net-udfald som inaktivitet, hvis git eller Claude tæller som aktivitet
  (spørgsmål til B256).

## Gardinerne (vurderet 2026-10-28, kode + historik)

**Intet gardin kører forkert og intet låses.** Motorerne er lokale (Somfy via
Broadlink-RF, sove-gardinet på Zigbee), så alle knapper og manuelle veje virker. Fem
automatiske veje læser met.no. Alle fejler på én af to måder: som "klart vejr",
hvor lokal lux/temp stadig afgør, eller som "rør ikke gardinet".

| Vej | Læser | Uden net |
|---|---|---|
| Sommer-forsvar (Dormant, 09-20) | skydække, `float(0)` | antager klart; luk afgøres af inde-temp (TIMMERFLOTTE/Broadlink, lokal) = hede-beskyttelsen bevares. Genåbning ved skyer udebliver |
| Putte-vest-blænding | skydække, `float(0)` | antager klart; lux-gaten (lokal) afgør stadig |
| Mosbilledet | skydække kun i log/feedback | ingen effekt, beslutningen er lux |
| Vinter: Dormant-luk, mørke-luk, sol-opvarmning, kuldebølge | `sensor.udetemp` | `unknown` → numeric_state falsk → **intet luk, ingen åbning**. Mørke-luk re-armer selv på `unknown → under`-flanken når nettet kommer tilbage; sol-opvarmningen gør ikke (kun komfort) |

Prisen: under et udfald i fyringssæsonen (`winter_heating_season_temp`, i dag
5 °C) lukker stuen ikke af sig selv ved mørkets frembrud. Det er det neutrale
valg ("slip frem for at tvinge"), og det sker allerede i dag: met.no var væk
3 gange på 30 døgn, 56-63 min hver (3/10, 19/10, 21/10). `sensor.udetemp` blev
`unknown` i hele vinduet. En lokal udetemp-føler ville fjerne hullet, men huset
har ingen. Genvex'en viser ingen ude-temp i HA.

Telefon-vejene (`house_state_to_dormant_gps_fast`, ankomst) mister GPS fra
telefoner ude af huset. Dormant kommer så kun via døren og presence, og
sommer-forsvaret (kun Dormant) fyrer sjældnere. Det er ikke farligt.

## Ikke dækket her

- **HA-genstart MENS nettet er væk**: integrationerne går i setup-retry →
  `unavailable` → samme fail-open. Det er kun læst i koden, ikke testet.

## Testen (afventer user-OK)

Hent WAN-kablet ud af routeren i ~30 min, mens familien er hjemme. Brug ægte
tryk og ægte bevægelse i hvert rum, og stop til sidst radioen fra en Styrbar.
Mål:

1. Lys tænder og slukker i hvert rum (tryk og presence), latens som før.
2. `sensor.global_brightness_factor` og `binary_sensor.luksus_lys_elpris_block`
   holder sig neutrale.
3. Højttaleren genstarter ikke af sig selv.
4. Står telefonerne stadig `home`?
5. Når kablet sættes i igen, kommer integrationerne selv tilbage. Tjek med
   `./scripts/ha_health.sh deploy`.
