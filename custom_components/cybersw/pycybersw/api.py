from __future__ import annotations

import asyncio
import logging
import struct
from asyncio import Lock
from dataclasses import dataclass
from enum import IntEnum
from collections.abc import Callable

from bleak import BleakClient, BleakGATTCharacteristic
from bleak.exc import BleakDBusError
from events import Events

from .const import (
    SWITCH_STATE_CHARACTERISTIC,
    WRITE_CONFIG_CHARACTERISTIC,
    READ_CONFIG_CHARACTERISTIC,
    BATTERY_CHARACTERISTIC,
    UPTIME_CHARACTERISTIC,
    CONN_INT_CHARACTERISTIC,

    # FIRMWARE_REVISION_CHARACTERISTIC,
    # HARDWARE_REVISION_CHARACTERISTIC,
    # MANUFACTURER_NAME_CHARACTERISTIC,
    # MODEL_NUMBER_CHARACTERISTIC,
    # SOFTWARE_REVISION_CHARACTERISTIC,
)
from .model import (
    CyberswitchDeviceCharacteristicData,
    CyberswitchDeviceState,
    CyberswitchDeviceConfig,
)

# values less than this have no effect
#MIN_DEVICE_VOLUME = 10
#MIN_FAN_SPEED = 10

# When auto fan is enabled, the device will poll for fan power state updates since
# the device doesn't push them. This is the interval of temperature updates to
# wait for before requesting the current state of the device.
#AUTO_FAN_TEMP_POLL_INTERVAL = 5

# number of times to retry a transient command failure before giving up
RETRY_WRITE_FAILURE_COUNT = 5
RETRY_SLEEP_DURATIONS = [0, 0.5, 1, 1, 2]
DBUS_ERRORS_TO_RETRY = (
    "org.bluez.Error",
    "org.bluez.Error.Failed",
    "org.bluez.Error.InProgress",
)

_LOGGER = logging.getLogger(__name__)


class Command(IntEnum):
    #MOTOR_SPEED = 1
    # ...
    #ENABLE_LAST_POWERED_STATE = 35
    SWITCH = 0


class ResponseCommand(IntEnum):
    #SEND_ON_SCHEDULE = 1
    # ...
    #SEND_OTHER_SETTINGS = 6
    #OTA_IDX = 7
    #OTA_FAILED = 8
    #TEMPERATURE = 9
    WHATEVER = 10


class MissingCharacteristicError(Exception):
    """Raised when a required characteristic is missing on a client."""

    def __init__(self, uuid: str | None = None) -> None:
        super().__init__(f"Missing characteristic {uuid}")


@dataclass
class CharacteristicReference:
    uuid: str
    required: bool = True

    def get(self, client: BleakClient) -> BleakGATTCharacteristic:
        char = client.services.get_characteristic(self.uuid)

        if char is None and self.required:
            raise MissingCharacteristicError(self.uuid)

        return char


class CyberswitchDeviceApi:
    event_names = ("on_disconnect", "on_state_patched")

    def __init__(
        self,
        client: BleakClient | None = None,
        format_log_message: Callable[[str], str] | None = None,
    ) -> None:
        self.unsubscribe_all_events()
        self._client = client
        self._write_lock = Lock()
        self._ = format_log_message or (lambda msg: msg)
        self._switch_state_char = CharacteristicReference(SWITCH_STATE_CHARACTERISTIC)
        self._write_config_char = CharacteristicReference(WRITE_CONFIG_CHARACTERISTIC)
        self._read_config_char = CharacteristicReference(READ_CONFIG_CHARACTERISTIC)
        self._battery_char = CharacteristicReference(BATTERY_CHARACTERISTIC)
        self._uptime_char = CharacteristicReference(UPTIME_CHARACTERISTIC)
        self._connection_interval_char = CharacteristicReference(CONN_INT_CHARACTERISTIC)
        self._info_chars = [
        #    CharacteristicReference(MANUFACTURER_NAME_CHARACTERISTIC),
        #    CharacteristicReference(MODEL_NUMBER_CHARACTERISTIC),
        #    CharacteristicReference(HARDWARE_REVISION_CHARACTERISTIC),
        #    CharacteristicReference(FIRMWARE_REVISION_CHARACTERISTIC),
        #    # Older Cyberswitch devices don't have this
        #    CharacteristicReference(SOFTWARE_REVISION_CHARACTERISTIC, required=False),
        ]
        self._required_chars = [
            *[
                ref
                for ref in [getattr(self, c) for c in dir(self)]
                if isinstance(ref, CharacteristicReference) and ref.required
            ],
            *[ref for ref in self._info_chars if ref.required],
        ]

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    def load_client(self, client: BleakClient) -> None:
        self._client = client
        self._info = None

        for char in self._required_chars:
            char.get(client)

    def _require_client(self, require_connection: bool = True) -> BleakClient:
        if self._client is None:
            raise AssertionError("client was None")

        if require_connection and not self._client.is_connected:
            raise AssertionError("client was not connected")

        return self._client

    def unsubscribe_all_events(self) -> None:
        self.events = Events(self.event_names)

    async def async_disconnect(self) -> None:
        client = self._require_client()
        await client.disconnect()

    async def async_get_info(self) -> CyberswitchDeviceCharacteristicData | None:
        client = self._require_client(False)
        if not client.is_connected:
            return None
        string_props: list[str | None] = []
        #for char_ref in self._info_chars:
        #    char = char_ref.get(client)
        #    if not char:
        #        value = None
        #    else:
        #        value = (await client.read_gatt_char(char)).decode().split("\0")[0]
        #    string_props.append(value)
        string_props.append(None) # MANUFACTURER_NAME_CHARACTERISTIC
        string_props.append(None) # MODEL_NUMBER_CHARACTERISTIC
        string_props.append(None) # HARDWARE_REVISION_CHARACTERISTIC
        string_props.append(None) # FIRMWARE_REVISION_CHARACTERISTIC
        string_props.append(None) # SOFTWARE_REVISION_CHARACTERISTIC

        return CyberswitchDeviceCharacteristicData(*string_props)  # type: ignore

    async def async_set_power(self, on: bool) -> None:
        #await self._async_write_state(bytes([Command.MOTOR_ENABLED, 1 if on else 0]))
        await self._async_send_command(bytes([
            # Command.SWITCH,
            1 if on else 0
        ]))

    async def async_set_connection_interval(self, connection_interval_ms: int) -> None:
        await self._async_write_data(self._connection_interval_char, struct.pack(
            "<H",
            connection_interval_ms,
        ))

#    async def async_set_light_brightness(self, brightness: int) -> None:
#        if brightness < 0 or brightness > 100:
#            raise ValueError(f"Brightness must be between 0 and 100 - got {brightness}")
#
#        button_triggered_brightness = 0 if brightness == 0 else brightness + 10
#        await self._async_write_state(
#            bytes(
#                [
#                    Command.NIGHTLIGHT,
#                    1,
#                    brightness,
#                    min(100, button_triggered_brightness),
#                ]
#            )
#        )
#
#    async def async_set_night_mode_enabled(
#        self, enabled: bool, brightness: int
#    ) -> None:
#        await self._async_write_state(
#            bytes([Command.NIGHTLIGHT, 0 if enabled else 1, 0, brightness])
#        )
#
#    async def async_set_fan_power(self, on: bool) -> None:
#        await self._async_write_state(bytes([Command.FAN_ENABLED, 1 if on else 0]))
#
#    async def async_set_auto_temp_enabled(self, on: bool) -> None:
#        await self._async_write_state(
#            bytes([Command.AUTO_TEMP_ENABLED, 1 if on else 0])
#        )
#        await self.async_request_other_settings()
#
#    async def async_set_volume(self, volume: int) -> None:
#        if volume < 0 or volume > 100:
#            raise ValueError(f"Volume must be between 0 and 100 - got {volume}")
#
#        await self._async_write_state(bytes([Command.MOTOR_SPEED, volume]))
#
#    async def async_set_fan_speed(self, speed: int) -> None:
#        if speed < 0 or speed > 100:
#            raise ValueError(f"Speed must be between 0 and 100 - got {speed}")
#
#        await self._async_write_state(bytes([Command.FAN_SPEED, speed]))
#
#    async def async_set_auto_temp_threshold(self, threshold_f: int) -> None:
#        if threshold_f < 0 or threshold_f > 100:
#            raise ValueError(
#                f"Temperature must be between 0 and 100 - got {threshold_f}"
#            )
#
#        await self._async_write_state(bytes([Command.AUTO_TEMP_THRESHOLD, threshold_f]))
#        await self.async_request_other_settings()
#
    async def async_read_state(self, use_cached: bool = False) -> CyberswitchDeviceState:
        client = self._require_client()

        data = await client.read_gatt_char(
            self._switch_state_char.get(client), use_cached=use_cached
        )
        return unpack_switch_state(data)

    async def async_subscribe(self) -> None:
        client = self._require_client(False)

        if not client.is_connected:
            return

        await client.start_notify(
            self._switch_state_char.get(client),
            lambda _, payload: self.events.on_state_patched(unpack_switch_state(payload))
        )
        await client.start_notify(
            self._battery_char.get(client),
            lambda _, payload: self.events.on_state_patched(unpack_battery_state(payload))
        )
        await client.start_notify(
            self._uptime_char.get(client),
            lambda _, payload: self.events.on_state_patched(unpack_uptime_state(payload))
        )

    async def _async_write_data(self, char: CharacteristicReference, data: bytes) -> None:
        client = self._require_client(False)

        attempts = 0

        async with self._write_lock:
            last_ex: BleakDBusError | None = None

            while client.is_connected and attempts <= RETRY_WRITE_FAILURE_COUNT:
                try:
                    message = f"write {data.hex('-')}"
                    if attempts > 0 and last_ex is not None:
                        message += f" (attempt {attempts+1}, last error: {last_ex})"
                    _LOGGER.debug(self._(message))
                    await client.write_gatt_char(char.get(client), data, response=True)
                    return
                except BleakDBusError as ex:
                    last_ex = ex
                    if ex.dbus_error in DBUS_ERRORS_TO_RETRY:
                        sleep_duration = RETRY_SLEEP_DURATIONS[
                            attempts % len(RETRY_SLEEP_DURATIONS)
                        ]
                        attempts += 1

                        if attempts > RETRY_WRITE_FAILURE_COUNT:
                            raise Exception(
                                f"Got transient error {attempts} times"
                            ) from ex

                        await asyncio.sleep(sleep_duration)
                    else:
                        raise

    async def _async_send_command(self, data: bytes) -> None:
        await self._async_write_data(self._switch_state_char, data)

    async def _async_write_config_command(self, data: bytes) -> None:
        await self._async_write_data(self._write_config_char, data)

    async def async_read_config(self, use_cached: bool = False) -> CyberswitchDeviceConfig:
        client = self._require_client()
        data = await client.read_gatt_char(
            self._read_config_char.get(client), use_cached=use_cached
        )
        return unpack_config(data)

    async def async_write_config(self, config: CyberswitchDeviceConfig) -> None:
        data = bytes([ 0x7F ]) + pack_config(config)
        await self._async_write_config_command(data)

    async def async_store_config(self) -> None:
        await self._async_write_config_command(bytes([ 0x80 ]))


    async def async_restore_config(self) -> None:
        await self._async_write_config_command(bytes([ 0x81 ]))


def unpack_response_command(command: ResponseCommand, data: bytes) -> CyberswitchDeviceState:
    result = CyberswitchDeviceState()

#    if command == ResponseCommand.SEND_OTHER_SETTINGS:
#        (auto_enabled, target_temperature) = struct.unpack("<xxxxxxxxxxBB", data[0:12])
#
#        result.fan_auto_enabled = bool(auto_enabled)
#        result.target_temperature = target_temperature
#    if command == ResponseCommand.TEMPERATURE:
#        [temp] = struct.unpack("<f", data[0:4])
#        result.temperature = round(temp, 2)
#
    return result


def unpack_switch_state(data: bytes) -> CyberswitchDeviceState:
    (
        on,
#        fan_speed,
#        fan_on,
#        light_mode,
#        light_brightness,
#        night_mode_brightness,
#    ) = struct.unpack("<BxBBxxxxxxxxxxxBBBx", data)
    ) = struct.unpack("<B", data)
#     night_mode_enabled: bool = light_mode == 0 and light_brightness == 0
    return CyberswitchDeviceState(
        on=bool(on),
#        light_on=not night_mode_enabled and light_brightness > 0,
#        night_mode_enabled=night_mode_enabled,
    )

def unpack_battery_state(data: bytes) -> CyberswitchDeviceState:
    (
        battery_level,
        _, # voltage,
        _, # raw_reading,
        _, # calibrated
    ) = struct.unpack("<BHHB", data)

    return CyberswitchDeviceState(
        battery_level=battery_level
    )

def unpack_uptime_state(data: bytes) -> CyberswitchDeviceState:
    (
        uptime,
    ) = struct.unpack("<Q", data)

    return CyberswitchDeviceState(
        uptime=uptime
    )

def unpack_config(data: bytes) -> CyberswitchDeviceConfig:
    (
        switch_angle_on,
        switch_angle_off,
        switch_angle_midpoint,
        switch_inverted,
        switch_delay_ms,
        connection_interval_ms,
    ) = struct.unpack("<bbb?HH", data)
    return CyberswitchDeviceConfig(
        switch_angle_midpoint=switch_angle_midpoint,
        switch_angle_on=switch_angle_on,
        switch_angle_off=switch_angle_off,
        switch_inverted=switch_inverted,
        switch_delay_ms=switch_delay_ms,
        connection_interval_ms=connection_interval_ms,
    )


def pack_config(config: CyberswitchDeviceConfig) -> bytes:
    return struct.pack(
        "<bbb?HH",
        config.switch_angle_on,
        config.switch_angle_off,
        config.switch_angle_midpoint,
        config.switch_inverted,
        config.switch_delay_ms,
        config.connection_interval_ms,
    )
