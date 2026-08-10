"""Verify the bounded P4A IBIS 7.1 observation-scope candidate record."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.p4a-ibis71-behavior-scope-preflight.v1"
DEFAULT_MANIFEST = ROOT / "docs" / "baselines" / "p4a-ibis71-behavior-scope-preflight.v1.yaml"
COMMIT = "f6ba0311350fc67bd90fa13b8d578312f956d7e7"
IBS_PATH = "models/ibisami/example_rx.ibs"


class ScopeError(RuntimeError):
    pass


def _git_blob(pybert_root: Path) -> tuple[str, bytes]:
    object_name = f"{COMMIT}:{IBS_PATH}"
    oid = subprocess.run(["git", "-C", str(pybert_root), "rev-parse", object_name], capture_output=True, check=False, text=True)
    payload = subprocess.run(["git", "-C", str(pybert_root), "cat-file", "blob", object_name], capture_output=True, check=False)
    if oid.returncode != 0 or payload.returncode != 0:
        raise ScopeError("candidate_git_object_unavailable")
    return oid.stdout.strip(), payload.stdout


def _exact_keys(value: dict[str, Any], keys: set[str], reason: str) -> None:
    if set(value) != keys:
        raise ScopeError(reason)


def _contains_raw_material(value: Any) -> bool:
    if isinstance(value, str):
        forbidden = ("[IBIS Ver]", "[GND Clamp]", "[Power Clamp]", "|", "C_comp     ")
        return any(token in value for token in forbidden)
    if isinstance(value, dict):
        return any(_contains_raw_material(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_raw_material(item) for item in value)
    return False


def validate_manifest(document: dict[str, Any], pybert_root: Path | None = None) -> dict[str, Any]:
    _exact_keys(document, {"schema", "status", "promotion_eligible", "public_standard", "candidate_fact", "observation_scope", "semantic_boundary", "non_claims"}, "manifest_shape_invalid")
    if document["schema"] != SCHEMA or document["status"] != "candidate_observation_scope_preflight_passed" or document["promotion_eligible"] is not False:
        raise ScopeError("manifest_status_invalid")
    expected_standard = {"title": "I/O Buffer Information Specification", "version": "7.1", "official_source_url": "https://ibis.org/ver7.1/", "accessed_on": "2026-08-10", "evidence_status": "official_public_document_listed", "use": "observation_basis_only", "embedded_standard_text": False}
    if document["public_standard"] != expected_standard:
        raise ScopeError("public_standard_invalid")
    fact = document["candidate_fact"]
    if not isinstance(fact, dict):
        raise ScopeError("candidate_fact_invalid")
    expected_presence = {"c_comp": "present", "gnd_clamp": "present", "power_clamp": "present", "package": "present", "temperature_range": "present", "voltage_range": "present", "algorithmic_model_attachment": "present"}
    if fact.get("profile_id") != "ibis-ami-example-rx-raw-abi-v1" or fact.get("boundary") != "oracle_only" or fact.get("required") is not False or fact.get("source_repository") != "pybert-f6ba031" or fact.get("source_commit") != COMMIT or fact.get("model_selector") != "example_rx" or fact.get("model_role") != "input_model" or fact.get("structural_presence") != expected_presence or fact.get("dll_identity_status") != "blocked_declared_windows_x64_dll_identity":
        raise ScopeError("candidate_fact_scope_invalid")
    asset = fact.get("ibis_asset")
    if not isinstance(asset, dict) or set(asset) != {"path", "git_blob", "content_sha256"} or asset["path"] != IBS_PATH or len(asset["git_blob"]) != 40 or len(asset["content_sha256"]) != 64:
        raise ScopeError("candidate_asset_invalid")
    expected_scope = [
        {"id": "model_selection", "status": "candidate_fact_only"},
        {"id": "pvt_selector_presence", "status": "candidate_fact_only"},
        {"id": "c_comp_and_clamp_presence", "status": "candidate_fact_only"},
        {"id": "package_presence", "status": "candidate_fact_only"},
        {"id": "input_waveform_timebase", "status": "profile_contract_not_selected"},
        {"id": "raw_ami_waveform_clock_lifecycle", "status": "not_run_blocked_asset_identity"},
    ]
    if document["observation_scope"] != expected_scope:
        raise ScopeError("observation_scope_invalid")
    expected_boundary = {"ibis_input_electrical_behavior": "separate_future_scope", "ami_algorithmic_behavior": "separate_future_scope", "algorithmic_attachment_implies_runtime": "forbidden", "ibis_ami_implicit_composition": "forbidden", "parser_interpolation_clamp_package_pvt_semantics": "not_defined"}
    if document["semantic_boundary"] != expected_boundary:
        raise ScopeError("semantic_boundary_invalid")
    if not isinstance(document["non_claims"], list) or len(document["non_claims"]) != 4 or _contains_raw_material(document):
        raise ScopeError("raw_material_or_non_claims_invalid")
    if pybert_root is not None:
        oid, data = _git_blob(pybert_root)
        if oid != asset["git_blob"] or hashlib.sha256(data).hexdigest() != asset["content_sha256"]:
            raise ScopeError("candidate_asset_identity_mismatch")
        text = data.decode("ascii", errors="strict")
        required_markers = ("Model_type   Input", "C_comp", "[GND Clamp]", "[Power Clamp]", "[Package]", "[Temperature_Range]", "[Voltage_Range]", "[Algorithmic Model]")
        if not all(marker in text for marker in required_markers):
            raise ScopeError("candidate_structural_fact_mismatch")
    return {"schema": SCHEMA, "status": "candidate_observation_scope_preflight_passed", "profile_id": fact["profile_id"], "required": False, "black_box_status": "not_run_blocked_asset_identity", "promotion_eligible": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--pybert-root", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        document = yaml.safe_load(args.manifest.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise ScopeError("manifest_invalid")
        report = validate_manifest(document, args.pybert_root)
    except (OSError, yaml.YAMLError, ScopeError, TypeError) as error:
        report = {"schema": SCHEMA, "status": "rejected", "reason": str(error)}
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":"))
    if args.report:
        args.report.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if report["status"] == "candidate_observation_scope_preflight_passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
