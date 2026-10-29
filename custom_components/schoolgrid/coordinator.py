"""Data coordinator for SchoolGrid."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import AuthError, SchoolGridApi, SchoolGridError
from .const import DOMAIN, MANUAL_REFRESH_COOLDOWN, SCAN_INTERVAL
from .model import Child, DayInfo, parse_children, parse_days

_LOGGER = logging.getLogger(__name__)


@dataclass
class ChildData:
    child: Child
    days: dict[date, DayInfo] = field(default_factory=dict)


@dataclass
class SchoolGridData:
    today: date
    children: dict[int, ChildData]


class SchoolGridCoordinator(DataUpdateCoordinator[SchoolGridData]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: SchoolGridApi) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=SCAN_INTERVAL)
        self.api = api
        self._last_manual_refresh = None

    def _cooldown_left(self) -> int:
        """Seconds until another on-demand refresh is allowed (0 if allowed now)."""
        if not self._last_manual_refresh:
            return 0
        left = MANUAL_REFRESH_COOLDOWN - (dt_util.utcnow() - self._last_manual_refresh)
        return max(0, int(left.total_seconds()) + 1) if left.total_seconds() > 0 else 0

    async def async_manual_refresh(self) -> None:
        """Refresh on demand (the button), at most once per cooldown so it can't hammer SchoolGrid."""
        if wait := self._cooldown_left():
            raise HomeAssistantError(f"SchoolGrid was refreshed manually a moment ago; try again in {wait}s")
        self._last_manual_refresh = dt_util.utcnow()
        await self.async_refresh()

    async def async_request_refresh(self) -> None:
        """Other on-demand refreshes (e.g. homeassistant.update_entity) share the button's cooldown."""
        if self._cooldown_left():
            _LOGGER.debug("Ignoring refresh request during the manual refresh cooldown")
            return
        self._last_manual_refresh = dt_util.utcnow()
        await super().async_request_refresh()

    async def _async_update_data(self) -> SchoolGridData:
        today = dt_util.now().date()
        start, end = today.isoformat(), (today + timedelta(days=1)).isoformat()
        try:
            children = parse_children(await self.api.accounts())

            async def load(child: Child) -> ChildData:
                menus, orders = await asyncio.gather(
                    self.api.menus(child.id, start, end), self.api.orders(child.id, start, end)
                )
                return ChildData(child, parse_days(menus, orders))

            loaded = await asyncio.gather(*(load(c) for c in children))
        except AuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except SchoolGridError as err:
            raise UpdateFailed(str(err)) from err
        return SchoolGridData(today, {c.child.id: c for c in loaded})
