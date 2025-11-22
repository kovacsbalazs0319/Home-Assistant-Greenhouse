"""Coordinator for BG22 BLE device state updates."""
import logging
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

class BG22Coordinator(DataUpdateCoordinator):
    """DataUpdateCoordinator for managing BG22 device state updates."""

    def __init__(self, hass, instance):
        """Initialize the BG22Coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="BG22 BLE Coordinator",
            update_interval=None,  # push mode, event driven
        )
        self.instance = instance
        # States for HA
        self.data = {
            "position_feedback": 0,
            "error": 0,
            "target_position": 0,
        }

    async def _async_update_data(self):
        _LOGGER.debug("Coordinator: data = %s", self.data)
        return self.data

    def handle_position_feedback(self, value: int):
        self.data["position_feedback"] = value
        _LOGGER.debug("Coordinator updated: position_feedback = %s", value)
        self.async_set_updated_data(self.data)

    def handle_error(self, code: int):
        self.data["error"] = code
        _LOGGER.debug("Coordinator updated: error = %s", code)
        self.async_set_updated_data(self.data)

    def handle_target_position(self, value: int):
        self.data["target_position"] = value
        _LOGGER.debug("Coordinator updated: target_position = %s", value)
        self.async_set_updated_data(self.data)
