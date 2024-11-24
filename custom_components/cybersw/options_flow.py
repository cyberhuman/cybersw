"""Options flow for CyberSW integration."""
import asyncio
import logging
from typing import Any

from .pycybersw.model import CyberswitchDeviceConfig
from homeassistant.config_entries import (
    ConfigEntry,
    OptionsFlowWithConfigEntry,
)
from homeassistant.const import (
    DEGREE,
    UnitOfTime,
)
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

import voluptuous as vol

from .const import (
    DOMAIN,
    OPTION_IDLE_DISCONNECT_DELAY,
)

from .models import CyberswitchConfigurationData
from .coordinator import CyberswitchCoordinator


_LOGGER = logging.getLogger(__name__)

class CyberswitchOptionsFlow(OptionsFlowWithConfigEntry):
    """Handle an options flow for Cyberswitch."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        super().__init__(config_entry)
        self._async_task : asyncio.Task | None = None
        self._config : CyberswitchDeviceConfig | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "hass_config",
                "device_config_wait_read",
                "device_config_wait_store",
                "device_config_wait_restore",
            ]
        )

    async def async_step_device_config_wait_read(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Wait to connect to the device and read the config."""
        if not self._async_task:
            self._async_task = self.hass.async_create_task(
                self._async_read_task()
            )
        if not self._async_task.done():
            return self.async_show_progress(
                step_id="device_config_wait_read",
                progress_action="device_config_wait_read",
                progress_task=self._async_task,
            )
        try:
            await self._async_task
        except asyncio.TimeoutError:
            self._async_task = None
            return self.async_show_progress_done(next_step_id="read_timeout")
        self._async_task = None
        return self.async_show_progress_done(next_step_id="device_config")

    async def _async_read_task(self):
        coordinator: CyberswitchCoordinator = self.hass.data[DOMAIN][self.config_entry.entry_id]
        config: CyberswitchConfigurationData = coordinator.config
        try:
            self._config = await config.device.async_read_config()
        finally:
            self.hass.async_create_task(
                self.hass.config_entries.options.async_configure(flow_id=self.flow_id)
            )

    async def async_step_device_config(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the device-side config."""
        assert self._config
        if user_input is not None:
            self._config = CyberswitchDeviceConfig(
                switch_angle_midpoint=int(user_input["switch_angle_midpoint"]),
                switch_angle_on=int(user_input["switch_angle_on"]),
                switch_angle_off=int(user_input["switch_angle_off"]),
                switch_inverted=bool(user_input["switch_inverted"]),
                switch_delay_ms=int(user_input["switch_delay_ms"]),
                connection_interval_ms=int(user_input["connection_interval_ms"])
            )
            return await self.async_step_device_config_wait_write()

        return self.async_show_form(
            step_id="device_config",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "switch_angle_midpoint",
                        default=self._config.switch_angle_midpoint,
                    ) : NumberSelector(
                        NumberSelectorConfig(
                            min=-45,
                            max=45,
                            mode=NumberSelectorMode.BOX,
                            unit_of_measurement=DEGREE,
                        )
                    ),
                    vol.Required(
                        "switch_angle_on",
                        default=self._config.switch_angle_on,
                    ) : NumberSelector(
                        NumberSelectorConfig(
                            min=0,
                            max=45,
                            mode=NumberSelectorMode.BOX,
                            unit_of_measurement=DEGREE,
                        )
                    ),
                    vol.Required(
                        "switch_angle_off",
                        default=self._config.switch_angle_off,
                    ) : NumberSelector(
                        NumberSelectorConfig(
                            min=0,
                            max=45,
                            mode=NumberSelectorMode.BOX,
                            unit_of_measurement=DEGREE,
                        )
                    ),
                    vol.Required(
                        "switch_inverted",
                        default=self._config.switch_inverted,
                    ) : BooleanSelector(),
                    vol.Required(
                        "switch_delay_ms",
                        default=self._config.switch_delay_ms,
                    ) : NumberSelector(
                        NumberSelectorConfig(
                            min=0,
                            max=1000,
                            mode=NumberSelectorMode.BOX,
                            unit_of_measurement=UnitOfTime.MILLISECONDS,
                        )
                    ),
                    vol.Required(
                        "connection_interval_ms",
                        default=self._config.connection_interval_ms,
                    ) : NumberSelector(
                        NumberSelectorConfig(
                            min=0,
                            max=4000,
                            mode=NumberSelectorMode.BOX,
                            unit_of_measurement=UnitOfTime.MILLISECONDS,
                        )
                    ),
                }
            ),
        )

    async def async_step_device_config_wait_write(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Wait to connect to the device and write the config."""
        if not self._async_task:
            self._async_task = self.hass.async_create_task(
                self._async_write_config_task()
            )
        if not self._async_task.done():
            return self.async_show_progress(
                step_id="device_config_wait_write",
                progress_action="device_config_wait_write",
                progress_task=self._async_task,
            )
        try:
            await self._async_task
        except asyncio.TimeoutError:
            self._async_task = None
            return self.async_show_progress_done(next_step_id="write_timeout")
        self._async_task = None
        return self.async_show_progress_done(next_step_id="device_config_done")

    async def _async_write_config_task(self):
        coordinator: CyberswitchCoordinator = self.hass.data[DOMAIN][self.config_entry.entry_id]
        config: CyberswitchConfigurationData = coordinator.config
        try:
            await config.device.async_write_config(self._config)
        finally:
            self.hass.async_create_task(
                self.hass.config_entries.options.async_configure(flow_id=self.flow_id)
            )

    async def async_step_device_config_wait_store(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Wait to connect to the device and store the config."""
        if not self._async_task:
            self._async_task = self.hass.async_create_task(
                self._async_store_config_task()
            )
        if not self._async_task.done():
            return self.async_show_progress(
                step_id="device_config_wait_store",
                progress_action="device_config_wait_store",
                progress_task=self._async_task,
            )
        try:
            await self._async_task
        except asyncio.TimeoutError:
            self._async_task = None
            return self.async_show_progress_done(next_step_id="store_timeout")
        self._async_task = None
        return self.async_show_progress_done(next_step_id="device_config_done")

    async def _async_store_config_task(self):
        coordinator: CyberswitchCoordinator = self.hass.data[DOMAIN][self.config_entry.entry_id]
        config: CyberswitchConfigurationData = coordinator.config
        try:
            await config.device.async_store_config()
        finally:
            self.hass.async_create_task(
                self.hass.config_entries.options.async_configure(flow_id=self.flow_id)
            )

    async def async_step_device_config_wait_restore(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Wait to connect to the device and restore the config."""
        if not self._async_task:
            self._async_task = self.hass.async_create_task(
                self._async_restore_config_task()
            )
        if not self._async_task.done():
            return self.async_show_progress(
                step_id="device_config_wait_restore",
                progress_action="device_config_wait_restore",
                progress_task=self._async_task,
            )
        try:
            await self._async_task
        except asyncio.TimeoutError:
            self._async_task = None
            return self.async_show_progress_done(next_step_id="restore_timeout")
        self._async_task = None
        return self.async_show_progress_done(next_step_id="device_config_done")

    async def _async_restore_config_task(self):
        coordinator: CyberswitchCoordinator = self.hass.data[DOMAIN][self.config_entry.entry_id]
        config: CyberswitchConfigurationData = coordinator.config
        try:
            await config.device.async_restore_config()
        finally:
            self.hass.async_create_task(
                self.hass.config_entries.options.async_configure(flow_id=self.flow_id)
            )

    async def async_step_device_config_done(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        return self.async_create_entry(title=None, data=self.options)

    async def async_step_hass_config(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the client-side options."""
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    OPTION_IDLE_DISCONNECT_DELAY: user_input["idle_disconnect_delay_ms"]
                }
            )

        return self.async_show_form(
            step_id="hass_config",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "idle_disconnect_delay_ms",
                        default=self.options.get(OPTION_IDLE_DISCONNECT_DELAY, 0)
                    #) : vol.All(vol.Coerce(int), vol.Range(min=0, max=60000)),
                    ) : NumberSelector(
                        NumberSelectorConfig(
                            min=0,
                            max=60000,
                            mode=NumberSelectorMode.BOX,
                            unit_of_measurement=UnitOfTime.MILLISECONDS,
                        )
                    ),
                }
            ),
        )
