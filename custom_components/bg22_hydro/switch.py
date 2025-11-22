"""Pump switch entity."""

# -----------------------------------------------------------------------------
# Purpose
# -------
# • Represent the irrigation pump as a controllable Home Assistant switch.
# • Forward user actions (turn_on / turn_off) to the BLE device.
# • Reflect current pump state (on/off) based on coordinator data updates.
#
# Data flow
# ---------
#   HA UI → PumpSwitch.async_turn_on/off → IrrigationBLE.turn_on/off()
#   BLE notify → coordinator.handle_state_update() → async_set_updated_data()
#   → entity refresh → is_on property updates
#
# Notes
# -----
# • CoordinatorEntity provides automatic refresh when the coordinator’s data changes.
# • The device control methods (turn_on / turn_off) are async BLE writes
#   handled by IrrigationBLE; failures will log through bleak exceptions.
# • No polling — state updates rely solely on push notifications.
# • Unique IDs derived from config_entry ensure stable entity IDs.
# -----------------------------------------------------------------------------

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN, CONF_DEVICE_NAME, CONF_DEVICE_MAC
from .hydro_device import IrrigationBLE
from .coordinator import IrrigationCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the pump switch entity for the BLE Hydro integration."""
    data = hass.data[DOMAIN][entry.entry_id]
    device: IrrigationBLE = data["device"]
    coordinator = data["coordinator"]

    device_name = entry.data.get(CONF_DEVICE_NAME, "Hydro")
    mac = entry.data.get(CONF_DEVICE_MAC, entry.entry_id)
    uid_base = f"{entry.entry_id}"

    # Register the pump switch
    async_add_entities([
        PumpSwitch(coordinator, device, device_name, mac, f"{uid_base}_pump"),
    ])


class PumpSwitch(CoordinatorEntity, SwitchEntity):
    """Switch entity controlling the irrigation pump via BLE."""
    
    def __init__(self, coordinator, device, name, mac, unique_id):
        """Initialize the pump switch."""
        super().__init__(coordinator)
        self._device = device
        self._attr_name = f"{name} Pump"
        self._attr_unique_id = unique_id
        self._mac = mac

    @property
    def is_on(self):
        """Return True if the pump is currently ON."""
        data = self.coordinator.data or {}
        return bool(data.get("pump_on", False))

    async def async_turn_on(self):
        """Send BLE command to turn the pump ON."""
        await self._device.turn_on()

    async def async_turn_off(self):
        """Send BLE command to turn the pump OFF."""
        await self._device.turn_off()
