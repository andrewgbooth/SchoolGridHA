"""SchoolGrid School Lunches: what has been ordered for school lunch today and tomorrow (read-only)."""
from __future__ import annotations

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.event import async_track_time_change

from .api import SchoolGridApi
from .coordinator import SchoolGridCoordinator

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON]

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
        # "Today" and "tomorrow" move on at midnight; refresh then rather than waiting for the next poll.
        # Scheduled, so it bypasses the on-demand cooldown.
        hass.async_create_task(coordinator.async_refresh())

    entry.async_on_unload(async_track_time_change(hass, _new_day, hour=0, minute=5, second=0))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SchoolGridConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
