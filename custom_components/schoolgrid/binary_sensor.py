"""Per child: is a school lunch order missing for today or tomorrow?"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SchoolGridConfigEntry
from .const import STATUS_NOT_ORDERED
from .coordinator import SchoolGridCoordinator
from .entity import ChildEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: SchoolGridConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    known: set[int] = set()

    @callback
    def _add_new_children() -> None:
        new = [MissingOrdersSensor(coordinator, cid) for cid in coordinator.data.children if cid not in known]
        known.update(e._child_id for e in new)
        if new:
            async_add_entities(new)

    _add_new_children()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_children))


class MissingOrdersSensor(ChildEntity, BinarySensorEntity):
    """On when today or tomorrow is a school day with no lunch ordered (weekends and holidays never count)."""

    _attr_name = "Lunch orders missing"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: SchoolGridCoordinator, child_id: int) -> None:
        super().__init__(coordinator, child_id)
        self._attr_unique_id = f"{child_id}_missing"

    def _missing(self) -> list[str]:
        cd = self._child_data
        if not cd:
            return []
        today = self.coordinator.data.today
        days = (today, today + timedelta(days=1))
        return [d.isoformat() for d in days if (i := cd.days.get(d)) and i.status == STATUS_NOT_ORDERED]

    @property
    def is_on(self) -> bool:
        return bool(self._missing())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"dates": self._missing()}
