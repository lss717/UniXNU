# Format 1 XNU patch series

`series` is the authoritative application order. Build scripts must not glob
and sort `*.patch` independently. The series validator rejects duplicate
entries, listed files that do not exist, and patch files that exist but are not
listed.

The filenames describe function, not chronology. Historical H numbers may
remain in diagnostics and comments, but they do not control order.

Keep these dependency groups in their current relative order:

- `native-gpu-addon-mount.patch` introduces the addon parser and union-mount
  helpers.
- `staged-system-apps.patch` appends to the mount preparation path introduced
  above.
- `native-gpu-addon-log.patch` instruments the helpers introduced by the mount
  patch and must precede the later `addon-*.patch` files that extend those
  paths.
- `springboard-late-union.patch` (historically H437) touches the same late
  `kern_exec.c` region as the addon, staged-app, boot-progress and logging
  patches, so it stays at the end of the series.
- `log-process-state.patch` establishes the process sampler structures used by
  `ipc-event-ring.patch`, the BKS ring patches and
  `springboard-lsd-target-port.patch`.
- `ipc-event-ring.patch` precedes the SpringBoard/BKS filters and target-port
  lookup that consume its events.
- `data-mount-ready.patch` precedes the LaunchServices filesystem and stable
  gate probes that rely on the bounded Data wait.
- `springboard-lsd-target-port.patch` follows the sampler and event-ring
  patches it reads, and precedes later diagnostics that must continue to
  compile against the same structures.

NativePrelink patches have their own authoritative
`kits/NativePrelink/patches/series`. The XNU series is applied first, followed
by the NativePrelink series, matching the successful Format 1 build path.
