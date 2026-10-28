"""SchoolGrid School Lunches: one sensor per child per school day showing what has been ordered."""
from __future__ import annotations

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.event import async_track_time_change

from .api import SchoolGridApi
from .coordinator import SchoolGridCoordinator

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]

type SchoolGridConfigEntry = ConfigEntry[SchoolGridCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: SchoolGridConfigEntry) -> bool:
    # Own cookie jar: the SchoolGrid session cookie must not be shared with other integrations.
    session = async_create_clientsession(hass, cookie_jar=aiohttp.CookieJar())
    api = SchoolGridApi(session, entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD])
    coordinator = SchoolGridCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    @callback
    def _new_day(_now) -> None:
        # Roll "today"/"past"/weekend-to-next-week state over at midnight without waiting for the poll.
        hass.async_create_task(coordinator.async_request_refresh())

    entry.async_on_unload(async_track_time_change(hass, _new_day, hour=0, minute=5, second=0))
    entry.async_on_unload(entry.add_update_listener(_reload_on_options))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _reload_on_options(hass: HomeAssistant, entry: SchoolGridConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: SchoolGridConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
