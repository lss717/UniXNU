# H408 USB source cross-check (2026-11-17)

Device location for this audit: local Windows host, OnePlus 5 `16149951`.
The y9000x host was not used.

## Pinned sources

| Source | Branch | Commit | Kernel |
| --- | --- | --- | --- |
| `LineageOS/android_kernel_oneplus_msm8998` | `lineage-22.2` | `9932c9e387c8e9a82f3ce57b2104216c3ae958bb` | Linux 4.4.302 |
| `OnePlusOSS/android_kernel_oneplus_msm8998` | `oneplus/QC8998_Q_10.0` | `2103804389449d228b7b1080b99ccdbab7148668` | Linux 4.4.205 |
| `torvalds/linux` | `master` snapshot | `666539eecdf4db623f5e3c3e55cf9f2dfad24aa4` | 7.4.0-rc3 |

Pinned raw copies are under
`main-route/artifacts/H408/source-crosscheck-20261117/`.

## Board identity and USB wiring

- LineageOS and OnePlus both build separate `cheeseburger-v2.1-pvt.dtb` and
  `dumpling-v2.1-pvt.dtb` targets, so OnePlus 5 and 5T share the MSM8998 DWC3
  controller family rather than one device being an alias of the other.
- `arch/arm/boot/dts/qcom/Makefile:177-178` lists both targets in LineageOS
  4.4.302; the OnePlus Q10 Makefile lists them at lines 213 and 217.
- Both `cheeseburger.dtsi` versions define `qusb_phy0` at `qusb@c012000`
  (lines 271 onward). This is the USB2/QUSB2 PHY used by the failing board
  path. No SuperSpeed PHY participation is observed in the H408 freeze.
- The official product/SoC combination is therefore consistent with the
  earlier conclusion: the DWC3 IP can have SuperSpeed capability, but this
  phone's physical USB path is USB2 only.

## Line references for the control-transfer path

### CDC ACM request itself

All three trees accept `GET_LINE_CODING` as a 7-byte IN data stage:

- LineageOS `drivers/usb/gadget/function/f_acm.c:371-380`
- OnePlus Q10 `drivers/usb/gadget/function/f_acm.c:371-380`
- Linux master `drivers/usb/gadget/function/f_acm.c` current `GET_LINE_CODING` branch

The function copies `min(wLength, sizeof(usb_cdc_line_coding))`, so H408's
`data-in start length=7` is correct.

### Physical versus logical endpoints

- `drivers/usb/dwc3/core.h` says the physical endpoint number goes 0..31,
  EP0 is always OUT and EP1 is always IN:
  LineageOS 434-435, OnePlus Q10 438-439, mainline 594-595.
- `drivers/usb/dwc3/gadget.c` documents 1:1 mapping for logical endpoints:
  physical EP2 maps to logical OUT EP1 and physical EP3 to logical IN EP1
  (`0x81` maps to physical 3). Relevant lines: LineageOS 548-551,
  OnePlus Q10 548-551, mainline 627-630.
- Therefore H408's control transfers must use physical EP0 OUT (`0`) and EP1
  IN (`1`). CDC bulk OUT is physical EP2, bulk IN is physical EP3, and
  notification IN is physical EP5.

### Event and TRB bits

All three trees agree:

- XferNotReady control phase codes: DATA = 1, STATUS = 2
  (LineageOS/OnePlus `core.h:1114-1115`, mainline `core.h:1519-1520`).
- `DWC3_DEPCMD_PARAM(x)` is `(x << 16)` in the DEPCMD command word
  (LineageOS/OnePlus `core.h:413-415`, mainline `core.h:570-571`).
- Setup-pending TRB status is 2 (`core.h:637` LineageOS/OnePlus,
  `core.h:860` mainline).
- HWO/LST/IOC are bit 0/1/11 in the TRB control word
  (LineageOS `core.h:641-647`, OnePlus 645-651, mainline 864-870).

### Data-complete and STATUS gating

- LineageOS `ep0.c:884-920` sets `ep0_next_event = DWC3_EP0_NRDY_STATUS`
  only in `dwc3_ep0_complete_data()` after an actual data completion and checks
  `DWC3_TRBSTS_SETUP_PENDING` before returning a request.
- LineageOS `ep0.c:1204-1220` accepts a STATUS NotReady only when
  `ep0_next_event == DWC3_EP0_NRDY_STATUS`; an early STATUS event is ignored.
- OnePlus Q10 has the same sequence at `ep0.c:884-920` and `1167-1220`.
- Mainline `ep0.c:871-927` implements the same ordering and additionally
  records `setup_packet_pending`; its STATUS path at `1150-1208` explicitly
  rejects STATUS unless that transition is expected and stalls on setup-pending.
- The reference STATUS TRB type is STATUS3 for a three-stage control transfer
  and STATUS2 only for a zero-length/two-stage request:
  LineageOS/OnePlus `ep0.c:1115-1133`, mainline `ep0.c:1081-1091`.

### SET_CONFIGURATION resource reset

This is the decisive board-independent mismatch:

- LineageOS and OnePlus Q10 use the older
  `dwc3_gadget_start_config(dwc, dep)` helper. It issues DEPSTARTCFG for EP0
  OUT, then walks all endpoints with DEPXFERCFG/SETTRANSFRESOURCE:
  LineageOS/OnePlus `gadget.c:470-499`.
- Mainline supports resource index 0 or 2 and encodes it in the DEPCMD command
  word: `cmd |= DWC3_DEPCMD_PARAM(resource_index)` at
  `gadget.c:553-568`. Index 2 resets non-control endpoint resources on
  SET_CONFIGURATION.
- H408 commit `6cd4c78` intended the newer model but passed
  `2U << 16` as DEPCMDPAR0 while leaving the command word at type 9 only.
  The raw H408 freeze then showed the control endpoint resource search failing
  immediately after SET_CONFIGURATION (`ep0 command 6 failed status=1`) before
  GET_LINE_CODING.
- H408 commit `cdb3574` moves the index to the command word:
  `kDepcmdTypeStartConfig | (2U << 16)`. This is a one-line behavioral fix
  matching all three sources and the frozen evidence.

### ENDTRANSFER

- Mainline calls ENDTRANSFER for a wrong-direction data phase, reset/stall,
  cancellation, or cleanup. It does not terminate a successfully completed
  7-byte data stage merely because an EP0 completion arrived.
- H408's later `consumeSetupPendingDataIn()` workaround was useful for diagnosis:
  it proved `setup-bytes=a1 21 00 00 00 00 07 00`, i.e. no hidden Windows
  request and no host retry with a different setup packet.
- Because the data TRB remained HWO/IOC/LST with `resource=1`, the earlier
  log was not evidence of an ordinary completed Data-IN. It is consistent with
  resource allocation being reset incorrectly during SET_CONFIGURATION.
  The ENDTRANSFER workaround is therefore not the chosen next change.

### DMA cache handling

- Linux maps request buffers through `usb_gadget_map_request*` and allocates
  TRB/control buffers with coherent DMA (`ep0.c`, `gadget.c` references above).
- H408 owns one IOMemoryDescriptor and performs explicit `dc civac` before
  handing a TRB/buffer to hardware and `dc ivac` before reading a completion.
- No frozen-log evidence currently distinguishes a cache-consistency defect
  from the resource-index defect, so no DMA change was made in this step.

## Three-way conclusion

| Area | LineageOS 4.4.302 | OnePlus Q10 4.4.205 | Mainline 7.4-rc3 | H408 action |
| --- | --- | --- | --- | --- |
| Device/DWC3 basis | cheeseburger + dumpling, QUSB2 | cheeseburger + dumpling, QUSB2 | generic DWC3/QCOM | matches board class |
| GET_LINE_CODING | 7-byte IN | 7-byte IN | 7-byte IN | response length 7 retained |
| Physical EP0 | 0 OUT, 1 IN | 0 OUT, 1 IN | 0 OUT, 1 IN | kept |
| Early STATUS | ignored until data complete | ignored until data complete | gated by `ep0_next_event` | diagnostic only |
| Set-config resources | DEPSTARTCFG + all DEPXFERCFG | same | resource index in DEPCMD | fixed in `cdb3574` |
| ENDTRANSFER | error/cancel path | error/cancel path | error/cancel path | no blind port |
| TRB cache | DMA map/coherent | DMA map/coherent | DMA map/coherent | unchanged pending evidence |

The next test therefore changes only the DEPSTARTCFG resource-index encoding.
The earlier event-ignoring experiment (`b8692bb`) was deliberately reverted;
the raw setup diagnostic is retained.
## Post-fix device validation

The resource-index fix (`cdb3574`) made the 7-byte IN data stage complete and
allowed Windows to advance to `SET_LINE_CODING`. The 7-byte OUT stage then hung,
matching the 4.4 `dep->number == 0` non-aligned bounce rule at
`ep0.c:1066-1098` in both LineageOS and OnePlus Q10. Commit `5a63ff0` rounds
the H408 control-OUT TRB length up to 64 while retaining a 7-byte logical
payload.

After removing the diagnostic H103 freeze in `0a74a02`, the final device
acceptance passed:

- three consecutive SerialPort open/close cycles;
- DTR/RTS activation, close, reopen and close;
- 1286 valid UXL1 frames in the primary 30-second capture and 138 in a
  separate reopened 20-second capture;
- identical boot ID `34BE3A2E`, build `H408`, zero CRC errors and no sequence
  gaps;
- no panic, EP0 fault or invalid completion in the captured live text.

Raw capture initially produced no frames because `CreateFile("\\.\COM8")`
does not assert DTR. `e3df5a1` adds `EscapeCommFunction(SETDTR/SETRTS)` before
reading; CDC notification and Bulk-IN then worked.

Evidence: `main-route/artifacts/H408/no-freeze-0a74a02/`.
