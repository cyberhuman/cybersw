"""Constants for the CyberSW integration."""

from homeassistant.const import Platform

DOMAIN = "cybersw"
PLATFORMS: list[Platform] = [Platform.SWITCH]

OPTION_IDLE_DISCONNECT_DELAY = "idle_disconnect_delay_ms"
DEFAULT_IDLE_DISCONNECT_DELAY = -1
