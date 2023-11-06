"""Config flow for CyberSW integration."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from bleak import BleakClient

#from .pycybersw.advertisement import CyberswitchAdvertisementData
from .pycybersw.advertisement import (
    parse_cyberswitch_advertisement,
    get_device_display_name
)
from .pycybersw.model import CyberswitchAdvertisementData

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothScanningMode,
    BluetoothServiceInfo,
    async_discovered_service_info,
    async_process_advertisements,
    async_ble_device_from_address,
)
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    OptionsFlow,
)
from homeassistant.const import (
    CONF_ADDRESS,
    #CONF_NAME,
    #CONF_TOKEN,
)
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from bleak_retry_connector import (
    BleakAbortedError,
    BleakClientWithServiceCache,
    BleakConnectionError,
    BleakNotFoundError,
    establish_connection,
)

from .const import (
    DOMAIN,
    OPTION_IDLE_DISCONNECT_DELAY,
    DEFAULT_IDLE_DISCONNECT_DELAY,
)
from .options_flow import CyberswitchOptionsFlow

_LOGGER = logging.getLogger(__name__)

# number of seconds to wait for a device to be put in pairing mode
WAIT_FOR_PAIRING_TIMEOUT = 30
CONNECT_TIMEOUT = 20


@dataclass
class DiscoveredCyberswitch:
    """Represents a discovered Cyberswitch device."""

    info: BluetoothServiceInfo
    device: CyberswitchAdvertisementData


class DeviceDisappearedError(Exception):
    """Raised when the discovered device disappears before pairing can be complete."""

    def __init__(self) -> None:
        super().__init__("Device disappeared")


class DevicePairingError(Exception):
    """Raised when pairing with the device wasn't successful."""

    def __init__(self) -> None:
        super().__init__("Device pairing error")


class CyberswitchConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Cyberswitch."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovery: DiscoveredCyberswitch | None = None
        self._discovered_devices: dict[str, DiscoveredCyberswitch] = {}
        self._pairing_task: asyncio.Task | None = None

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfo
    ) -> FlowResult:
        """Handle the bluetooth discovery step."""
        _LOGGER.info(f"discovered bluetooth device {discovery_info.address}")
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        device = parse_cyberswitch_advertisement(discovery_info)
        if device is None:
            return self.async_abort(reason="not_supported")
        self._discovery = DiscoveredCyberswitch(discovery_info, device)
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm discovery."""
        assert self._discovery is not None

        if user_input is not None:
            if not self._discovery.device.is_pairing:
                return await self.async_step_wait_for_pairing_mode()

            return self._create_cyberswitch_entry(self._discovery)

        self._set_confirm_only()
        #assert self._discovery.device.display_name
        #placeholders = {"name": self._discovery.device.display_name}
        display_name = get_device_display_name(self._discovery.info.name, self._discovery.info.address)
        placeholders = {"name": display_name}
        self.context["title_placeholders"] = placeholders
        return self.async_show_form(
            step_id="bluetooth_confirm", description_placeholders=placeholders
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the user step to pick discovered device."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]

            discovered = self._discovered_devices[address]

            assert discovered is not None

            self._discovery = discovered

            if not discovered.device.is_pairing:
                return await self.async_step_wait_for_pairing_mode()

            #address = discovered.info.address
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self._create_cyberswitch_entry(discovered)

        configured_addresses = self._async_current_ids()

        for info in async_discovered_service_info(self.hass):
            address = info.address
            if address in configured_addresses:
                continue
            device = parse_cyberswitch_advertisement(info)
            if device is None:
                _LOGGER.info(f"couldn't parse device {address} advertisement")
            else:
                #assert device.display_name
                display_name = get_device_display_name(info.name, address)
                #self._discovered_devices[display_name] = DiscoveredCyberswitch(
                self._discovered_devices[address] = DiscoveredCyberswitch(
                    info, device
                )

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(
                        {
                            key: get_device_display_name(value.info.name, value.info.address)
                            for key, value in self._discovered_devices.items()
                        }
                        #[
                        #    #d.device.display_name
                        #    get_device_display_name(d.info.name, d.info.address)
                        #    for d in self._discovered_devices.values()
                        #]
                    )
                }
            ),
        )

    async def async_step_wait_for_pairing_mode(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Wait for device to enter pairing mode."""
        if not self._pairing_task:
            self._pairing_task = self.hass.async_create_task(
                self._async_wait_for_pairing_mode()
            )
            return self.async_show_progress(
                step_id="wait_for_pairing_mode",
                progress_action="wait_for_pairing_mode",
            )

        try:
            await self._pairing_task
        except asyncio.TimeoutError:
            self._pairing_task = None
            return self.async_show_progress_done(next_step_id="pairing_mode_timeout")

        self._pairing_task = None

        return self.async_show_progress_done(next_step_id="wait_for_pairing")

    async def async_step_pairing_mode_timeout(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Inform the user that the device never entered pairing mode."""
        if user_input is not None:
            return await self.async_step_wait_for_pairing_mode()

        self._set_confirm_only()
        return self.async_show_form(step_id="pairing_timeout")

    async def async_step_wait_for_pairing(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Wait for device to complete pairing."""
        if not self._pairing_task:
            self._pairing_task = self.hass.async_create_task(
                self._async_wait_for_pairing()
            )
            return self.async_show_progress(
                step_id="wait_for_pairing",
                progress_action="wait_for_pairing",
            )

        try:
            try:
                await self._pairing_task
            finally:
                _LOGGER.info(f"async_step_wait_for_pairing finalize")
                self._pairing_task = None
        except (asyncio.TimeoutError, DeviceDisappearedError, DevicePairingError) as exn:
            _LOGGER.info(f"async_step_wait_for_pairing got error {exn=}")
            return self.async_show_progress_done(next_step_id="pairing_timeout")
        except Exception as exn:
            _LOGGER.info(f"async_step_wait_for_pairing got general error {exn=}")
            return self.async_show_progress_done(next_step_id="pairing_timeout")  #  FIXME
        _LOGGER.info(f"async_step_wait_for_pairing pairing complete")
        return self.async_show_progress_done(next_step_id="pairing_complete")

    async def async_step_pairing_timeout(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Inform the user that the device failed pairing."""
        if user_input is not None:
            return await self.async_step_wait_for_pairing()

        self._set_confirm_only()
        return self.async_show_form(step_id="pairing_timeout")

    async def async_step_pairing_complete(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Create a configuration entry for a device that entered pairing mode."""
        assert self._discovery

        await self.async_set_unique_id(
            self._discovery.info.address, raise_on_progress=False
        )
        self._abort_if_unique_id_configured()

        return self._create_cyberswitch_entry(self._discovery)

    def _create_cyberswitch_entry(self, discovery: DiscoveredCyberswitch) -> FlowResult:
        #assert discovery.device.display_name
        display_name = get_device_display_name(discovery.info.name, discovery.info.address)
        _LOGGER.info(f'_create_cyberswitch_entry {discovery=} {display_name=}')
        return self.async_create_entry(
            #title=discovery.device.display_name,
            title=display_name,
            data={
                CONF_ADDRESS: discovery.info.address,
                #CONF_TOKEN: discovery.device.pairing_token,
            },
            options={
                OPTION_IDLE_DISCONNECT_DELAY: DEFAULT_IDLE_DISCONNECT_DELAY,
            },
        )

    async def _async_wait_for_pairing_mode(self) -> None:
        """Process advertisements until pairing mode is detected."""
        assert self._discovery
        #device = self._discovery.device

        def is_device_in_pairing_mode(
            service_info: BluetoothServiceInfo,
        ) -> bool:
            #return device.supported(service_info) and device.is_pairing
            flags = parse_cyberswitch_advertisement(service_info)
            _LOGGER.info(f"{flags is not None=} is_device_in_pairing_mode={flags is not None and flags.is_pairing}")
            return flags is not None and flags.is_pairing

        try:
            await async_process_advertisements(
                self.hass,
                is_device_in_pairing_mode,
                {"address": self._discovery.info.address},
                BluetoothScanningMode.ACTIVE,
                WAIT_FOR_PAIRING_TIMEOUT,
            )
        finally:
            self.hass.async_create_task(
                self.hass.config_entries.flow.async_configure(flow_id=self.flow_id)
            )

    async def _async_wait_for_pairing(self) -> None:
        """Wait until pairing is complete."""
        assert self._discovery
        #device = self._discovery.device
        _LOGGER.info(f"_async_wait_for_pairing")
        try:
            def get_ble_device():
                _LOGGER.info(f"_async_wait_for_pairing get_ble_device")
                ble_device = async_ble_device_from_address(self.hass, self._discovery.info.address, connectable=True)
                _LOGGER.info(f"_async_wait_for_pairing get_ble_device got {ble_device=}")
                if not ble_device:
                    raise DeviceDisappearedError()
                return ble_device

            client = await establish_connection(
                BleakClientWithServiceCache,
                get_ble_device(),
                get_device_display_name(self._discovery.info.name, self._discovery.info.address),
                disconnected_callback=None,
                use_services_cache=True,
                ble_device_callback=get_ble_device,
            )
            _LOGGER.info(f"_async_wait_for_pairing_mode got {client=}")
            try:
                if not await client.pair():
                    _LOGGER.info(f"_async_wait_for_pairing_mode pairing failed")
                    raise DevicePairingError()
                _LOGGER.info(f"_async_wait_for_pairing_mode pairing succeeded (?)")
            finally:
                await client.disconnect()
            #client = BleakClient(ble_device) #, disconnected_callback=)
            #async with asyncio_timeout(WAIT_FOR_PAIRING_TIMEOUT):
            #    await client.connect(timeout=CONNECT_TIMEOUT)
            #    paired = await client.pair()
            #except asyncio.TimeoutError as exc:
            #    raise exc
        finally:
            _LOGGER.info(f"_async_wait_for_pairing_mode finally")
            self.hass.async_create_task(
                self.hass.config_entries.flow.async_configure(flow_id=self.flow_id)
            )
        # def is_device_in_pairing_mode(
        #     service_info: BluetoothServiceInfo,
        # ) -> bool:
        #     #return device.supported(service_info) and device.is_pairing
        #     flags = parse_cyberswitch_advertisement(service_info)
        #     _LOGGER.info(f"{flags is not None=} is_device_in_pairing_mode={flags is not None and flags.is_pairing}")
        #     return flags is not None and flags.is_pairing

        # try:
        #     await async_process_advertisements(
        #         self.hass,
        #         is_device_in_pairing_mode,
        #         {"address": self._discovery.info.address},
        #         BluetoothScanningMode.ACTIVE,
        #         WAIT_FOR_PAIRING_TIMEOUT,
        #     )
        # finally:
        #     self.hass.async_create_task(
        #         self.hass.config_entries.flow.async_configure(flow_id=self.flow_id)
        #     )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> OptionsFlow:
        """Create the options flow."""
        return CyberswitchOptionsFlow(config_entry)
