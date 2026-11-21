#!/usr/bin/env python3
"""Validate and apply a directory's ordered patch series.

The series file lists exactly the patches to apply, one basename per line.
Blank lines and comments are ignored. Every listed patch must exist, every
patch file in the directory must be listed, and duplicate entries are errors.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


class SeriesError(Exception):
    pass


def load_series(root: Path) -> list[Path]:
    root = root.resolve()
    manifest = root / "series"
    if not manifest.is_file():
        raise SeriesError(f"missing series file: {manifest}")

    names: list[str] = []
    seen: set[str] = set()
    for line_number, raw in enumerate(manifest.read_text(encoding="utf-8").splitlines(), 1):
        name = raw.strip()
        if not name or name.startswith("#"):
            continue
        path = Path(name)
        if path.is_absolute() or path.name != name or path.suffix != ".patch":
            raise SeriesError(
                f"{manifest}:{line_number}: expected one patch basename, got {name!r}"
            )
        if name in seen:
            raise SeriesError(f"{manifest}:{line_number}: duplicate patch {name}")
        candidate = root / name
        if not candidate.is_file():
            raise SeriesError(f"{manifest}:{line_number}: missing patch {candidate}")
        seen.add(name)
        names.append(name)

    actual = {path.name for path in root.glob("*.patch") if path.is_file()}
    unlisted = sorted(actual - seen)
    if unlisted:
        raise SeriesError(
            f"{manifest}: unlisted patch files: {', '.join(unlisted)}"
        )
    return [root / name for name in names]


def run_git_apply(worktree: Path, patch: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(worktree), "apply", *arguments, str(patch)],
        text=True,
        capture_output=True,
    )


def apply_series(worktree: Path, patches: list[Path], skip_applied: bool) -> None:
    worktree = worktree.resolve()
    if not (worktree / ".git").exists():
        raise SeriesError(f"worktree is not a Git checkout: {worktree}")

    for patch in patches:
        if skip_applied:
            reverse = run_git_apply(worktree, patch, "--reverse", "--check")
            if reverse.returncode == 0:
                print(f"already applied: {patch.name}")
                continue

        check = run_git_apply(worktree, patch, "--check")
        if check.returncode:
            raise SeriesError(
                f"cannot apply {patch.name}:\n{check.stderr.strip() or check.stdout.strip()}"
            )
        applied = run_git_apply(worktree, patch)
        if applied.returncode:
            raise SeriesError(
                f"failed to apply {patch.name}:\n"
                f"{applied.stderr.strip() or applied.stdout.strip()}"
            )
        print(f"applied: {patch.name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list")
    check = subparsers.add_parser("check")
    check.add_argument("--worktree", required=True, type=Path)
    apply = subparsers.add_parser("apply")
    apply.add_argument("--worktree", required=True, type=Path)
    apply.add_argument("--skip-applied", action="store_true")
    args = parser.parse_args()

    try:
        patches = load_series(args.root)
        if args.command == "list":
            for patch in patches:
                print(patch)
        elif args.command == "check":
            for patch in patches:
                result = run_git_apply(args.worktree.resolve(), patch, "--check")
                if result.returncode:
                    raise SeriesError(
                        f"cannot apply {patch.name}:\n"
                        f"{result.stderr.strip() or result.stdout.strip()}"
                    )
        else:
            apply_series(args.worktree, patches, args.skip_applied)
    except (OSError, SeriesError) as error:
        print(f"apply-patch-series: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
