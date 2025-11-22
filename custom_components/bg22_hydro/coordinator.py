"""Coordinator for irrigation BLE device (event-driven)."""

# -----------------------------------------------------------------------------
# Purpose
# -------
# • Centralizes state management for the BLE Hydro device.
# • Acts as a Home Assistant DataUpdateCoordinator in *push mode* (update_interval=None),
#   meaning data changes are triggered by BLE notifications instead of polling.
# • Computes derived flags like `flow_detected` and `dry_run` from raw telemetry.
#
# Responsibilities
# ----------------
# • Maintain a unified state snapshot in self.data for entities to read.
# • Handle push updates from the IrrigationBLE instance via handle_state_update().
# • Detect dry-run conditions (pump ON but no flow for N seconds).
# • Generate consistent error codes/messages for the UI.
#
# Flow summary
# ------------
#   BLE → device callback → handle_state_update()
#      → compute derived flags
#      → self.async_set_updated_data() → entities automatically refresh
#
# Timing model
# -------------
#   monotonic() timestamps are used to measure duration of “no flow” periods.
#
# Notes
# -----
# • update_interval=None disables scheduled polling; this class only updates on push.
# • DataUpdateCoordinator automatically handles entity refresh and throttling.
# -----------------------------------------------------------------------------

import logging
from time import monotonic
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from .const import (
    FLOW_THRESHOLD_LPM, DRY_RUN_DELAY_SEC,
    ERROR_OK, ERROR_DRY_RUN, ERROR_SENSOR_FAULT
)

_LOGGER = logging.getLogger(__name__)

class IrrigationCoordinator(DataUpdateCoordinator):
    """Push-style coordinator; device notifies, we compute derived states."""

    def __init__(self, hass, instance):
        super().__init__(
            hass,
            _LOGGER,
            name="Irrigation BLE Coordinator",
            update_interval=None,  # push mode — updates come via BLE notifications
        )
        self.instance = instance
        # Canonical state dict shared with HA entities
        self.data = {
            "pump_on": False,               # Pump enable flag
            "flow_lpm": None,               # Current flow in L/min (float)
            "flow_detected": False,         # Boolean: above threshold
            "dry_run": False,               # Boolean: ON but no flow for long enough
            "error_code": ERROR_OK,         # Numeric error status
            "error_message": "OK",          # Human-readable error
        }
        # Internal timestamps for dry-run detection
        self._no_flow_since = None
        self._last_flow_rx = None  # TS when flow last updated (reserved for future use)

    async def _async_update_data(self):
        """Return current snapshot on HA refresh requests."""
        # Normally unused since updates are event-driven, but HA still requires it.
        return self.data

    # -------------------------------------------------------------------------
    # BLE push handler
    # -------------------------------------------------------------------------
    def handle_state_update(self, pump_on: bool, flow_lpm: float | None, error_code: int):
        """Handle incoming BLE notification with current device state."""
        # Store raw incoming values
        self.data["pump_on"] = pump_on
        self.data["flow_lpm"] = flow_lpm
        self.data["error_code"] = error_code

        # ---------------------------------------------------------------------
        # Compute derived states
        # ---------------------------------------------------------------------
        # Flow detection: only valid if we have a numeric flow_lpm reading
        flow_detected = (flow_lpm is not None) and (flow_lpm >= FLOW_THRESHOLD_LPM)
        self.data["flow_detected"] = flow_detected

        # Dry run logic: triggered if pump ON and no flow for > DRY_RUN_DELAY_SEC
        dry_run = False
        now = monotonic()
        if pump_on and not flow_detected:
            if self._no_flow_since is None:
                # Start timing the “no flow” condition
                self._no_flow_since = now
            elif (now - self._no_flow_since) >= DRY_RUN_DELAY_SEC:
                dry_run = True
        else:
            # Flow restored or pump off — reset timer
            self._no_flow_since = None

        self.data["dry_run"] = dry_run

        # ---------------------------------------------------------------------
        # Error code selection logic
        # ---------------------------------------------------------------------
        # Priority:
        #   1) Explicit error from device (firmware-detected)
        #   2) Computed dry-run condition
        #   3) Missing/invalid flow sensor data
        #   4) OK
        if error_code != ERROR_OK:
            code = error_code
        elif dry_run:
            code = ERROR_DRY_RUN
        elif flow_lpm is None:  # e.g. read/parse failure
            code = ERROR_SENSOR_FAULT
        else:
            code = ERROR_OK

        self.data["error_code"] = code
        self.data["error_message"] = _err_msg(code)

        # ---------------------------------------------------------------------
        # Emit update event — triggers all subscribed entities to refresh.
        # ---------------------------------------------------------------------
        _LOGGER.debug("Coordinator state: %s", self.data)
        self.async_set_updated_data(self.data)

# -----------------------------------------------------------------------------
# Helper: map numeric error codes to human-readable messages
# -----------------------------------------------------------------------------
def _err_msg(code: int) -> str:
    """Translate internal error code to display string."""
    return {
        ERROR_OK: "OK",
        ERROR_DRY_RUN: "Dry run detected",
        ERROR_SENSOR_FAULT: "Flow sensor fault",
    }.get(code, "Unknown error")
