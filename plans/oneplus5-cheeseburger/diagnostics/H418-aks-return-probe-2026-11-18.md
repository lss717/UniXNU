# H418 AppleKeyStore return-value probe

Date: 2026-11-18

## Competing hypotheses

H417 reached the correct CA ABI observations but did not directly record the
`AppleKeyStore::newUserClient` result.  The entry trace
`NATIVE_IOKIT: op=open ... ok=0` is emitted before the provider is called and
cannot distinguish success from `kIOReturnNotReady`.

Two hypotheses remain:

1. `sheng-aks=1` enables the state client, and the next missing gate is
   SpringBoard/CoreAnimation main-scene completion.
2. The consumer still receives an error from `newUserClient` or a required
   key-state selector, so the main-scene chain remains blocked at AKS.

## Unique variable

H418 keeps the H417 kernel arguments, UEFI, Data seed, accelerator, A540Trace
observer, IOMFB path and device repository unchanged.  It adds observation only
to `NativeKeyStoreEvents.cpp`:

- log the parsed `sheng-aks` value once;
- log the caller, request type and exact `IOReturn` of every bounded
  `newUserClient` attempt, capped at 32 lines;
- aggregate selector calls/errors by selector in fixed storage;
- log the caller, selector and exact result on the first call and on result
  transitions, capped at eight transitions per selector.

No return value, state answer, service registration, selector payload or
display behavior changes.

## Required result

Use one bounded H418 boot to classify the branch before adding another scene
probe:

```text
open rc != 0
  -> identify caller/type/error and fix only that AKS path

open rc == 0, required selector rc != 0
  -> identify caller/selector/error and fix only that selector

open rc == 0, selectors succeed
  -> stop adding AKS probes; trace SpringBoard main-scene completion and
     definesDisplayBounds in the next candidate
```

The existing layer subtree remains supporting evidence only.  It does not by
itself prove that every private scene layer is non-drawable.  A selector 4 must
appear before IOSurface, IOMFB copy or scanout work is allowed.

## Static gates

```text
check-h418-aks-return.py
check-display-first-frame-probe.py
verify_h418.py
```

Build and device status are appended after the bounded run.
