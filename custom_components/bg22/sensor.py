import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.sensor import SensorEntity
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
        PositionFeedbackSensor(coordinator, device_name, mac),
        MotorErrorSensor(coordinator, device_name, mac),
    ])


class PositionFeedbackSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator: BG22Coordinator, name: str, mac: str):
        super().__init__(coordinator)
        self._attr_name = f"{name} Position Feedback"
        self._attr_unit_of_measurement = "%"
        self._mac = mac

    @property
    def unique_id(self):
        return f"bg22_{self._mac.replace(':', '_')}_position_feedback"

    @property
    def native_value(self):
        return self.coordinator.data.get("position_feedback", 0)


class MotorErrorSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator: BG22Coordinator, name: str, mac: str):
        super().__init__(coordinator)
        self._attr_name = f"{name} Motor Error"
        self._mac = mac

    @property
    def unique_id(self):
        return f"bg22_{self._mac.replace(':', '_')}_error"

    @property
    def native_value(self):
        return self.coordinator.data.get("error", 0)
