"""Verify P3B-03 receiver self-conformance completeness.

P3B-03 requires the profile-scoped data-aided fixed-phase/fixed-training
receiver clean-room self-conformance with the erasure amendment and the
v2 delegated phase policy. P3B-03a-g delivered this (Orca audited), with
two fresh external RFM handoffs reaching
`delegated_policy_semantic_agreement_observed`. This gate fails closed if
the semantic/erasure/delegated verifiers or the publication row
disappear. P3B-04 (external replay acceptance) stays separate and open.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.p3b-03.receiver-self-conformance.v1"

SEMANTIC_VERIFIERS = {
    "semantic_approval": "tools/verify_channel_rfm_receiver_semantic_approval.py",
    "erasure_amendment": "tools/verify_channel_rfm_receiver_erasure_amendment.py",
    "delegated_phase": "tools/verify_channel_rfm_receiver_delegated_phase_amendment.py",
    "diagnostic_route": "tools/verify_p3b_03g_receiver_diagnostic_contract.py",
}
PUBLICATION = "docs/baselines/release-capability-publication.v1.yaml"


class ReceiverSelfConformanceError(RuntimeError):
    pass


def load_yaml(relative: str) -> dict[str, Any]:
    if yaml is None:
        raise ReceiverSelfConformanceError("pyyaml_unavailable")
    value = yaml.safe_load((ROOT / relative).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ReceiverSelfConformanceError("document_not_mapping")
    return value


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
    for name, relative in SEMANTIC_VERIFIERS.items():
        if not (root / relative).is_file():
            raise ReceiverSelfConformanceError(f"verifier_missing:{name}")
    publication = load_yaml(PUBLICATION)
    row = next((r for r in publication.get("rows", []) if isinstance(r, dict) and r.get("id") == "link-receiver-diagnostic"), None)
    if (
        row is None
        or row.get("command_id") != "link.receiver.run"
        or row.get("product_surface") != "available"
        or row.get("acceptance_state") != "specified"
    ):
        raise ReceiverSelfConformanceError("receiver_row_binding_invalid")
    return {"valid": True, "verifiers": len(SEMANTIC_VERIFIERS)}


def main() -> int:
    parser = argparse.ArgumentParser()
    arguments = parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except ReceiverSelfConformanceError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
