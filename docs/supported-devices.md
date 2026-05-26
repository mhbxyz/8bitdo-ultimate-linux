# Supported Devices

## Current Status

The project currently treats all devices with vendor ID `0x2dc8` as 8BitDo candidates.

## Expected Families

- 8BitDo Ultimate Bluetooth Controller
- 8BitDo Ultimate 2.4G Controller
- 8BitDo Ultimate C family

## Notes

- Product IDs are not hard-coded beyond examples in the udev rule comments.
- USB, Bluetooth, and dongle modes can report different product IDs.
- Contributions should include `ultim8do report --json` output when adding a new device profile.
