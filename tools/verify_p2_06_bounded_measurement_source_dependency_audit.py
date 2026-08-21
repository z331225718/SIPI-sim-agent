"""Verify the hash-bound P2-06 bounded-measurement dependency audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "docs" / "baselines" / "p2-06-bounded-measurement-source-dependency-audit.v1.yaml"
SCHEMA = "sipi.p2-06.bounded-measurement-source-dependency-audit.v1"
PRODUCT_COMMIT = "b6071779d8164e685d15ddf45c19dcb6b2553c78"
PRODUCT_TREE = "5f4859d40e9cfedb4445c0cc17e3bd4b1dfecdaa"
EXTERNAL_COMMIT = "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5"
EXTERNAL_TREE = "b6bde97128030d6cea0d68b2f0a35d807be8c402"
HEX = set("0123456789abcdef")
PRODUCT_TREE_PATHS = {"crates/sipi-tran"}

PRODUCT_INVENTORY = {
    "crates/sipi-tran": "6583a013c17931cbf79e2c0cf339c781e0273537",
    "crates/sipi-tran/src/lib.rs": "faa836467dc0e83a9b831c73ce637c03b76b8f59",
    "crates/sipi-tran/Cargo.toml": "972d8ef4c5a49da67d9dded266e0b19037cece86",
    "crates/sipi-contracts/src/lib.rs": "54194613628aafb6cf45c626ee5612e716257dd0",
    "crates/sipi-contracts/Cargo.toml": "ed26bad2d79e4631ad90f3dc4acb1c891c05187e",
    "crates/sipi-cli/src/main.rs": "75e1a028a5c37db4120535c44b839fd79dc17e84",
    "crates/sipi-types/src/lib.rs": "fdd1361f425c126549f2efcccd32c0977c1fc332",
    "docs/baselines/p2-03-tran-semantic-freeze.v1.yaml": "123e6a68558e1b56880e6c27b0047776bd6b8de5",
    "docs/baselines/p2-06-stage-compare-coverage.v1.yaml": "4002dcc6f6f5e5736577affc09bae5b18c904b30",
}
EXTERNAL_INVENTORY = {
    "native/agent-spice-sim/src/netlist.rs": "83ffa04c90fb7c523875fb93c64b1f245793bcd1",
    "native/agent-spice-sim/src/simulator.rs": "ed5712567420013d70c39a14257e1f77004a64b4",
    "native/agent-spice-sim/src/result.rs": "f13c37b9fd367c5cb66a148deecedcea7d12b794",
    "native/agent-spice-sim/src/main.rs": "a333857287fc093f2f1fa515b135fe31a2bc9eb1",
    "native/agent-spice-sim/Cargo.toml": "b56d29811d0293c878b22485523f03ea06dc2d91",
    "native/agent-spice-sim/Cargo.lock": "d23dfb66a1ce13a91316d952fb52d988c4bcb238",
}
EXTERNAL_DIRECT_DEPENDENCIES = ["faer", "num-complex", "serde", "serde_json", "thiserror", "vecfit"]
PARSER_MEASUREMENT_GRAPH = {
    "deck_entry": "netlist.rs:773 Deck::parse_file",
    "measurement_types": [
        "netlist.rs:526 MeasurementQuantity",
        "netlist.rs:535 MeasurementTarget",
        "netlist.rs:553 MeasurementOperation",
        "netlist.rs:623 Measurement",
    ],
    "measurement_parse": [
        "netlist.rs:2291 Parser::parse_measurement",
        "netlist.rs:2619 parse_measurement_target",
        "netlist.rs:2674 parse_measurement_event",
    ],
    "measurement_evaluation": [
        "simulator.rs:378 evaluate_measurements",
        "simulator.rs:505 measurement_samples",
        "simulator.rs:579 measurement_value",
        "simulator.rs:650 interpolate_measurement",
        "simulator.rs:712 measurement_window",
        "simulator.rs:738 integrate_measurement",
    ],
    "result_types": [
        "result.rs:22 MeasurementResult",
        "result.rs:52 SimulationResult.measurements",
    ],
    "cli_path": [
        "main.rs:207 Deck::parse_file",
        "main.rs:231 retain_points includes measurements",
        "main.rs:255/268 JSON output includes measurements",
    ],
}
CANDIDATE_ORIGINAL_SEMANTICS = [
    "parser_declares_analysis_name_target_and_optional_from_to_window",
    "target_resolution_supports_node_voltage_and_branch_current_quantities",
    "analysis_points_are_selected_and_sorted",
    "window_endpoints_are_interpolated_when_not_sample_points",
    "result_carries_analysis_name_and_value",
]
CANDIDATE_PRODUCT_GAP = [
    "no measurement request field or schema exists",
    "no measurement result field or schema exists",
    "product retains requested output samples, not the original engine point set",
    "interpolation is explicitly not_implemented",
    "no owner-approved measurement error taxonomy or tolerance/compare contract exists",
]
OWNER_INPUTS = [
    "measurement request/result schema and naming rules",
    "fixed V(out) operation and window endpoint policy",
    "point-set and interpolation policy for measurements",
    "finite/error behavior and comparison tolerance",
    "artifact/provenance/publication binding for a scalar result",
]
NO_IMPLEMENTATION_REASONS = [
    "adding MAX even for V(out) changes the frozen measurement_semantics field",
    "copying original parser/evaluator would introduce generic netlist and source reuse",
    "a private helper without a contract would not satisfy P2-06 stage compare or production semantics",
]


class EvidenceError(ValueError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
        value = yaml.safe_load(raw) if yaml is not None else json.loads(raw)
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
        raise EvidenceError("record_invalid") from error
    if not isinstance(value, dict):
        raise EvidenceError("record_invalid")
    return value


def _git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        check=False,
        timeout=60,
    )
    if result.returncode:
        raise EvidenceError("git_object_missing")
    return result.stdout.strip()


def _object_id(value: object) -> None:
    if not isinstance(value, str) or len(value) != 40 or set(value) - HEX:
        raise EvidenceError("git_object_id_invalid")


def _inventory(value: object, expected: dict[str, str], *, field: str) -> dict[str, str]:
    if value != expected:
        raise EvidenceError(f"{field}_inventory_invalid")
    for item in expected.values():
        _object_id(item)
    return expected


def _validate_shape(document: dict[str, Any]) -> None:
    required = {
        "schema",
        "status",
        "authority",
        "product_baseline",
        "pinned_original_project",
        "candidate_slice",
        "minimum_missing_semantics",
        "non_claims",
    }
    if set(document) != required or document["schema"] != SCHEMA:
        raise EvidenceError("record_shape_invalid")
    if document["status"] != "blocked_missing_minimum_semantics":
        raise EvidenceError("status_invalid")
    if document["authority"] != {
        "actor": "project",
        "decision_ref": "task-t10-2026-08-21-agent-spice-p2-06-second-round",
        "scope": "pinned_original_source_dependency_and_bounded_measurement_slice_audit",
    }:
        raise EvidenceError("authority_invalid")

    product = document["product_baseline"]
    if not isinstance(product, dict) or product.get("commit") != PRODUCT_COMMIT or product.get("tree") != PRODUCT_TREE:
        raise EvidenceError("product_identity_invalid")
    if product.get("source_inventory_kind") != "mixed_tree_and_blob_git_object_ids_sha1":
        raise EvidenceError("product_inventory_kind_invalid")
    _inventory(product.get("source_inventory"), PRODUCT_INVENTORY, field="product")
    if product.get("current_contract") != {
        "request_surface": "typed_one_node_rc_pulse_and_rc_pwl_only",
        "result_surface": "requested_time_axis_voltage_in_voltage_out_only",
        "parsed_circuit": "rejected",
        "measurement_semantics": "not_implemented",
        "interpolation": "not_implemented",
        "netlist_text": "not_accepted",
        "current_sipi_tran_dependencies": ["sipi-runtime", "sipi-types"],
    }:
        raise EvidenceError("product_contract_invalid")

    external = document["pinned_original_project"]
    if not isinstance(external, dict) or external.get("commit") != EXTERNAL_COMMIT or external.get("tree") != EXTERNAL_TREE:
        raise EvidenceError("external_identity_invalid")
    if external.get("source_inventory_kind") != "mixed_tree_and_blob_git_object_ids_sha1":
        raise EvidenceError("external_inventory_kind_invalid")
    _inventory(external.get("source_inventory"), EXTERNAL_INVENTORY, field="external")
    if external.get("direct_dependencies_from_manifest") != EXTERNAL_DIRECT_DEPENDENCIES:
        raise EvidenceError("dependency_inventory_invalid")
    if external.get("parser_measurement_graph") != PARSER_MEASUREMENT_GRAPH:
        raise EvidenceError("parser_measurement_graph_invalid")

    candidate = document["candidate_slice"]
    if not isinstance(candidate, dict) or candidate.get("name") != "bounded_tran_max_vout" or candidate.get("source_semantics") != "original_measurement_operation_max" or candidate.get("disposition") != "rejected_without_owner_decision":
        raise EvidenceError("candidate_invalid")
    if candidate.get("proposed_restriction") != {
        "analysis": "tran",
        "target": "V(out)",
        "window": "whole_reported_axis_only",
        "output": "one_named_scalar",
    }:
        raise EvidenceError("candidate_restriction_invalid")
    if candidate.get("original_required_semantics") != CANDIDATE_ORIGINAL_SEMANTICS:
        raise EvidenceError("candidate_original_semantics_invalid")
    if candidate.get("product_gap") != CANDIDATE_PRODUCT_GAP:
        raise EvidenceError("candidate_product_gap_invalid")

    missing = document["minimum_missing_semantics"]
    if not isinstance(missing, dict) or missing.get("required_owner_inputs") != OWNER_INPUTS:
        raise EvidenceError("missing_semantics_invalid")
    if missing.get("reason_no_implementation") != NO_IMPLEMENTATION_REASONS:
        raise EvidenceError("no_implementation_reason_invalid")
    non_claims = document["non_claims"]
    if not isinstance(non_claims, list) or len(non_claims) != 4 or any(not isinstance(item, str) for item in non_claims):
        raise EvidenceError("non_claims_invalid")


def _verify_objects(document: dict[str, Any], external_root: Path | None) -> None:
    product = document["product_baseline"]
    _git(ROOT, "cat-file", "-e", f"{PRODUCT_COMMIT}^{{commit}}")
    if _git(ROOT, "rev-parse", f"{PRODUCT_COMMIT}^{{tree}}") != PRODUCT_TREE:
        raise EvidenceError("product_tree_drift")
    for path, expected in product["source_inventory"].items():
        object_name = f"{PRODUCT_COMMIT}:{path}"
        expected_type = "tree" if path in PRODUCT_TREE_PATHS else "blob"
        if _git(ROOT, "cat-file", "-t", object_name) != expected_type or _git(ROOT, "rev-parse", object_name) != expected:
            raise EvidenceError(f"product_source_drift:{path}")
    if external_root is None:
        return
    external = document["pinned_original_project"]
    _git(external_root, "cat-file", "-e", f"{EXTERNAL_COMMIT}^{{commit}}")
    if _git(external_root, "rev-parse", f"{EXTERNAL_COMMIT}^{{tree}}") != EXTERNAL_TREE:
        raise EvidenceError("external_tree_drift")
    for path, expected in external["source_inventory"].items():
        object_name = f"{EXTERNAL_COMMIT}:{path}"
        if _git(external_root, "cat-file", "-t", object_name) != "blob" or _git(external_root, "rev-parse", object_name) != expected:
            raise EvidenceError(f"external_source_drift:{path}")


def verify_document(document: dict[str, Any]) -> dict[str, Any]:
    _validate_shape(document)
    return {"valid": True, "implementation": "none", "external_source_verified": False}


def verify(external_root: Path | None = None) -> dict[str, Any]:
    document = _load(RECORD)
    result = verify_document(document)
    _verify_objects(document, external_root)
    result["external_source_verified"] = external_root is not None
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent-spice-root", type=Path, help="optional Agent-Spice Git root for external object verification")
    arguments = parser.parse_args()
    try:
        print(json.dumps({"schema": SCHEMA, **verify(arguments.agent_spice_root)}, sort_keys=True))
        return 0
    except (EvidenceError, OSError, subprocess.SubprocessError) as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
