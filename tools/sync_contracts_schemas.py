"""Regenerate the packaged sipi-contracts schema bundle from the authoritative source.

The repository keeps ``schemas/`` as the single source of truth and intentionally
does not commit the generated ``_schemas/`` copy.  Run this before packaging or
after editing any schema so the editable/wheel bundle stays byte-identical.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "schemas"
TARGET = ROOT / "packages" / "sipi-contracts" / "src" / "sipi_contracts" / "_schemas"


def main() -> int:
    if not SOURCE.is_dir():
        print(f"missing authoritative schemas directory: {SOURCE}", file=sys.stderr)
        return 1
    target = TARGET.resolve()
    if target != (ROOT / "packages" / "sipi-contracts" / "src" / "sipi_contracts" / "_schemas").resolve():
        print(f"refusing unexpected target: {target}", file=sys.stderr)
        return 1
    target.mkdir(parents=True, exist_ok=True)
    for child in target.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    shutil.copytree(SOURCE, target, dirs_exist_ok=True)
    print(f"synced {SOURCE.resolve()} -> {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
