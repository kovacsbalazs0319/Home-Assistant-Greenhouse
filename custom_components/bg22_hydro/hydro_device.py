"""Handles Bluetooth comms with the irrigation device (pump + flow)."""

# -----------------------------------------------------------------------------
# Purpose
# -------
# • Wrap BLE GATT communication for the pump + flow device.
# • Maintain local cached state (pump_on, flow_lpm, error_code, totals).
# • Subscribe to notifications for flow and error updates.
# • Push state snapshots into the HA coordinator on any change.
#
# Design notes
# ------------
# • Uses bleak + bleak-retry-connector for robust connections/retries.
# • All notify callbacks may run off the HA event loop thread; we forward
#   updates back via hass.loop.call_soon_threadsafe() to avoid race conditions.
# • Flow integration approximates total delivered volume: integrates the
#   latest flow (L/min) over wall time between updates.
#
# Watch outs / potential issues 
# ------------------------------------------------------------
# • In connect(): after read_gatt_char(FLOW_RATE_UUID) the code logs into `d`
#   but then uses `data` (undefined) for len()/unpack. Same for `_flow_lpm = _unpack_f32_le(data)`.
#   This is likely a typo (`data` → `d`).
# • In _on_flow_notif(): `self._flow_lpm = flow` assigns from an undefined name.
#   Probably intended to keep self._flow_lpm (parsed above).
# • Scaling branches accept 4/2/1-byte payloads. The 2-byte branch divides by 100.0
#   as a temporary scale. Ensure the firmware and HA agree on units and scaling.
# • `_flow_detect_thresh` is 0.05 L/min here while the coordinator uses a
#   threshold from const.py; consider de-duplicating thresholds in the future.
# • Error handling is best-effort; failures log and continue, which is fine for BLE.
# -----------------------------------------------------------------------------


import logging
import struct
from time import monotonic
from bleak import BleakClient, BleakError
from bleak_retry_connector import establish_connection

_LOGGER = logging.getLogger(__name__)

# ==== UUIDs====

PUMP_STATE_UUID = "61a885a4-41c3-60d0-9a53-6d652a700002"  # rw, 1 byte: 0/1
FLOW_RATE_UUID  = "5b026510-4088-c297-46d8-be6c736a0001"  # notify/rd, float32 LE
ERROR_CODE_UUID = "a094a4cb-ec14-40dd-aa93-38222d5d0003"  # notify/rd, u8

# Small helpers for packing/unpacking BLE payloads
def _pack_bool(b: bool) -> bytes: return bytes((1 if b else 0,))
def _unpack_bool(b: bytes) -> bool: return bool(b[0])
def _unpack_f32_le(b: bytes) -> float: return struct.unpack("<f", b)[0]
def _unpack_u8(b: bytes) -> int: return b[0]

class IrrigationBLE:
    """BLE client wrapper for pump + flow sensor."""

    def __init__(self, hass, ble_device) -> None:
        # HA app handle and discovered BleDevice
        self.hass = hass
        self._ble_device = ble_device
        self._cli: BleakClient | None = None
        self._connected = False
        self._coordinator = None

        # cached states
        self._pump_on = False
        self._flow_lpm: float | None = None
        self._error_code = 0
        self._last_flow_ts: float | None = None

        # Accumulated volume and detection flags
        self._total_volume_l = 0.0
        self._flow_detected = False
        self._flow_detect_thresh = 0.05

    def set_coordinator(self, coordinator):
        """Attach the HA coordinator (receives push updates)."""
        self._coordinator = coordinator

    async def connect(self):
        """Establish (or reuse) a BLE connection and subscribe to notifications."""
        if self._cli and self._cli.is_connected:
            self._connected = True
            return
        _LOGGER.debug("Connecting irrigation BLE via bleak-retry-connector...")
        try:
            self._cli = await establish_connection(
                BleakClient,
                self._ble_device,
                name="BG22-Hydro",
                disconnected_callback=self._on_disconnect,
            )
            self._connected = True
            _LOGGER.info("Irrigation BLE connected")

            # Some backends require an explicit service discovery (best-effort)
            try:
                await self._cli.get_services()  # if non existant, AttributeError
            except AttributeError:
                pass

            # Subscribe to flow and error notifications
            await self._safe_start_notify(FLOW_RATE_UUID, self._on_flow_notif)
            await self._safe_start_notify(ERROR_CODE_UUID, self._on_error_notif)

            # Read initial values to populate state right away
            await self._read_initial()

            # Additional initial flow read (with format fallbacks)
            try:
                d = await self._cli.read_gatt_char(FLOW_RATE_UUID)
                _LOGGER.debug("Initial flow read: len=%s hex=%s", len(d), d.hex())
                n = len(data)
                if n == 4:
                    self._flow_lpm = _unpack_f32_le(data)             # float32 LE
                elif n == 2:
                    raw = int.from_bytes(data, "little", signed=False) # u16
                    self._flow_lpm = raw / 100.0                       # scale for now!
                elif n == 1:
                    self._flow_lpm = float(data[0])                    # u8 fallback
                else:
                    _LOGGER.debug("Flow notif: unexpected len=%s hex=%s", n, data.hex())
                    return
                self._last_flow_ts = monotonic()
            except Exception:
                pass

        except Exception as e:
            self._connected = False
            _LOGGER.error("BLE connect failed: %s", e)

    async def disconnect(self):
        """Disconnect from BLE (best-effort) and mark state."""
        if self._cli and self._cli.is_connected:
            try:
                await self._cli.disconnect()
            except Exception as e:
                _LOGGER.warning("BLE disconnect error: %s", e)
        self._connected = False

    async def _safe_start_notify(self, uuid: str, cb):
        """Subscribe to a notify characteristic; log but don’t fail setup."""
        try:
            await self._cli.start_notify(uuid, cb)
            _LOGGER.debug("Subscribed to notifications on %s", uuid)
        except Exception as e:
            _LOGGER.warning("Notify failed for %s: %s", uuid, e)

    async def _read_initial(self):
        """Best-effort initial reads to populate local cache; swallow errors."""
        try:
            d = await self._cli.read_gatt_char(PUMP_STATE_UUID)
            self._pump_on = _unpack_bool(d)
        except Exception: pass
        try:
            d = await self._cli.read_gatt_char(FLOW_RATE_UUID)
            self._flow_lpm = _unpack_f32_le(d)
            self._flow_detected = (self._flow_lpm or 0.0) >= self._flow_detect_thresh
            self._push()
            self._last_flow_ts = monotonic()
        except Exception: pass
        try:
            d = await self._cli.read_gatt_char(ERROR_CODE_UUID)
            self._error_code = _unpack_u8(d)
        except Exception: pass
        self._push()

    def _on_disconnect(self, _client):
        """Bleak disconnect callback: clear transient flags and push state."""
        self._connected = False
        self._flow_detected = False
        _LOGGER.warning("BLE disconnected")
        self._push()

    # ---------- public control ----------
    async def turn_on(self):  await self._write_pump(True)
    async def turn_off(self): await self._write_pump(False)

    async def _write_pump(self, on: bool):
        """Write the pump state characteristic (0/1). Also handles integration edge case when turning off."""
        if not self._connected:
            await self.connect()
        if not self._connected:
            raise BleakError("Not connected")
        try:
            await self._cli.write_gatt_char(PUMP_STATE_UUID, _pack_bool(on), response=True)
            self._pump_on = on

            if not on:
                now = monotonic()
                if self._last_flow_ts is not None:
                    dt = max(0.0, now - self._last_flow_ts)
                    self._total_volume_l += (self._flow_lpm or 0.0) / 60.0 * dt
                
                self._flow_lpm = 0.0
                self._flow_detected = False
                self._last_flow_ts = now

            self._push()
        except Exception as e:
            _LOGGER.error("Write pump failed: %s", e)
            raise


    async def read_all(self) -> dict:
        """Synchronous snapshot read of all key characteristics (best-effort)."""
        if not self._connected:
            await self.connect()
        try:
            d = await self._cli.read_gatt_char(PUMP_STATE_UUID)
            self._pump_on = _unpack_bool(d)
        except Exception: pass
        try:
            d = await self._cli.read_gatt_char(FLOW_RATE_UUID)
            self._flow_lpm = _unpack_f32_le(d)
            self._last_flow_ts = monotonic()
        except Exception: pass
        try:
            d = await self._cli.read_gatt_char(ERROR_CODE_UUID)
            self._error_code = _unpack_u8(d)
        except Exception: pass
        self._push()
        return {
            "pump_on": self._pump_on,
            "flow_lpm": self._flow_lpm,
            "error_code": self._error_code,
        }

    # ---------- notify handlers ----------
    def _on_flow_notif(self, _sender, data: bytes):
        """Handle flow notifications with flexible payload formats (f32/u16/u8)."""
        try:
            n = len(data)
            if n == 4:
                self._flow_lpm = _unpack_f32_le(data)             # float32 LE
            elif n == 2:
                raw = int.from_bytes(data, "little", signed=False) # u16
                self._flow_lpm = raw / 100.0                       # scale for now!
            elif n == 1:
                self._flow_lpm = float(data[0])                    # u8 fallback
            else:
                _LOGGER.debug("Flow notif: unexpected len=%s hex=%s", n, data.hex())
                return

            now = monotonic()
            # L/min → L/s → dV
            if self._last_flow_ts is not None:
                dt = max(0.0, now - self._last_flow_ts)
                self._total_volume_l += (self._flow_lpm or 0.0) / 60.0 * dt
            self._flow_lpm = flow
            self._last_flow_ts = now

            self._flow_detected = (self._flow_lpm or 0.0) >= self._flow_detect_thresh

        except Exception as e:
            _LOGGER.debug("Flow notif parse error len=%s hex=%s err=%s", len(data), data.hex(), e)
        finally:
            self._push()

    def _on_error_notif(self, _sender, data: bytes):
        """Handle error-code notifications (u8)."""
        try:
            if not data:
                _LOGGER.debug("Error notif: empty payload")
                return
            # u8 hibakód
            self._error_code = data[0]
        except Exception as e:
            _LOGGER.debug("Error notif parse error len=%s hex=%s err=%s", len(data), data.hex() if data else "", e)
        finally:
            self._push()


    # ---------- push into coordinator (thread-safe a HA loopra) ----------
    def _push(self):
        """Thread-safe push of the current snapshot into the coordinator."""
        if not self._coordinator:
            return
        payload = {
            "pump_on": self._pump_on,
            "flow_lpm": self._flow_lpm,
            "error_code": self._error_code,
            "flow_detected": self._flow_detected,
            "total_volume_l": round(self._total_volume_l, 3),
        }
        
        # Bleak callback can be on other thread, so drop event to HA loop
        self.hass.loop.call_soon_threadsafe(
            self._coordinator.async_set_updated_data, payload
        )
