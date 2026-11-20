# H474b long no-accelerator control (2026-11-21)

## Purpose

H475 loaded A540Trace successfully but SpringBoard aborted with signal 6.
H474b repeats H474 without the accelerator to separate the baseline full-addon
path from the Metal observer/accelerator contribution.

## Held constant

```text
kernel       4577d3bc93a48dec1c910e76d4262e8ceda64869f6b370a2ee3ff42556364b00
trust cache  cd754067b9587960d336715b35c933cfb50b29f3b5b7b48feb0d8988092541cf
GPU addon    88251c35d6a1b6b6df2c761c2c136f04a9090e1361f16fdaceac798ba6da5dee
Data seed    7522c2b803bac371190e5f316bacc825d1dd3c964ef3a3ab6ffd75bf0f9bae79
sheng-gpu-addon=1
sheng-no-lc=1
offline-accelerator=0
```

The full addon contains:

```text
addons/A540Trace.bundle/A540Trace
addons/A540Trace.bundle/Info.plist
addons/A540Trace.bundle/_CodeSignature/CodeResources
addons/A540Trace.scene-observer
lib/SpringBoardSceneObserver.dylib
springboard/SpringBoard
xpc/launchd.plist
```

## Result

Runtime boot ID `2247fedf`; observation extended through 2405.616845 seconds.

```text
addon=7/5/2/0/0/0
ext=4/2 dm=5/0 wp=5/0
accel=0/0/0/0
NATIVE_MTL lines=0
s345=0/0/0 val=0 xf=0 fr=0
```

SpringBoard crashed five times with the same code:

```text
2166.240319 s pid=27  status=0x6 ns=2 code=0x6
2217.609221 s pid=189 status=0x6 ns=2 code=0x6
2233.849345 s pid=194 status=0x6 ns=2 code=0x6
2291.854704 s pid=199 status=0x6 ns=2 code=0x6
2366.458940 s pid=219 status=0x6 ns=2 code=0x6
```

There was no AMFI launch-constraint loop. UFS remained healthy:

```text
2402.885791 s seq=352327 done=352326 flight=1
timeout=0 ocs_err=0 dbto=0 recover=0 recovered=0 lock_timeout=0
lock_wait_max_ms=33803
```

`watchdog_seen=4680` is the existing observation counter, not a recorded
watchdog-fired/recovery event. This run does not verify watchdog recovery.
`lock_waiters=4294967295` is the known non-atomic counter underflow.

## Conclusion

The baseline SpringBoard signal-6 crash does not require the A540Trace
accelerator or Metal observer. The next single variable is the GPU addon
contents: use the three-file A540Trace bundle addon while retaining the full
addon's other boot conditions and the working accelerator path.

Classification:
`H474b-no-accelerator-same-springboard-sigabrt`.

```text
H474b-live.log
  c7e97c24fbfa748da73c15b81fbff25a2520d2832a1f64e3a6846b78495f1a87
H474b-tail32.bin
  763d4fc1ebfd07e42707da9c12fee1a7273e8feded32a803a73fb68e25d6029a
H474b-h103.txt
  732d2b1a08e7d1f81a3fc2a62f205bed713e09c4b8d2dcae972c967b68c7f21e
```
