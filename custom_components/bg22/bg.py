"""Handles Bluetooth communication with the BG22 device."""
import logging
from bleak import BleakClient

_LOGGER = logging.getLogger(__name__)

# UUIDs for motor control
POSITION_SET_UUID = "5b026510-4088-c297-46d8-be6c736a087a"
POSITION_FEEDBACK_UUID = "61a885a4-41c3-60d0-9a53-6d652a70d29c"
ERROR_UUID = "dbe45d18-3909-44ff-8402-b848487b0dac"

class BG22Instance:
    """Handles BLE communication with the BG22 device."""

    def __init__(self, mac: str) -> None:
        self._mac = mac
        self._device = BleakClient(self._mac)
        self._connected = False
        self._coordinator = None  
        _LOGGER.debug(f"BG22Instance created for MAC: {self._mac}")

    def set_coordinator(self, coordinator):
        """Assign the DataUpdateCoordinator to this instance."""
        self._coordinator = coordinator

    async def connect(self):
        """Establish a connection with the BG22 device."""
        if self._connected:
            return
        _LOGGER.debug("Connecting to BG22 device...")
        try:
            await self._device.connect(timeout=20)
            self._connected = True
            _LOGGER.info("Connected to BG22 successfully!")

            await self._device.start_notify(POSITION_FEEDBACK_UUID, self._position_feedback_handler)
            await self._device.start_notify(ERROR_UUID, self._error_handler)
        except Exception as e:
            _LOGGER.error(f"Failed to connect to BG22: {e}")

    async def disconnect(self):
        """Disconnect from the BG22 device."""
        if self._connected:
            try:
                await self._device.disconnect()
                self._connected = False
                _LOGGER.info("Disconnected from BG22.")
            except Exception as e:
                _LOGGER.error(f"Error disconnecting: {e}")

    async def _send(self, uuid: str, data: bytes):
        """Send data to the BG22 device over BLE."""
        if not self._connected:
            await self.connect()
            if not self._connected:
                services = await self._device.get_services()
                for service in services:
                    _LOGGER.debug("Service %s", service.uuid)
                    for char in service.characteristics:
                        _LOGGER.debug("  Characteristic %s — properties: %s", char.uuid, char.properties)

        try:
            await self._device.write_gatt_char(uuid, data)
            _LOGGER.debug("Data sent to %s: %s", uuid, data.hex())
        except Exception as e:
            _LOGGER.error(f"Error sending data to {uuid}: {e}")

    async def write_position(self, value: int):
        """Send position set value (0–100)"""
        await self._send(POSITION_SET_UUID, bytes([value]))

    async def _position_feedback_handler(self, sender, data):
        """Handle feedback notifications."""
        feedback = int(data[0])
        _LOGGER.debug(f"Position feedback received: {feedback}")
        if self._coordinator:
            self._coordinator.handle_position_feedback(feedback)

    async def _error_handler(self, sender, data):
        """Handle error notifications."""
        error_code = int(data[0])
        _LOGGER.debug(f"Error received: {error_code}")
        if self._coordinator:
            self._coordinator.handle_error(error_code)
