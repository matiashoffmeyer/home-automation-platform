# Modified from Home Assistant Core 2026.9.2 (Apache License 2.0); the changes are listed in README.md.
"""The Volumio integration."""

from dataclasses import dataclass
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pyvolumio import CannotConnectError, Volumio

from . import legacy

PLATFORMS = [Platform.MEDIA_PLAYER]


@dataclass
class VolumioData:
    """Volumio data class."""

    volumio: Volumio
    info: dict[str, Any]


type VolumioConfigEntry = ConfigEntry[VolumioData]


async def async_setup_entry(hass: HomeAssistant, entry: VolumioConfigEntry) -> bool:
    """Set up Volumio from a config entry."""

    volumio = Volumio(entry.data[CONF_HOST], entry.data[CONF_PORT], async_get_clientsession(hass))
    try:
        info = await volumio.get_system_version()
    except CannotConnectError as error:
        raise ConfigEntryNotReady from error

    # OEM-firmware uden getSystemVersion over REST (pyvolumio giver {}):
    # spørg via socket.io, og husk at play_media skal samme vej (legacy.py).
    if "hardware" not in info:
        try:
            sio = await legacy.emit(
                async_get_clientsession(hass),
                entry.data[CONF_HOST],
                entry.data[CONF_PORT],
                "getSystemVersion",
                reply="pushSystemVersion",
            )
        except (aiohttp.ClientError, TimeoutError, ValueError) as error:
            raise ConfigEntryNotReady from error
        info = {"hardware": "Volumio", "systemversion": None, **(sio or {})}
        info["legacy"] = True

    entry.runtime_data = VolumioData(volumio=volumio, info=info)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: VolumioConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
