"""Verify the narrowly authorized ADS 100-as source-edge amendment."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs/baselines/p3c-prbs9-waveform-jitter-contract.v2.yaml"
V1 = ROOT / "docs/baselines/p3c-prbs9-waveform-jitter-contract.v1.yaml"
P4B = ROOT / "docs/baselines/p4b-ads-pcie-gen5-dual-ami-asset-preflight.v1.yaml"
PUBLICATION = ROOT / "docs/baselines/release-capability-publication.v1.yaml"
SCHEMA = "sipi.p3c-prbs9-waveform-jitter-contract.v2"
V1_SHA256 = "7c55086abe681e4a4a64aec15379eb839fc3514a94b2f4b3d920ec9c9f391751"
POLICY_SHA256 = "32a6ea9608260a605541f7af56d1388442234ae7148eaf139e781f006194d4aa"
TRANSITION = {
    "component_semantics": "ads_prbssrc",
    "edge_shape_code": 0,
    "rise_time_seconds": 1.0e-16,
    "fall_time_seconds": 1.0e-16,
    "transition_reference": 0.0,
    "transition_starts_at": "symbol_boundary",
}


class ContractV2Error(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ContractV2Error("document_not_mapping")
    return value


def digest(document: object) -> str:
    return hashlib.sha256(json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def invariant_projection_v1(document: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(document)
    for key in ("schema", "status", "authority"):
        value.pop(key, None)
    value["stimulus"].pop("modulation", None)
    value["timebase"].pop("waveform_update", None)
    return value


def invariant_projection_v2(document: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(document)
    for key in ("schema", "status", "supersedes", "authority"):
        value.pop(key, None)
    value["stimulus"].pop("modulation", None)
    value["stimulus"].pop("transition", None)
    return value


def verify_external_gates(root: Path) -> None:
    p4b = load_yaml(root / P4B.relative_to(ROOT))
    if p4b.get("status") != "external_only_identity_observed_worker_blocked":
        raise ContractV2Error("p4b_runtime_admission_drift")
    publication = json.loads((root / PUBLICATION.relative_to(ROOT)).read_text(encoding="utf-8"))
    compare = next((row for row in publication.get("rows", []) if row.get("id") == "compare"), None)
    if not isinstance(compare, dict) or compare.get("acceptance_state") != "specified" or "metric_profile_semantics_not_implemented" not in compare.get("blockers", []):
        raise ContractV2Error("release_compare_metric_gate_drift")


def verify_document(document: object, *, root: Path = ROOT) -> dict[str, Any]:
    if not isinstance(document, dict) or document.get("schema") != SCHEMA or digest(document) != POLICY_SHA256:
        raise ContractV2Error("contract_v2_drift")
    v1 = load_yaml(root / V1.relative_to(ROOT))
    if sha256_file(root / V1.relative_to(ROOT)) != V1_SHA256:
        raise ContractV2Error("superseded_contract_source_drift")
    if document.get("status") != "specified_external_ads_100as_reference_and_accepted_receiver_pending":
        raise ContractV2Error("contract_v2_status_invalid")
    if document.get("supersedes") != {"schema": "sipi.p3c-prbs9-waveform-jitter-contract.v1", "content_sha256": V1_SHA256, "reason": "user_authorized_ads_prbssrc_finite_100as_source_edge_semantics"}:
        raise ContractV2Error("supersedes_invalid")
    if document.get("authority") != {"actor": "user", "decision_ref": "user-authorized-2026-08-12-p3c-ads-prbssrc-100as-source-edge", "scope": "metric_semantics_and_external_ads_source_edge_only_not_runtime_or_acceptance"}:
        raise ContractV2Error("authority_invalid")
    stimulus = document.get("stimulus")
    if not isinstance(stimulus, dict) or stimulus.get("modulation") != "finite_edge_nrz" or stimulus.get("transition") != TRANSITION:
        raise ContractV2Error("source_edge_semantics_invalid")
    if invariant_projection_v1(v1) != invariant_projection_v2(document):
        raise ContractV2Error("unauthorized_semantic_diff")
    admission = document.get("admission")
    if not isinstance(admission, dict) or any(admission.get(key) is not False for key in ("acceptance_ready", "promotion_eligible", "runtime_invoked", "ads_runtime_invoked", "ami_runtime_invoked", "external_reference_observed", "release_ledger_promoted")):
        raise ContractV2Error("admission_gate_drift")
    verify_external_gates(root)
    return {"schema": SCHEMA, "status": document["status"], "source_edge_seconds": TRANSITION["rise_time_seconds"], "acceptance_ready": False, "external_reference_observed": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=DEFAULT)
    arguments = parser.parse_args(argv)
    try:
        report = verify_document(load_yaml(arguments.contract))
    except (OSError, ValueError, yaml.YAMLError, ContractV2Error) as error:
        print(json.dumps({"schema": SCHEMA, "status": "rejected", "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
