"""BLE Irrigation (Pump + Flow) integration for Home Assistant."""

# -----------------------------------------------------------------------------
# Module responsibilities
# -----------------------------------------------------------------------------
# • Register a BLE irrigation device (pump + flow) in HA’s device registry.
# • Create the BLE transport (IrrigationBLE) and the DataUpdateCoordinator.
# • Kick off the initial BLE connection (which also starts notifications).
# • Forward the config entry to platform entities: switch, sensor, binary_sensor.
# • Cleanly disconnect and unload on removal.
#
# Concurrency / lifecycle notes
# -----------------------------
# • async_setup_entry runs in HA’s event loop; do not block.
# • BLE discovery may be slightly delayed after HA boot; we try to fetch a
#   BleDevice by address immediately. If it’s not in the cache yet, we raise
#   to fail setup; HA will retry later (standard HA pattern).
# • The device object holds a reference to the coordinator for state fan-out.
#
# Error handling
# --------------
# • If the BleDevice is not available yet, we raise RuntimeError so HA logs a
#   clear reason and schedules a retry. This is common for BLE flows.

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import async_get as async_get_device_registry
from homeassistant.const import Platform

from .const import DOMAIN, CONF_DEVICE_MAC, CONF_DEVICE_NAME
from .hydro_device import IrrigationBLE
from .coordinator import IrrigationCoordinator

# Platforms provided by this integration:
#   • SWITCH: pump enable/disable
#   • SENSOR: flow rate, pulse count, total volume, etc.
#   • BINARY_SENSOR: flow detected / dry-run flags
PLATFORMS = [Platform.SWITCH, Platform.SENSOR, Platform.BINARY_SENSOR]

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    # Reserved for YAML-based bootstrap (not used here; config entries are UI-driven).
    # Return True so HA proceeds; all real setup is done in async_setup_entry.
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the BLE Hydro integration."""
    # Create root domain bucket if not present:
    # hass.data[DOMAIN][entry_id] stores integration-scoped objects.
    hass.data.setdefault(DOMAIN, {})

    # -------------------------------------------------------------------------
    # 1) Device registry: register a logical device ahead of entity creation.
    #    This ensures a stable device entry for entities to attach to and lets
    #    users rename the device early in the UI.
    # -------------------------------------------------------------------------
    device_registry = async_get_device_registry(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.data[CONF_DEVICE_MAC])},
        manufacturer="Custom",
        model="BLE Hydro",
        name=entry.data.get(CONF_DEVICE_NAME, "Hydro"),
    )

    # -------------------------------------------------------------------------
    # 2) Resolve the underlying BleDevice from HA’s Bluetooth layer.
    #    We use MAC address from the config entry (set by the discovery/flow).
    #    If discovery hasn’t seen the device yet, return None => fail fast so
    #    HA retries setup later (device likely to appear shortly).
    # -------------------------------------------------------------------------
    from homeassistant.components.bluetooth import async_ble_device_from_address
    from homeassistant.exceptions import ConfigEntryNotReady
    ble_device = async_ble_device_from_address(
        hass, entry.data[CONF_DEVICE_MAC], connectable=True
    )
    if ble_device is None:
        # Discovery has not cached the peripheral yet. Raising here lets HA
        # reschedule setup without partially-initialized state.
        raise ConfigEntryNotReady(f"BLE eszköz nem található: {entry.data[CONF_DEVICE_MAC]}")

    # -------------------------------------------------------------------------
    # 3) Instantiate transport + coordinator
    #    IrrigationBLE encapsulates BLE GATT I/O and notifications.
    #    IrrigationCoordinator schedules state refresh and centralizes data flow.
    # -------------------------------------------------------------------------
    device = IrrigationBLE(hass, ble_device)
    coordinator = IrrigationCoordinator(hass, device)
    device.set_coordinator(coordinator)

    # -------------------------------------------------------------------------
    # 4) Connect (starts notify subscriptions inside IrrigationBLE)
    #    This should be non-blocking; underlying library handles retries/backoff.
    # -------------------------------------------------------------------------
    await device.connect()

    # -------------------------------------------------------------------------
    # 5) Store integration objects for later lookup (entities/unload)
    # -------------------------------------------------------------------------
    hass.data[DOMAIN][entry.entry_id] = {
        "device": device,
        "coordinator": coordinator,
    }

    # -------------------------------------------------------------------------
    # 6) Forward to entity platforms
    #    Each platform will call into the coordinator/device to expose entities.
    # -------------------------------------------------------------------------
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # Tear down: pop from domain bucket and disconnect BLE before unloading
    # platforms so no callbacks fire on dead entities.
    data = hass.data[DOMAIN].pop(entry.entry_id, None)
    if data:
        device: IrrigationBLE = data["device"]
        await device.disconnect()
    # Ask HA to unload entities for the listed platforms; returns True on success.
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
