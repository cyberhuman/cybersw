from __future__ import annotations

import logging
from dataclasses import dataclass

from home_assistant_bluetooth import BluetoothServiceInfo

from .const import (
    FIRMWARE_PAIRING_FLAGS,
    FIRMWARE_VERSION_BY_FLAGS,
    #MODEL_NAME_BREEZ,
    MIN_CYBERSW_ADVERTISEMENT_LENGTH,
    SUPPORTED_MODEL_NAMES,
)
from .model import CyberswitchAdvertisementData, CyberswitchDeviceModel, CyberswitchFirmwareVersion

_LOGGER = logging.getLogger(__name__)


@dataclass
class ParsedAdvertisementFlags:
    firmware_version: CyberswitchFirmwareVersion
    is_pairing: bool


def parse_firmware_flags(flags: int) -> ParsedAdvertisementFlags | None:
    is_pairing = (FIRMWARE_PAIRING_FLAGS & flags) == FIRMWARE_PAIRING_FLAGS
    flags_without_pairing = flags & ~FIRMWARE_PAIRING_FLAGS

    if flags_without_pairing not in FIRMWARE_VERSION_BY_FLAGS:
        _LOGGER.debug(f"Unknown device flags {flags_without_pairing:02X}")
        return None

    return ParsedAdvertisementFlags(
        FIRMWARE_VERSION_BY_FLAGS[flags_without_pairing], is_pairing
    )


def parse_cyberswitch_advertisement(
    data: BluetoothServiceInfo,
) -> CyberswitchAdvertisementData | None:
    advertisement = data.manufacturer_data.get(data.manufacturer_id)
#
    if advertisement is None:
        _LOGGER.debug(
            f"{data.address} doesn't advertise manufacturer data"
        )
        return None

    if len(advertisement) < MIN_CYBERSW_ADVERTISEMENT_LENGTH:
        _LOGGER.debug(
            f"{data.address} advertisement length is {len(advertisement)}, expected >={MIN_CYBERSW_ADVERTISEMENT_LENGTH}"
        )
        return None

    if not (flags := parse_firmware_flags(advertisement[0])):
        return None

#    model = get_device_model(data.name, flags.firmware_version)
#
#    if model == CyberswitchDeviceModel.UNSUPPORTED:
#        _LOGGER.debug(
#            f"{data.name} is unsupported with firmware {flags.firmware_version}"
#        )
#        return None
#
#    return CyberswitchAdvertisementData(
#        model,
#        flags.firmware_version,
#        password=advertisement[1:].hex() if flags.is_pairing else None,
#    )
    return CyberswitchAdvertisementData(
        CyberswitchDeviceModel.CYBERSW,
        CyberswitchFirmwareVersion.V1,
        is_pairing=flags.is_pairing,
        password=None,
    )



def match_known_device_name(advertised_name: str) -> str | None:
    return next(
        (
            value
            for value in SUPPORTED_MODEL_NAMES
            if advertised_name.lower().startswith(value.lower())
        ),
        None,
    )


def get_device_model(
    advertised_name: str,
    firmware: CyberswitchFirmwareVersion
) -> CyberswitchDeviceModel:
    known = match_known_device_name(advertised_name)

    # The advertised name is in the format "CyberSW-XXXX" or "CySW-XXXX"
    # we require this format since the name stored in device characteristics
    # is always "Cyberswitch" and matching it would not correctly identify Breez models
    if known is None or len(advertised_name) != len(known) + 5:
        _LOGGER.debug(
            f"{advertised_name} {known=} {len(advertised_name)=}"
        )
        return CyberswitchDeviceModel.UNSUPPORTED

    if firmware in [
        CyberswitchFirmwareVersion.V2,
        CyberswitchFirmwareVersion.V3,
        CyberswitchFirmwareVersion.V4,
        CyberswitchFirmwareVersion.V5,
    ]:
        return CyberswitchDeviceModel.ORIGINAL

    if firmware == CyberswitchFirmwareVersion.V6:
        return (
            CyberswitchDeviceModel.CYBERSW

#            CyberswitchDeviceModel.BREEZ
#            if known == MODEL_NAME_BREEZ
#            else CyberswitchDeviceModel.PRO
        )

    return CyberswitchDeviceModel.UNSUPPORTED


def get_device_display_name(advertised_name: str, address: str) -> str:
    known = match_known_device_name("CySW1")
    #known = match_known_device_name(advertised_name)
    if known is not None:
        return f"{known} {address.replace(':', '')[-4:]}"

    return advertised_name.replace("-", " ")
