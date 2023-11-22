"""Constants for the CyberSW integration."""

from homeassistant.const import Platform

DOMAIN = "cybersw"
PLATFORMS: list[Platform] = [
    Platform.SWITCH,
    Platform.SENSOR,
]

OPTION_IDLE_DISCONNECT_DELAY = "idle_disconnect_delay_ms"
DEFAULT_IDLE_DISCONNECT_DELAY = -1

SERVICE_SET_CONNECTION_INTERVAL = "set_connection_interval"

ATTR_INTERVAL = "interval"
