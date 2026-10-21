# Modified from Home Assistant Core 2026.9.2 (Apache License 2.0); the changes are listed in README.md.
"""Volumio Platform.

Volumio rest API: https://volumio.github.io/docs/API/REST_API.html
"""

import asyncio
import json
import logging
import re
import time
from datetime import timedelta
from typing import Any, override

import aiohttp
from homeassistant.components.media_player import (
    BrowseMedia,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
    RepeatMode,
)
from homeassistant.const import CONF_ID, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import Throttle
from pyvolumio import CannotConnectError

from . import VolumioConfigEntry, legacy
from .browse_media import browse_node, browse_top_level
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
PLAYLIST_UPDATE_INTERVAL = timedelta(seconds=15)
# Efter et kald pollet hurtigt i ~15 s: ellers står knappen "død" til næste
# 10-s-poll, og en webradio er 2-12 s om at gå stop → pause → play (målt 08/10).
REFRESH_AFTER_COMMAND = (0.5, 1, 1.5, 3, 4, 5)
# Ikke-giver-sig-GET (Pi'en halvt nede) må ikke fryse entity'en i aiohttp's 300 s.
UPDATE_TIMEOUT = 8
# Music Assistant spiller til højttaleren over DLNA som en "webradio" med
# flow-URL'en http://<ma>:8097/flow/<session>/<queue_id>/… . Volumio husker den,
# men MA har lukket sessionen — play skal genoptage MA-KØEN (user 09/10: "lys
# sidens play skal genoptage hvad end der spillede af musik").
MA_FLOW = re.compile(r":8097/flow/[^/]+/([^/]+)/")
# Spotify via HA (MA's Spotify Connect-plugin) spiller som
# http://<ma>:8097/source/<session>/<player_id>/… . Strømmen er LIVE fra
# go-librespot: Volumio's stop kapper kun DLNA, mens MA og Spotify-appen bliver
# ved med at "spille", og Volumio's play på den døde URL hænger i 4 min
# (14/10 13:03-13:07: tre play-tryk, ingen lyd, to fejl i HA). → knapperne
# går til MA-afspilleren, som sender dem videre til appen.
MA_SOURCE = re.compile(r":8097/source/[^/]+/([^/]+)/")
MA_API = "/config/scripts/ma_api.py"
# Spotify-broen (B237, add-on local_spotify_bro) spiller som webradio-URL'en
# http://192.0.2.151:8098/spotify.l16. Knapperne går til broen, som sender
# dem videre til appen — Volumio's stop ville kun kappe strømmen, og appen
# "spillede" så videre indtil broens takeover-tjek (2,5 s) greb.
BRO_URI = ":8098/spotify."
BRO_CMD = "http://127.0.0.1:8098/cmd/"
# Giver ingen mening for en radiostream (prev/next/shuffle/repeat gør intet);
# PAUSE væk → UI'et viser STOP, som er det pause alligevel gør ved webradio.
WEBRADIO_HIDDEN = (
    MediaPlayerEntityFeature.PAUSE
    | MediaPlayerEntityFeature.PREVIOUS_TRACK
    | MediaPlayerEntityFeature.NEXT_TRACK
    | MediaPlayerEntityFeature.SHUFFLE_SET
    | MediaPlayerEntityFeature.REPEAT_SET
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: VolumioConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Volumio media player platform."""

    data = config_entry.runtime_data
    volumio = data.volumio
    info = data.info
    # Manuelt tilføjet OEM-firmware giver intet UUID (getSystemInfo mangler) →
    # entry_id, så entity'en kan omdøbes i registret.
    uid = config_entry.data[CONF_ID] or config_entry.entry_id
    name = config_entry.data[CONF_NAME]

    entity = Volumio(volumio, uid, name, info)
    async_add_entities([entity])


class Volumio(MediaPlayerEntity):
    """Volumio Player Object."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_supported_features = (
        MediaPlayerEntityFeature.PAUSE
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.PREVIOUS_TRACK
        | MediaPlayerEntityFeature.NEXT_TRACK
        | MediaPlayerEntityFeature.STOP
        | MediaPlayerEntityFeature.PLAY
        | MediaPlayerEntityFeature.PLAY_MEDIA
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.SELECT_SOURCE
        | MediaPlayerEntityFeature.REPEAT_SET
        | MediaPlayerEntityFeature.SHUFFLE_SET
        | MediaPlayerEntityFeature.CLEAR_PLAYLIST
        | MediaPlayerEntityFeature.BROWSE_MEDIA
    )

    def __init__(self, volumio, uid, name, info):
        """Initialize the media player."""
        self._volumio = volumio
        self._legacy = bool(info.get("legacy"))
        unique_id = uid
        self._state = {}
        # Kilden der sidst SPILLEDE (Volumios service ved status play). Efter en
        # myair-pause falder Volumio tilbage til sin gamle kø (radioen) og
        # glemmer Spotify — målt 10/10 09:23-09:26: Bob Dylan via myair, 20 s
        # senere stod getState på P4, og Lys-sidens play startede radioen.
        self._sidst_spillet: str | None = None
        # MA-strømmen var HA's EGEN sang (script.hoejttaler_spil_sang, fx "Regn"
        # ved regnvarsel) — ikke din Spotify via HA. 13/10 06:50: play genoptog
        # MA-køen = regnsangen forfra i stedet for radioen. Glemmes ved restart
        # (så genoptager play MA-køen som før).
        self._ma_er_ha_sang = False
        # MA-afspilleren bag en Spotify via HA-session der sidst spillede.
        # Volumio's uri er TOM efter stop, så den huskes til play.
        self._ma_kilde_player: str | None = None
        self._refresh_task: asyncio.Task | None = None
        # Spøgelses-radio (se _async_fix_spoegelse): kur i gang + sidste kurs slut.
        self._spoegelse_kur_koerer = False
        self._spoegelse_kur = 0.0
        # MPD's lyd-udgang (output 0 "alsa") slået FRA af os → slås til igen af
        # _async_mpd_ud_til (når MPD ikke spiller) eller før HA starter radio.
        self._mpd_ud_fra = False
        self._mpd_ud_task: asyncio.Task | None = None
        self._push_task: asyncio.Task | None = None
        self._push_refresh: asyncio.Task | None = None
        # Radio-tilstand set i pushState: spiller nu / stoppede (monotonic).
        self._radio_spiller = False
        self._radio_stoppet = 0.0
        self.thumbnail_cache = {}
        self._attr_source_list = []
        self._attr_unique_id = unique_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, unique_id)},
            manufacturer="Volumio",
            model=info["hardware"],
            name=name,
            sw_version=info["systemversion"],
        )

    async def async_update(self) -> None:
        """Update state."""
        # Core fryser på sidste state når højttaleren er slukket (N3 forsvinder
        # helt af nettet) — dashboardet viste "spiller" og døde knapper (08/10).
        try:
            async with asyncio.timeout(UPDATE_TIMEOUT):
                self._state = await self._volumio.get_state()
        except CannotConnectError, TimeoutError:
            self._attr_available = False
            return
        self._attr_available = True
        if self._state.get("status") == "play" and self._state.get("service"):
            self._sidst_spillet = self._state["service"]
            m = MA_SOURCE.search(self._state.get("uri") or "")
            self._ma_kilde_player = m.group(1) if m else None
            if MA_FLOW.search(self._state.get("uri") or ""):
                sang = self.hass.states.get("script.hoejttaler_spil_sang")
                self._ma_er_ha_sang = sang is not None and sang.state == "on"
        # Pollen sætter kun radio-flaget (efter en restart kommer intet push før
        # næste ændring); kun pushes rydder det. Et hængende flag koster højst
        # en harmløs udgang-fra/til ved næste Spotify-start.
        if self._state.get("status") == "play" and (
            self._state.get("service") == "webradio" or self._state.get("trackType") == "webradio"
        ):
            self._radio_spiller = True
        await self._async_fix_spoegelse()
        await self._async_update_playlists()

    @staticmethod
    def _er_spoegelse(st: dict) -> bool:
        uri = st.get("uri") or ""
        return (
            st.get("status") == "play"
            and not st.get("service")
            and uri.startswith("http")
            and BRO_URI not in uri
        )

    async def _async_fix_spoegelse(self) -> None:
        """Spotify (myair) valgt MENS radioen spiller: radioen kører videre.

        Målt 14/10 14:18:15 og 14:24:34: Volumio skiftede 1 s til
        volspotconnect2 og faldt tilbage til P4 med service None — appen
        "spillede", højttaleren spillede radio. Volumio genstarter selv MPD
        (stop, clear → P4 igen på 2 s). Det der fik Spotify igennem — men ikke
        hver gang: REST-stop (virkede 14:26:51, ikke 14:19:04) og socket.io
        stop (virkede 14:21:12, ikke 14:24:42/14:25:42). → skiftevis, hver
        2,5 s i ≤ 20 s, til Volumio melder en kilde igen.
        Signatur: play + INGEN service + http-stream, stadig efter 3 s
        (et overgangs-sample må ikke tælle).
        """
        if not self._er_spoegelse(self._state):
            return
        if (
            not self._legacy
            or self._spoegelse_kur_koerer
            or time.monotonic() - self._spoegelse_kur < 60
        ):
            return
        # Egen 3-s-gen-tjek i stedet for at vente på næste 10-s-poll (14:35:
        # 30 s fra appens valg til lyd, heraf ~20 s ventetid på pollen).
        self._spoegelse_kur_koerer = True
        self.hass.async_create_background_task(
            self._async_spoegelse_kur(), f"{self.entity_id} spøgelses-radio"
        )

    async def _async_spoegelse_kur(self) -> None:
        try:
            await self._async_spoegelse_kur_inner()
        finally:
            self._spoegelse_kur_koerer = False

    async def _async_spoegelse_kur_inner(self) -> None:
        await asyncio.sleep(3)
        try:
            st = await self._volumio.get_state()
        except CannotConnectError:
            return
        if not self._er_spoegelse(st):
            return  # et overgangs-sample, ikke et spøgelse
        self._spoegelse_kur = time.monotonic() + 20  # 60 s cooldown fra kurens slut
        # INGEN mute: prøvet 14:50 (user: "mute den i stedet for hak") — alle 8
        # stop-forsøg fejlede med mute på (0/8), mod 2/2 kure uden. Mute er en
        # volumen-kommando, og Volumio holdt fast i radioen; e55c2c3 rullet tilbage.
        # Lyd-udgangen fra (14:58:57): MPD gik på PAUSE — ikke stop, så Volumio's
        # webradio-genstart greb ikke ind — og Spotify fik lyden på 3 s.
        await self._async_mpd_ud_fra("spøgelse set af pollen")
        for _ in range(6):
            await asyncio.sleep(1)
            try:
                st = await self._volumio.get_state()
            except CannotConnectError:
                return
            if not self._er_spoegelse(st):
                _LOGGER.warning(
                    "Spøgelses-radio (%s) kureret af MPD-udgang fra → %s %s",
                    st.get("uri"),
                    st.get("service"),
                    st.get("status"),
                )
                self._refresh_soon()
                return
        await self._async_spoegelse_stop_loop(st.get("uri"))

    async def _async_spoegelse_stop_loop(self, uri: str | None) -> None:
        for forsoeg in range(1, 9):
            # socket.io først: kurerede 14:21:12 + 14:35:03 (REST: 14:26:51).
            vej = "socket.io stop" if forsoeg % 2 else "REST stop"
            try:
                if not forsoeg % 2:
                    await self._volumio.stop()
                else:
                    await legacy.emit(
                        async_get_clientsession(self.hass),
                        self._volumio._host,
                        self._volumio._port,
                        "stop",
                    )
                await asyncio.sleep(2.5)
                st = await self._volumio.get_state()
            except Exception as e:  # noqa: BLE001 — kuren må aldrig vælte pollen
                _LOGGER.warning("Spøgelses-radio: %s fejlede: %s", vej, e)
                continue
            if not self._er_spoegelse(st):
                _LOGGER.warning(
                    "Spøgelses-radio (%s) kureret af %s, forsøg %d → %s %s",
                    uri,
                    vej,
                    forsoeg,
                    st.get("service"),
                    st.get("status"),
                )
                self._refresh_soon()
                return
        _LOGGER.warning("Spøgelses-radio (%s) IKKE kureret efter 8 forsøg", uri)

    async def _mpd(self, cmd: str) -> str:
        """Én kommando direkte til MPD (port 6600) — Volumio's egen afspiller."""
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(self._volumio._host, 6600), 3
        )
        try:
            await asyncio.wait_for(reader.readline(), 3)
            writer.write(f"{cmd}\nclose\n".encode())
            await writer.drain()
            data = await asyncio.wait_for(reader.read(4096), 3)
        finally:
            writer.close()
        return data.decode(errors="replace")

    async def _async_mpd_ud_fra(self, hvorfor: str) -> None:
        """Slå MPD's lyd-udgang fra, så radioen ikke kan tage lyden fra Spotify.

        MPD pauser selv når den ikke har nogen udgang (målt 14:58:57) — en
        PAUSE, som Volumio's webradio-genstart lader være. Slås til igen af
        _async_mpd_ud_til når MPD ikke spiller.
        """
        try:
            await self._mpd("disableoutput 0")
        except (OSError, TimeoutError) as e:
            _LOGGER.warning("MPD-udgang fra fejlede (%s): %s", hvorfor, e)
            return
        self._mpd_ud_fra = True
        _LOGGER.warning("MPD-udgang FRA (%s)", hvorfor)
        if self._mpd_ud_task is None or self._mpd_ud_task.done():
            self._mpd_ud_task = self.hass.async_create_background_task(
                self._async_mpd_ud_til_naar_stille(), f"{self.entity_id} mpd-udgang"
            )

    async def _async_mpd_ud_til(self, hvorfor: str) -> None:
        """Lyd-udgangen til igen (idempotent; kun hvis VI slog den fra)."""
        if not self._mpd_ud_fra:
            return
        try:
            await self._mpd("enableoutput 0")
        except (OSError, TimeoutError) as e:
            _LOGGER.warning("MPD-udgang til fejlede (%s): %s", hvorfor, e)
            return
        self._mpd_ud_fra = False
        _LOGGER.warning("MPD-udgang TIL (%s)", hvorfor)

    async def _async_mpd_ud_til_naar_stille(self) -> None:
        """Til igen så snart MPD ikke spiller (pause/stop) — så radioen virker
        næste gang. Spiller MPD stadig efter 60 s, er det ægte radio → til."""
        await asyncio.sleep(5)
        for _ in range(55):
            if not self._mpd_ud_fra:
                return
            try:
                status = await self._mpd("status")
            except OSError, TimeoutError:
                status = ""
            if status and "state: play" not in status:
                await self._async_mpd_ud_til("MPD står stille")
                return
            await asyncio.sleep(1)
        await self._async_mpd_ud_til("60 s — MPD spiller stadig")

    async def _async_push(self, st: dict) -> None:
        """pushState i realtid (legacy.listen): forhindr spøgelses-radioen og
        opdatér HA med det samme i stedet for ved næste 10-s-poll."""
        # "Radioen spiller, eller stoppede for < 5 s siden": Volumio sender et
        # stop-push MELLEM radio og Spotify (19:22:49-52), og pushes kommer kun
        # ved ændringer (19:41: sidste radio-push 14 s før Spotify) → hverken
        # "forrige push" eller "radio-push < 5 s" så radioen.
        radio_foer = self._radio_spiller or time.monotonic() - self._radio_stoppet < 5
        radio_nu = st.get("status") == "play" and (
            st.get("service") == "webradio" or st.get("trackType") == "webradio"
        )
        if radio_nu:
            self._radio_spiller = True
        elif self._radio_spiller:
            self._radio_spiller = False
            self._radio_stoppet = time.monotonic()
        if st.get("service") == "volspotconnect2" and radio_foer and not self._mpd_ud_fra:
            # Spotify tager over fra radioen: ~1 s efter kommer radioen igen
            # (14:18:16, 14:24:35, 14:34:37, 14:43:38, 14:58:57). Udgangen fra
            # NU → genstarten er lydløs, og Spotify får lyden.
            await self._async_mpd_ud_fra("Spotify tager over fra radioen")
        elif self._er_spoegelse(st) and not self._mpd_ud_fra:
            await self._async_mpd_ud_fra("spøgelse i pushState")
        if self._push_refresh is None or self._push_refresh.done():
            self._push_refresh = self.hass.async_create_background_task(
                self._async_push_refresh(), f"{self.entity_id} push-refresh"
            )

    async def _async_push_refresh(self) -> None:
        await asyncio.sleep(0.3)
        await self.async_update()
        self.async_write_ha_state()

    @override
    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self._legacy:
            self._push_task = self.hass.async_create_background_task(
                legacy.listen(
                    async_get_clientsession(self.hass),
                    self._volumio._host,
                    self._volumio._port,
                    self._async_push,
                ),
                f"{self.entity_id} pushState",
            )

    def _refresh_soon(self) -> None:
        """Vis resultatet af et kald med det samme i stedet for ved næste poll."""
        if self._refresh_task is not None:
            self._refresh_task.cancel()
        self._refresh_task = self.hass.async_create_background_task(
            self._async_refresh_burst(), f"{self.entity_id} refresh"
        )

    async def _async_refresh_burst(self) -> None:
        for delay in REFRESH_AFTER_COMMAND:
            await asyncio.sleep(delay)
            await self.async_update()
            self.async_write_ha_state()

    @property
    @override
    def extra_state_attributes(self) -> dict[str, str | None]:
        """Lys-sidens linje: "start Spotify fra telefonen" når play intet gør."""
        return {"sidst_spillet": self._sidst_spillet}

    @property
    @override
    def supported_features(self) -> MediaPlayerEntityFeature:
        """Kun knapper der gør noget på det der spiller (N3: dashboardet 08/10)."""
        features = self._attr_supported_features
        if self._ma_kilde_aktiv() or self._bro_aktiv():
            # Spotify via HA/broen: pause/næste/forrige går til appen.
            features &= ~(
                MediaPlayerEntityFeature.SHUFFLE_SET | MediaPlayerEntityFeature.REPEAT_SET
            )
        elif self._state.get("trackType") == "webradio":
            features &= ~WEBRADIO_HIDDEN
        if not self._attr_source_list:
            features &= ~MediaPlayerEntityFeature.SELECT_SOURCE
        return features

    @property
    @override
    def state(self) -> MediaPlayerState:
        """Return the state of the device."""
        status = self._state.get("status", None)
        if status == "pause":
            return MediaPlayerState.PAUSED
        if status == "play":
            return MediaPlayerState.PLAYING

        return MediaPlayerState.IDLE

    @property
    @override
    def media_content_type(self) -> MediaType:
        """Webradio = kanal, så automationer kan skelne radio fra Spotify/kø."""
        if self._state.get("trackType") == "webradio":
            return MediaType.CHANNEL
        return MediaType.MUSIC

    @property
    @override
    def app_name(self) -> str | None:
        """Volumio-kilden (webradio, mpd, Spotify …) — radio vs. Spotify (08/10)."""
        return self._state.get("service") or self._state.get("trackType") or None

    @property
    @override
    def media_content_id(self) -> str | None:
        """Stream-URL'en: radioen kan genoptages uden om HA (play-knap, app)."""
        return self._state.get("uri") or None

    @property
    @override
    def media_title(self):
        """Title of current playing media."""
        return self._state.get("title", None)

    @property
    @override
    def media_artist(self):
        """Artist of current playing media (Music track only)."""
        return self._state.get("artist", None)

    @property
    @override
    def media_album_name(self):
        """Artist of current playing media (Music track only)."""
        return self._state.get("album", None)

    @property
    @override
    def media_image_url(self):
        """Image url of current playing media."""
        url = self._state.get("albumart", None)
        return self._volumio.canonic_url(url)

    @property
    def media_seek_position(self):
        """Time in seconds of current seek position."""
        return self._state.get("seek", None)

    @property
    @override
    def media_duration(self):
        """Time in seconds of current song duration."""
        return self._state.get("duration", None)

    @property
    @override
    def volume_level(self):
        """Volume level of the media player (0..1)."""
        volume = self._state.get("volume", None)
        if volume is not None and volume != "":
            volume = int(volume) / 100
        return volume

    @property
    @override
    def is_volume_muted(self):
        """Boolean if volume is currently muted."""
        return self._state.get("mute", None)

    @property
    @override
    def shuffle(self):
        """Boolean if shuffle is enabled."""
        return self._state.get("random", False)

    @property
    @override
    def repeat(self) -> RepeatMode:
        """Return current repeat mode."""
        if self._state.get("repeat", None):
            return RepeatMode.ALL
        return RepeatMode.OFF

    def _ma_kilde_aktiv(self) -> bool:
        """Spotify via HA er det der spiller — eller sidst spillede (play)."""
        if MA_SOURCE.search(self._state.get("uri") or ""):
            return True
        return self._ma_kilde_player is not None and self._state.get("status") != "play"

    def _bro_aktiv(self) -> bool:
        """Spotify-broen spiller — eller er pauset (Volumio husker dens URL)."""
        return BRO_URI in (self._state.get("uri") or "")

    async def _bro_kald(self, cmd: str) -> bool:
        """Én kommando til Spotify-broen (/cmd/<cmd>); appen følger med."""
        try:
            async with (
                asyncio.timeout(5),
                async_get_clientsession(self.hass).post(BRO_CMD + cmd) as resp,
            ):
                svar = await resp.json(content_type=None)
                ok = resp.status == 200 and isinstance(svar, dict) and svar.get("ok") is True
        # aiohttp.ClientError er IKKE altid en OSError (ServerDisconnectedError,
        # ClientPayloadError) — en ufanget fejl her ville vælte hele service-
        # kaldet i stedet for at falde tilbage til Volumio.
        except (aiohttp.ClientError, OSError, TimeoutError, ValueError) as e:
            _LOGGER.warning("Spotify-bro %s fejlede: %s", cmd, e)
            return False
        _LOGGER.info("Spotify-bro %s → %s", cmd, "ok" if ok else "afvist")
        return ok

    @override
    async def async_media_next_track(self) -> None:
        """Send media_next command to media player."""
        if self._bro_aktiv() and await self._bro_kald("next"):
            pass
        elif self._ma_kilde_player and self._ma_kilde_aktiv():
            await self._ma_kald("players/cmd/next", {"player_id": self._ma_kilde_player})
        else:
            await self._volumio.next()
        self._refresh_soon()

    @override
    async def async_media_previous_track(self) -> None:
        """Send media_previous command to media player."""
        if self._bro_aktiv() and await self._bro_kald("prev"):
            pass
        elif self._ma_kilde_player and self._ma_kilde_aktiv():
            await self._ma_kald("players/cmd/previous", {"player_id": self._ma_kilde_player})
        else:
            await self._volumio.previous()
        self._refresh_soon()

    @override
    async def async_media_play(self) -> None:
        """Genoptag det der spillede sidst: MA-køen hvis det var MA, ellers Volumio."""
        if (
            self._sidst_spillet == "volspotconnect2"
            and self._state.get("service") != "volspotconnect2"
        ):
            # Sidst spillede telefonens Spotify (myair), men Volumio har sluppet
            # den: play ville starte den gamle radio-kø. Spotify kan kun startes
            # fra telefonen → ingen radio (user 10/10: "satte spotify på via ha
            # men ha startede radioen i stedet").
            _LOGGER.info("Play ignoreret: sidst spillede Spotify via myair")
            return
        if self._bro_aktiv():
            # Spotify-broen: genoptag Spotify-sessionen (broen sender selv
            # MPD pause 0 eller en ny replaceAndPlay). Broen nede/sessionen
            # væk: Volumio's play på broens døde URL hænger → gør intet
            # (Spotify kan altid startes fra telefonen).
            await self._fra_standby()
            await self._bro_kald("resume")
            self._refresh_soon()
            return
        if self._ma_kilde_player and self._ma_kilde_aktiv():
            # Spotify via HA: MA genoptager go-librespot-sessionen (appen
            # følger med) og starter selv DLNA igen — målt 14/10 13:07:40.
            await self._fra_standby()
            if await self._ma_kald("players/cmd/play", {"player_id": self._ma_kilde_player}):
                self._refresh_soon()
                return
            # MA nede/sessionen væk: Volumio's play på den døde strøm hænger
            # bare → gør intet (Spotify kan altid startes fra telefonen).
            self._ma_kilde_player = None
            return
        m = MA_FLOW.search(self._state.get("uri") or "")
        if m and self._ma_er_ha_sang:
            # Sidst spillede HA's egen sang — den skal ikke spilles igen. Play =
            # radio-favoritten (scriptet hæver selv fra standby).
            _LOGGER.info("Play: sidst spillede HA's sang → radio-favoritten")
            fav = self.hass.states.get("input_select.hoejttaler_radio_favorit")
            await self.hass.services.async_call(
                "script",
                "hoejttaler_radio",
                {"kanal": fav.state if fav else "DR P4 København"},
            )
            self._refresh_soon()
            return
        if m:
            # Standby er stop + volumen 0 (packages/hoejttaler.yaml) — som radioen
            # hæves der til start-volumen, ellers "spiller" den lydløst.
            await self._fra_standby()
            if not await self._ma_kald("player_queues/play", {"queue_id": m.group(1)}):
                # MA kører ikke: flow-URL'en er død, så Volumio's play er tavs →
                # radio-favoritten (scriptet hæver selv fra standby).
                fav = self.hass.states.get("input_select.hoejttaler_radio_favorit")
                await self.hass.services.async_call(
                    "script",
                    "hoejttaler_radio",
                    {"kanal": fav.state if fav else "DR P4 København"},
                )
            self._refresh_soon()
            return
        await self._async_mpd_ud_til("play")
        await self._volumio.play()
        self._refresh_soon()

    async def _fra_standby(self) -> None:
        """Standby er stop + volumen 0 → start-volumen, ellers lydløs afspilning."""
        if (self.volume_level or 0) < 0.01:
            start = self.hass.states.get("input_number.hoejttaler_standby_start_volumen")
            await self._volumio.set_volume_level(int(float(start.state) if start else 25))

    async def _ma_kald(self, command: str, args: dict) -> bool:
        """Én MA-kommando via scripts/ma_api.py (MA's API kræver login)."""
        cmd = json.dumps([[command, args]])
        try:
            proc = await asyncio.create_subprocess_exec(
                "python3",
                MA_API,
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            async with asyncio.timeout(30):
                out, err = await proc.communicate()
        except (OSError, TimeoutError) as e:
            _LOGGER.warning("MA %s %s fejlede: %s", command, args, e)
            return False
        res = out.decode().strip()
        if proc.returncode or "error_code" in res:
            _LOGGER.warning("MA %s %s fejlede: %s", command, args, (err.decode() or res)[-300:])
            return False
        _LOGGER.info("MA %s %s", command, args)
        return True

    @override
    async def async_media_pause(self) -> None:
        """Send media_pause command to media player."""
        if await self._bro_pause() or await self._ma_kilde_pause():
            return
        if self._state.get("trackType") == "webradio":
            await self._volumio.stop()
        else:
            await self._volumio.pause()
            await self._async_insist_stopped("pause")
        self._refresh_soon()

    @override
    async def async_media_stop(self) -> None:
        """Send media_stop command to media player."""
        if await self._bro_pause() or await self._ma_kilde_pause():
            return
        await self._volumio.stop()
        if self._state.get("trackType") != "webradio":
            await self._async_insist_stopped("stop")
        self._refresh_soon()

    async def _bro_pause(self) -> bool:
        """Spotify-broen spiller: pause i appen (broen sætter MPD på pause).

        Stop = pause her, som for Spotify via HA: en Spotify-session har intet
        "stop", og play skal kunne genoptage. Fejler kaldet (broen nede), falder
        vi tilbage til Volumio — broens takeover-tjek pauser så appen selv.
        """
        try:
            async with asyncio.timeout(UPDATE_TIMEOUT):
                self._state = await self._volumio.get_state()
        except CannotConnectError, TimeoutError:
            pass
        if not self._bro_aktiv() or self._state.get("status") != "play":
            return False
        if not await self._bro_kald("pause"):
            return False
        self._refresh_soon()
        return True

    async def _ma_kilde_pause(self) -> bool:
        """Spotify via HA: pause i MA (appen viser pause, play kan genoptage).

        Stop = pause her: en Spotify Connect-session har ingen "stop", og
        Volumio's stop alene efterlod appen spillende mod ingenting (14/10).
        Spiller DLNA stadig 4 s efter, kappes den også, som før. Kaldes også
        før radioen (play_media): ellers "spillede" appen videre, og
        go-librespots dealer hang efter ~90 s uden aftager (14/10 13:20-13:22).
        """
        # FRISK state, ikke 10-s-pollens: P1 valgt 7 s efter Spotify via HA
        # startede så stadig P4 → ingen pause, appen "spillede" videre (13:30).
        try:
            async with asyncio.timeout(UPDATE_TIMEOUT):
                self._state = await self._volumio.get_state()
        except CannotConnectError, TimeoutError:
            pass
        m = MA_SOURCE.search(self._state.get("uri") or "")
        if not m or self._state.get("status") != "play":
            return False
        self._ma_kilde_player = m.group(1)
        if not await self._ma_kald("players/cmd/pause", {"player_id": m.group(1)}):
            return False
        state: dict = {}
        for _ in range(8):
            await asyncio.sleep(0.5)
            try:
                state = await self._volumio.get_state()
            except CannotConnectError:
                state = {}
            if state.get("status") != "play":
                break
        if state.get("status") == "play":
            _LOGGER.info("MA-pause stoppede ikke DLNA inden for 4 s → Volumio stop")
            await self._volumio.stop()
        self._refresh_soon()
        return True

    async def _async_insist_stopped(self, cmd: str) -> None:
        """Spotify (B202): REST-pause ramte IKKE en Spotify-session 08/10 19:03.

        Spiller den stadig 2 s efter REST-kaldet, sendes socket.io `stop` (som
        web-UI'ets knap). Hvilken vej der virkede logges med Volumio-kilden, så
        næste ægte Spotify-session lukker B202's åbne spørgsmål.
        """
        service = self._state.get("service")
        await asyncio.sleep(2)
        try:
            state = await self._volumio.get_state()
        except CannotConnectError:
            return
        if state.get("status") != "play":
            _LOGGER.info("Volumio %s via REST stoppede %s", cmd, service)
            return
        if self._legacy:
            await legacy.emit(
                async_get_clientsession(self.hass),
                self._volumio._host,
                self._volumio._port,
                "stop",
            )
            await asyncio.sleep(2)
            try:
                state = await self._volumio.get_state()
            except CannotConnectError:
                return
        _LOGGER.warning(
            "Volumio %s: REST ramte ikke %s; efter socket.io stop: %s",
            cmd,
            service,
            state.get("status"),
        )

    @override
    async def async_set_volume_level(self, volume: float) -> None:
        """Send volume_up command to media player."""
        await self._volumio.set_volume_level(int(volume * 100))
        self._refresh_soon()

    @override
    async def async_volume_up(self) -> None:
        """Service to send the Volumio the command for volume up."""
        await self._volumio.volume_up()
        self._refresh_soon()

    @override
    async def async_volume_down(self) -> None:
        """Service to send the Volumio the command for volume down."""
        await self._volumio.volume_down()
        self._refresh_soon()

    @override
    async def async_mute_volume(self, mute: bool) -> None:
        """Send mute command to media player."""
        if mute:
            await self._volumio.mute()
        else:
            await self._volumio.unmute()
        self._refresh_soon()

    @override
    async def async_set_shuffle(self, shuffle: bool) -> None:
        """Enable/disable shuffle mode."""
        await self._volumio.set_shuffle(shuffle)
        self._refresh_soon()

    @override
    async def async_set_repeat(self, repeat: RepeatMode) -> None:
        """Set repeat mode."""
        if repeat == RepeatMode.OFF:
            await self._volumio.repeatAll("false")
        else:
            await self._volumio.repeatAll("true")
        self._refresh_soon()

    @override
    async def async_select_source(self, source: str) -> None:
        """Choose an available playlist and play it."""
        await self._volumio.play_playlist(source)
        self._attr_source = source
        self._refresh_soon()

    @override
    async def async_clear_playlist(self) -> None:
        """Clear players playlist."""
        await self._volumio.clear_playlist()
        self._attr_source = None
        self._refresh_soon()

    @Throttle(PLAYLIST_UPDATE_INTERVAL)
    async def _async_update_playlists(self, **kwargs):
        """Update available Volumio playlists."""
        self._attr_source_list = await self._volumio.get_playlists()

    @override
    async def async_play_media(
        self, media_type: MediaType | str, media_id: str, **kwargs: Any
    ) -> None:
        """Send the play_media command to the media player."""
        item = json.loads(media_id)
        # Radioen må aldrig starte lydløst efter en Spotify-overtagelse.
        await self._async_mpd_ud_til("HA starter afspilning")
        # Spotify via HA spiller: pause den i MA først (appen følger med).
        # IKKE broen: dens MPD pause 1 kommer asynkront efter svaret og kunne
        # ramme radioen. Broen ser selv den nye kilde og pauser appen (2,5 s).
        await self._ma_kilde_pause()
        if self._legacy:
            # Efter en knap-tænding står N3 i en tom state uden "status", hvor
            # replaceAndPlay ignoreres indtil et stop (målt 08/10 kl. 18).
            if not self._state.get("status"):
                await self._volumio.stop()
            await legacy.emit(
                async_get_clientsession(self.hass),
                self._volumio._host,
                self._volumio._port,
                "replaceAndPlay",
                item,
            )
        else:
            await self._volumio.replace_and_play(item)
        self._refresh_soon()

    @override
    async def async_will_remove_from_hass(self) -> None:
        if self._refresh_task is not None:
            self._refresh_task.cancel()
        for task in (self._push_task, self._mpd_ud_task):
            if task is not None:
                task.cancel()

    @override
    async def async_browse_media(
        self,
        media_content_type: MediaType | str | None = None,
        media_content_id: str | None = None,
    ) -> BrowseMedia:
        """Implement the websocket media browsing helper."""
        self.thumbnail_cache = {}
        # OEM-firmwaren har ingen REST-browse (302 → KeyError, "Unknown error" i
        # mediebrowseren 08/10) → samme navigation via socket.io.
        library = (
            legacy.Library(async_get_clientsession(self.hass), self._volumio)
            if self._legacy
            else self._volumio
        )
        if media_content_type in (None, "library"):
            return await browse_top_level(library)

        return await browse_node(self, library, media_content_type, media_content_id)

    @override
    async def async_get_browse_image(
        self,
        media_content_type: MediaType | str,
        media_content_id: str,
        media_image_id: str | None = None,
    ) -> tuple[bytes | None, str | None]:
        """Get album art from Volumio."""
        cached_url = self.thumbnail_cache.get(media_content_id)
        image_url = self._volumio.canonic_url(cached_url)
        return await self._async_fetch_image(image_url)
