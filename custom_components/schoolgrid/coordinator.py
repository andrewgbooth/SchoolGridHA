"""Data coordinator for SchoolGrid."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import AuthError, SchoolGridApi, SchoolGridError
from .const import DOMAIN, SCAN_INTERVAL
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
