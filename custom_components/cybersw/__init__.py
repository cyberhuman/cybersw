"""The CyberSW integration."""
from __future__ import annotations

import logging

from .pycybersw.advertisement import (
    get_device_display_name,
    parse_cyberswitch_advertisement,
)

from .pycybersw.device import CyberswitchDevice

from homeassistant.components.bluetooth import (
    async_ble_device_from_address,
    #async_scanner_devices_by_address,
    async_last_service_info,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_ADDRESS,
    # CONF_TOKEN,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    DOMAIN,
    PLATFORMS,
    OPTION_IDLE_DISCONNECT_DELAY,
    DEFAULT_IDLE_DISCONNECT_DELAY,
)
from .models import CyberswitchConfigurationData
from .coordinator import CyberswitchCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Cyberswitch device from a config entry."""
    address: str = entry.data[CONF_ADDRESS]
    #token: str = entry.data[CONF_TOKEN]

    # transitions info logs are verbose. Only enable warnings
    logging.getLogger("transitions.core").setLevel(logging.WARNING)

    if not (ble_device := async_ble_device_from_address(hass, address)):
        raise ConfigEntryNotReady(
            f"Could not find CyberSW with address {address}. Try power cycling the device"
        )
    if not (info := async_last_service_info(hass, address)):
        raise ConfigEntryNotReady(
            f"Could not find CyberSW service info for {address}. Try power cycling the device"
        )

    advertisement = parse_cyberswitch_advertisement(info)
    device = CyberswitchDevice(
        ble_device,
        advertisement,
        idle_disconnect_delay_ms=entry.options.get(OPTION_IDLE_DISCONNECT_DELAY, DEFAULT_IDLE_DISCONNECT_DELAY)
    )
    config = CyberswitchConfigurationData(
        ble_device,
        device,
        entry.title,
        get_device_display_name(device.name, device.address)
    )
    coordinator = CyberswitchCoordinator(hass, config)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    coordinator: CyberswitchCoordinator = hass.data[DOMAIN][entry.entry_id]
    config: CyberswitchConfigurationData = coordinator.config
    if (
        entry.title != config.title or
        entry.options.get(OPTION_IDLE_DISCONNECT_DELAY, DEFAULT_IDLE_DISCONNECT_DELAY) !=
            config.device.idle_disconnect_delay_ms
    ):
        await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator: CyberswitchCoordinator = hass.data[DOMAIN][entry.entry_id]
        config: CyberswitchConfigurationData = coordinator.config

        # also called by switch entities, but do it here too for good measure
        await config.device.async_disconnect()

        hass.data[DOMAIN].pop(entry.entry_id)

        if not hass.config_entries.async_entries(DOMAIN):
            hass.data.pop(DOMAIN)

    return unload_ok
