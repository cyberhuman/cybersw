"""Switch representation of a CyberSW device."""
from __future__ import annotations

from collections.abc import Callable
#from datetime import timedelta
from typing import Any
import logging

from .pycybersw.device import (
    CyberswitchDevice,
    DisconnectionReason,
)
from .pycybersw.model import UnknownCyberswitchState
from .pycybersw.commands import (
    CyberswitchCommandData,
    CyberswitchCommandResultStatus,
#    set_volume,
    turn_off,
    turn_on,
)

import voluptuous as vol

from homeassistant.components.switch import (
    PLATFORM_SCHEMA,
    SwitchEntity,
    SwitchDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_NAME,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_platform, config_validation as cv
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    #ATTR_DURATION,
    #DEFAULT_TRANSITION_DURATION,
    DOMAIN,
    #SERVICE_TRANSITION_OFF,
    #SERVICE_TRANSITION_ON,
)
from .models import CyberswitchConfigurationData
from .coordinator import CyberswitchCoordinator

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = "CyberSW"

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
#    platform.xsync_register_entity_service(
#        SERVICE_TRANSITION_ON,
#        {
#            vol.Optional(ATTR_VOLUME): vol.All(
#                vol.Coerce(int), vol.Range(min=0, max=100)
#            ),
#            vol.Optional(ATTR_DURATION, default=DEFAULT_TRANSITION_DURATION): vol.All(
#                vol.Coerce(int), vol.Range(min=1, max=300)
#            ),
#        },
#        "async_transition_on",
#    )
#    platform.xsync_register_entity_service(
#        SERVICE_TRANSITION_OFF,
#        {
#            vol.Optional(ATTR_DURATION, default=DEFAULT_TRANSITION_DURATION): vol.All(
#                vol.Coerce(int), vol.Range(min=1, max=300)
#            ),
#        },
#        "async_transition_off",
#    )

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
        CyberswitchSwitch(coordinator),
        CyberswitchConnectionSwitch(coordinator),
    ])


class CyberswitchSwitch(CoordinatorEntity, SwitchEntity, RestoreEntity):
    """Switch representation of a CyberSW device.

    The CoordinatorEntity class provides:
      should_poll
      async_update
      async_added_to_hass
      available
    """

    _attr_has_entity_name = True
    _attr_name = None
    #_attr_should_poll = False
    _is_on: bool | None = None
    #_percentage: int | None = None

    def __init__(self, coordinator):
        """Pass coordinator to CoordinatorEntity."""
        super().__init__(coordinator)
        config: CyberswitchConfigurationData = coordinator.config
        name = config.display_name
        self._device : CyberswitchDevice = config.device
        self._attr_unique_id = coordinator.config_entry.entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={ (DOMAIN, config.device.address) },
            name=name,
#            model=VERSION,
#            manufacturer=NAME,
        )
        self._attr_device_class = SwitchDeviceClass.SWITCH

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._is_on = self._device.state.on
        _LOGGER.info(f'handle_coordinator_update() {self._device.state=}')
        self.async_write_ha_state()

    @callback
    def _async_write_state_changed(self) -> None:
        _LOGGER.info(f'_async_write_state_changed() {self.assumed_state=} {self._device.state=} {self._device.connection_status=}')
        # cache state for restore entity
        if not self.assumed_state:
            self._is_on = self._device.state.on
            #self._percentage = self._device.state.volume
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore state and subscribe to device events."""
        await super().async_added_to_hass()

        if last_state := await self.async_get_last_state():
            if last_state.state in (STATE_ON, STATE_OFF):
                self._is_on = last_state.state == STATE_ON
            else:
                self._is_on = None
            #self._percentage = last_state.attributes.get(ATTR_PERCENTAGE)
        self.async_on_remove(self._async_subscribe_to_device_change())

    @callback
    def _async_subscribe_to_device_change(self) -> Callable[[], None]:
        return self._device.subscribe_to_state_change(self._async_write_state_changed)

    async def async_will_remove_from_hass(self) -> None:
        """Unpair."""
        await super().async_will_remove_from_hass()
        # FIXME cannot unpair because HaBleakClientWrapper doesn't set the backend unless connected
        #client = BleakClient(self._device._device)
        #_LOGGER.info(f'async_will_remove_from_hass {self._device=} {self._device._device=} {client.__class__.__name__=}')
        #await client.unpair()

    #@property
    #def percentage(self) -> int | None:
    #    """Volume level of the device."""
    #    return self._percentage if self.assumed_state else self._device.state.volume
#
    @property
    def is_on(self) -> bool | None:
        """Power state of the device."""
        return self._is_on if self.assumed_state else self._device.state.on

    @property
    def assumed_state(self) -> bool:
        """Return True if unable to access real state of the entity."""
        return not self._device.is_connected or self._device.state is UnknownCyberswitchState

#    @property
#    def entity_picture(self) -> str | None:
#        """Return the entity picture to use in the frontend.
#
#        Update entities return the brand icon based on the integration domain by default.
#        """
#        return (
#                f"/_/{self.platform.platform_name}/icon.png"
#        )
#
    async def async_turn_on(self) -> None:
        """Turn on the device."""
        await self._async_execute_command(turn_on())

    async def async_turn_off(self) -> None:
        """Turn off the device."""
        await self._async_execute_command(turn_off())

#    async def async_set_percentage(self, percentage: int) -> None:
#        """Set the volume of the device. A value of 0 will turn off the device."""
#        await self._async_execute_command(
#            set_volume(percentage) if percentage > 0 else turn_off()
#        )
#
#    async def async_transition_on(self, duration: int, **kwargs: Any) -> None:
#        """Transition on the device."""
#        await self._async_execute_command(
#            turn_on(volume=kwargs.get("volume"), duration=timedelta(seconds=duration))
#        )
#
#    async def async_transition_off(self, duration: int, **kwargs: Any) -> None:
#        """Transition off the device."""
#        await self._async_execute_command(
#            turn_off(duration=timedelta(seconds=duration))
#        )

    async def _async_execute_command(self, command: CyberswitchCommandData) -> None:
        result = await self._device.async_execute_command(command)
        if result.status == CyberswitchCommandResultStatus.SUCCESSFUL:
            #self._async_write_state_changed()
            pass
        elif result.status != CyberswitchCommandResultStatus.CANCELLED:
            raise HomeAssistantError(
                f"Command {command} failed with status {result.status.name} after"
                f" {result.duration}"
            )

class CyberswitchConnectionSwitch(CoordinatorEntity, SwitchEntity, RestoreEntity):
    """Switch representation of the connection to a CyberSW device."""

    #_attr_has_entity_name = True
    _attr_name = "Connection"
    #_attr_should_poll = False
    _attr_entity_registry_enabled_default = False
    _is_on: bool | None = None
    _attr_icon = "mdi:connection"

    def __init__(self, coordinator):
        """Pass coordinator to CoordinatorEntity."""
        super().__init__(coordinator)
        config: CyberswitchConfigurationData = coordinator.config
        self._device : CyberswitchDevice = config.device
        self._attr_unique_id = coordinator.config_entry.entry_id + "-connection"
        self._attr_device_info = DeviceInfo(
            identifiers={ (DOMAIN, config.device.address) },
#            name=name,
#            model=VERSION,
#            manufacturer=NAME,
        )
        self._attr_device_class = SwitchDeviceClass.SWITCH

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        _LOGGER.info(f'handle_coordinator_update() {self._device.state=}')
        self._is_on = self._device.is_connected
        self.async_write_ha_state()

    @callback
    def _async_write_state_changed(self) -> None:
        _LOGGER.info(f'_async_write_state_changed() {self.assumed_state=} {self._device.state=} {self._device.connection_status=}')
        self._is_on = self._device.is_connected
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore state and subscribe to device events."""
        await super().async_added_to_hass()
        self.async_on_remove(self._async_subscribe_to_device_change())

    @callback
    def _async_subscribe_to_device_change(self) -> Callable[[], None]:
        return self._device.subscribe_to_state_change(self._async_write_state_changed)

    @property
    def is_on(self) -> bool | None:
        """Power state of the device."""
        return self._device.is_connected

    async def async_turn_on(self) -> None:
        """Turn on the device."""
        await self._device.async_wait_for_connection_complete()

    async def async_turn_off(self) -> None:
        """Turn off the device."""
        await self._device.async_disconnect(reason=DisconnectionReason.USER)
