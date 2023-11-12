from dataclasses import dataclass
from enum import IntEnum


class CyberswitchDeviceModel(IntEnum):
    UNSUPPORTED = 0
    CYBERSW = 1
#    ORIGINAL = 1
#    PRO = 2
#    BREEZ = 3


class CyberswitchFirmwareVersion(IntEnum):
    V1 = 1
#    V2 = 2
#    V3 = 3
#    V4 = 4
#    V5 = 5
#    V6 = 6
#    V7 = 7
#    V8 = 8
#    V9 = 9
#    V10 = 10
#    V11 = 11
#    V12 = 12
#    V13 = 13
#    V14 = 14
#    V15 = 15


@dataclass
class CyberswitchDeviceCharacteristicData:
    manufacturer: str
    model: str
    hardware: str
    firmware: str
    software: str | None


@dataclass
class CyberswitchAdvertisementData:
    model: CyberswitchDeviceModel
    firmware_version: CyberswitchFirmwareVersion
    is_pairing: bool
    password: str | None

    #@property
    #def is_pairing(self) -> bool:
    #    return self.password is not None
#
#    @property
#    def supports_fan(self) -> bool:
#        return self.model == CyberswitchDeviceModel.CYBERSW


@dataclass(repr=False)
class CyberswitchDeviceState:
    on: bool | None = None
    battery_level: int | None = None
#
#    light_on: bool | None = None
#    light_brightness: int | None = None
#    night_mode_enabled: bool | None = None
#    night_mode_brightness: int | None = None
#
#    # Breez specific
#    fan_on: bool | None = None
#    fan_speed: int | None = None
#    fan_auto_enabled: bool | None = None
#    temperature: float | None = None
#    target_temperature: int | None = None
#
    def __repr__(self) -> str:
        if self == UnknownCyberswitchState:
            return "Cyberswitch(Unknown)"

        #attributes = [f"Noise {'On' if self.on else 'Off'} at {self.volume}% volume"]
        attributes = [f"Switch {'On' if self.on else 'Off'}"]

        if self.battery_level is not None:
            attributes += [f"battery {self.battery_level}%"]

#        if self.night_mode_enabled is True:
#            brightness = ""
#
#            if self.night_mode_brightness is not None:
#                brightness += f"({self.night_mode_brightness}%)"
#
#            attributes += [f"[NightMode{brightness}]"]
#        elif self.light_on is True and self.light_brightness is not None:
#            attributes += [f"Light is {self.light_brightness}%"]
#
#        fan_attrs: list[str] = []
#
#        if self.fan_on is not None:
#            fan_attrs += [f"Fan {'On' if self.fan_on else 'Off'}"]
#
#        if self.fan_speed is not None:
#            fan_attrs += [f"at {self.fan_speed}% speed"]
#
#        if self.fan_auto_enabled is True:
#            fan_attrs += ["[Auto]"]
#
#        if len(fan_attrs) > 0:
#            attributes += [" ".join(fan_attrs)]
#
#        if self.temperature is not None:
#            attributes += [f"{self.temperature}°F"]
#
#        if self.target_temperature is not None:
#            attributes += [f"{self.target_temperature}°F target"]
#
        parts = ", ".join(attributes)

        return f"CyberswitchDeviceState({parts})"


UnknownCyberswitchState = CyberswitchDeviceState()


@dataclass
class CyberswitchDeviceConfig:
    switch_angle_midpoint: int
    switch_angle_on: int
    switch_angle_off: int
    switch_delay_ms: int
    connection_interval_ms: int
