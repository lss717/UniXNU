# H408 USB CDC live-log design

Date: 2026-11-17

## Baseline

- UniXNU: `main@56afe31b638d62d1c5c328e8759da2f13155228e`
- Device: `main@c4f84bbc01002e8b6d37d04a228b44a5f01eebe8`
- H407 boot and ring evidence remains read-only.
- H408 work occurs only on the `h408-usb-live-log` branches.

## H407 descriptor audit

The H407 device descriptor advertises class `0xff` / subclass `0` / protocol `0`.
Its configuration descriptor is 18 bytes and contains one interface with
`bNumEndpoints=0` and class `0xff`. Windows therefore creates the expected
vendor-class PnP node with Problem 28 and never reaches a data interface.

The H407 SET_CONFIGURATION handler only marks `configured=true`; it does not
enable or arm a non-EP0 endpoint. Existing DWC3 event handling also ignores
events above physical endpoint 1.

## Selected first-stage transport

Use standard CDC ACM:

- device class `0x02`, subclass `0x02`, protocol `0x01`;
- two interfaces: communication class `0x02` and data class `0x0a`;
- interrupt IN notification endpoint, bulk OUT and bulk IN data endpoints;
- Windows inbox `usbser.sys`, no third-party driver or INF installation.

CDC ACM is preferred over WinUSB/MS OS 2.0 for H408 because it minimizes host
setup: Windows creates a COM port without a device-specific driver package.
WinUSB can be evaluated later if CDC throughput or framing becomes limiting.

## Endpoint mapping

DWC3 physical endpoint command indices follow the existing control mapping:

| USB endpoint | Direction | Type | DWC3 index |
| --- | --- | --- | --- |
| EP0 | OUT | control | 0 |
| EP0 | IN | control | 1 |
| 0x01 | OUT | bulk | 2 |
| 0x81 | IN | bulk | 3 |
| 0x82 | IN | interrupt | 5 |

High-speed bulk max packet size is 512 bytes; notification max packet size is
16 bytes. EP0 remains 64 bytes.

## Minimal protocol

After SET_CONFIGURATION and bulk endpoint configuration, the device streams
msgbuf deltas into fixed 32-byte little-endian frames:

- magic `UXL1`, version 1, header size 32;
- boot ID and monotonic frame sequence;
- constant build ID `H408`;
- dropped-byte counter and payload length;
- CRC-32 of the payload.

The host receiver validates frame boundaries, sequence gaps, CRC, boot ID and
build ID, then stores both raw frames and decoded text. The first phase is
one-way bulk IN plus the CDC control channel. Bulk OUT is configured and kept
armed so Windows can complete the CDC interface setup.

## Allowed scope

- Handler additions only for standard/class CDC control requests.
- Enable EP1 OUT, EP1 IN and EP2 IN after accepted SET_CONFIGURATION.
- Stream read-only kernel msgbuf data; no shell, memory or storage commands.
- Preserve H407 userland/UFS behavior and EP0 no-fault behavior.
- Only `fastboot boot`; no flash, erase or format.

## Host execution gate

The phone and USB host are on `y9000x`. Device enumeration, TWRP, Fastboot,
PnP inspection and the CDC receiver run through one PowerShell `ssh y9000x`
connection. Candidates use `E:\Users\ls\Documents\OnePlus5_ios`.
