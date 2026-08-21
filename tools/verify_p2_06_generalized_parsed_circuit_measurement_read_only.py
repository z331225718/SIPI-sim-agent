"""Verify the hash-bound P2-06 parsed-circuit/measurement read-only audit."""

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
RECORD = ROOT / "docs" / "baselines" / "p2-06-generalized-parsed-circuit-measurement-read-only-evidence.v1.yaml"
SCHEMA = "sipi.p2-06.generalized-parsed-circuit-measurement-read-only-evidence.v1"
PRODUCT_COMMIT = "fbec03c7cc370a630a0869329263caf0f1294731"
PRODUCT_TREE = "324298c913e1c83483f37504d73bdfa4f32f5893"
EXTERNAL_COMMIT = "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5"
EXTERNAL_TREE = "b6bde97128030d6cea0d68b2f0a35d807be8c402"
HEX = set("0123456789abcdef")
EXPECTED_PRODUCT_INVENTORY = {
    "crates/sipi-tran": "6583a013c17931cbf79e2c0cf339c781e0273537",
    "crates/sipi-tran/src/lib.rs": "faa836467dc0e83a9b831c73ce637c03b76b8f59",
    "crates/sipi-contracts": "45cb474fb470d88256788ab69f9020d273c26952",
    "crates/sipi-contracts/src/lib.rs": "54194613628aafb6cf45c626ee5612e716257dd0",
    "crates/sipi-cli/src/main.rs": "75e1a028a5c37db4120535c44b839fd79dc17e84",
    "crates/sipi-cli/tests/cli.rs": "11b6c8e7db71260c2b9135001ac1ba18cd0b2830",
    "docs/baselines/p2-03-tran-semantic-freeze.v1.yaml": "123e6a68558e1b56880e6c27b0047776bd6b8de5",
    "docs/baselines/tran-rc-pulse-acceptance.v1.yaml": "52231bb2ca98aa50a530a91dd955717f61164d2f",
    "docs/baselines/p2-06-stage-compare-coverage.v1.yaml": "4002dcc6f6f5e5736577affc09bae5b18c904b30",
}
EXPECTED_EXTERNAL_INVENTORY = {
    "native/agent-spice-sim": "273af568660c867f457366abcb43ed11163d637d",
    "native/agent-spice-sim/src/netlist.rs": "83ffa04c90fb7c523875fb93c64b1f245793bcd1",
    "native/agent-spice-sim/src/result.rs": "f13c37b9fd367c5cb66a148deecedcea7d12b794",
    "native/agent-spice-sim/src/simulator.rs": "ed5712567420013d70c39a14257e1f77004a64b4",
    "native/agent-spice-sim/src/main.rs": "a333857287fc093f2f1fa515b135fe31a2bc9eb1",
    "native/agent-spice-sim/Cargo.toml": "b56d29811d0293c878b22485523f03ea06dc2d91",
    "native/agent-spice-sim/Cargo.lock": "d23dfb66a1ce13a91316d952fb52d988c4bcb238",
    "LICENSE": "55aac2e4f8c36a978d315efb02815972579b8293",
    "LICENSE-MANIFEST.md": "2b549451fdf28b4fbaf524010efbe33c6d49b385",
    "native/AgentSpice.Engine/fixtures/rc.cir": "f9c29055902fe8aa2b268b4375a5bdbbf67df9da",
}
PRODUCT_TREE_PATHS = {"crates/sipi-tran", "crates/sipi-contracts"}
EXTERNAL_TREE_PATHS = {"native/agent-spice-sim"}


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


def _git_object_id(value: object) -> None:
    if not isinstance(value, str) or len(value) != 40 or set(value) - HEX:
        raise EvidenceError("git_object_id_invalid")


def _validate_shape(document: dict[str, Any]) -> None:
    required = {
        "schema",
        "status",
        "authority",
        "current_product",
        "external_agent_spice",
        "observed_original_semantics",
        "slice_decision",
        "non_claims",
    }
    if set(document) != required or document["schema"] != SCHEMA:
        raise EvidenceError("record_shape_invalid")
    if document["status"] != "blocked_no_current_contract_slice":
        raise EvidenceError("status_invalid")
    authority = document["authority"]
    if authority != {
        "actor": "project",
        "decision_ref": "task-t10-2026-08-21-agent-spice-p2-06-audit",
        "scope": "exact_git_object_and_clean_room_read_only_audit",
    }:
        raise EvidenceError("authority_invalid")

    current = document["current_product"]
    if not isinstance(current, dict):
        raise EvidenceError("product_identity_invalid")
    if current["commit"] != PRODUCT_COMMIT or current["tree"] != PRODUCT_TREE:
        raise EvidenceError("product_identity_invalid")
    inventory = current.get("source_inventory")
    if inventory != EXPECTED_PRODUCT_INVENTORY or current.get("source_inventory_kind") != "mixed_tree_and_blob_git_object_ids_sha1":
        raise EvidenceError("product_inventory_invalid")
    for value in inventory.values():
        _git_object_id(value)
    expected_contract = {
        "parsed_circuit": "rejected",
        "request_surface": "typed_one_node_rc_pulse_and_rc_pwl_only",
        "measurement_semantics": "not_implemented",
        "result_surface": "time_axis_voltage_in_voltage_out_only",
        "generic_spice_expansion": "prohibited",
    }
    if current.get("contract_observation") != expected_contract:
        raise EvidenceError("contract_observation_invalid")

    external = document["external_agent_spice"]
    if not isinstance(external, dict):
        raise EvidenceError("external_identity_invalid")
    if external.get("commit") != EXTERNAL_COMMIT or external.get("tree") != EXTERNAL_TREE:
        raise EvidenceError("external_identity_invalid")
    external_inventory = external.get("source_inventory")
    if external_inventory != EXPECTED_EXTERNAL_INVENTORY or external.get("source_inventory_kind") != "mixed_tree_and_blob_git_object_ids_sha1":
        raise EvidenceError("external_inventory_invalid")
    for value in external_inventory.values():
        _git_object_id(value)
    fixture_sha = external.get("fixture_content_sha256")
    if fixture_sha != {"native/AgentSpice.Engine/fixtures/rc.cir": "bcdbd81a40dde01f0e72a8c36be928b6a7325fabbc25f83f72073757154dcefc"}:
        raise EvidenceError("fixture_identity_invalid")
    license_boundary = external.get("license_boundary")
    if license_boundary != {
        "crate_declared_license": "MIT",
        "project_license": "MIT",
        "source_classification": "authorized_private",
        "reference_fixture_classification": "authorized_private",
        "product_use": "comparator_reference_only",
        "source_reuse_in_product": "prohibited_by_current_clean_room_boundary",
        "license_note": "MIT evidence is recorded, but it does not replace the current product contract or clean-room boundary decision.",
    }:
        raise EvidenceError("license_boundary_invalid")

    semantics = document["observed_original_semantics"]
    if not isinstance(semantics, dict) or set(semantics) != {"parsed_circuit", "measurements", "cli_result_path"}:
        raise EvidenceError("semantics_shape_invalid")
    parsed = semantics["parsed_circuit"]
    if parsed.get("type") != "generic_netlist_deck" or parsed.get("product_admission") != "not_admitted":
        raise EvidenceError("parser_semantics_invalid")
    measurements = semantics["measurements"]
    if measurements.get("result_type") != "result.rs:22 MeasurementResult" or measurements.get("product_admission") != "not_admitted":
        raise EvidenceError("measurement_semantics_invalid")
    cli = semantics["cli_result_path"]
    if cli.get("parser_call") != "main.rs:207 Deck::parse_file" or cli.get("json_output") != "main.rs:255 output::write_json; main.rs:268 measurement field":
        raise EvidenceError("cli_semantics_invalid")

    decision = document["slice_decision"]
    if decision.get("selected") != "none" or decision.get("implementation_status") != "read_only_audit_no_product_api":
        raise EvidenceError("slice_decision_invalid")
    if not isinstance(decision.get("reason"), list) or not decision["reason"]:
        raise EvidenceError("slice_reason_invalid")
    if not isinstance(decision.get("owner_decisions_required_before_any_future_slice"), list) or not decision["owner_decisions_required_before_any_future_slice"]:
        raise EvidenceError("owner_inputs_invalid")
    non_claims = document["non_claims"]
    if not isinstance(non_claims, list) or not non_claims or any(not isinstance(item, str) for item in non_claims):
        raise EvidenceError("non_claims_invalid")


def _verify_objects(document: dict[str, Any], external_root: Path | None) -> None:
    product = document["current_product"]
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
    external = document["external_agent_spice"]
    _git(external_root, "cat-file", "-e", f"{EXTERNAL_COMMIT}^{{commit}}")
    if _git(external_root, "rev-parse", f"{EXTERNAL_COMMIT}^{{tree}}") != EXTERNAL_TREE:
        raise EvidenceError("external_tree_drift")
    for path, expected in external["source_inventory"].items():
        object_name = f"{EXTERNAL_COMMIT}:{path}"
        expected_type = "tree" if path in EXTERNAL_TREE_PATHS else "blob"
        if _git(external_root, "cat-file", "-t", object_name) != expected_type or _git(external_root, "rev-parse", object_name) != expected:
            raise EvidenceError(f"external_source_drift:{path}")


def verify_document(document: dict[str, Any]) -> dict[str, Any]:
    _validate_shape(document)
    return {
        "valid": True,
        "implementation": "none",
        "publication": "blocked",
        "external_source_verified": False,
    }


def verify(external_root: Path | None = None) -> dict[str, Any]:
    document = _load(RECORD)
    result = verify_document(document)
    _verify_objects(document, external_root)
    result["external_source_verified"] = external_root is not None
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--agent-spice-root",
        type=Path,
        help="optional clean Agent-Spice Git repository root for external object verification",
    )
    arguments = parser.parse_args()
    try:
        print(json.dumps({"schema": SCHEMA, **verify(arguments.agent_spice_root)}, sort_keys=True))
        return 0
    except (EvidenceError, OSError, subprocess.SubprocessError) as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
