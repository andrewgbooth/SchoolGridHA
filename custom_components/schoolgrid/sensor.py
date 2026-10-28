"""Sensors: one per child per school day (Mon-Fri, this week and following), plus the food balance."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import voluptuous as vol
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_platform
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SchoolGridConfigEntry
from .api import SchoolGridError
from .const import (
    DOMAIN, SERVICE_PLACE_ORDER, STATUS_HOLIDAY, STATUS_NO_MENU, STATUS_NOT_ORDERED, STATUS_ORDERED, STATUS_PAST,
)
from .coordinator import SchoolGridCoordinator
from .model import DayInfo, Dish, no_menu

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
STATE_TEXT = {
    STATUS_NOT_ORDERED: "Not ordered",
    STATUS_PAST: "No order",
    STATUS_HOLIDAY: "No school",
    STATUS_NO_MENU: "No menu yet",
}
ICONS = {
    STATUS_ORDERED: "mdi:food",
    STATUS_NOT_ORDERED: "mdi:food-off-outline",
    STATUS_PAST: "mdi:food-off",
    STATUS_HOLIDAY: "mdi:calendar-remove",
    STATUS_NO_MENU: "mdi:calendar-question",
}


def device_info(child_id: int, name: str, school: str) -> DeviceInfo:
    return DeviceInfo(identifiers={(DOMAIN, str(child_id))}, name=name, manufacturer="SchoolGrid", model=school)


def _week_label(week: int) -> str:
    return {0: "this", 1: "next"}.get(week, f"+{week}w")


def _match(dishes: list[Dish], text: str, what: str) -> Dish:
    """Find a dish by recipe id, exact name or unique partial name (case-insensitive)."""
    t = text.strip().casefold()
    exact = [d for d in dishes if str(d.recipe_id) == t or d.name.casefold() == t]
    found = exact or [d for d in dishes if t in d.name.casefold()]
    if len(found) == 1:
        return found[0]
    options = "; ".join(d.name for d in dishes) or "none available"
    reason = "is ambiguous" if found else "was not found"
    raise ServiceValidationError(f"{what} '{text}' {reason}. Options: {options}")


async def async_setup_entry(
    hass: HomeAssistant, entry: SchoolGridConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    known: set[int] = set()

    @callback
    def _add_new_children() -> None:
        new = []
        for child_id, cd in coordinator.data.children.items():
            if child_id in known:
                continue
            known.add(child_id)
            new.append(BalanceSensor(coordinator, child_id))
            for week in range(coordinator.weeks):
                for weekday in range(5):
                    new.append(LunchDaySensor(coordinator, child_id, week, weekday))
        if new:
            async_add_entities(new)

    _add_new_children()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_children))

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_PLACE_ORDER,
        {vol.Required("main"): cv.string, vol.Optional("dessert"): cv.string},
        "async_place_order",
    )


class _ChildEntity(CoordinatorEntity[SchoolGridCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: SchoolGridCoordinator, child_id: int) -> None:
        super().__init__(coordinator)
        self._child_id = child_id
        child = coordinator.data.children[child_id].child
        self._attr_device_info = device_info(child_id, child.name, child.school_name)

    @property
    def _child_data(self):
        return self.coordinator.data.children.get(self._child_id)

    @property
    def available(self) -> bool:
        return super().available and self._child_data is not None


class BalanceSensor(_ChildEntity, SensorEntity):
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


class LunchDaySensor(_ChildEntity, SensorEntity):
    """State is the ordered main, or why there isn't one. Attributes carry the dessert and the menu."""

    _unrecorded_attributes = frozenset({"main_options", "dessert_options"})

    def __init__(self, coordinator: SchoolGridCoordinator, child_id: int, week: int, weekday: int) -> None:
        super().__init__(coordinator, child_id)
        self._week = week
        self._weekday = weekday
        self._attr_unique_id = f"{child_id}_w{week}_d{weekday}"
        self._attr_name = f"Lunch {_week_label(week)} {WEEKDAYS[weekday]}"

    @property
    def _date(self) -> date:
        return self.coordinator.data.start + timedelta(weeks=self._week, days=self._weekday)

    @property
    def _day(self) -> DayInfo:
        cd = self._child_data
        return (cd.days.get(self._date) if cd else None) or no_menu(self._date)

    @property
    def native_value(self) -> str:
        day = self._day
        return day.main if day.status == STATUS_ORDERED else STATE_TEXT[day.status]

    @property
    def icon(self) -> str:
        return ICONS[self._day.status]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        day = self._day
        return {
            "date": day.date.isoformat(),
            "status": day.status,
            "dessert": day.dessert,
            "order_id": day.order_id,
            "can_order": day.status == STATUS_NOT_ORDERED,
            "main_options": [d.name for d in day.mains if not d.sold_out and not d.needs_choice],
            "dessert_options": [d.name for d in day.desserts if not d.sold_out and not d.needs_choice],
        }

    async def async_place_order(self, main: str, dessert: str | None = None) -> None:
        """Place (never change or cancel) the lunch order for this day. Main and dessert go in together."""
        day, cd = self._day, self._child_data
        if cd is None or day.status == STATUS_NO_MENU:
            raise ServiceValidationError(f"No menu is published for {day.date} yet.")
        if day.status == STATUS_HOLIDAY:
            raise ServiceValidationError(f"No lunch service on {day.date}.")
        if day.status == STATUS_ORDERED:
            raise ServiceValidationError(
                f"{cd.child.first_name} already has an order for {day.date} ({day.main}). "
                "This integration can't change or cancel orders; use the SchoolGrid website."
            )
        if day.status == STATUS_PAST:
            raise ServiceValidationError(f"{day.date} is in the past.")

        main_dish = _match(day.mains, main, "Main")
        dessert_dish = _match(day.desserts, dessert, "Dessert") if dessert else None
        for dish in (main_dish, dessert_dish):
            if dish and dish.sold_out:
                raise ServiceValidationError(f"{dish.name} is sold out.")
            if dish and dish.needs_choice:
                raise ServiceValidationError(f"{dish.name} needs a sub-choice; order it on the SchoolGrid website.")

        api, child = self.coordinator.api, cd.child
        iso = day.date.isoformat()
        try:
            if await api.orders(child.id, iso, iso):  # someone may have ordered since the last poll
                await self.coordinator.async_request_refresh()
                raise ServiceValidationError(f"{child.first_name} already has an order for {iso}.")
            stypes = await api.service_types(child.school_id, child.client_id)
            stype = next(s["id"] for s in stypes if s["clientServiceTypeId"] == day.service_id)
            result = await api.insert_order(
                {
                    "id": 0, "customerId": child.id, "mealDate": f"{iso}T00:00:00",
                    "mainCourseId": main_dish.recipe_id,
                    "dessertId": dessert_dish.recipe_id if dessert_dish else None,
                    "customOrder": None, "menuAssignmentId": day.menu_assignment_id, "isLocked": True,
                    "schoolServiceTypeId": stype, "schoolId": child.school_id, "yearId": child.year_id,
                }
            )
        except SchoolGridError as err:
            raise HomeAssistantError(f"SchoolGrid order failed: {err}") from err
        except StopIteration as err:
            raise HomeAssistantError("Could not find the lunch service type for this school.") from err
        if isinstance(result, dict) and result.get("isSoldOut"):
            raise ServiceValidationError("That item has just sold out.")
        await self.coordinator.async_request_refresh()
