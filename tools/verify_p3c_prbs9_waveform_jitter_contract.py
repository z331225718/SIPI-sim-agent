"""Verify the owner-confirmed but still non-executing PRBS9 metric contract."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs/baselines/p3c-prbs9-waveform-jitter-contract.v1.yaml"
PREFLIGHT = ROOT / "docs/baselines/p3c-prbs9-waveform-jitter-preflight.v1.yaml"
P4B = ROOT / "docs/baselines/p4b-ads-pcie-gen5-dual-ami-asset-preflight.v1.yaml"
PUBLICATION = ROOT / "docs/baselines/release-capability-publication.v1.yaml"
SCHEMA = "sipi.p3c-prbs9-waveform-jitter-contract.v1"
POLICY_SHA256 = "d045e9459d322c0d8a583683cd575ef0444ae85e39873fde27290f507c94ef03"
PERIOD_SHA256 = "4437fb3beb2fa1ca99b4177673c53fc20089ac9cf68b1adaa1e0fad14d742127"


class ContractError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ContractError("document_not_mapping")
    return value


def policy_digest(document: object) -> str:
    return hashlib.sha256(json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()


def generated_period() -> str:
    state = 0x1A5
    output: list[str] = []
    seen: set[int] = set()
    for _ in range(511):
        if state == 0 or state in seen:
            raise ContractError("prbs9_cycle_invalid")
        seen.add(state)
        output.append(str((state >> 8) & 1))
        feedback = ((state >> 8) ^ (state >> 4)) & 1
        state = ((state << 1) & 0x1FF) | feedback
    if state != 0x1A5 or len(seen) != 511:
        raise ContractError("prbs9_cycle_invalid")
    return "".join(output)


def verify_external_gates(root: Path) -> None:
    preflight = load_yaml(root / PREFLIGHT.relative_to(ROOT))
    if preflight.get("status") != "specified_preflight_only_pending_generator_reference_and_jitter_tolerance":
        raise ContractError("historical_preflight_drift")
    p4b = load_yaml(root / P4B.relative_to(ROOT))
    if p4b.get("status") != "external_only_identity_observed_worker_blocked":
        raise ContractError("p4b_runtime_admission_drift")
    publication = json.loads((root / PUBLICATION.relative_to(ROOT)).read_text(encoding="utf-8"))
    compare = next((row for row in publication.get("rows", []) if row.get("id") == "compare"), None)
    if not isinstance(compare, dict) or compare.get("acceptance_state") != "specified" or "metric_profile_semantics_not_implemented" not in compare.get("blockers", []):
        raise ContractError("release_compare_metric_gate_drift")


def verify_document(document: object, root: Path = ROOT) -> dict[str, Any]:
    if not isinstance(document, dict) or document.get("schema") != SCHEMA or policy_digest(document) != POLICY_SHA256:
        raise ContractError("metric_contract_drift")
    period = generated_period()
    if hashlib.sha256(period.encode("ascii")).hexdigest() != PERIOD_SHA256:
        raise ContractError("prbs9_period_hash_mismatch")
    if document["stimulus"]["prbs"]["period_sha256"] != PERIOD_SHA256:
        raise ContractError("prbs9_period_hash_mismatch")
    admission = document["admission"]
    if admission != {
        "metric_semantics_ready": True,
        "acceptance_ready": False,
        "promotion_eligible": False,
        "runtime_invoked": False,
        "ads_runtime_invoked": False,
        "ami_runtime_invoked": False,
        "external_reference_observed": False,
        "release_ledger_promoted": False,
    }:
        raise ContractError("admission_gate_drift")
    verify_external_gates(root)
    return {
        "schema": SCHEMA,
        "status": document["status"],
        "metric_semantics_ready": True,
        "acceptance_ready": False,
        "runtime_invoked": False,
        "external_reference_observed": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=DEFAULT)
    arguments = parser.parse_args(argv)
    try:
        result = verify_document(load_yaml(arguments.contract))
    except (OSError, ValueError, yaml.YAMLError, ContractError) as error:
        print(json.dumps({"schema": SCHEMA, "status": "rejected", "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
