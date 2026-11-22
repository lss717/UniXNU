#!/usr/bin/env python3
"""Build H436's SpringBoard app-bundle wrapper addon.

Usage:
  build-h436-springboard-bundle.py LAUNCHD-CACHE.plist SPRINGBOARD OUTPUT [LSD]

The input is /System/Library/xpc/launchd.plist, the binary job cache consumed by
launchd_cache_loader. The cached job keeps its original standard executable
path; a separate bindfs view overlays that path with the signed wrapper and
places the original signed SpringBoard beside it as SpringBoard.real.
"""

import copy
import hashlib
import json
import os
import plistlib
import re
import shutil
import struct
import subprocess
import sys
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build/h436-springboard-bundle"
BUNDLE = OUT / "A540Trace.bundle"
OBSERVER = OUT / "SpringBoardSceneObserver.dylib"
BOOTSTRAP = OUT / "scenebootstrap"
LSD_BOOTSTRAP = OUT / "lsdwrap"
LSD_SHIM = OUT / "LsdRecoveryAsync.dylib"
LSD_BINARY = OUT / "lsd.real"
XPC = OUT / "xpc"
SPRINGBOARD_DIR = OUT / "springboard"
SPRINGBOARD_JOB = (
    "/System/Library/LaunchDaemons/com.apple.SpringBoard.plist"
)
LSD_JOB = "/System/Library/LaunchDaemons/com.apple.lsd.plist"


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


def require_binary_markers(path: Path, markers: tuple[bytes, ...]) -> None:
    data = path.read_bytes()
    for marker in markers:
        if marker not in data:
            raise SystemExit(
                f"{path} is missing required marker {marker.decode(errors='replace')}"
            )


def main() -> int:
    if len(sys.argv) not in (4, 5):
        raise SystemExit(__doc__)
    cache_source = Path(sys.argv[1]).resolve()
    springboard_source = Path(sys.argv[2]).resolve()
    output = Path(sys.argv[3]).resolve()
    lsd_source = Path(sys.argv[4]).resolve() if len(sys.argv) == 5 else None
    if output.exists():
        raise SystemExit("Refuse to overwrite " + str(output))

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True, exist_ok=True)
    BUNDLE.mkdir(parents=True, exist_ok=True)
    XPC.mkdir(parents=True, exist_ok=True)
    SPRINGBOARD_DIR.mkdir(parents=True, exist_ok=True)
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
         "-Wl,-undefined,dynamic_lookup",
         "-framework", "Foundation", "-framework", "IOKit",
         "-framework", "CoreGraphics",
         "-I", str(ROOT / "drivers/NativeAdreno"),
         str(ROOT / "drivers/NativeMetal/SpringBoardSceneObserver.mm"),
         str(ROOT / "drivers/NativeMetal/SpringBoardCCSBypass.mm"),
         str(ROOT / "drivers/NativeMetal/SpringBoardLSWorkspaceObserverBypass.mm"),
         "-o", str(OBSERVER)],
        check=True,
    )
    subprocess.run(["strip", "-x", str(OBSERVER)], check=True)
    require_binary_markers(
        OBSERVER,
        (
            b"observer load process=",
            b"build=H582",
            b"H492_CCS",
            b"filter bypass installed",
            b"filter bypass pid",
            b"H540_LS",
            b"h541_did_finish_enter",
            b"h541_application_state",
            b"h542_status_server_bypass_enter",
            b"h542_after_did_finish",
            b"h543_mc_wait_bypass_enter",
            b"h545_cloud_config_ui_bypass",
            b"h546_setup_manager_init_enter",
            b"h547_by_setup_assistant_needs_to_run_bypass",
            b"h548_by_setup_prepare_launch_sentinel_bypass",
            b"h549_setup_return_sampler_start",
            b"h549_setup_return_main_sample",
            b"h550_setup_hud_enter",
            b"h550_sound_shared_enter",
            b"h550_sound_init_enter",
            b"h550_ringer_init_enter",
            b"h550_uncaught_exception",
            b"h551_status_data_log_empty_init_enter",
            b"h551_status_hooks",
            b"h552_telephony_shared_enter",
            b"h552_telephony_shared_creating_enter",
            b"h552_telephony_init_enter",
            b"h552_telephony_hooks",
            b"h553_application_controller_init_enter",
            b"h553_application_library_installed_application_enter",
            b"h553_application_library_installed_applications_enter",
            b"h553_application_library_all_installed_enter",
            b"h553_application_hooks",
            b"h554_mutable_set_remove_nil_ignored",
            b"h554_mutable_set_remove_guard",
            b"h555_concrete_set_remove_guard",
            b"h556_post_did_finish_snapshot_enter",
            b"h556_post_transaction_flush",
            b"h557_startup_hooks",
            b"h557_complete_startup_enter",
            b"h557_ui_run_enter",
            b"h557_post_run_snapshot",
            b"h572_observer_loaded",
            b"h572_observer_alive",
            b"h572_cxx_terminate",
            b"h575_cxx_throw",
            b"h577_chrono_subscribe_skip",
            b"h578_exception_reporters_rearmed",
            b"h578_abort_signal",
            b"h578_abort_frame",
            b"h579_chrono_assertion_stub",
            b"h579_chrono_assertion_stub_installed",
            b"h580_objc_exception",
            b"h581_nsexception",
            b"h582_icon_init_exception_caught",
            b"methods installed add=independent state=",
            b"observer bypass pid=",
            b"application enumeration skipped",
            b"current process proxy skipped",
            b"application proxy identifier skipped",
            b"application proxy URL skipped",
            b"h572_observer_alive sample=",
        ),
    )
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
        BOOTSTRAP, "org.blu-sharky.H435SpringBoardWrapper", entitlements
    )

    lsd_report = None
    if lsd_source is not None:
        expected_lsd_sha256 = (
            "43ee16e03145f3ad6b84fc7dac63ee767ec8182b51bc9cb5bd8bf8650baa4e5b"
        )
        actual_lsd_sha256 = hashlib.sha256(lsd_source.read_bytes()).hexdigest()
        if actual_lsd_sha256 != expected_lsd_sha256:
            raise SystemExit(
                f"lsd input SHA-256 {actual_lsd_sha256} "
                f"does not match 21H461 {expected_lsd_sha256}"
            )
        subprocess.run(
            [*common, "-std=c++17", "-fobjc-arc",
             "-framework", "Foundation", "-framework", "IOKit",
             str(ROOT / "drivers/NativeMetal/LsdBootstrap.mm"),
             "-o", str(LSD_BOOTSTRAP)],
            check=True,
        )
        subprocess.run(["strip", "-x", str(LSD_BOOTSTRAP)], check=True)
        require_binary_markers(
            LSD_BOOTSTRAP,
            (
                b"H518_LSDWRAP",
                b"/System/Library/xpc/lsd.real",
                b"/private/var/ngpu/lib/LsdRecoveryAsync.dylib",
            ),
        )
        lsd_bootstrap_cdhash = compact_signed_bundle(
            LSD_BOOTSTRAP,
            "org.blu-sharky.H518LsdWrapper",
            entitlements,
        )

        subprocess.run(
            [*common, "-std=c++17", "-fobjc-arc", "-fblocks",
             "-dynamiclib", "-framework", "Foundation",
             str(ROOT / "drivers/NativeMetal/LsdRecoveryAsync.mm"),
             "-o", str(LSD_SHIM)],
            check=True,
        )
        subprocess.run(["strip", "-x", str(LSD_SHIM)], check=True)
        require_binary_markers(
            LSD_SHIM,
            (
                b"H536_LSD",
                b"recovery skip installed",
                b"recovery install failed",
                b"recovery skipped",
            ),
        )
        lsd_shim_cdhash = compact_signed_bundle(
            LSD_SHIM,
            "org.blu-sharky.H536LsdRecoveryAsync",
        )
        lsd_entitlements = subprocess.run(
            ["codesign", "-d", "--entitlements", ":-", str(lsd_source)],
            capture_output=True,
            check=True,
        )
        if b"<plist" not in lsd_entitlements.stdout:
            raise SystemExit("Original lsd had no readable entitlements")
        entitlements_path = OUT / "lsd-entitlements.plist"
        entitlements_path.write_bytes(lsd_entitlements.stdout)
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/add-macho-load-dylib.py"),
                str(lsd_source),
                "/private/var/ngpu/lib/LsdRecoveryAsync.dylib",
                str(LSD_BINARY),
            ],
            check=True,
        )
        os.chmod(LSD_BINARY, 0o755)
        lsd_binary_cdhash = compact_signed_bundle(
            LSD_BINARY,
            "com.apple.lsd",
            entitlements_path,
        )
        load_commands = subprocess.check_output(
            ["otool", "-l", str(LSD_BINARY)], text=True
        )
        if "/private/var/ngpu/lib/LsdRecoveryAsync.dylib" not in load_commands:
            raise SystemExit("Patched lsd is missing the recovery LC_LOAD_DYLIB")
        lsd_report = {
            "lsd_source_sha256": actual_lsd_sha256,
            "lsd_binary_sha256": hashlib.sha256(LSD_BINARY.read_bytes()).hexdigest(),
            "lsd_binary_cdhash": lsd_binary_cdhash,
            "lsd_bootstrap_cdhash": lsd_bootstrap_cdhash,
            "lsd_recovery_cdhash": lsd_shim_cdhash,
        }

    original = cache_source.read_bytes()
    cache = plistlib.loads(original)
    daemons = cache.get("LaunchDaemons")
    if not isinstance(daemons, dict) or not isinstance(
        daemons.get(SPRINGBOARD_JOB), dict
    ):
        raise SystemExit("launchd cache has no SpringBoard job")
    before = copy.deepcopy(daemons[SPRINGBOARD_JOB])
    job = daemons[SPRINGBOARD_JOB]
    if job.get("ProgramArguments") != [
        "/System/Library/CoreServices/SpringBoard.app/SpringBoard"
    ]:
        raise SystemExit("cached SpringBoard job has an unexpected executable")
    environment = dict(job.get("EnvironmentVariables", {}))
    environment["DYLD_INSERT_LIBRARIES"] = (
        "/private/var/ngpu/lib/SpringBoardSceneObserver.dylib"
    )
    environment["DYLD_FORCE_FLAT_NAMESPACE"] = "1"
    job["EnvironmentVariables"] = environment
    modified = plistlib.dumps(cache, fmt=plistlib.FMT_BINARY, sort_keys=False)
    modified_cache = plistlib.loads(modified)
    for key, value in daemons.items():
        if key != SPRINGBOARD_JOB and modified_cache["LaunchDaemons"].get(key) != value:
            raise SystemExit("launchd cache changed unrelated job " + key)
    if modified_cache["LaunchDaemons"][SPRINGBOARD_JOB] != job:
        raise SystemExit("launchd cache SpringBoard job did not round-trip")
    if lsd_source is not None:
        lsd_job = daemons.get(LSD_JOB)
        if not isinstance(lsd_job, dict):
            raise SystemExit("launchd cache has no mobile lsd job")
        before_lsd = copy.deepcopy(lsd_job)
        if lsd_job.get("ProgramArguments") != ["/usr/libexec/lsd"]:
            raise SystemExit("cached lsd job has an unexpected executable")
        lsd_job["ProgramArguments"] = ["/System/Library/xpc/lsdwrap"]
        lsd_report["lsd_job_before_program_arguments"] = before_lsd["ProgramArguments"]
        lsd_report["lsd_job_after_program_arguments"] = lsd_job["ProgramArguments"]
        modified = plistlib.dumps(cache, fmt=plistlib.FMT_BINARY, sort_keys=False)
        modified_cache = plistlib.loads(modified)
        if modified_cache["LaunchDaemons"][LSD_JOB] != lsd_job:
            raise SystemExit("launchd cache lsd job did not round-trip")
        for key, value in daemons.items():
            if key not in (SPRINGBOARD_JOB, LSD_JOB) and \
                    modified_cache["LaunchDaemons"].get(key) != value:
                raise SystemExit("launchd cache changed unrelated job " + key)
    (XPC / "launchd.plist").write_bytes(modified)
    if not springboard_source.is_file():
        raise SystemExit("SpringBoard input is missing")
    (SPRINGBOARD_DIR / "SpringBoard.real").write_bytes(
        springboard_source.read_bytes()
    )
    os.chmod(SPRINGBOARD_DIR / "SpringBoard.real", 0o755)
    os.chmod(BOOTSTRAP, 0o755)
    shutil.copyfile(BOOTSTRAP, SPRINGBOARD_DIR / "SpringBoard")
    os.chmod(SPRINGBOARD_DIR / "SpringBoard", 0o755)
    springboard_entitlements = subprocess.run(
        ["codesign", "-d", "--entitlements", ":-", str(springboard_source)],
        capture_output=True,
        check=True,
    )
    if b"<plist" not in springboard_entitlements.stdout:
        raise SystemExit("Original SpringBoard had no readable entitlements")
    springboard_entitlements_path = OUT / "springboard-entitlements.plist"
    springboard_entitlements_path.write_bytes(springboard_entitlements.stdout)
    springboard_binary = SPRINGBOARD_DIR / "SpringBoard.patched"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/add-macho-load-dylib.py"),
            str(springboard_source),
            "/private/var/ngpu/lib/SpringBoardSceneObserver.dylib",
            str(springboard_binary),
        ],
        check=True,
    )
    os.chmod(springboard_binary, 0o755)
    springboard_cdhash = compact_signed_bundle(
        springboard_binary, "com.apple.springboard",
        springboard_entitlements_path,
    )
    springboard_load_commands = subprocess.check_output(
        ["otool", "-l", str(springboard_binary)], text=True
    )
    if "/private/var/ngpu/lib/SpringBoardSceneObserver.dylib" not in \
            springboard_load_commands:
        raise SystemExit("Patched SpringBoard is missing the observer LC_LOAD_DYLIB")

    files = []
    for path in sorted(p for p in BUNDLE.rglob("*") if p.is_file()):
        mode = 0o755 if path.name == "A540Trace" else 0o644
        files.append(("addons/A540Trace.bundle/" + path.relative_to(BUNDLE).as_posix(),
                      mode, path.read_bytes()))
    files.append(("addons/A540Trace.scene-observer", 0o644, b"H436\n"))
    files.append(("lib/SpringBoardSceneObserver.dylib", 0o755, OBSERVER.read_bytes()))
    files.append(("bin/scenebootstrap", 0o755, BOOTSTRAP.read_bytes()))
    files.append(("xpc/launchd.plist", 0o644, modified))
    # The H483 launchd environment did not inject the observer on 21H461.
    # Install a copy of the original executable with an explicit observer
    # LC_LOAD_DYLIB and its original entitlements. The raw executable remains
    # beside it for inspection and wrapper compatibility.
    files.append(("springboard/SpringBoard", 0o755,
                  springboard_binary.read_bytes()))
    files.append(("springboard/SpringBoard.real", 0o755,
                  (SPRINGBOARD_DIR / "SpringBoard.real").read_bytes()))
    if lsd_source is not None:
        files.append(("xpc/lsdwrap", 0o755, LSD_BOOTSTRAP.read_bytes()))
        files.append(("xpc/lsd.real", 0o755, LSD_BINARY.read_bytes()))
        files.append(("lib/LsdRecoveryAsync.dylib", 0o755, LSD_SHIM.read_bytes()))

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
        "launchd_cache_sha256_source": hashlib.sha256(original).hexdigest(),
        "launchd_cache_sha256_modified": hashlib.sha256(modified).hexdigest(),
        "springboard_job_before_program_arguments": before["ProgramArguments"],
        "springboard_job_posix_spawn_type": job.get("POSIXSpawnType"),
        "springboard_binary_sha256": hashlib.sha256(
            springboard_source.read_bytes()
        ).hexdigest(),
        "springboard_patched_sha256": hashlib.sha256(
            springboard_binary.read_bytes()
        ).hexdigest(),
        "springboard_cdhash": springboard_cdhash,
        "springboard_observer_load_command": True,
        "springboard_environment": {
            "DYLD_INSERT_LIBRARIES": environment["DYLD_INSERT_LIBRARIES"],
            "DYLD_FORCE_FLAT_NAMESPACE": environment["DYLD_FORCE_FLAT_NAMESPACE"],
        },
        "springboard_program_arguments": job["ProgramArguments"],
        "lsd": lsd_report,
        "files": [name for name, _, _ in files],
    }
    (OUT / "trust.json").write_text(json.dumps(report, indent=2) + "\n")
    for name, mode, data in files:
        print(f"{mode:o} {len(data):>10} {name}")
    print(f"addon {output}: {len(files)} files, {output.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
