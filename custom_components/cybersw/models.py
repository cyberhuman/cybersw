"""Data models for the CyberSW integration."""

from dataclasses import dataclass

from bleak.backends.device import BLEDevice
from .pycybersw.device import CyberswitchDevice


@dataclass
class CyberswitchConfigurationData:
    """Configuration data for CyberSW."""

    ble_device: BLEDevice
    device: CyberswitchDevice
    title: str
    display_name: str
