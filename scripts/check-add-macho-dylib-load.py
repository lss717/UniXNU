#!/usr/bin/env python3
"""Static checks for add-macho-dylib-load.py."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "scripts/add-macho-dylib-load.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    text = TOOL.read_text(encoding="utf-8")
    for marker in (
        "MH_MAGIC_64 = 0xFEEDFACF",
        "LC_LOAD_DYLIB = 0x0C",
        "LC_CODE_SIGNATURE = 0x1D",
        "if kind == LC_CODE_SIGNATURE:",
        "new_header_end > section_start",
        "install name already present",
        "refusing to overwrite nonzero header padding",
        "caller must\nre-sign",
    ):
        require(marker in text, "missing safety marker: " + marker)
    for forbidden in ("subprocess", "codesign", "fastboot", "os.system"):
        require(forbidden not in text, "tool must not perform external writes: " + forbidden)
    print("Mach-O dylib load-command insertion gate: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
