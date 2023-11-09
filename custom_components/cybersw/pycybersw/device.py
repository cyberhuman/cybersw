from __future__ import annotations

import asyncio
import logging
from asyncio import AbstractEventLoop, CancelledError, Event, Lock, Task
from datetime import datetime
from enum import Enum
from typing import Any
from collections.abc import Callable

from bleak.backends.device import BLEDevice
from bleak_retry_connector import (
    BleakAbortedError,
    BleakClientWithServiceCache,
    BleakConnectionError,
    BleakNotFoundError,
    establish_connection,
)
from events import Events
from transitions import EventData, Machine, State

from .advertisement import get_device_display_name
from .api import MissingCharacteristicError, CyberswitchDeviceApi
from .commands import (
    CommandProcessorState,
    CyberswitchCommandData,
    CyberswitchCommandProcessor,
    CyberswitchCommandResult,
    create_command_processor,
    read_device_config,
    write_device_config,
    store_device_config,
    restore_device_config,
    get_device_info,
)
from .const import UNEXPECTED_ERROR_LOG_MESSAGE
from .model import (
    CyberswitchAdvertisementData,
    CyberswitchDeviceCharacteristicData,
    CyberswitchDeviceModel,
    CyberswitchDeviceState,
    CyberswitchDeviceConfig,
    CyberswitchFirmwareVersion,
    UnknownCyberswitchState,
)
from .store import CyberswitchStateStore

_LOGGER = logging.getLogger(__name__)

MAX_RECONNECTION_ATTEMPTS = 3
RECONNECTION_DELAY_SECONDS = 0.25
DEVICE_UNAVAILABLE_EXCEPTIONS = (
    BleakAbortedError,
    BleakConnectionError,
    BleakNotFoundError,
    MissingCharacteristicError,
)


class CyberswitchConnectionStatus(Enum):
    DISCONNECTED = 0
    CONNECTING = 1
    CONNECTED = 2


class DisconnectionReason(Enum):
    # disconnect was initiated by the user
    USER = 0
    # the bluetooth connection was lost
    DEVICE = 1
    # a connection attempt failed with a known error
    # like a timeout or device not found or missing characteristic
    DEVICE_UNAVAILABLE = 2
    # automatic disconnect on idle
    IDLE = 3
    # an exception was thrown during connection or
    # command execution that was uncaught
    UNEXPECTED_ERROR = 4


class CyberswitchDeviceUnavailableError(Exception):
    pass


class CyberswitchDevice:
    def __init__(
        self,
        device: BLEDevice,
        adv_data: CyberswitchAdvertisementData,
        idle_disconnect_delay_ms: int | None = None,
        loop: AbstractEventLoop | None = None,
    ) -> None:
        self.events = Events(
            (
                # one or more state properties have changed
                "on_state_change",
                # CyberswitchConnectionStatus
                "on_connection_status_change",
                # time it takes to create a bluetooth connection, authenticate
                # and subscribe to notifications
                "on_connection_load_time",
                # time between connection ready and disconnect
                "on_connection_duration",
            )
        )
        self._device = device
        self._adv_data = adv_data
        self._loop = loop if loop is not None else asyncio.get_running_loop()
        self._last_dispatched_connection_status: CyberswitchConnectionStatus | None = None
        self._connection_complete = Event()
        self._connections_exhausted = Event()
        self._connection_attempts: int = 0
        self._connection_start_time: datetime | None = None
        self._connection_ready_time: datetime | None = None
        self._api: CyberswitchDeviceApi | None = None
        self._store = CyberswitchStateStore(self._adv_data)
        self._connect_lock = Lock()
        self._command_lock = Lock()
        self._connection_task: Task[None] | None = None
        self._reconnection_task: Task[None] | None = None
        self.idle_disconnect_delay_ms: int = idle_disconnect_delay_ms if idle_disconnect_delay_ms is not None else 0
        self._idle_disconnect_task: Task[None] | None = None
        self._current_command: CyberswitchCommandProcessor | None = None
        self._expected_disconnect: bool = False
        self._last_disconnect_reason: DisconnectionReason | None = None

        not_disconnected = [
            CyberswitchConnectionStatus.CONNECTING,
            CyberswitchConnectionStatus.CONNECTED,
        ]

        states = [
            State(
                CyberswitchConnectionStatus.DISCONNECTED,
                on_enter=self._on_device_disconnected,
            ),
            State(CyberswitchConnectionStatus.CONNECTING),
            State(CyberswitchConnectionStatus.CONNECTED, on_enter=self._on_connection_ready),
        ]

        self._machine = Machine(
            model_attribute="connection_status",
            states=states,
            initial=CyberswitchConnectionStatus.DISCONNECTED,
            after_state_change=self._on_connection_status_change,
            send_event=True,
            on_exception=self._on_machine_exception,
        )
        self._machine.add_transition(
            "connection_start",
            CyberswitchConnectionStatus.DISCONNECTED,
            CyberswitchConnectionStatus.CONNECTING,
            before=self._on_connection_start,
        )
        self._machine.add_transition(
            "connection_ready",
            CyberswitchConnectionStatus.CONNECTING,
            CyberswitchConnectionStatus.CONNECTED,
        )
        self._machine.add_transition(
            "device_disconnected",
            not_disconnected,
            CyberswitchConnectionStatus.DISCONNECTED,
            after=self._after_device_disconnected,
        )
        self._machine.add_transition(
            "command_execution_cancelled",
            [CyberswitchConnectionStatus.DISCONNECTED, CyberswitchConnectionStatus.CONNECTED],
            None,
            before=lambda _: self._cancel_current_command(),
        )

        def set_expected_disconnect(expected: bool) -> None:
            self._expected_disconnect = expected

        self._machine.add_transition(
            "command_execution_cancelled",
            CyberswitchConnectionStatus.CONNECTING,
            CyberswitchConnectionStatus.DISCONNECTED,
            prepare=lambda _: set_expected_disconnect(True),
            before=lambda _: self._cancel_current_command(),
            after=lambda _: set_expected_disconnect(False),
        )

        self.events.on_connection_load_time += lambda t: _LOGGER.debug(
            self._(f"Connection load time: {t}")
        )
        self.events.on_connection_duration += lambda t: _LOGGER.debug(
            self._(f"Connection duration: {t}")
        )

    @property
    def name(self) -> str:
        return self._device.name

    @property
    def address(self) -> str:
        return self._device.address

    @property
    def model(self) -> CyberswitchDeviceModel:
        return self._adv_data.model

    @property
    def firmware_version(self) -> CyberswitchFirmwareVersion:
        return self._adv_data.firmware_version

    @property
    def connection_status(self) -> CyberswitchConnectionStatus:
        return self._machine.connection_status

    @property
    def is_connected(self) -> bool:
        return self.connection_status == CyberswitchConnectionStatus.CONNECTED

    @property
    def state(self) -> CyberswitchDeviceState:
        return self._store.current

    def subscribe_to_state_change(
        self, callback: Callable[[], None]
    ) -> Callable[[], None]:
        """Subscribe to device state and connection status change.
        Returns a callback to unsubscribe.
        """

        def wrapped_callback(*_: Any) -> None:
            callback()

        self.events.on_state_change += wrapped_callback
        self.events.on_connection_status_change += wrapped_callback

        def unsubscribe() -> None:
            self.events.on_state_change -= wrapped_callback
            self.events.on_connection_status_change -= wrapped_callback

        return unsubscribe

    async def async_disconnect(self, reason=DisconnectionReason.USER) -> None:
        _LOGGER.info(f'async_idle_disconnect {self.connection_status=}')
        if self.connection_status == CyberswitchConnectionStatus.DISCONNECTED:
            return

        self._expected_disconnect = True
        try:
            _LOGGER.info('async_idle_disconnect _cancel_current_command()')
            self._cancel_current_command()
            _LOGGER.info('async_idle_disconnect _async_cancel_idle_disconnect()')
            self._async_cancel_idle_disconnect()

            if (
                self._reconnection_task is not None
                and not self._reconnection_task.done()
            ):
                _LOGGER.info('async_idle_disconnect _reconnection_task.cancel()')
                self._reconnection_task.cancel()

            if self._connection_task is not None and not self._connection_task.done():
                _LOGGER.info('async_idle_disconnect _connection_task.cancel()')
                self._connection_task.cancel()

            if self._api is not None:
                _LOGGER.info('async_idle_disconnect _api.async_disconnect()')
                await self._api.async_disconnect()

            _LOGGER.info(f'async_idle_disconnect _machine.device_disconnected({reason=})')
            self._machine.device_disconnected(reason=reason)
        finally:
            _LOGGER.info('async_idle_disconnect finally')
            self._expected_disconnect = False

    async def async_get_info(self) -> CyberswitchDeviceCharacteristicData | None:
        result = await self.async_execute_command(get_device_info())
        return result.response

    async def async_read_config(self) -> CyberswitchDeviceConfig | None:
        result = await self.async_execute_command(read_device_config())
        return result.response

    async def async_write_config(self, config: CyberswitchDeviceConfig) -> None:
        result = await self.async_execute_command(write_device_config(config))
        return result.response

    async def async_store_config(self) -> None:
        result = await self.async_execute_command(store_device_config())
        return result.response

    async def async_restore_config(self) -> None:
        result = await self.async_execute_command(restore_device_config())
        return result.response

    def _async_cancel_idle_disconnect(self):
        if self._idle_disconnect_task is not None and not self._idle_disconnect_task.done():
            self._idle_disconnect_task.cancel()

    def _async_start_idle_disconnect(self):
        if self.is_connected and self.idle_disconnect_delay_ms > 0:
            # automatically disconnect after the idle timeout
            self._idle_disconnect_task = self._loop.create_task(
                self._async_idle_disconnect(),
                name=f"[Disconnect] {self.display_name}",
            )

    async def async_execute_command(self, data: CyberswitchCommandData) -> CyberswitchCommandResult:
        self._cancel_current_command()
        # cancel previous auto disconnect task
        self._async_cancel_idle_disconnect()

        start_time = datetime.now()
        command = create_command_processor(
            self._loop,
            start_time,
            data,
            format_log_message=self._,
        )
        self._current_command = command

        try:
            await self._async_execute_current_command()

        except CancelledError:
            self._machine.command_execution_cancelled()

            # when async_disconnect() is called, return a cancelled command
            # instead of raising since the cancellation is expected by the user
            if (
                not self.is_connected
                and self._last_disconnect_reason in (DisconnectionReason.USER, DisconnectionReason.DEVICE)
            ):
                pass
            else:
                self._async_start_idle_disconnect()
                raise
        except Exception:
            self._async_start_idle_disconnect()
            raise

        try:
            result = await command.result
        finally:
            self._async_start_idle_disconnect()

        self._current_command = None

        return result

    def _cancel_current_command(self) -> None:
        if self._current_command is None:
            return

        self._current_command.cancel()
        self._current_command = None

    async def _async_execute_current_command(self) -> None:
        command = self._current_command

        try:
            try:
                await self._async_wait_for_connection_complete()
            except CancelledError:
                raise

            async with self._command_lock:
                if (
                    self._api is not None
                    and command is not None
                    and command.state != CommandProcessorState.COMPLETE
                ):
                    await command.async_execute(self._api, raise_on_cancel=True)
        except CyberswitchDeviceUnavailableError:
            self._machine.device_disconnected(
                reason=DisconnectionReason.DEVICE_UNAVAILABLE
            )
        except Exception:
            self._machine.device_disconnected(
                reason=DisconnectionReason.UNEXPECTED_ERROR
            )

    async def _async_wait_for_connection_complete(self) -> None:
        if self.connection_status == CyberswitchConnectionStatus.DISCONNECTED:
            async with self._connect_lock:
                if self._connection_task is None or self._connection_task.done():
                    self._connection_task = self._loop.create_task(
                        self._async_connect(), name=f"[Connect] {self.display_name}"
                    )
            await self._connection_task

        await self._connection_complete.wait()

    async def _async_connect(self) -> None:
        self._machine.connection_start()

        try:
            api = await self._async_create_api()
            api.events.on_disconnect += lambda: self._machine.device_disconnected(
                reason=DisconnectionReason.DEVICE
            )

            def apply_state_patch(state: CyberswitchDeviceState) -> None:
                if self._store.patch(state):
                    self.events.on_state_change(self.state)

            api.events.on_state_patched += apply_state_patch

            self._before_device_connected()
            self._api = api
        except DEVICE_UNAVAILABLE_EXCEPTIONS as ex:
            raise CyberswitchDeviceUnavailableError() from ex

        # ensure each call with side effects checks the connection status
        # to prevent a cancellation race condition

        #if self.connection_status == CyberswitchConnectionStatus.CONNECTING:
        #    if self._adv_data.password is None:
        #        raise ValueError("Missing device password")
        #    await api.async_authenticate_connection(self._adv_data.password)

        if self.connection_status == CyberswitchConnectionStatus.CONNECTING:
            await api.async_subscribe()

        if self.connection_status == CyberswitchConnectionStatus.CONNECTING:
            self._machine.connection_ready()

    async def _async_create_api(self) -> CyberswitchDeviceApi:
        api = CyberswitchDeviceApi(format_log_message=self._)

        def _on_disconnect(_: BleakClientWithServiceCache) -> None:
            # don't trigger a device disconnect event when a user
            # manually requests a disconnect or we're reconnecting
            if not self._expected_disconnect:
                api.events.on_disconnect()

        client = await establish_connection(
            BleakClientWithServiceCache,
            self._device,
            self.display_name,
            disconnected_callback=_on_disconnect,
            max_attempts=1,
            use_services_cache=True,
            ble_device_callback=lambda: self._device,
        )

        try:
            api.load_client(client)
        except MissingCharacteristicError:
            await client.clear_cache()

            self._expected_disconnect = True
            try:
                await client.disconnect()
            finally:
                self._expected_disconnect = False

            raise

        return api

    def _cleanup_api(self) -> None:
        if self._api is not None:
            self._api.unsubscribe_all_events()
        self._api = None

    async def _async_reconnect(self) -> None:
        await asyncio.sleep(RECONNECTION_DELAY_SECONDS)
        await self._async_execute_current_command()

    async def _async_idle_disconnect(self) -> None:
        _LOGGER.info('_async_idle_disonnect start')
        await asyncio.sleep(0.001 * self.idle_disconnect_delay_ms)
        _LOGGER.info('_async_idle_disonnect disconnect()')
        # prevent async_disconnect() from cancelling the _idle_disconnect_task and itself
        self._idle_disconnect_task = None
        await self.async_disconnect(reason=DisconnectionReason.IDLE)
        _LOGGER.info('_async_idle_disonnect done')

    def _on_machine_exception(self, e: EventData) -> None:
        # make sure any pending commands are completed
        if (
            self._current_command is not None
            and self._current_command.state != CommandProcessorState.COMPLETE
        ):
            self._current_command.on_unhandled_exception()

        _LOGGER.exception(
            self._(
                "An exception occurred during a state transition.\n"
                + UNEXPECTED_ERROR_LOG_MESSAGE
            )
        )

    def _on_connection_start(self, e: EventData) -> None:
        message = "Start connection"
        if self._connection_attempts >= 1:
            message += f" (attempt {self._connection_attempts})"
        _LOGGER.debug(self._(message))

        self._connection_complete.clear()
        self._connections_exhausted.clear()
        self._connection_attempts += 1
        self._connection_start_time = datetime.now()
        self._last_disconnect_reason = None

    def _before_device_connected(self) -> None:
        start_time = datetime.now()
        if self._connection_start_time is not None:
            start_time = self._connection_start_time
        message = f"Got connection in {datetime.now() - start_time}"
        if self._connection_attempts >= 1:
            message += f" (attempt {self._connection_attempts})"
        _LOGGER.debug(self._(message))

    def _on_connection_ready(self, e: EventData) -> None:
        self._connection_attempts = 0
        self._connection_ready_time = datetime.now()
        if self._connection_start_time is not None:
            self.events.on_connection_load_time(
                self._connection_ready_time - self._connection_start_time
            )
        self._connection_complete.set()
        self._connections_exhausted.clear()

    def _on_connection_status_change(self, e: EventData) -> None:
        new_status = self.connection_status

        if new_status == self._last_dispatched_connection_status:
            return

        _LOGGER.debug(self._(describe_connection_status(new_status)))

        self._last_dispatched_connection_status = new_status
        self.events.on_connection_status_change(new_status)

    def _after_device_disconnected(self, e: EventData) -> None:
        reason: DisconnectionReason = e.kwargs.get("reason")
        level = (
            logging.ERROR
            if reason == DisconnectionReason.DEVICE_UNAVAILABLE
            else logging.INFO
        )
        _LOGGER.log(
            level,
            self._(f"disconnected because {describe_disconnect_reason(reason)}"),
            exc_info=reason
            not in (DisconnectionReason.USER, DisconnectionReason.DEVICE),
        )

    def _on_device_disconnected(self, e: EventData) -> None:
        self._cleanup_api()

        last_event = self._connection_ready_time or self._connection_start_time
        if last_event is not None:
            self.events.on_connection_duration(datetime.now() - last_event)

        self._connection_start_time = None
        self._connection_ready_time = None
        self._connection_complete.set()

        disconnect_reason: DisconnectionReason = e.kwargs.get("reason")
        self._last_disconnect_reason = disconnect_reason

        # if the disconnect was initiated from the user, don't attempt to reconnect
        if disconnect_reason == DisconnectionReason.USER or self._expected_disconnect:
            return

        if self._connection_attempts >= MAX_RECONNECTION_ATTEMPTS:
            _LOGGER.error(
                self._(
                    f"Unavailable after {self._connection_attempts}"
                    " connection attempts"
                )
            )

            if (
                self._current_command is not None
                and self._current_command.state != CommandProcessorState.COMPLETE
            ):
                self._current_command.on_device_unavailable()

            self._connections_exhausted.set()
            self._connection_attempts = 0

            return

        if self._current_command is not None:
            # don't reconnect on unexpected errors
            if disconnect_reason == DisconnectionReason.UNEXPECTED_ERROR:
                self._current_command.on_unhandled_exception()
                return

            self._current_command.on_disconnected()

        # attempt to reconnect automatically
        # we don't await the result since this is called from a sync state transition
        # we cleanup this task on disconnect
        reconnection_task = self._loop.create_task(
            self._async_reconnect(),
            name=f"[Reconnect] {self.display_name}",
        )

        # cancel previous tasks to avoid any zombies
        if self._reconnection_task is not None and not self._reconnection_task.done():
            self._reconnection_task.cancel()

        self._reconnection_task = reconnection_task

    def _(self, message: str) -> str:
        """Format a message for logging."""
        return f"[{self.display_name}] {message}"

    @property
    def display_name(self) -> str:
        return get_device_display_name(self.name, self.address)

    def __repr__(self) -> str:
        description: list[str] = []

        if self.is_connected:
            state = self.state
            if state is None or state == UnknownCyberswitchState:
                description += ["Unknown state"]
            else:
                description += [state.__repr__()]
        else:
            description += ["Disconnected"]

        return f"CyberswitchDevice({self.address} {' '.join(description)})"


def describe_connection_status(status: CyberswitchConnectionStatus) -> str:
    descriptions = {
        CyberswitchConnectionStatus.DISCONNECTED: "🔴 Disconnected",
        CyberswitchConnectionStatus.CONNECTING: "🟡 Connecting",
        CyberswitchConnectionStatus.CONNECTED: "🟢 Connected",
    }
    return descriptions[status] or status.name


def describe_disconnect_reason(reason: DisconnectionReason) -> str:
    descriptions = {
        DisconnectionReason.USER: (
            f"{CyberswitchDevice.async_disconnect.__qualname__}() was called"
        ),
        DisconnectionReason.DEVICE: "the bluetooth connection was lost",
        DisconnectionReason.IDLE: "the bluetooth connection was idle",
        DisconnectionReason.UNEXPECTED_ERROR: (
            f"an uncaught exception occurred.\n{UNEXPECTED_ERROR_LOG_MESSAGE}"
        ),
        DisconnectionReason.DEVICE_UNAVAILABLE: (
            "the device couldn't establish a connection"
        ),
    }
    return descriptions[reason] or reason.name
