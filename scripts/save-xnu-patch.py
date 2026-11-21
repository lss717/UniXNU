#!/usr/bin/env python3
"""Regenerate one incremental XNU patch from the working tree: save-xnu-patch.py NAME FILE...

The result is the difference between "pinned XNU + every series entry before
NAME" and the working tree, for the named files only, written to
patches/xnu/NAME. Patches that the build applies outside the normal series
order must be reversed in the working tree first."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
XNU = ROOT / '.cache/xnu-work'
name, files = sys.argv[1], sys.argv[2:]
series_path = ROOT / 'patches/xnu/series'
series = [
    line.strip()
    for line in series_path.read_text(encoding='utf-8').splitlines()
    if line.strip() and not line.lstrip().startswith('#')
]
if name not in series:
    raise SystemExit(f'{name} is not listed in {series_path}')
earlier = [ROOT / 'patches/xnu' / item for item in series[:series.index(name)]]


def git(tmp, *args, check=True):
    return subprocess.run(['git', '-c', 'user.email=a@b', '-c', 'user.name=n', *args], cwd=tmp, check=check,
                          capture_output=True, text=True).stdout


tmp = Path(tempfile.mkdtemp(dir=ROOT / '.cache'))
try:
    git(tmp, 'init', '-q')
    for f in files:
        (tmp / f).parent.mkdir(parents=True, exist_ok=True)
        (tmp / f).write_bytes(subprocess.run(['git', 'show', 'HEAD:' + f], cwd=XNU, check=True, capture_output=True).stdout)
    git(tmp, 'add', '-A')
    git(tmp, 'commit', '-q', '-m', 'base')
    for patch in earlier:
        for f in files:
            git(tmp, 'apply', '--include=' + f, str(patch), check=False)
    git(tmp, 'add', '-A')
    git(tmp, 'commit', '-q', '-m', 'earlier', '--allow-empty')
    for f in files:
        shutil.copy(XNU / f, tmp / f)
    diff = git(tmp, 'diff', '--binary')
finally:
    shutil.rmtree(tmp)
(ROOT / 'patches/xnu' / name).write_text(diff)
print('wrote patches/xnu/%s (%d lines)' % (name, len(diff.splitlines())))
