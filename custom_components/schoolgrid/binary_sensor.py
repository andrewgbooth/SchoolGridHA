"""Per child: is there an upcoming school day with no lunch ordered?"""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SchoolGridConfigEntry
from .const import STATUS_NOT_ORDERED
from .sensor import _ChildEntity


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


class MissingOrdersSensor(_ChildEntity, BinarySensorEntity):
    """On when a future school day has a menu but no order. Today is excluded (the cut-off may have passed)."""

    _attr_name = "Lunch orders missing"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator, child_id: int) -> None:
        super().__init__(coordinator, child_id)
        self._attr_unique_id = f"{child_id}_missing"

    def _missing(self) -> list[str]:
        cd, today = self._child_data, self.coordinator.data.today
        if not cd:
            return []
        return sorted(
            d.isoformat() for d, info in cd.days.items() if info.status == STATUS_NOT_ORDERED and d > today
        )

    @property
    def is_on(self) -> bool:
        return bool(self._missing())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        missing = self._missing()
        return {"dates": missing, "next_missing": missing[0] if missing else None}
