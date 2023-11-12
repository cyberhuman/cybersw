"""Sensor representation of a CyberSW device."""
from __future__ import annotations

from collections.abc import Callable
import logging

from .pycybersw.device import (
    CyberswitchConnectionStatus,
    CyberswitchDevice,
)

import voluptuous as vol

#from homeassistant.components.fan import ATTR_PERCENTAGE, FanEntity, FanEntityFeature
from homeassistant.components.sensor import (
    PLATFORM_SCHEMA,
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_NAME,
    PERCENTAGE,
    STATE_ON,
    STATE_OFF,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_platform, config_validation as cv
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
)
from .models import CyberswitchConfigurationData
from .coordinator import CyberswitchCoordinator

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = "CyberSW SensorS"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    }
)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback
) -> None:
    """Set up CyberSW device from a config entry."""

    entity_platform.async_get_current_platform()
    coordinator: CyberswitchCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Fetch initial data so we have data when entities subscribe
    #
    # If the refresh fails, async_config_entry_first_refresh will
    # raise ConfigEntryNotReady and setup will try again later
    #
    # If you do not want to retry setup on failure, use
    # coordinator.async_refresh() instead
    #
    await coordinator.async_config_entry_first_refresh()

    async_add_entities([
        CyberswitchConnectionSensor(coordinator),
        CyberswitchSwitchStateSensor(coordinator),
        CyberswitchBatteryLevelSensor(coordinator),
    ])


class CyberswitchConnectionSensor(CoordinatorEntity, SensorEntity):
    """Connection sensor of a CyberSW device."""

    _attr_has_entity_name = True
    #_attr_should_poll = False
    _attr_device_class = SensorDeviceClass.ENUM

    def __init__(self, coordinator):
        """Pass coordinator to CoordinatorEntity."""
        super().__init__(coordinator)
        config: CyberswitchConfigurationData = coordinator.config
        self._attr_name = "Connection"
        self._device : CyberswitchDevice = config.device
        self._attr_unique_id = coordinator.config_entry.entry_id + "-conn"
        self._attr_device_info = DeviceInfo(
            identifiers={ (DOMAIN, config.device.address) },
#            name=name,
#            model=VERSION,
#            manufacturer=NAME,
        )
        self._attr_native_value = "disconnected"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        _LOGGER.info(f'_handle_coordinator_update() {self._device.connection_status=}')
        match self._device.connection_status:
            case CyberswitchConnectionStatus.DISCONNECTED:
                self._attr_native_value = "disconnected"
            case CyberswitchConnectionStatus.CONNECTING:
                self._attr_native_value = "connecting"
            case CyberswitchConnectionStatus.CONNECTED:
                self._attr_native_value = "connected"
        self.async_write_ha_state()

    @callback
    def _async_write_state_changed(self) -> None:
        _LOGGER.info(f'_async_write_state_changed() {self._device.connection_status=}')
        match self._device.connection_status:
            case CyberswitchConnectionStatus.DISCONNECTED:
                self._attr_native_value = "disconnected"
            case CyberswitchConnectionStatus.CONNECTING:
                self._attr_native_value = "connecting"
            case CyberswitchConnectionStatus.CONNECTED:
                self._attr_native_value = "connected"
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore state and subscribe to device events."""
        await super().async_added_to_hass()
        self.async_on_remove(self._async_subscribe_to_device_change())

    @callback
    def _async_subscribe_to_device_change(self) -> Callable[[], None]:
        """Subscribe to device state changes."""
        return self._device.subscribe_to_state_change(self._async_write_state_changed)

    @property
    def icon(self):
        """Icon to use in the frontend."""
        return "mdi:connection"


class CyberswitchSwitchStateSensor(CoordinatorEntity, SensorEntity):
    """Switch state sensor of a CyberSW device."""

    _attr_has_entity_name = True
    #_attr_should_poll = False
    _attr_device_class = SensorDeviceClass.ENUM

    def __init__(self, coordinator):
        """Pass coordinator to CoordinatorEntity."""
        super().__init__(coordinator)
        config: CyberswitchConfigurationData = coordinator.config
        self._attr_name = "Switch state"
        self._device : CyberswitchDevice = config.device
        self._attr_unique_id = coordinator.config_entry.entry_id + "-state"
        self._attr_device_info = DeviceInfo(
            identifiers={ (DOMAIN, config.device.address) },
#            name=name,
#            model=VERSION,
#            manufacturer=NAME,
        )
        self._attr_native_value = STATE_UNKNOWN

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        _LOGGER.info(f'_handle_coordinator_update() {self._device.state.on=}')
        match self._device.state.on:
            case None:
                self._attr_native_value = STATE_UNKNOWN
            case True:
                self._attr_native_value = STATE_ON
            case False:
                self._attr_native_value = STATE_OFF
        self.async_write_ha_state()

    @callback
    def _async_write_state_changed(self) -> None:
        _LOGGER.info(f'_async_write_state_changed() {self._device.state.on=}')
        match self._device.state.on:
            case None:
                self._attr_native_value = STATE_UNKNOWN
            case True:
                self._attr_native_value = STATE_ON
            case False:
                self._attr_native_value = STATE_OFF
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore state and subscribe to device events."""
        await super().async_added_to_hass()
        self.async_on_remove(self._async_subscribe_to_device_change())

    @callback
    def _async_subscribe_to_device_change(self) -> Callable[[], None]:
        """Subscribe to device state changes."""
        return self._device.subscribe_to_state_change(self._async_write_state_changed)


class CyberswitchBatteryLevelSensor(CoordinatorEntity, SensorEntity):
    """Battery level sensor of a CyberSW device."""

    _attr_has_entity_name = True
    #_attr_should_poll = False
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, coordinator):
        """Pass coordinator to CoordinatorEntity."""
        super().__init__(coordinator)
        config: CyberswitchConfigurationData = coordinator.config
        #self._attr_name = config.display_name
        self._device : CyberswitchDevice = config.device
        self._attr_unique_id = coordinator.config_entry.entry_id + "-battery"
        self._attr_device_info = DeviceInfo(
            identifiers={ (DOMAIN, config.device.address) },
#            name=name,
#            model=VERSION,
#            manufacturer=NAME,
        )
        self._attr_native_value = None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        _LOGGER.info(f'_handle_coordinator_update() {self._device.state.battery_level=}')
        self._attr_native_value = self._device.state.battery_level
        self.async_write_ha_state()

    @callback
    def _async_write_state_changed(self) -> None:
        _LOGGER.info(f'_async_write_state_changed() {self._device.state.battery_level=}')
        self._attr_native_value = self._device.state.battery_level
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore state and subscribe to device events."""
        await super().async_added_to_hass()
        self.async_on_remove(self._async_subscribe_to_device_change())

    @callback
    def _async_subscribe_to_device_change(self) -> Callable[[], None]:
        """Subscribe to device state changes."""
        return self._device.subscribe_to_state_change(self._async_write_state_changed)
#
#    @property
#    def icon(self):
#        """Icon to use in the frontend."""
#        return "mdi:battery-30"