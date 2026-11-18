# OnePlus 5 (cheeseburger) USB CDC log and normal-reboot console

This page explains how to read the H410 Format 1 USB CDC live log from Windows and how to
send the one supported command (normal reboot) over the same COM handle.

> The wire format is binary **UXL1**, not plain text. PuTTY, TeraTerm, `mode` or
> `Get-Content COMx` will usually show binary garbage. Use
> `tools/h410-cdc-console.ps1` (live decode, optional reboot) or
> `tools/capture-h408-cdc.ps1` (capture to disk, decode afterwards).

## 1. Requirements and versions

| Item | Value |
| :--- | :--- |
| Candidate image | H410 (see the manifest under `main-route/artifacts/H410/`) |
| Device USB driver | `drivers/CheeseburgerUsb/CheeseburgerUsb.cpp`, build tag `H410` |
| Live decode / command tool | `UniXNU-cheeseburger/tools/h410-cdc-console.ps1` |
| Capture tool | `UniXNU-cheeseburger/tools/capture-h408-cdc.ps1` |
| Static contract check | `UniXNU-cheeseburger/tools/check-h408-cdc.py` |
| USB ID | `USB\VID_1209&PID_0001` (CDC ACM; PnP string remains `OP5CDCH408`) |
| Core source | UniXNU `h410-usb-status`, based on `5e204e7d984aac66af3c57c9961926a8d4080062` |
| Device source | UniXNU-cheeseburger `h410-usb-status`, based on `001e694cc5211c79d283151a2c2204e443d72277` |
| Display submodule | GopFramebuffer `cc31bd33e2209e0f261720babb7b4a9dc6b1b0c2` |
| Platform submodule | ArmDTPlatform `4d057d020124012e545853f6f75a2a6c202d3171` |
| Boot image | `a4201dbc7825166b3724b47f2be8b94c64b41a094f91392e19841201876a4fbe` |
| Kernel | `9c7640f149018af39e70f7b8eeff4231d7347c45cd1d349125596987edf01873` |
| Payload | `20587408e4315a840feea6e4a9890d27e2978c12c26a855b2d9583bbc1612383` |
| UEFI FD | `e9135e17397165425d0794e8e64c0a4ae63575ce222b06b80305fcde6b16f1b3` |
| Measured boot ID / build | `549D06A5` / `H410` |
| Remote main | H410 was fast-forwarded into core/device `main`; use `git ls-remote` and `H410-manifest.json` for the exact SHA (device H410 commit `481fcfe73a1e73ed9c9bb7eef6ceb7ddffe3ce91`) |

These values come from the actual H410 build and device regression. The full manifest is
`main-route/artifacts/H410/H410-manifest.json` and `STATUS.md`.

## 2. Find the port

1. Connect the phone to the local Windows workstation and boot the H410 image.
2. In Device Manager, under **Ports (COM & LPT)**, find the `usbser` device enumerated from
   VID `1209`, PID `0001`, and note its `COMx`. `COM8` below is only an example.
3. Make sure nothing else holds the port open. The tool opens it exclusively (`share=0`), so
   PuTTY, TeraTerm, another `h410-cdc-console.ps1` and similar programs must be closed.

```powershell
Get-CimInstance Win32_PnPEntity |
  Where-Object { $_.PNPDeviceID -match '^USB\\VID_1209&PID_0001' } |
  Select-Object Name, Caption, PNPDeviceID, Status
```

## 3. Serial settings

- CDC ACM line coding is nominal **115200 8N1, no flow control**. The actual throughput is
  USB Bulk, not limited by 115200.
- **DTR and RTS must be asserted**: the device sends UXL1 log frames only while `dtr` is
  true. The tool calls `EscapeCommFunction` to set both after opening the port.

## 4. Live decode and save

```powershell
cd C:\path\to\UniXNU-cheeseburger\tools
powershell -NoProfile -ExecutionPolicy Bypass -File .\h410-cdc-console.ps1 `
  -Port COM8 -Seconds 600 `
  -TextOutput .\H410-live.log -FrameOutput .\H410-live.frames.bin
```

The tool prints decoded payload text as frames complete, appends it to `H410-live.log` and
writes the complete frames to `H410-live.frames.bin`. `-Seconds 0` runs until `Ctrl+C`.
At the end it prints `H410 frames=... payload_bytes=... crc_errors=... sequence_gaps=...
boot_switches=...`. To follow the text file from another window use
`Get-Content .\H410-live.log -Wait` (file read only; it does not touch COM).

## 5. Send a normal reboot over the same handle

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\h410-cdc-console.ps1 `
  -Port COM8 -Reboot -RequestId 12345 -Seconds 120 `
  -TextOutput .\H410-reboot.log -FrameOutput .\H410-reboot.frames.bin
```

`-Reboot` writes one 16-byte **UXC1** frame to Bulk-OUT, then keeps reading the log with the
same handle. The device decodes the frame, emits
`NATIVE_USB_CMD: ack req=<id> op=reboot`, and after the ACK is submitted (or a bounded
1 s timeout) a dedicated kernel worker calls `halt_all_cpus(TRUE)`, the standard XNU
reboot entry. ArmDTPlatform routes `PE_halt_restart` to the existing PSCI `SYSTEM_RESET`.

This only works while USB and the kernel are still alive. It does not set a recovery marker;
to enter recovery, let Android boot and then run `adb reboot recovery`.

### UXC1 frame (16 bytes, little-endian)

| Offset | Size | Meaning |
| :--- | :--- | :--- |
| 0..3 | 4 | ASCII `UXC1` |
| 4 | 1 | version, `1` |
| 5 | 1 | opcode, `1` = normal reboot |
| 6..7 | 2 | payload length, must be `0` |
| 8..11 | 4 | non-zero request ID |
| 12..15 | 4 | CRC32 over bytes 0..11 |

Only exactly 16 bytes with valid magic/version/opcode/payload/CRC are accepted. There is no
text, shell, memory or register channel.

## 6. Health metrics

- `frames`, `payload_bytes`: valid UXL1 frames and payload bytes.
- `crc_errors`: must stay 0.
- `sequence_gaps`: must stay 0 within one boot; a boot change resets the sequence.
- `boot_switches`: more than one means the phone rebooted during the capture.
- Each header also carries `boot=`, `build=` (must be `H410`) and `dropped=`.

## 7. Fifth status cell and disk-log pause

The fifth 16×16 cell at `(80,0)` shows USB state: gray = driver not started, yellow =
started but not connected, green = connected and idle, green/white = Bulk-IN log frames
are actually completing. See `display-colors.md`.

When the link is genuinely healthy (connected plus at least 8 real Bulk-IN completions
across a ~2 s window) the H103 disk sink is paused: only the 32 MiB `userdata_ios` slot/header
writes stop, the memory ring and USB source continue, and ordinary UFS/APFS I/O is untouched.
Disconnect, deconfiguration, fault, transfer error or ~1.5 s without a completion resumes
disk logging. During the pause the fourth cell is cyan (`#00FFFF`); the fifth cell still
shows the USB state.

## 8. Troubleshooting

| Symptom | Check |
| :--- | :--- |
| No COM port | Is `VID_1209&PID_0001` present? Was the image booted with `cheeseburger-usb=2`? Try another cable/port. |
| `CreateFile \\.\COMx failed` | Wrong `COMx`, or the device is not enumerated yet. |
| Access denied / sharing violation | Another program holds the COM port. |
| Bytes but no text | You are reading binary UXL1 with a text terminal; use the decoder. |
| CRC errors | Cable/port/driver reset, or another reader; recapture. |
| Sequence gaps | Capture interruption or ring drops; check `dropped=`. |
| No reboot | Look for `NATIVE_USB_CMD: reboot armed`; only valid while USB/kernel are alive. |

A black screen does not prove the USB log stopped: the first user frame can overdraw the
status panel. Check the decoded stream and `STATUS.md`.
