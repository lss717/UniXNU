# H417 AppleKeyStore state gate and typed CA observer

Date: 2026-11-18

## Public control

The normal userland reference is fixed at:

```text
https://github.com/xVanTuring/UniXNU-qemu
commit 97b75b1f63c6b7e895cd7646029db741d5fe5488
```

That repository uses the same iPad7,1 / 17.7.11 / 21H461 inputs and XNU pin.
Its documented successful CPU-rendered desktop requires:

```text
offline-key-events=1
sheng-aks=1
```

With that AppleKeyStore state provider, the documented queue is:

```text
liveactivitiesd MKBEventsRegister succeeds
  -> chronod completes its ActivityKit startup
  -> SpringBoard completes _completeStartupAfterMainSceneConnect
  -> a definesDisplayBounds context update reaches the built-in display
```

H416 published a service named `AppleKeyStore` through
`sheng-aks-publish=1`, but did not set `sheng-aks=1`. In
`NativeKeyStoreEvents.cpp`, every user-client open returns
`kIOReturnNotReady` while that state gate is off. H416's ring records the
service at 76.402742 s and later AppleKeyStore open attempts from liveactivitiesd
and SpringBoard, but those attempts cannot become useful user clients.

The main-route `native_keystore_probe()` is a no-op, so merely adding the QEMU
argument `offline-key-events=1` would not construct an equivalent provider.
The H416 mechanism already publishes the service; the missing state is the
single gate below.

## Single behavior variable

```text
sheng-aks=1
```

All other H416 behavior inputs remain fixed: accelerator/addon, phase 4,
unit scale 3, dot pitch 163, Data seed, UEFI, IOMFB validation, CPU transfer and
retirement. This is not a display write or a synthetic frame.

## Observer corrections

The 21H461 QuartzCore binary is
`9b86fb33545d1e0ce12d5b02609f33093fba3a0937675610196365ba5a325a3a`.
Direct disassembly establishes:

```text
-[CADisplay pointScale]        returns 32-bit w0
-[CADisplay displayId]         returns 32-bit w0
-[CADisplayMode width]         returns 64-bit x0
-[CADisplayMode height]        returns 64-bit x0
-[CADisplayMode refreshRate]   returns d0
-[CADisplayMode preferredScale] returns 32-bit w0
```

`pixelWidth` and `pixelHeight` have no selector in 21H461 `CADisplayMode`.
H416's `px=0x0` therefore means "unsupported getters", not two real zero-valued
mode fields. Its `displayScale=0.000` is invalid because it called the 32-bit
`pointScale` return as a double.

H417 changes the observer to:

- validate `method_getTypeEncoding` before each non-object return;
- call `pointScale`, `displayId`, and `preferredScale` as 32-bit integers;
- never call `pixelWidth`/`pixelHeight`;
- distinguish `UNSUPPORTED` from nil and scalar zero;
- log displayId, contextId, displayMask, renderer flags and context object;
- walk at most three layer levels and 64 nodes;
- report class, frame, bounds, hidden, opacity, contents object type/context and
  sublayer count without modifying any layer;
- preserve the constructor-only schedule at 30/120/300 seconds.

Root `CALayer.contents=0` is not treated as proof that a subtree is empty.
Chromium's platform-specific remote-context example puts content in sublayers,
and the 21H461 renderer ignores updates until a `definesDisplayBounds` context
update exists.

## Requested result

The round distinguishes:

1. AKS state becomes usable: user-client opens succeed.
2. liveactivitiesd and chronod complete their documented startup dependencies.
3. SpringBoard/display updates resume.
4. display/context identity and the bounded sublayer tree reveal whether content
   exists and where the first observable break now moves.

The observer must not infer that point scale is zero unless the typed 32-bit
value is zero, and must not infer an empty subtree from root contents alone.

## Stop conditions

- H417 marker absent: no interpretation.
- AppleKeyStore open still returns `kIOReturnNotReady`: verify that the packaged
  `unixnu.toml` contains `sheng-aks=1`.
- Observer writes a layer/context or presents a frame: contaminated round.
- Insufficient bootargs capacity: remove only explicit default-valued arguments.
- No context/display progress after successful AKS opens: trace
  liveactivitiesd/chronod/SpringBoard startup before touching mode properties.
- Root remains empty while sublayers contain content: treat the scene as present
  and move to display binding.
- Selector 4 remains absent: do not start IOSurface, IOMFB copy or scanout fixes.

## Status

H417 completed the isolated two-pass PMGR build and one bounded device boot.

```text
kernel       2dd2ffd9f4a0979fedd9ae16213ea8e31e9d9f798d855e434d34d12c3f02f85d
payload      a6df0696032d4a562e6cfb906da1962f3f299df1a860e771c23d0f2e5dffe6cc
boot         a9618be5b19fbd46205070ff140ffc327bef9e2394001c6b46abeb132ab9b619
plugin       acd6c793e0aca8a8a2dafc1f56c8367645570916400f32e6e60bd1dfc533e07d
plugin CDHash e10c473b2ffb3565b63c9cd472e54e4789ef5755
```

`verify_h417.py`, the inherited Data gate, the display gate, and the typed CA
observer checker pass. The observer checker requires
`H417_NATIVE_SOURCE` to point at the sibling NativeMetal H417 worktree:

```text
H417_NATIVE_SOURCE=<NativeMetal-h417-aks-observer>/A540TracePlugin.mm
```

The device boot reported `NATIVE_BUILD: H417 boot=25f21e0c`. CDC appeared after
256 seconds and a 360-second capture carried 5,397 UXL1 frames / 817,993
payload bytes with zero CRC errors, sequence gaps, truncation or boot switches.

The early ring recovered the AKS/userland path:

```text
 73.891228  NATIVE_AKS: AppleKeyStore published (late)
132.392601  keybagd exec
142.602218  SpringBoard exec
166.601169  keybagd called AppleKeyStore open
202.407710  backboardd exec
218.338030  chronod exec
224.494809  backboardd opened NativeLegacyDisplay
233.636017  backboardd opened AGXAccelerator type=0
236.297705  backboardd opened IOSurfaceRoot
261.503326  IOMFB_FDR_Loader opened NativeLegacyDisplay
271.922954  liveactivitiesd exec
276.230628  display gate sample=6000
300.871255  liveactivitiesd called AppleKeyStore open
334.929386  backboardd opened AGXAccelerator type=1
334.936168  backboardd accelerator ABI selector=2
347.705676  SpringBoard called AppleKeyStore open
```

The captured `op=open ... ok=0` line is emitted before
`is_io_service_open_extended()` reaches the provider. It is an entry sentinel,
not the user-client return value. This round therefore proves that the AKS
publication and later open path were reached; it does not directly prove that
`sheng-aks=1` made each client return `kIOReturnSuccess`.

Two CA observation rounds completed before the first captured UFS OCS timeout:

```text
326.150325  probe round 1
347.938589  displays=6 d0id=0x1 d0ctx=UNSUPPORTED renderer=3 ctxs=2
363.349159  ctx 0x195fa2cc displayId=0x1 mask=0xffffffff CALayer 1080x1920
363.349571  ctx 0x182f8c1f displayId=0x1 mask=0xffffffff CALayer 1080x1920

368.982341  probe round 2
371.415143  displays=6 d0id=0x1 d0ctx=UNSUPPORTED renderer=3 ctxs=2
376.024691  ctx 0x195fa2cc displayId=0x1 mask=0xffffffff CALayer 1080x1920
376.025184  ctx 0x182f8c1f displayId=0x1 mask=0xffffffff CALayer 1080x1920
```

The primary display now reports `1080x1920`, refresh `60`, preferred scale `3`
and point scale `3`; `pixelWidth`/`pixelHeight` are explicitly
`UNSUPPORTED`. Each context's four-node, at-most-three-level tree contains only
`CALayer` nodes: a full-screen root, a full-screen first child, a full-screen
second child, and a 0x0 grandchild. Every node has null contents, and no render
context is exposed. The context mask weakens the earlier missing-display-binding
hypothesis; the unsupported display-side getters are an observation limitation,
not evidence that every private QuartzCore slot is empty.

Display gate results:

```text
276.230628 sample=6000 accel=2/0/199/0 dpy=2/11/0/0/0 s345=0/0/0 val=0 xf=0 fr=0
577.852738 sample=6060 accel=5/0/484/0 dpy=3/18/0/1/0 s345=0/0/0 val=0 xf=0 fr=0
```

The first gate is before the UFS failure window. The later gate is supporting
evidence only because it lies after the first OCS timeout. The H417 capture had
13 OCS timeouts, 13 retries, 15 stall/no-panic records and 27 process-corpse
crashes, with no kernel panic or undefined instruction.

No draw/commit, `nextDrawable`, IOMFB selector 4, surface validation, transfer,
or frame appeared. The earliest observable break therefore moved upstream of
IOMFB: SpringBoard/CoreAnimation produced two geometrically valid, display-bound
context roots, but no drawable-bearing scene content or renderer draw/commit.
The next round should directly log the AKS `newUserClient` result and then trace
the SpringBoard main-scene / `definesDisplayBounds` boundary. It should not
touch IOSurface, IOMFB copy or MSM8998 scanout while selector 4 remains zero.

Device evidence:

```text
main-route/display-first-frame/logs/H417/device/20261118-213940/
```
