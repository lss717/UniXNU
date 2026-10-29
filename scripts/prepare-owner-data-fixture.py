#!/usr/bin/env python3
"""Create a small mutable offline APFS Data seed from the supplied OS's initial var tree."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import stat
import subprocess

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, default=ROOT / 'build/owner-data-fixture')
parser.add_argument('--skeleton', action='store_true', help='Create an empty APFS Data skeleton (CI bring-up; no OS var copy)')
parser.add_argument('--size-mib', type=int, default=96, help='Skeleton APFS container size in MiB')
args = parser.parse_args()
fixture = args.output.resolve()
image = fixture / 'owner-data-32.cdr'
if image.exists():
    raise SystemExit('Refuse to overwrite an existing Data seed')
if args.skeleton:
    fixture.mkdir(parents=True, exist_ok=True)
    subprocess.run(['hdiutil', 'create', '-size', f'{args.size_mib}m', '-layout', 'NONE', '-fs', 'APFS',
                    '-volname', 'OwnerData', '-type', 'UDTO', str(image)], check=True)
    target = fixture / 'mount'
    target.mkdir(exist_ok=True)
    attached = plistlib.loads(subprocess.check_output(['hdiutil', 'attach', '-nobrowse', '-owners', 'off',
                                                      '-mountpoint', str(target), '-plist', str(image)]))
    device = attached['system-entities'][0]['dev-entry']
    volume_uuid = None
    try:
        volumes = [e for e in attached['system-entities'] if e.get('mount-point') == str(target)]
        if len(volumes) != 1:
            raise SystemExit('Require exactly one newly formatted scratch volume')
        info = plistlib.loads(subprocess.check_output(['diskutil', 'info', '-plist', volumes[0]['dev-entry']]))
        volume_uuid = info['VolumeUUID']
        # The first launchd boot only needs the writable skeleton. It creates
        # launchd.db and the per-service state below these directories itself.
        for name in ('audit', 'buddy', 'datamigrator', 'db', 'db/com.apple.xpc.launchd',
                     'db/dslocal/nodes/Default/users', 'db/dslocal/nodes/Default/groups',
                     'db/dslocal/nodes/Default/config', 'dextcores', 'empty', 'folders',
                     'hardware', 'installd', 'keybags', 'keybags/backup', 'Library',
                     'log', 'log/com.apple.xpc.launchd', 'mobile', 'mobile/Containers',
                     'mobile/Documents', 'mobile/Library', 'mobile/Library/Caches',
                     'mobile/Library/Logs', 'mobile/Library/Preferences', 'mobile/Media',
                     'mobile/tmp', 'networkd', 'preferences', 'preferences/Logging',
                     'preboot', 'root', 'run', 'tmp', 'cores', 'containers', 'containers/Data',
                     'containers/Data/Application', 'containers/Data/System',
                     'containers/Shared', 'containers/Shared/SystemGroup', 'PersonaVolumes'):
            (target / name).mkdir(parents=True, exist_ok=True)
        os.chmod(target / 'tmp', 0o1777)
    finally:
        subprocess.run(['hdiutil', 'detach', device], check=True, capture_output=True)
        shutil.rmtree(target, ignore_errors=True)
    data = image.read_bytes()
    if data[32:36] != b'NXSB':
        raise SystemExit('Host formatting did not produce an APFS container')
    report = dict(volume_uuid=volume_uuid, bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                  seed='Empty APFS Data skeleton for launchd bring-up; directories only',
                  owner_keybag_created=False, os_inputs_modified=False, production_storage_qualified=False)
    (fixture / 'seed.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    raise SystemExit(0)
source = ROOT / '.cache/firmware/target-volumes/os-mount'
if hashlib.sha256((source / 'sbin/launchd').read_bytes()).hexdigest() != '8cec9a3c44a443b08e977ccc5d577850316ad428c575dc01f09b018dbd5b6a25':
    raise SystemExit('Require the unchanged supplied original OS mount')
fixture.mkdir(parents=True, exist_ok=True)
subprocess.run(['hdiutil', 'create', '-size', '32m', '-layout', 'NONE', '-fs', 'APFS',
                '-volname', 'OwnerData', '-type', 'UDTO', str(image)], check=True)
target = fixture / 'mount'
target.mkdir(exist_ok=True)
attached = plistlib.loads(subprocess.check_output(['hdiutil', 'attach', '-nobrowse', '-owners', 'off',
                                                  '-mountpoint', str(target), '-plist', str(image)]))
device = attached['system-entities'][0]['dev-entry']
volume_uuid = None
count = total = 0
source = source / 'private/var'
try:
    volumes = [e for e in attached['system-entities'] if e.get('mount-point') == str(target)]
    if len(volumes) != 1:
        raise SystemExit('Require exactly one newly formatted scratch volume')
    info = plistlib.loads(subprocess.check_output(['diskutil', 'info', '-plist', volumes[0]['dev-entry']]))
    volume_uuid = info['VolumeUUID']
    for current, dirs, files in os.walk(source, followlinks=False):
        dirs[:] = [name for name in dirs if name != 'staged_system_apps']
        dest = target / Path(current).relative_to(source)
        dest.mkdir(exist_ok=True)
        os.chmod(dest, stat.S_IMODE(Path(current).stat().st_mode))
        for name in list(dirs) + files:
            src, dst = Path(current) / name, dest / name
            if src.is_symlink():
                os.symlink(os.readlink(src), dst)
                if name in dirs:
                    dirs.remove(name)
            elif src.is_file():
                shutil.copy2(src, dst)
                count += 1
                total += src.stat().st_size
    for name in ('keybags', 'mobile/tmp', 'tmp', 'run'):
        (target / name).mkdir(parents=True, exist_ok=True)
    os.chmod(target / 'tmp', 0o1777)
finally:
    subprocess.run(['hdiutil', 'detach', device], check=True)
data = image.read_bytes()
if len(data) != 32 * 1024**2 or data[32:36] != b'NXSB':
    raise SystemExit('Host formatting did not produce the requested raw APFS container')
report = dict(volume_uuid=volume_uuid, bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), source_regular_files=count,
              source_regular_bytes=total, guest_mutable=True, initial_seed_signature_verified=False,
              seed='Original private/var excluding staged_system_apps; symlinks preserved; runtime directories added',
              owner_keybag_created=False, os_inputs_modified=False, production_storage_qualified=False)
(fixture / 'seed.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
