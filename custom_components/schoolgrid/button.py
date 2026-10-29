"""A button to poll SchoolGrid now instead of waiting for the next scheduled refresh."""
from __future__ import annotations

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SchoolGridConfigEntry
from .const import DOMAIN
from .coordinator import SchoolGridCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: SchoolGridConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([RefreshButton(entry.runtime_data, entry.entry_id)])


class RefreshButton(ButtonEntity):
    """One per account. Rate limited by the coordinator (one manual refresh per minute)."""

    _attr_has_entity_name = True
    _attr_name = "Refresh"
    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator: SchoolGridCoordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_refresh"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)}, name="SchoolGrid", manufacturer="SchoolGrid"
        )

    async def async_press(self) -> None:
        await self._coordinator.async_manual_refresh()
