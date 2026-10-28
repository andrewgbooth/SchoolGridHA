"""Sensors per child: lunch and dessert for today and tomorrow, and the food balance."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SchoolGridConfigEntry
from .const import STATUS_HOLIDAY, STATUS_NO_MENU, STATUS_NOT_ORDERED, STATUS_ORDERED
from .coordinator import SchoolGridCoordinator
from .entity import ChildEntity
from .model import DayInfo, no_menu

STATE_TEXT = {STATUS_NOT_ORDERED: "Not ordered", STATUS_HOLIDAY: "No school", STATUS_NO_MENU: "No menu yet"}
ICONS = {
    STATUS_ORDERED: "mdi:food",
    STATUS_NOT_ORDERED: "mdi:food-off-outline",
    STATUS_HOLIDAY: "mdi:calendar-remove",
    STATUS_NO_MENU: "mdi:calendar-question",
}


async def async_setup_entry(
    hass: HomeAssistant, entry: SchoolGridConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    known: set[int] = set()

    @callback
    def _add_new_children() -> None:
        new = []
        for child_id in coordinator.data.children:
            if child_id not in known:
                known.add(child_id)
                new += [
                    LunchSensor(coordinator, child_id, "today", 0),
                    LunchSensor(coordinator, child_id, "tomorrow", 1),
                    DessertSensor(coordinator, child_id, "today", 0),
                    DessertSensor(coordinator, child_id, "tomorrow", 1),
                    BalanceSensor(coordinator, child_id),
                ]
        if new:
            async_add_entities(new)

    _add_new_children()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_children))


class LunchSensor(ChildEntity, SensorEntity):
    """State is the ordered main course, or why there isn't one. The dessert is an attribute."""

    def __init__(self, coordinator: SchoolGridCoordinator, child_id: int, key: str, offset_days: int) -> None:
        super().__init__(coordinator, child_id)
        self._offset = offset_days
        self._attr_unique_id = f"{child_id}_{key}"
        self._attr_name = f"Lunch {key}"

    @property
    def _date(self) -> date:
        return self.coordinator.data.today + timedelta(days=self._offset)

    @property
    def _day(self) -> DayInfo:
        cd = self._child_data
        return (cd.days.get(self._date) if cd else None) or no_menu(self._date)

    @property
    def native_value(self) -> str:
        day = self._day
        if day.status == STATUS_ORDERED:
            return day.main or "Dessert only"
        return STATE_TEXT[day.status]

    @property
    def icon(self) -> str:
        return ICONS[self._day.status]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        day = self._day
        return {"date": day.date.isoformat(), "status": day.status, "dessert": day.dessert}


class DessertSensor(LunchSensor):
    """The dessert as its own entity so it shows on dashboards without opening the attributes."""

    def __init__(self, coordinator: SchoolGridCoordinator, child_id: int, key: str, offset_days: int) -> None:
        super().__init__(coordinator, child_id, key, offset_days)
        self._attr_unique_id = f"{child_id}_dessert_{key}"
        self._attr_name = f"Dessert {key}"

    @property
    def native_value(self) -> str:
        day = self._day
        if day.status == STATUS_ORDERED:
            return day.dessert or "No dessert"
        return STATE_TEXT[day.status]

    @property
    def icon(self) -> str:
        day = self._day
        if day.status == STATUS_ORDERED:
            return "mdi:cupcake" if day.dessert else "mdi:food-off-outline"
        return ICONS[day.status]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"date": self._day.date.isoformat()}


class BalanceSensor(ChildEntity, SensorEntity):
    _attr_name = "Food balance"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "GBP"
    _attr_icon = "mdi:cash"

    def __init__(self, coordinator: SchoolGridCoordinator, child_id: int) -> None:
        super().__init__(coordinator, child_id)
        self._attr_unique_id = f"{child_id}_balance"

    @property
    def native_value(self) -> float | None:
        cd = self._child_data
        return cd.child.balance if cd else None
