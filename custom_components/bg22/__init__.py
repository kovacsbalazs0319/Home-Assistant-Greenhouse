"""BG22 BLE Light integration for Home Assistant."""
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import async_get as async_get_device_registry

from .const import DOMAIN
from .bg import BG22Instance
from .coordinator import BG22Coordinator

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up BG22 integration."""
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up BG22 integration via UI."""
    device_registry = async_get_device_registry(hass)

    #Register device into registry
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.data["device_mac"])},
        manufacturer="Silicon Labs",
        model="BG22",
        name=entry.data["device_name"]
    )

    mac = entry.data["device_mac"]
    instance = BG22Instance(mac)
    coordinator = BG22Coordinator(hass, instance)
    instance.set_coordinator(coordinator)
    await instance.connect()

    #Using built_in hass.data do sync with coordinator
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "instance": instance,
        "coordinator": coordinator,
    }

    
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor", "number"])


    return True
