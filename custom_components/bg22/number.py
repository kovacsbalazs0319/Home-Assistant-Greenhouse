import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.number import NumberEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DOMAIN
from .bg import BG22Instance
from .coordinator import BG22Coordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    instance: BG22Instance = data["instance"]
    coordinator: BG22Coordinator = data["coordinator"]

    device_name = entry.data["device_name"]
    mac = instance._mac

    async_add_entities([
        PositionSetNumber(coordinator, device_name, mac, instance),
    ])


class PositionSetNumber(CoordinatorEntity, NumberEntity):
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_unit_of_measurement = "%"
    _attr_mode = "slider"
    _attr_should_poll = False

    def __init__(self, coordinator: BG22Coordinator, name: str, mac: str, instance: BG22Instance):
        super().__init__(coordinator)
        self._attr_name = f"{name} Position Set"
        self._mac = mac
        self._device = instance

    @property
    def unique_id(self) -> str:
        return f"bg22_{self._mac.replace(':', '_')}_position_set"

    
    @property
    def native_value(self):
        return self.coordinator.data.get("target_position", 0)


    async def async_set_native_value(self, value: float) -> None:
        await self._device.write_position(int(value))
        self.coordinator.handle_target_position(int(value))
