#!/usr/bin/env python3
"""Prepare a packed Data seed for the iOS 17 LaunchServices startup path.

  seed-data-launchservices-readiness.py BASE.dbr OUTPUT.dbr

BASE is a DBRDISK1 packed APFS container. This tool expands it, mounts the raw
APFS image read-write, adds the Data-side directories used by lsd and
iconservicesagent, records the 21H461 DataMigration completion state under the
file name used by iOS 17, and writes system/user launchd disabled files that
stop iconservicesagent before lsd can wait for it synchronously.

The original seed and its Data volume UUID remain unchanged. Existing
preferences and launchd entries are preserved.
"""

import json
import os
import plistlib
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "drivers/DarwinBoot/Test"))
import packed_ramdisk

BUILD = "21H461"
DIRECTORIES = (
    ("db/lsd", 0o755),
    ("containers/Shared/SystemGroup/systemgroup.com.apple.lsd.iconscache", 0o755),
    ("containers/Shared/SystemGroup/systemgroup.com.apple.lsd.iconscache/Library", 0o755),
    ("containers/Shared/SystemGroup/systemgroup.com.apple.lsd.iconscache/Library/Caches", 0o755),
    ("containers/Shared/SystemGroup/systemgroup.com.apple.mobilegestaltcache", 0o755),
    ("containers/Shared/SystemGroup/systemgroup.com.apple.mobilegestaltcache/Library", 0o755),
    ("containers/Shared/SystemGroup/systemgroup.com.apple.mobilegestaltcache/Library/Caches", 0o755),
    ("mobile/Library/Caches/com.apple.LaunchServices", 0o755),
    ("mobile/Library/Caches/com.apple.IconsCache", 0o755),
)

MIGRATION = {
    "LastSystemVersion": BUILD,
    "DMLastMigrationResults": {"success": True, "buildVersion": BUILD},
    "DMUserDataDisposition": {
        "SyntheticDidUpgrade": False,
        "buildVersion": BUILD,
    },
}


def write_plist(path, values):
    data = {}
    if path.exists():
        data = plistlib.loads(path.read_bytes())
    data.update(values)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(plistlib.dumps(data, fmt=plistlib.FMT_BINARY))
    os.chmod(path, 0o644 if path.parent.name == "com.apple.xpc.launchd" else 0o600)


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)

    base = Path(sys.argv[1]).resolve()
    output = Path(sys.argv[2]).resolve()
    if output.exists():
        sys.exit("Refuse to overwrite " + str(output))

    blob = base.read_bytes()
    logical, extents = packed_ramdisk.regions(blob)
    (ROOT / "build").mkdir(exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="data-ls-", dir=str(ROOT / "build")) as temporary:
        raw = Path(temporary) / "seed.raw"
        with raw.open("wb") as handle:
            handle.truncate(logical)
            for offset, data in extents:
                handle.seek(offset)
                handle.write(data)

        mount = Path(temporary) / "mount"
        mount.mkdir()
        attached = plistlib.loads(
            subprocess.check_output(
                [
                    "hdiutil",
                    "attach",
                    "-imagekey",
                    "diskimage-class=CRawDiskImage",
                    "-nobrowse",
                    "-owners",
                    "off",
                    "-mountpoint",
                    str(mount),
                    "-plist",
                    str(raw),
                ]
            )
        )
        device = attached["system-entities"][0]["dev-entry"]
        try:
            for relative, mode in DIRECTORIES:
                directory = mount / relative
                directory.mkdir(parents=True, exist_ok=True)
                os.chmod(directory, mode)

            preferences = mount / "mobile/Library/Preferences"
            write_plist(preferences / "com.apple.DataMigration.plist", MIGRATION)
            write_plist(preferences / "com.apple.migration.plist", MIGRATION)

            disable_iconservices = {"com.apple.iconservices.iconservicesagent": True}
            launchd = mount / "db/com.apple.xpc.launchd"
            write_plist(launchd / "disabled.plist", disable_iconservices)
            write_plist(launchd / "disabled.501.plist", disable_iconservices)

            for relative, _ in DIRECTORIES:
                if not (mount / relative).is_dir():
                    sys.exit("Missing postcondition directory " + relative)
            for name in (
                "com.apple.DataMigration.plist",
                "com.apple.migration.plist",
            ):
                values = plistlib.loads((preferences / name).read_bytes())
                if values.get("LastSystemVersion") != BUILD:
                    sys.exit("Invalid postcondition " + name)
            for name in ("disabled.plist", "disabled.501.plist"):
                values = plistlib.loads((launchd / name).read_bytes())
                if values.get("com.apple.iconservices.iconservicesagent") is not True:
                    sys.exit("Invalid postcondition " + name)
        finally:
            subprocess.run(["hdiutil", "detach", device], check=True)

        if raw.read_bytes()[32:36] != b"NXSB":
            sys.exit("The edited image is no APFS container any more")
        metadata = packed_ramdisk.pack(raw, output)

    report = {
        "base": str(base),
        "base_identity": packed_ramdisk.inspect(base)[0],
        "output": metadata,
        "build": BUILD,
        "directories": [relative for relative, _ in DIRECTORIES],
        "data_migration_files": [
            "mobile/Library/Preferences/com.apple.DataMigration.plist",
            "mobile/Library/Preferences/com.apple.migration.plist",
        ],
        "launchd_disabled_files": [
            "db/com.apple.xpc.launchd/disabled.plist",
            "db/com.apple.xpc.launchd/disabled.501.plist",
        ],
        "disabled_jobs": ["com.apple.iconservices.iconservicesagent"],
    }
    output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
