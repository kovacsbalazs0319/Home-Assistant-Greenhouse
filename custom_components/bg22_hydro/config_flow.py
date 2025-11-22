"""Config flow for BLE Hydro."""

# -----------------------------------------------------------------------------
# Purpose
# -------
# • Guide the user through adding a BLE Hydro device via UI or Bluetooth discovery.
# • Prefer zero-click setup when exactly one matching device is visible.
# • Support direct Bluetooth discovery → confirm → create entry flow.
#
# How it works
# ------------
# • async_step_user:
#     - Collects currently discovered BLE peripherals from HA’s BT cache.
#     - If none → abort("no_devices_found") so the UI shows a helpful message.
#     - If exactly one → create the entry immediately.
#     - If multiple → present a selection form keyed by MAC (CONF_ADDRESS).
# • async_step_select_device: handles the selection form result and creates entry.
# • async_step_bluetooth: handles discovery-initiated onboarding; stores device,
#   sets unique_id to the MAC, then goes to a confirm step.
# • async_step_bluetooth_confirm: shows a confirm-only form; on submit, creates entry.
#
# Notes
# -----
# • Unique IDs: we use BLE MAC address as the unique_id. HA prevents duplicates.
# • Title placeholders: populate the flow header with device name for better UX.
# • The DiscoveredDevice dataclass keeps minimal state for the interim selection.

from __future__ import annotations

import dataclasses
from typing import Any, Dict

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.bluetooth import (
    BluetoothServiceInfo,
    async_discovered_service_info,
)
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback

from .const import DOMAIN, CONF_DEVICE_NAME, CONF_DEVICE_MAC


@dataclasses.dataclass
class DiscoveredDevice:
    """Lightweight container for one discovered BLE device."""
    name: str
    address: str
    discovery_info: BluetoothServiceInfo


class IrrigationConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """UI-driven and discovery-driven config flow for BLE Hydro."""
    VERSION = 1

    def __init__(self) -> None:
        # address -> DiscoveredDevice
        self._discovered: Dict[str, DiscoveredDevice] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Entry point when user clicks 'Add Integration'."""
        # Collect devices that HA Bluetooth has already seen in this session.
        current_ids = self._async_current_ids()
        for info in async_discovered_service_info(self.hass):
            # Skip already-configured entries and avoid duplicates in this run.
            if info.address in current_ids or info.address in self._discovered:
                continue
            self._store(info)

        # Nothing visible yet → abort with a friendly reason (HA will show text).
        if not self._discovered:
            return self.async_abort(reason="no_devices_found")

        # Exactly one candidate → create the config entry without a form.
        if len(self._discovered) == 1:
            dev = next(iter(self._discovered.values()))
            self.context.setdefault("title_placeholders", {})["name"] = dev.name
            return self.async_create_entry(
                title=dev.name,
                data={CONF_DEVICE_MAC: dev.address, CONF_DEVICE_NAME: dev.name},
            )

        # Multiple candidates → present a selection list by MAC (address).
        return self.async_show_form(
            step_id="select_device",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(
                        {addr: dev.name for addr, dev in self._discovered.items()}
                    )
                }
            ),
        )

    async def async_step_select_device(self, user_input: dict[str, Any]):
        """Handle the device selection form and finalize entry creation."""
        addr = user_input[CONF_ADDRESS]
        dev = self._discovered[addr]
        self.context.setdefault("title_placeholders", {})["name"] = dev.name
        return self.async_create_entry(
            title=dev.name,
            data={CONF_DEVICE_MAC: dev.address, CONF_DEVICE_NAME: dev.name},
        )

    async def async_step_bluetooth(self, discovery_info: BluetoothServiceInfo):
        """Handle a Bluetooth discovery kickoff (automatic onboarding)."""
        # Use MAC as unique_id so duplicates are prevented globally.
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        # Friendly name fallback if advertisement had no name:
        name = discovery_info.name or f"Hydro {discovery_info.address[-5:]}"
        self.context.setdefault("title_placeholders", {})["name"] = name

        # Keep it in our temporary discovered list; then ask for confirmation.
        self._store(discovery_info)
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ):
        """Confirmation step for discovery-driven flows."""
        title = self.context.get("title_placeholders", {}).get("name", "Hydro")
        if user_input is not None:
            # Create the entry bound to the unique_id (MAC) set earlier.
            dev = self._discovered[self.unique_id]
            return self.async_create_entry(
                title=title,
                data={CONF_DEVICE_MAC: dev.address, CONF_DEVICE_NAME: title},
            )
        # Show a confirm-only card; no editable fields.
        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={"name": title},
        )

    def _store(self, info: BluetoothServiceInfo):
        """Cache a discovered device by address for this config flow run."""
        if info.address not in self._discovered:
            self._discovered[info.address] = DiscoveredDevice(
                name=info.name or f"Hydro {info.address[-5:]}",
                address=info.address,
                discovery_info=info,
            )
