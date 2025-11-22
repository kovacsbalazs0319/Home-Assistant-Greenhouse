"""Config flow for BG22 Light integration."""
from __future__ import annotations

import dataclasses
import logging
from typing import Any, Dict
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import BluetoothServiceInfo, async_discovered_service_info
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

@dataclasses.dataclass
class DiscoveredDevice:
    """Represents a discovered BG22 Bluetooth device."""
    name: str
    address: str
    discovery_info: BluetoothServiceInfo

class BG22ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the config flow for BG22 Light."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovered_devices: Dict[str, DiscoveredDevice] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> config_entries.FlowResult:
        """Handle user-initiated setup by showing discovered devices."""
        current_addresses = self._async_current_ids()

        
        for discovery_info in async_discovered_service_info(self.hass):
            if discovery_info.address in current_addresses or discovery_info.address in self._discovered_devices:
                continue
            self._store_discovered_device(discovery_info)

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        
        if len(self._discovered_devices) == 1:
            device = next(iter(self._discovered_devices.values()))
            self.context.setdefault("title_placeholders", {})["name"] = device.name  
            return self.async_create_entry(
                title=device.name,
                data={
                    "device_mac": device.address,
                    "device_name": device.name
                }
            )

        
        return self.async_show_form(
            step_id="select_device",
            data_schema=vol.Schema({
                vol.Required(CONF_ADDRESS): vol.In(
                    {addr: dev.name for addr, dev in self._discovered_devices.items()}
                )
            })
        )

    async def async_step_select_device(self, user_input: dict[str, Any]) -> config_entries.FlowResult:
        """Handle device selection."""
        address = user_input[CONF_ADDRESS]
        device = self._discovered_devices[address]

        _LOGGER.debug(f"Selected device: {device.name}, Address: {device.address}")

        self.context.setdefault("title_placeholders", {})["name"] = device.name 

        return self.async_create_entry(
            title=device.name,
            data={
                "device_mac": device.address,
                "device_name": device.name
            }
        )       

    async def async_step_bluetooth(self, discovery_info: BluetoothServiceInfo) -> config_entries.FlowResult:
        """Handle Bluetooth discovery."""
        _LOGGER.debug("Discovered Bluetooth device: %s", discovery_info.address)

        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        device_name = discovery_info.name or f"BG22 Device {discovery_info.address[-5:]}"
        self.context.setdefault("title_placeholders", {})["name"] = device_name  
        self._store_discovered_device(discovery_info)

        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(self, user_input: dict[str, Any] | None = None) -> config_entries.FlowResult:
        """Confirm the discovered device before adding it."""
        title = self.context.get("title_placeholders", {}).get("name", "Unknown Device")

        if user_input is not None:
            return self.async_create_entry(
                title=title,
                data={"device_mac": self._discovered_devices[self.unique_id].address}
            )

        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={"name": title},
        )

    def _store_discovered_device(self, discovery_info: BluetoothServiceInfo):
        """Helper function to store a discovered device."""
        address = discovery_info.address
        if address not in self._discovered_devices:
            self._discovered_devices[address] = DiscoveredDevice(
                name=discovery_info.name or f"BG22 Device {discovery_info.address[-5:]}",
                address=address,
                discovery_info=discovery_info
            )

class BG22OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle an options flow for BG22 Light."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options_schema = vol.Schema({
            vol.Optional("custom_setting", default=self.config_entry.options.get("custom_setting", False)): bool
        })

        return self.async_show_form(step_id="init", data_schema=options_schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        """Return the options flow handler."""
        return BG22OptionsFlowHandler(config_entry)
