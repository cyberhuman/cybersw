"""DataUpdateCoordinator for cybersw."""
from __future__ import annotations

import logging
#from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
#    UpdateFailed,
)
#from homeassistant.exceptions import ConfigEntryAuthFailed

from .pycybersw.model import (
    CyberswitchDeviceState,
    #UnknownCyberswitchState,
)
from .pycybersw.commands import (
    CyberswitchCommandResult,
    CyberswitchCommandData,
    get_device_info,
)

from .models import (
    CyberswitchConfigurationData,
)
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


# https://developers.home-assistant.io/docs/integration_fetching_data#coordinated-single-api-poll-for-data-for-all-entities
class CyberswitchCoordinator(DataUpdateCoordinator[CyberswitchDeviceState]):
    """Class to manage fetching data from the API."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config: CyberswitchConfigurationData
    ) -> None:
        """Initialize."""
        self.config = config
        super().__init__(
            hass=hass,
            logger=_LOGGER,
            name=DOMAIN,
            # push-only coordinator
            #update_interval=timedelta(minutes=5),
        )

    async def _async_update_data(self):
        """Update data via library."""
        await self._async_execute_command(get_device_info()) # FIXME implement a no-op
        return self.config.device.state
#        try:
#            return await self.client.async_get_data()
#        except CyberswitchApiClientAuthenticationError as exception:
#            raise ConfigEntryAuthFailed(exception) from exception
#        except CyberswitchApiClientError as exception:
#            raise UpdateFailed(exception) from exception
#        try:
#            # Note: asyncio.TimeoutError and aiohttp.ClientError are already
#            # handled by the data update coordinator.
#            async with async_timeout.timeout(10):
#                # Grab active context variables to limit data required to be fetched from API
#                # Note: using context is not required if there is no need or ability to limit
#                # data retrieved from API.
#                # FIXME
#                listening_idx = set(self.async_contexts())
#                return await self.my_api.fetch_data(listening_idx)
#        except ApiAuthError as err:
#            # Raising ConfigEntryAuthFailed will cancel future updates
#            # and start a config flow with SOURCE_REAUTH (async_step_reauth)
#            raise ConfigEntryAuthFailed from err
#        except ApiError as err:
#            raise UpdateFailed(f"Error communicating with API: {err}")

    async def _async_execute_command(self, command: CyberswitchCommandData) -> CyberswitchCommandResult:
        return await self.config.device.async_execute_command(command)
