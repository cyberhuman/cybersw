from .model import CyberswitchFirmwareVersion

NEW_ISSUE_URL = (
    "https://github.com/cyberhuman/pycybersw/issues/new?labels=bug"
    "&template=log-unexpected-error.yaml&title=Uncaught+exception"
)
UNEXPECTED_ERROR_LOG_MESSAGE = (
    f"1️⃣  Report this issue: {NEW_ISSUE_URL}\n"
    "2️⃣  ⬇ copy the trace and paste in the issue ⬇\n"
)

# FIXME
SEND_COMMAND_CHARACTERISTIC = "0000ff01-0000-1000-8000-00805f9b34fb"
WRITE_CONFIG_CHARACTERISTIC = "0000ff02-0000-1000-8000-00805f9b34fb"
READ_CONFIG_CHARACTERISTIC = "0000ff03-0000-1000-8000-00805f9b34fb"
#MODEL_NUMBER_CHARACTERISTIC = "00002a24-0000-1000-8000-00805f9b34fb"
#FIRMWARE_REVISION_CHARACTERISTIC = "00002a26-0000-1000-8000-00805f9b34fb"
#HARDWARE_REVISION_CHARACTERISTIC = "00002a27-0000-1000-8000-00805f9b34fb"
#SOFTWARE_REVISION_CHARACTERISTIC = "00002a28-0000-1000-8000-00805f9b34fb"
#MANUFACTURER_NAME_CHARACTERISTIC = "00002a29-0000-1000-8000-00805f9b34fb"
#READ_STATE_CHARACTERISTIC = "80c37f00-cc16-11e4-8830-0800200c9a66"
#WRITE_STATE_CHARACTERISTIC = "90759319-1668-44da-9ef3-492d593bd1e5"
#READ_COMMAND_CHARACTERISTIC = "f0499b1b-33ab-4df8-a6f2-2484a2ad1451"


#CYBERSW_ADVERTISEMENT_LENGTH = 9
MIN_CYBERSW_ADVERTISEMENT_LENGTH = 1

FIRMWARE_PAIRING_FLAGS = 0x01
FIRMWARE_VERSION_BY_FLAGS = {
    0x00: CyberswitchFirmwareVersion.V1,
#    0x04: CyberswitchFirmwareVersion.V2,
#    0x08: CyberswitchFirmwareVersion.V3,
#    0x0C: CyberswitchFirmwareVersion.V4,
#    0x10: CyberswitchFirmwareVersion.V5,
#    0x14: CyberswitchFirmwareVersion.V6,
#    0x18: CyberswitchFirmwareVersion.V7,
#    0x1C: CyberswitchFirmwareVersion.V8,
#    0x20: CyberswitchFirmwareVersion.V9,
#    0x24: CyberswitchFirmwareVersion.V10,
#    0x28: CyberswitchFirmwareVersion.V11,
#    0x2C: CyberswitchFirmwareVersion.V12,
#    0x30: CyberswitchFirmwareVersion.V13,
#    0x34: CyberswitchFirmwareVersion.V14,
#    0x38: CyberswitchFirmwareVersion.V15,
}
SUPPORTED_FIRMWARE_VERSIONS = [
    CyberswitchFirmwareVersion.V1,
#    CyberswitchFirmwareVersion.V2,
#    CyberswitchFirmwareVersion.V3,
#    CyberswitchFirmwareVersion.V4,
#    CyberswitchFirmwareVersion.V5,
#    CyberswitchFirmwareVersion.V6,
]

MODEL_NAME_CYBERSW = "CyberSW"
MODEL_NAME_CYSW = "CySW"
SUPPORTED_MODEL_NAMES = [MODEL_NAME_CYBERSW, MODEL_NAME_CYSW]