"""Verify the pending owner-semantic charter preflight for the required RFM profile."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.channel.receiver-semantic-charter.v1"
PROFILE_ID = "channel-rfm-block-2-current-drive-v1"
DECISION_REF = "user-confirmed-2026-08-10-channel-rfm-receiver"
RECEIVER_SCHEMA = "sipi.receiver-semantics.v1"
RECEIVER_SCHEMA_PATH = "crates/sipi-contracts/schemas/sipi.receiver-semantics.v1.schema.json"
PENDING = "pending_owner_approval"
PENDING_DECISIONS = {
    "product_stimulus_and_causal_link_waveform",
    "dfe_model_and_adaptation",
    "dfe_tap_order_cursor_units_and_sign",
    "cdr_detector_phase_frequency_update_lock_reset_and_cancel",
    "ber_reference_bits_polarity_alignment_threshold_ties_window_metric",
    "external_oracle_stage_scope_and_tolerances",
}


def _load(path: Path) -> dict:
    if yaml is None:
        raise RuntimeError("pyyaml is unavailable")
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("semantic charter must be a YAML object")
    return value


def _exact(value: object, keys: set[str]) -> bool:
    return isinstance(value, dict) and set(value) == keys


def verify_document(document: object, root: Path = ROOT) -> dict:
    blockers: list[str] = []
    required = {"schema", "status", "profile_id", "decision_ref", "receiver_contract", "pending_decisions", "non_claims"}
    if not _exact(document, required):
        return {"valid": False, "blockers": ["charter has unknown or missing fields"]}
    if document["schema"] != SCHEMA or document["status"] != PENDING or document["profile_id"] != PROFILE_ID or document["decision_ref"] != DECISION_REF:
        blockers.append("charter identity or pending status is invalid")
    contract = document["receiver_contract"]
    if not _exact(contract, {"schema", "schema_path", "schema_sha256"}) or contract.get("schema") != RECEIVER_SCHEMA or contract.get("schema_path") != RECEIVER_SCHEMA_PATH or not isinstance(contract.get("schema_sha256"), str) or len(contract["schema_sha256"]) != 64:
        blockers.append("receiver contract binding is invalid")
    else:
        schema_path = root / RECEIVER_SCHEMA_PATH
        if not schema_path.is_file() or hashlib.sha256(schema_path.read_bytes()).hexdigest() != contract["schema_sha256"]:
            blockers.append("receiver contract schema hash does not match")
    decisions = document["pending_decisions"]
    if not _exact(decisions, PENDING_DECISIONS) or any(value != PENDING for value in decisions.values()):
        blockers.append("all required owner decisions must remain explicitly pending")
    non_claims = document["non_claims"]
    if not isinstance(non_claims, list) or len(non_claims) < 3 or not all(isinstance(item, str) and item for item in non_claims):
        blockers.append("charter non-claims are incomplete")
    return {"valid": not blockers, "status": document.get("status"), "pending_decision_count": len(decisions) if isinstance(decisions, dict) else 0, "blockers": blockers}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--charter", type=Path, default=ROOT / "docs/baselines/channel-rfm-receiver-semantic-charter.v1.yaml")
    args = parser.parse_args()
    try:
        report = verify_document(_load(args.charter))
    except (OSError, RuntimeError) as error:
        print(json.dumps({"valid": False, "blockers": [str(error)]}, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
