# H476 three-file addon control (2026-11-21)

## Single variable

H476 held the H475 kernel, Data seed, trust cache, boot arguments and
A540Trace accelerator constant. It replaced the seven-file full addon with
the three-file `H465-plugin-addon.img`:

```text
becf899a246099a87f2eda9c7062b303403ac8500f25264c80a06ad75742913c
```

The addon contains only:

```text
addons/A540Trace.bundle/A540Trace
addons/A540Trace.bundle/Info.plist
addons/A540Trace.bundle/_CodeSignature/CodeResources
```

The payload kernel and `unixnu.toml` round-trip stayed byte-identical to H475.
The boot arguments string was also identical. ADT, boot-image layout, required
placeholders and the 1016/1024-byte worst-case bootargs check passed.

## Device result

Serial `16149951`, runtime boot ID `2160c455`, CDC about 257 seconds after
boot acceptance.

```text
addon=3/1/2/0/0/0
owner=4/0 ext=4/2 dm=1/2 wp=1/2
```

The extension union mount still passed. `dm/wp=1/2` is expected because this
addon has no `xpc` or `springboard` directory. A540Trace remained active:

```text
NATIVE_MTL: return#22 ... class=A540TraceQueue
NATIVE_MTL: dev#13 initialize loaded=1
NATIVE_MTL: dev#15 initWithAcceleratorPort: port=0x6307
NATIVE_MTL: ca#218 probe observer class=1 main=1 list=6 server=6
```

The three-file control ran 2700 capture seconds:

```text
frames=25098 payload_bytes=3565359
crc_errors=0 sequence_gaps=0 boot_switches=0
last_sequence=25097
```

The live log reaches kernel uptime 2975.155933 seconds. SpringBoard pid 27
remains alive through the final sampler:

```text
2152.373030 s sb=27 n=11
2226.745827 s sb=27 n=13
2298.339065 s sb=27 n=16
2894.907742 s sb=27 n=16
```

`NATIVE_EXIT ... comm=SpringBoard` count is zero. This passes both the H475
crash point at about 2148 seconds and the H474b repeated-crash window through
2366 seconds.

## Display boundary

backboardd reached selector 4 at 431.002937 seconds. At 432.162410 seconds the
driver transferred 8,294,400 bytes and observed retirement; selector 5
completed at 432.162545 seconds.

This transfer remains synthetic/clear:

```text
NATIVE_LEGACY_READBACK: c=ff2020ff br=ff2020ff q=ff20ff20
NATIVE_LEGACY_SWAP: skip req=0 valid=0
```

The final display gate at 2894.988842 seconds remained:

```text
s345=0/1/1 val=1 xf=1 fr=0
```

There is no product frame. The addon also has no SpringBoard scene observer,
so this run cannot establish the true scene/window count.

## UFS boundary

An 8-block request remained in flight long enough to emit one stall:

```text
2529.896104 s req=59c7ea/8 cmds=407686 waited=200770114
```

The same `seq=422525 done=422524` remained through 2801.596478 seconds. At
2825.186673 seconds one window lock timed out:

```text
NATIVE_UFS_LOCK: readWindowBulk timeout
  holder=studentd waiter=voiced held_ms=1 waiters=36
```

The APFS path then logged a named-stream read error. The request path resumed
at 2831.868864 seconds with `seq=424011 done=424011 flight=0`. There is no
per-UTRD tag, so this proves path recovery, not completion of request
`59c7ea`.

The final status at 2970.719268 seconds was:

```text
seq=435340 done=435340 flight=0
timeout=0 ocs_err=0 dbto=0 recover=0 recovered=0
lock_timeout=1 lock_wait_max_ms=119055
```

This is not a zero-lock-timeout run. H103 reported `msg_bytes=0` with a wrapped
slot set, so the live CDC log is authoritative for the final section.

## Conclusion

The seven-file addon is necessary for the SpringBoard SIGABRT observed in
H475/H474b. The three-file A540Trace bundle alone does not trigger it. The
next controlled change can add launchd-based observer injection while keeping
the original SpringBoard binary.

Classification:
`H476-three-file-addon-clears-springboard-sigabrt/one-window-lock-timeout-no-product-frame`.

```text
H476-live.log             58ecc39e60d2c80626b8c9473eb4982b07747add08834e9aa2371ee0913f5e23
H476-live.frames.bin      9ec09474f258631115398801e1b8f286ded5ce2ce0dac409e8e698aad3e5577a
H476-tail32.bin           c9a674fe9d3001bc58749db3def6f2def603faf0b1765bc7ed671f95cb667789
H476-h103.txt             432558dbb10f175902d5879239c77122675d3b49eb2df58cfc5c115500d82c1c
```
