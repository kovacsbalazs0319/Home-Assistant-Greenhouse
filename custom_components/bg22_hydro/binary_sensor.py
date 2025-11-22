# -----------------------------------------------------------------------------
# binary_sensor.py — Flow detection (on/off) binary sensor for BLE Hydro
# -----------------------------------------------------------------------------
#
# Responsibilities
# ----------------
# • Define binary sensor entity class (FlowDetectedBinary) that reflects
#   whether the system detects active water flow.
# • Bind to IrrigationCoordinator for state updates (coordinator.data).
# • Expose the “flow_detected” flag as an HA binary_sensor.
#
# Entity model
# ------------
# Each binary sensor is tied to a config entry (unique_id derived from entry_id).
# The coordinator periodically refreshes its .data dict from BLE notifications.
# The entity reads its on/off state from coordinator.data["flow_detected"].
#
# Behavior
# --------
# • Returns True when flow is detected, False otherwise.
# • Uses a static icon (mdi:water-pump). Device class may be set if available.
# • Update is automatic via DataUpdateCoordinator; no polling.

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from .const import DOMAIN, CONF_DEVICE_NAME, CONF_DEVICE_MAC

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    # Retrieve coordinator + device objects created in __init__.py
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    device = data["device"]
    
    # Friendly name, MAC, and unique_id base derived from entry data
    name = entry.data.get(CONF_DEVICE_NAME, "Hydro")
    mac = entry.data[CONF_DEVICE_MAC]
    uid_base = entry.entry_id

    # Register entities
    async_add_entities([
        FlowDetectedBinary(coordinator, device, name, mac, f"{uid_base}_flow_detected"),
    ])

class FlowDetectedBinary(CoordinatorEntity, BinarySensorEntity):
    

    def __init__(self, coordinator, device, name, mac, unique_id):
        super().__init__(coordinator)
        self._device = device

        # Standard HA metadata
        self._attr_name = f"{name} Flow Detected"
        self._attr_unique_id = unique_id
        self._mac = mac
        self._attr_icon = "mdi:water-pump"

    @property
    def is_on(self):
        """Return True if flow is detected."""
        # coordinator.data is expected to be a dict updated by IrrigationCoordinator
        data = self.coordinator.data or {}
        return bool(data.get("flow_detected", False))
