#!/usr/bin/env python3
"""Build H432's SpringBoard launch-wrapper addon.

Usage:
  build-h432-springboard-wrapper.py SPRINGBOARD.plist OUTPUT

The build preserves the original SpringBoard launchd job metadata, installs the
wrapper as its ProgramArguments, and keeps the observer environment as defense
in depth. The wrapper logs before exec, sets the same environment in its own
process and then execs the original SpringBoard binary.
"""

import json
import plistlib
import re
import shutil
import struct
import subprocess
import sys
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build/h432-springboard-wrapper"
BUNDLE = OUT / "A540Trace.bundle"
OBSERVER = OUT / "SpringBoardSceneObserver.dylib"
BOOTSTRAP = OUT / "scenebootstrap"
DAEMONS = OUT / "daemons"


def pad(data: bytes) -> bytes:
    return data + bytes(-len(data) % 8)


def compact_signed_bundle(path: Path, identifier: str,
                          entitlements: Path | None = None) -> str:
    command = [
        "codesign", "--force", "--sign", "-", "--pagesize", "4096",
        "--identifier", identifier,
    ]
    if entitlements is not None:
        command.extend(["--entitlements", str(entitlements)])
    command.append(str(path))
    subprocess.run(
        command,
        check=True,
    )
    subprocess.run(["codesign", "--verify", "--strict", str(path)], check=True)
    detail = subprocess.run(
        ["codesign", "--display", "--verbose=4", str(path)],
        capture_output=True,
        text=True,
        check=True,
    ).stderr
    match = re.search(r"^CDHash=([a-f0-9]{40})$", detail, re.MULTILINE)
    if not match:
        raise SystemExit("No CDHash in codesign output for " + str(path))
    return match.group(1)


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    springboard_source = Path(sys.argv[1]).resolve()
    output = Path(sys.argv[2]).resolve()
    if output.exists():
        raise SystemExit("Refuse to overwrite " + str(output))

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True, exist_ok=True)
    BUNDLE.mkdir(parents=True, exist_ok=True)
    DAEMONS.mkdir(parents=True, exist_ok=True)
    sdk = subprocess.check_output(
        ["xcrun", "--sdk", "iphoneos", "--show-sdk-path"], text=True
    ).strip()
    common = [
        "xcrun", "clang++", "-target", "arm64-apple-ios17.0", "-isysroot", sdk,
        "-Os", "-Wall", "-Wextra", "-Werror", "-fstack-protector-strong",
    ]

    trace_executable = BUNDLE / "A540Trace"
    subprocess.run(
        [*common, "-std=c++17", "-fobjc-arc", "-bundle",
         "-framework", "Foundation", "-framework", "IOKit", "-framework", "Metal",
         "-I", str(ROOT / "drivers/NativeAdreno"),
         str(ROOT / "drivers/NativeMetal/A540TracePlugin.mm"),
         "-o", str(trace_executable)],
        check=True,
    )
    subprocess.run(["strip", "-x", str(trace_executable)], check=True)
    (BUNDLE / "Info.plist").write_bytes(plistlib.dumps({
        "CFBundleIdentifier": "org.blu-sharky.A540Trace",
        "CFBundleExecutable": "A540Trace",
        "CFBundlePackageType": "BNDL",
        "CFBundleVersion": "1",
        "CFBundleShortVersionString": "1",
        "NSPrincipalClass": "A540TraceDevice",
        "MinimumOSVersion": "17.0",
    }, fmt=plistlib.FMT_XML))
    trace_cdhash = compact_signed_bundle(BUNDLE, "org.blu-sharky.A540Trace")

    subprocess.run(
        [*common, "-std=c++17", "-fobjc-arc", "-fblocks", "-dynamiclib",
         "-framework", "Foundation", "-framework", "IOKit",
         "-framework", "CoreGraphics",
         "-I", str(ROOT / "drivers/NativeAdreno"),
         str(ROOT / "drivers/NativeMetal/SpringBoardSceneObserver.mm"),
         "-o", str(OBSERVER)],
        check=True,
    )
    subprocess.run(["strip", "-x", str(OBSERVER)], check=True)
    observer_cdhash = compact_signed_bundle(
        OBSERVER, "org.blu-sharky.SpringBoardSceneObserver"
    )

    subprocess.run(
        [*common, "-std=c++17", "-fobjc-arc",
         "-framework", "Foundation", "-framework", "IOKit",
         str(ROOT / "drivers/NativeMetal/SceneBootstrap.mm"),
         "-o", str(BOOTSTRAP)],
        check=True,
    )
    subprocess.run(["strip", "-x", str(BOOTSTRAP)], check=True)
    entitlements = OUT / "scenebootstrap-entitlements.plist"
    entitlements.write_bytes(plistlib.dumps({
        "com.apple.private.security.no-container": True,
    }))
    bootstrap_cdhash = compact_signed_bundle(
        BOOTSTRAP, "org.blu-sharky.H432SpringBoardWrapper", entitlements
    )

    original = springboard_source.read_bytes()
    job = plistlib.loads(original)
    job["ProgramArguments"] = [
        "/private/var/ngpu/bin/scenebootstrap",
        "--launch-springboard",
    ]
    environment = dict(job.get("EnvironmentVariables", {}))
    environment["DYLD_INSERT_LIBRARIES"] = (
        "/private/var/ngpu/lib/SpringBoardSceneObserver.dylib"
    )
    environment["DYLD_FORCE_FLAT_NAMESPACE"] = "1"
    job["EnvironmentVariables"] = environment
    plist_format = plistlib.FMT_BINARY if original.startswith(b"bplist") else plistlib.FMT_XML
    (DAEMONS / "com.apple.SpringBoard.plist").write_bytes(
        plistlib.dumps(job, fmt=plist_format, sort_keys=False)
    )

    (DAEMONS / "org.blu-sharky.adrenoprobed.plist").write_bytes(
        plistlib.dumps({
            "Label": "org.blu-sharky.adrenoprobed",
            "ProgramArguments": ["/usr/bin/true"],
            "RunAtLoad": False,
            "KeepAlive": False,
        }, fmt=plistlib.FMT_XML)
    )

    files = []
    for path in sorted(p for p in BUNDLE.rglob("*") if p.is_file()):
        mode = 0o755 if path.name == "A540Trace" else 0o644
        files.append(("addons/A540Trace.bundle/" + path.relative_to(BUNDLE).as_posix(),
                      mode, path.read_bytes()))
    files.append(("addons/A540Trace.scene-observer", 0o644, b"H432\n"))
    files.append(("lib/SpringBoardSceneObserver.dylib", 0o755, OBSERVER.read_bytes()))
    files.append(("bin/scenebootstrap", 0o755, BOOTSTRAP.read_bytes()))
    for path in sorted(p for p in DAEMONS.iterdir() if p.is_file()):
        files.append(("daemons/" + path.name, 0o644, path.read_bytes()))

    body = b""
    for name, mode, data in files:
        encoded = name.encode() + b"\0"
        if len(encoded) > 160 or ".." in name.split("/") or name.startswith("/"):
            raise SystemExit("Bad addon path " + name)
        packed = zlib.compress(data, 9)
        stored = len(packed) >= len(data)
        if stored:
            packed = data
        body += struct.pack(
            "<IIQQII", len(encoded), mode, len(data), len(packed),
            zlib.crc32(packed) & 0xFFFFFFFF, 1 if stored else 0,
        ) + pad(encoded) + pad(packed)
    output.write_bytes(
        b"NGPUADD2" + struct.pack("<IIQ", len(files), 0, 24 + len(body)) + body
    )

    report = {
        "trace_cdhash": trace_cdhash,
        "observer_cdhash": observer_cdhash,
        "bootstrap_cdhash": bootstrap_cdhash,
        "springboard_plist_sha256_source": springboard_source.name,
        "springboard_environment": {
            "DYLD_INSERT_LIBRARIES": environment["DYLD_INSERT_LIBRARIES"],
            "DYLD_FORCE_FLAT_NAMESPACE": environment["DYLD_FORCE_FLAT_NAMESPACE"],
        },
        "springboard_program_arguments": job["ProgramArguments"],
        "files": [name for name, _, _ in files],
    }
    (OUT / "trust.json").write_text(json.dumps(report, indent=2) + "\n")
    for name, mode, data in files:
        print(f"{mode:o} {len(data):>10} {name}")
    print(f"addon {output}: {len(files)} files, {output.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
