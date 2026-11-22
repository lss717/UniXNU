#!/usr/bin/env python3
"""Add a prepared preboot overlay to an existing packed Data seed.

  seed-data-preboot-overlay.py BASE.dbr OVERLAY_DIR OUTPUT.dbr

The seed's APFS volume UUID is preserved. The output refuses to overwrite an
existing file and is packed again with the repository's DBRDISK1 codec.
"""

import argparse
import hashlib
import json
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "drivers/DarwinBoot/Test"))
import packed_ramdisk


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("overlay", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    base = args.base.resolve()
    overlay = args.overlay.resolve()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit("Refuse to overwrite " + str(output))
    if not base.is_file():
        raise SystemExit("Missing packed Data seed: " + str(base))
    if not (overlay / "cryptex1/current").is_dir() or not (overlay / "Cryptexes").is_dir():
        raise SystemExit("Overlay must contain cryptex1/current and Cryptexes")

    blob = base.read_bytes()
    logical, extents = packed_ramdisk.regions(blob)
    (ROOT / "build").mkdir(exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="data-preboot-", dir=ROOT / "build") as temporary:
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
            preboot = mount / "preboot"
            preboot.mkdir(parents=True, exist_ok=True)
            shutil.copytree(overlay, preboot, symlinks=True, dirs_exist_ok=True)
            required = (
                preboot / "cryptex1/current/os.dmg.root_hash",
                preboot / "cryptex1/current/os.dmg.trustcache",
                preboot / "cryptex1/current/app.dmg.root_hash",
                preboot / "cryptex1/current/app.dmg.trustcache",
            )
            missing = [str(path.relative_to(preboot)) for path in required if not path.is_file()]
            symlinks = (
                preboot / "cryptex1/current/os.dmg",
                preboot / "cryptex1/current/app.dmg",
            )
            missing += [str(path.relative_to(preboot)) for path in symlinks if not path.is_symlink()]
            missing += [name for name in ("Cryptexes/OS", "Cryptexes/App")
                        if not (preboot / name).is_dir()]
            if missing:
                raise SystemExit("Missing preboot postconditions: " + ", ".join(missing))
        finally:
            subprocess.run(["hdiutil", "detach", device], check=True)

        if raw.read_bytes()[32:36] != b"NXSB":
            raise SystemExit("Edited image is not an APFS container")
        packed = packed_ramdisk.pack(raw, output)

    report = {
        "base": str(base),
        "base_identity": packed_ramdisk.inspect(base)[0],
        "overlay": str(overlay),
        "overlay_manifest_sha256": sha256(overlay / "manifest.json"),
        "output": packed,
        "preserved_volume_uuid": True,
        "preboot_overlay_present": True,
    }
    output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
