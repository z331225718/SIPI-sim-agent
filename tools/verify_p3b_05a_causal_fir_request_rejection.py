"""Verify the P3B-05a causal-FIR request rejection surface.

P3B-05a requires `sipi.link.causal-fir-request.v1` to fail closed on
seed, PRBS, noise, jitter, DFE/CDR/BER, and non-bypass stages: the wire
types expose only DirectLaunch TX and Bypass CTLE/FFE, every wire struct
denies unknown fields, and the schema id is fixed. This gate fails closed
if any of those invariants drift (e.g. a stage enum gains a non-bypass
variant, a new field is added without rejection, or the schema id
changes).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.p3b-05a.causal-fir-request-rejection.v1"

CONTRACTS = "crates/sipi-contracts/src/lib.rs"
REQUEST_SCHEMA_ID = "sipi.link.causal-fir-request.v1"

EXPECTED_STAGE_VARIANTS = frozenset({
    "DirectLaunch",
    "Bypass",
})

FORBIDDEN_FEATURE_TOKENS = frozenset({
    "seed",
    "prbs",
    "noise",
    "jitter",
    "dfe",
    "cdr",
    "ber",
    "training",
    "equalizer",
    "ctle_taps",
    "ffe_taps",
})

WIRE_STRUCT_PATTERNS = (
    r"enum WireTxStageV1\s*\{[^}]*\}",
    r"enum WireCtleStageV1\s*\{[^}]*\}",
    r"enum WireFfeStageV1\s*\{[^}]*\}",
    r"enum WireLinkChannelV1\s*\{[^}]*\}",
    r"struct WireLinkCausalFirRequestV1\s*\{[^}]*\}",
    r"struct WireRxStagesV1\s*\{[^}]*\}",
    r"struct WireLinkExecutionLimitsV1\s*\{[^}]*\}",
    r"struct WireUniformTimebaseV1\s*\{[^}]*\}",
)


class RejectionSurfaceError(RuntimeError):
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
        raise RejectionSurfaceError("source_read_failed") from error


def extract_enum_variants(body: str) -> set[str]:
    variants: set[str] = set()
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("//") or stripped.startswith("#"):
            continue
        name = re.match(r"([A-Za-z_][A-Za-z0-9_]*)", stripped)
        if name is not None:
            variants.add(name.group(1))
    return variants


def validate(root: Path = ROOT) -> dict[str, Any]:
    if not git_tracked(CONTRACTS) or not (root / CONTRACTS).is_file():
        raise RejectionSurfaceError("contracts_source_missing")
    text = read_text(CONTRACTS)

    # 1. Schema id must stay fixed and exported.
    if not re.search(r"LINK_CAUSAL_FIR_REQUEST_SCHEMA\s*:\s*&str\s*=\s*\"sipi\.link\.causal-fir-request\.v1\"", text):
        raise RejectionSurfaceError("request_schema_id_drift")

    # 2. Stage enums must contain only identity/bypass variants.
    for pattern in (r"enum WireTxStageV1\s*\{", r"enum WireCtleStageV1\s*\{", r"enum WireFfeStageV1\s*\{"):
        match = re.search(pattern + r"(.*?)\n\}", text, re.DOTALL)
        if match is None:
            raise RejectionSurfaceError(f"stage_enum_missing:{pattern}")
        variants = extract_enum_variants(match.group(1))
        if not variants or not variants <= EXPECTED_STAGE_VARIANTS:
            raise RejectionSurfaceError(f"stage_variant_added:{variants}")

    # 3. Every wire struct/enum must deny unknown fields.
    for pattern in WIRE_STRUCT_PATTERNS:
        match = re.search(pattern, text, re.DOTALL)
        if match is None:
            raise RejectionSurfaceError(f"wire_type_missing:{pattern}")
        block_start = match.start()
        preceding = text[max(0, block_start - 200):block_start]
        if "deny_unknown_fields" not in preceding and "deny_unknown_fields" not in match.group(0):
            raise RejectionSurfaceError(f"wire_type_missing_deny_unknown:{pattern}")

    # 4. Forbidden feature tokens must not appear as request fields.
    request_body = re.search(r"struct WireLinkCausalFirRequestV1\s*\{(.*?)\n\}", text, re.DOTALL)
    if request_body is None:
        raise RejectionSurfaceError("request_struct_missing")
    request_fields = request_body.group(1).lower()
    for token in FORBIDDEN_FEATURE_TOKENS:
        if re.search(rf"\b{re.escape(token)}\b", request_fields):
            raise RejectionSurfaceError(f"forbidden_feature_field_added:{token}")

    return {"valid": True, "stage_variants": len(EXPECTED_STAGE_VARIANTS)}


def main() -> int:
    parser = argparse.ArgumentParser()
    arguments = parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except RejectionSurfaceError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
