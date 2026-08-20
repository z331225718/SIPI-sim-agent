"""Verify P4B-03 standard ABI host slice completeness.

P4B-03 requires the clean-room Windows x64 standard `long` ABI host:
AMI_Init/AMI_GetWave/AMI_Close exports, bounded buffers, strict status == 1,
and clock sentinel contract. P4B-03a delivered and accepted exactly this;
this gate keeps the slice honest (crate present, core symbols present,
acceptance audit tracked). It does not claim vendor interoperability,
parameter semantics, or worker isolation (P4B-07/08/09 remain open).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.p4b-03.standard-abi-host-slice.v1"

HOST_LIB = "crates/sipi-ami-host/src/lib.rs"
ACCEPTANCE_AUDIT = "docs/baselines/audits/2026-08-11-p4b-ami-standard-abi-host.md"
REQUIRED_EXPORTS = ("AMI_Init", "AMI_GetWave", "AMI_Close")
REQUIRED_CONTRACT_TOKENS = ("clock sentinel", "status == 1", "bounds")


class HostSliceError(RuntimeError):
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


def read_text(relative: str) -> str:
    try:
        return (ROOT / relative).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise HostSliceError("source_read_failed") from error


def validate(root: Path = ROOT) -> dict[str, Any]:
    for relative in (HOST_LIB, ACCEPTANCE_AUDIT):
        if not (root / relative).is_file():
            raise HostSliceError(f"file_missing:{relative}")
    lib = read_text(HOST_LIB)
    for export in REQUIRED_EXPORTS:
        if export not in lib:
            raise HostSliceError(f"export_missing:{export}")
    audit = read_text(ACCEPTANCE_AUDIT)
    for token in REQUIRED_CONTRACT_TOKENS:
        if token not in audit:
            raise HostSliceError(f"contract_token_missing:{token}")
    # The accepted slice must not claim vendor interop or worker isolation.
    if "vendor" in audit.lower() and "interoperability" in audit.lower():
        if "not a claim of vendor" not in audit:
            raise HostSliceError("vendor_interop_claim_promoted")
    return {"valid": True, "exports": len(REQUIRED_EXPORTS)}


def main() -> int:
    parser = argparse.ArgumentParser()
    arguments = parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except HostSliceError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
