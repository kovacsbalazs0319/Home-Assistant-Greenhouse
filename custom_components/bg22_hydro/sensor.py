"""Sensors: flow rate + total volume."""

# -----------------------------------------------------------------------------
# Purpose
# -------
# • Expose read-only sensor entities backed by the push-style coordinator:
#     - FlowRateSensor: current flow in L/min.
#     - TotalVolumeSensor: accumulated delivered volume in liters.
#     - ErrorCodeSensor: numeric error code with a human-readable attribute.
#
# Data source
# -----------
# • All values are read from coordinator.data (set by the BLE device wrapper).
# • No polling: CoordinatorEntity wires updates via async_set_updated_data().
#
# Watch outs
# --------------------------------------
# • _HydroSensorBase contains references to hass/entry/async_add_entities that
#   are not in scope here and will raise if executed. It also tries to add
#   entities from inside a base class constructor, which is not the usual HA
#   pattern. If this class is unused, consider removing it later.
# • Units and device classes:
#   - Flow uses a plain unit string "L/min" (no SensorDeviceClass).
#   - Total volume uses SensorDeviceClass.VOLUME + TOTAL_INCREASING state class.
# • ERROR_STR maps only 0 and 1; other codes will show "Unknown".
# -----------------------------------------------------------------------------

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONF_DEVICE_NAME, CONF_DEVICE_MAC

# Simple text mapping for error codes shown as an extra attribute on ErrorCodeSensor
ERROR_STR = {
    0: "OK",
    1: "Low flow",
}

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up sensor entities for the BLE Hydro integration."""
    # Coordinator and device objects were created/stored by __init__.py
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    device = data["device"]

    device_name = entry.data.get(CONF_DEVICE_NAME, "Hydro")
    mac = entry.data[CONF_DEVICE_MAC]
    uid_base = f"{entry.entry_id}"

    # Register three sensors bound to this config entry
    async_add_entities([
        FlowRateSensor(coordinator, device, device_name, mac, f"{uid_base}_flow_rate"),
        ErrorCodeSensor(coordinator, device, device_name, mac, f"{uid_base}_error"),
        TotalVolumeSensor(coordinator, device, device_name, mac, f"{uid_base}_total_volume"),
    ])


class _HydroSensorBase(CoordinatorEntity, SensorEntity):
    """Common base with standard flags/device info (NOTE: see watch outs above)."""
    _attr_should_poll = False

    def __init__(self, coordinator, device_name: str, mac: str, unique_id: str) -> None:
        super().__init__(coordinator)
        # Unique ID allows HA to de-duplicate entities
        self._attr_unique_id = unique_id
        # Device card metadata so these sensors group under the BLE Hydro device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, mac)},
            manufacturer="Custom",
            model="BLE Hydro",
            name=device_name,
        )
        # ---- The code below references hass/entry/async_add_entities in a scope
        #      where they don’t exist; leaving unchanged per request. ----
        data = hass.data[DOMAIN][entry.entry_id]
        device = data["device"]
        coordinator = data["coordinator"]
        async_add_entities([
            FlowRateSensor(coordinator, device, device_name, mac, f"{uid_base}_flow_rate"),
            ErrorCodeSensor(coordinator, device, device_name, mac, f"{uid_base}_error"), ])


class FlowRateSensor(CoordinatorEntity, SensorEntity):
    """Instantaneous flow rate reported by the device (L/min)."""
    def __init__(self, coordinator, device, name, mac, unique_id):
        super().__init__(coordinator)
        self._device = device
        self._attr_name = f"{name} Flow rate"
        self._attr_unique_id = unique_id
        self._mac = mac
        self._attr_native_unit_of_measurement = "L/min"

    @property
    def native_value(self):
        """Return the latest flow rate in L/min (float) or None if unknown."""
        data = self.coordinator.data or {}
        return data.get("flow_lpm")


class TotalVolumeSensor(CoordinatorEntity, SensorEntity):
    """Total delivered volume since HA start (integrated by the device wrapper)."""
    _attr_device_class = SensorDeviceClass.VOLUME
    _attr_native_unit_of_measurement = "L"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, coordinator, device, name, mac, unique_id):
        super().__init__(coordinator)
        self._device = device
        self._attr_name = f"{name} Total Volume"
        self._attr_unique_id = unique_id
        self._mac = mac
        self._attr_icon = "mdi:cup-water"

    @property
    def native_value(self):
        """Return total volume in liters (float) or None if unknown."""
        data = self.coordinator.data or {}
        return data.get("total_volume_l")

class ErrorCodeSensor(CoordinatorEntity, SensorEntity):
    """Numeric error-code sensor (0 = OK). Shows a friendly text attribute."""

    def __init__(self, coordinator, device, name, mac, unique_id):
        super().__init__(coordinator)
        self._device = device
        self._attr_name = f"{name} Error code"
        self._attr_unique_id = unique_id
        self._mac = mac
        # Static icon; you could dynamically switch based on code if desired
        self._attr_icon = "mdi:alert-circle-outline"

    @property
    def native_value(self):
        """Return the raw numeric error code from the coordinator (int)."""
        data = self.coordinator.data or {}
        return data.get("error_code")

    @property
    def extra_state_attributes(self):
        """Provide a human-readable text for the current error code."""
        code = (self.coordinator.data or {}).get("error_code")
        if code is None:
            return None
        return {
            "error_text": ERROR_STR.get(code, "Unknown"),
        }
