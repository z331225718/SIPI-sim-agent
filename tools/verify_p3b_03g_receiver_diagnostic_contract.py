"""Verify the P3B-03g receiver diagnostic route contract invariant.

P3B-03g wires a strict caller-supplied `sipi link receiver run --stdin`
diagnostic artifact route. Its result must stay a product-owned
diagnostic: clock policy `policy_selected_not_locked`, external RFM false,
acceptance false, fixed profile id, and the data-aided delegated-ambiguity
algorithm. This gate fails closed if any of these markers drift or if
the route disappears from the command manifest.
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
SCHEMA = "sipi.p3b-03g.receiver-diagnostic-contract.v1"

CLI_MAIN = "crates/sipi-cli/src/main.rs"
CONTRACTS = "crates/sipi-contracts/src/lib.rs"

EXPECTED_MARKERS = frozenset({
    "product_owned_diagnostic",
    "policy_selected_not_locked",
    'external_rfm\\":false',
    'acceptance\\":false',
    "data_aided_fixed_training_receiver_delegated_ambiguity_v2",
})

EXPECTED_SCHEMAS = frozenset({
    "sipi.receiver.diagnostic-run-request.v1",
    "sipi.receiver.diagnostic-run-result.v1",
    "sipi.receiver.diagnostic.provenance.v1",
    "sipi.receiver.diagnostic-result.v1",
})
EXPECTED_PROFILE = "channel-rfm-block-2-current-drive-v1"


class DiagnosticContractError(RuntimeError):
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
        raise DiagnosticContractError("source_read_failed") from error


def validate(root: Path = ROOT) -> dict[str, Any]:
    for relative in (CLI_MAIN, CONTRACTS):
        if not git_tracked(relative) or not (root / relative).is_file():
            raise DiagnosticContractError(f"source_missing:{relative}")
    cli_text = read_text(CLI_MAIN)
    contracts_text = read_text(CONTRACTS)

    # 1. The route must remain wired in the command manifest.
    if not re.search(r"id:\s*\"link\.receiver\.run\"", cli_text):
        raise DiagnosticContractError("route_missing_from_manifest")
    if not re.search(r"fn\s+link_receiver_run_stdin", cli_text):
        raise DiagnosticContractError("route_handler_missing")

    # 2. Result/provenance markers must all be present in the CLI emission.
    for marker in sorted(EXPECTED_MARKERS):
        if marker not in cli_text:
            raise DiagnosticContractError(f"marker_missing:{marker}")

    # 3. Schemas must remain bound in contracts.
    for schema in sorted(EXPECTED_SCHEMAS):
        if schema not in contracts_text and schema not in cli_text:
            raise DiagnosticContractError(f"schema_missing:{schema}")

    # 4. Fixed profile id must remain bound.
    if EXPECTED_PROFILE not in contracts_text and EXPECTED_PROFILE not in cli_text:
        raise DiagnosticContractError("profile_id_missing")

    # 5. The diagnostic result must not claim lock, external RFM, or acceptance.
    if re.search(r'clock_policy":"(?!policy_selected_not_locked")', cli_text):
        raise DiagnosticContractError("clock_policy_drift")
    if re.search(r'external_rfm":true', cli_text):
        raise DiagnosticContractError("external_rfm_promoted")
    if re.search(r'acceptance":true', cli_text):
        raise DiagnosticContractError("acceptance_promoted")

    return {"valid": True, "markers": len(EXPECTED_MARKERS)}


def main() -> int:
    parser = argparse.ArgumentParser()
    arguments = parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except DiagnosticContractError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
