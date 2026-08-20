"""Verify the P0/P1 foundation governance verifier set is present.

P1 exit criteria require the product boundary, clean-room register,
license preflight, native source map, and acceptance profiles verifiers
to stay runnable and consistent. This gate fails closed if any of the
five foundation verifiers disappears from the tools tree.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.p1-foundation.gate-coverage.v1"

FOUNDATION_VERIFIERS = {
    "product_boundary": "tools/verify_product_boundary.py",
    "clean_room_register": "tools/verify_clean_room_register.py",
    "release_license_preflight": "tools/verify_release_license_preflight.py",
    "rust_candidate_source_map": "tools/verify_rust_candidate_source_map.py",
    "acceptance_profiles": "tools/verify_acceptance_profiles.py",
}


class FoundationError(RuntimeError):
    pass


def git_tracked(relative: str) -> bool:
    completed = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "--error-unmatch", "--", relative],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=60,
    )
    return completed.returncode == 0


def validate(root: Path = ROOT) -> dict[str, Any]:
    if not isinstance(FOUNDATION_VERIFIERS, dict) or not FOUNDATION_VERIFIERS:
        raise FoundationError("foundation_map_invalid")
    for name, relative in sorted(FOUNDATION_VERIFIERS.items()):
        if not (root / relative).is_file():
            raise FoundationError(f"verifier_missing:{name}:{relative}")
    return {"valid": True, "verifiers": len(FOUNDATION_VERIFIERS)}


def main() -> int:
    parser = argparse.ArgumentParser()
    arguments = parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except FoundationError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
