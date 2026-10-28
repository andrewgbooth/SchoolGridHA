"""Shared base entity: everything hangs off one device per child."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ChildData, SchoolGridCoordinator


class ChildEntity(CoordinatorEntity[SchoolGridCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: SchoolGridCoordinator, child_id: int) -> None:
        super().__init__(coordinator)
        self._child_id = child_id
        child = coordinator.data.children[child_id].child
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(child_id))}, name=child.name, manufacturer="SchoolGrid", model=child.school_name
        )

    @property
    def _child_data(self) -> ChildData | None:
        return self.coordinator.data.children.get(self._child_id)

    @property
    def available(self) -> bool:
        return super().available and self._child_data is not None
