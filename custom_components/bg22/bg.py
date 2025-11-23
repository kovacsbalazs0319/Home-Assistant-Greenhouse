"""Handles Bluetooth communication with the BG22 device."""
import logging
from typing import Optional

from bleak import BleakClient
from bleak_retry_connector import establish_connection, BLEAK_RETRY_EXCEPTIONS
from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# UUIDs for motor control
POSITION_SET_UUID = "5b026510-4088-c297-46d8-be6c736a087a"
POSITION_FEEDBACK_UUID = "61a885a4-41c3-60d0-9a53-6d652a70d29c"
ERROR_UUID = "dbe45d18-3909-44ff-8402-b848487b0dac"


class BG22Instance:
    """Handles BLE communication with the BG22 device via HA Bluetooth."""

    def __init__(self, hass: HomeAssistant, mac: str) -> None:
        self._hass = hass
        self._mac = mac

        self._client: Optional[BleakClient] = None
        self._connected: bool = False
        self._coordinator = None

        _LOGGER.debug("BG22Instance created for MAC: %s", self._mac)

    @property
    def mac(self) -> str:
        """Return MAC address of the device."""
        return self._mac

    def set_coordinator(self, coordinator) -> None:
        """Assign the DataUpdateCoordinator to this instance."""
        self._coordinator = coordinator

    async def _ensure_connected(self) -> None:
        """Ensure we are connected to the BG22 device."""
        if self._connected and self._client and self._client.is_connected:
            return

        ble_device = bluetooth.async_ble_device_from_address(
            self._hass,
            self._mac,
            connectable=True,
        )
        if not ble_device:
            _LOGGER.warning(
                "BG22 device %s not available via HA Bluetooth (no connectable path)",
                self._mac,
            )
            self._connected = False
            return

        _LOGGER.debug("Connecting to BG22 device %s via HA Bluetooth", self._mac)

        try:
            self._client = await establish_connection(
                BleakClient,
                ble_device,
                self._mac,
                timeout=20.0,
            )
        except BLEAK_RETRY_EXCEPTIONS as err:
            _LOGGER.error("Failed to connect to BG22 %s: %s", self._mac, err)
            self._connected = False
            return

        self._connected = True
        _LOGGER.info("Connected to BG22 %s successfully", self._mac)

        try:
            await self._client.start_notify(
                POSITION_FEEDBACK_UUID, self._position_feedback_handler
            )
            await self._client.start_notify(ERROR_UUID, self._error_handler)
        except Exception as err:
            _LOGGER.error(
                "Failed to start notifications on BG22 %s: %s",
                self._mac,
                err,
            )

    async def connect(self) -> None:
        """Public connect API – setupkor hívjuk, ha akarjuk."""
        await self._ensure_connected()

    async def disconnect(self) -> None:
        """Disconnect from the BG22 device."""
        if self._client and self._client.is_connected:
            try:
                await self._client.disconnect()
                _LOGGER.info("Disconnected from BG22 %s", self._mac)
            except Exception as err:
                _LOGGER.error("Error disconnecting from BG22 %s: %s", self._mac, err)
        self._connected = False
        self._client = None

    async def _send(self, uuid: str, data: bytes) -> None:
        """Send data to the BG22 device over BLE."""
        await self._ensure_connected()
        if not self._client or not self._client.is_connected:
            _LOGGER.error(
                "Cannot send data to BG22 %s, client is not connected", self._mac
            )
            return

        try:
            await self._client.write_gatt_char(uuid, data)
            _LOGGER.debug("Data sent to %s: %s", uuid, data.hex())
        except Exception as err:
            _LOGGER.error(
                "Error sending data to %s on BG22 %s: %s", uuid, self._mac, err
            )
            
            self._connected = False

    async def write_position(self, value: int) -> None:
        """Send position set value (0–100)."""
        value = max(0, min(100, int(value)))
        await self._send(POSITION_SET_UUID, bytes([value]))

    async def _position_feedback_handler(self, sender, data):
        """Handle feedback notifications."""
        if not data:
            return
        feedback = int(data[0])
        _LOGGER.debug("Position feedback received: %s", feedback)
        if self._coordinator:
            self._coordinator.handle_position_feedback(feedback)

    async def _error_handler(self, sender, data):
        """Handle error notifications."""
        if not data:
            return
        error_code = int(data[0])
        _LOGGER.debug("Error received: %s", error_code)
        if self._coordinator:
            self._coordinator.handle_error(error_code)
