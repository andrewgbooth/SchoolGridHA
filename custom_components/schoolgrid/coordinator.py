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
from .const import CONF_WEEKS, DEFAULT_WEEKS, DOMAIN, SCAN_INTERVAL
from .model import Child, DayInfo, parse_children, parse_days, week_start

_LOGGER = logging.getLogger(__name__)


@dataclass
class ChildData:
    child: Child
    days: dict[date, DayInfo] = field(default_factory=dict)


@dataclass
class SchoolGridData:
    today: date
    start: date  # Monday of the first week shown
    children: dict[int, ChildData]


class SchoolGridCoordinator(DataUpdateCoordinator[SchoolGridData]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: SchoolGridApi) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=SCAN_INTERVAL)
        self.api = api

    @property
    def weeks(self) -> int:
        return int(self.config_entry.options.get(CONF_WEEKS, DEFAULT_WEEKS))

    async def _async_update_data(self) -> SchoolGridData:
        today = dt_util.now().date()
        start = week_start(today)
        end = start + timedelta(days=7 * self.weeks - 1)
        try:
            children = parse_children(await self.api.accounts())

            async def load(child: Child) -> ChildData:
                menus, orders = await asyncio.gather(
                    self.api.menus(child.id, start.isoformat(), end.isoformat()),
                    self.api.orders(child.id, start.isoformat(), end.isoformat()),
                )
                return ChildData(child, parse_days(menus, orders, today))

            loaded = await asyncio.gather(*(load(c) for c in children))
        except AuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except SchoolGridError as err:
            raise UpdateFailed(str(err)) from err
        return SchoolGridData(today, start, {c.child.id: c for c in loaded})
