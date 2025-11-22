"""Constants for the BLE Irrigation integration."""
# -----------------------------------------------------------------------------
# Purpose
# --------
# Central place for static constants shared across integration modules.
# Keep this file minimal: domain identifiers, config keys, fixed thresholds,
# and symbolic error codes that align with firmware-side definitions.
# -----------------------------------------------------------------------------

# Home Assistant domain ID (must match manifest.json)
DOMAIN = "bg22_hydro"

# Config entry field keys
CONF_DEVICE_NAME = "device_name"
CONF_DEVICE_MAC = "device_mac"

# -----------------------------------------------------------------------------
# Error codes (mirror firmware-defined enumeration if applicable)
# -----------------------------------------------------------------------------
ERROR_OK = 0             # Normal operation
ERROR_DRY_RUN = 1        # Pump on but no detected flow
ERROR_SENSOR_FAULT = 2   # Pump off but read sensor value
ERROR_DRIVER_FAULT = 3

# -----------------------------------------------------------------------------
# Flow thresholds and timing constants
# -----------------------------------------------------------------------------
FLOW_THRESHOLD_LPM = 0.2  # Below this L/min → treat as no flow
DRY_RUN_DELAY_SEC  = 5.0  # Duration of no-flow before declaring dry-run