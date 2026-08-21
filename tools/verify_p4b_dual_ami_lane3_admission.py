"""Verify the serial, fail-closed P4B dual-AMI Lane 3 admission record."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/baselines/p4b-ads-pcie-gen5-dual-ami-lane3-admission.v1.yaml"
SCHEMA = "sipi.p4b-ads-pcie-gen5-dual-ami-lane3-admission.v1"
STATUS = "blocked_before_vendor_load_missing_runtime_rights_and_parameter_observation"
STAGES = [
    "asset_identity_and_rights_snapshot",
    "selected_profile_host_forwarded_parameter_subset",
    "pe_import_and_dynamic_closure",
    "isolated_worker_admission",
    "ami_init_and_get_wave",
]
BOUND_FILES = {
    "docs/baselines/p4b-ads-pcie-gen5-dual-ami-asset-preflight.v1.yaml":
        "7e9281833b13a38be8d523619afc5f4e163e330a314325e8ff3ea4f3faa13dcd",
    "docs/baselines/p4b-02-production-parameter-adapter-selection.v1.yaml":
        "cecc3921cf39bf1d531302f51c6db14b1d9007171949bd150592eafdfc695012",
    "docs/baselines/p4b-dual-ami-pe-loader-declarations.v1.yaml":
        "b9b12a4c5bb03daabc3c8172d44cefce2feabe834d9628eee9a2428f669af1ab",
    "crates/sipi-ami-worker/src/lib.rs":
        "ec918dce4d55ff348ad93cca978947df291642f4c23974f9740fedf1f75e8902",
    "docs/baselines/audits/2026-08-21-p4b-dual-ami-lane3-admission.md":
        "67d9a336a1b7174cfc84e32fcef730fe83ada2f222c948ed1aa700fafd21d111",
}
ASSETS = [
    ("ctspcie_tx_gen5.ami", "ami_text", 3280, "9272e241901d8fa749909e501c6625e508961f581e624c3f64d18a27a2408fb0"),
    ("ctspcie_rx_gen5.ami", "ami_text", 7489, "9e6206eddd32ab9d1a2ec8237d84608509131f7c3fc309c4f90f44a87f8905c1"),
    ("ctspcie_tx_win64.dll", "dll", 370045, "05d299826a9c69ae8ac3d236d88adcad5860fc7e229243f1541d1734b8ed28ea"),
    ("ctspcie_rx_win64.dll", "dll", 8850494, "88a284f0967ad332f6230a8c5e791f47e9d22a05ae6778426c35707a18a3ab63"),
]


class Lane3AdmissionError(RuntimeError):
    pass


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise Lane3AdmissionError(reason)


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise Lane3AdmissionError(f"read_failed:{path}") from error


def load_document(path: Path = EVIDENCE) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise Lane3AdmissionError(f"load_failed:{path}") from error
    _require(isinstance(value, dict), "document_not_mapping")
    return value


def verify_document(document: dict[str, Any], root: Path = ROOT) -> dict[str, Any]:
    _require(document.get("schema") == SCHEMA, "schema_invalid")
    _require(document.get("status") == STATUS, "status_invalid")
    _require(document.get("serial_stage_order") == STAGES, "serial_stage_order_invalid")
    _require(document.get("decision_scope") == {
        "owner_choices": ["D5=A", "E4=A"],
        "effect": "authorize_external_only_admission_workflow",
        "cannot_establish": [
            "third_party_runtime_rights",
            "redistribution_rights",
            "vendor_parameter_consumption",
        ],
    }, "decision_scope_invalid")

    profile = document.get("selected_profile")
    _require(isinstance(profile, dict), "selected_profile_missing")
    _require(profile.get("id") == "ads-pcie-gen5-dual-ami-windows-x64-v1", "profile_id_invalid")
    _require(profile.get("platform") == "windows-x86_64", "platform_invalid")
    _require(profile.get("composition") == "tx_and_rx_pair", "profile_composition_invalid")
    _require(profile.get("unique_profile_status") == "ready_existing_dual_binding", "profile_uniqueness_invalid")
    _require(profile.get("models") == [
        {"id": "pcie_tx", "role": "tx", "ami_root": "whistler_tx", "ami_asset": "ctspcie_tx_gen5.ami", "dll_asset": "ctspcie_tx_win64.dll"},
        {"id": "pcie_rx", "role": "rx", "ami_root": "whistler_rx", "ami_asset": "ctspcie_rx_gen5.ami", "dll_asset": "ctspcie_rx_win64.dll"},
    ], "profile_models_invalid")

    custody = document.get(STAGES[0])
    _require(isinstance(custody, dict), "custody_missing")
    _require(custody.get("status") == "identity_ready_rights_blocked", "custody_status_invalid")
    _require(custody.get("local_identity_recheck") == "exact_name_length_sha256_match", "identity_recheck_invalid")
    expected_assets = [
        {"logical_name": name, "kind": kind, "byte_length": length, "sha256": digest}
        for name, kind, length, digest in ASSETS
    ]
    _require(custody.get("assets") == expected_assets, "asset_identity_set_invalid")
    rights = custody.get("runtime_rights")
    _require(rights == {
        "status": "blocked",
        "reason": "exact_hash_bound_vendor_private_runtime_grant_not_evidenced",
        "owner_permission_is_vendor_rights": False,
        "redistribution_authorized": False,
        "assets_external_only": True,
    }, "rights_boundary_invalid")

    parameters = document.get(STAGES[1])
    _require(isinstance(parameters, dict), "parameter_stage_missing")
    _require(parameters.get("status") == "blocked_no_unique_hash_bound_runtime_parameter_observation", "parameter_status_invalid")
    adapter = parameters.get("production_adapter")
    _require(isinstance(adapter, dict), "production_adapter_missing")
    _require(adapter.get("representation") == "AmiTextBindingV1", "adapter_representation_invalid")
    _require(adapter.get("behavior") == "complete_raw_ami_text_verified_and_forwarded_to_AMI_Init", "adapter_behavior_invalid")
    _require(adapter.get("typed_parameter_helper_consumer_count") == 0, "typed_consumer_claim_invalid")
    _require(parameters.get("declared_ami_identity_is_runtime_consumption") is False, "declaration_consumption_claim")
    _require(parameters.get("selected_parameter_names") == [], "parameter_names_must_remain_empty")
    _require(parameters.get("promoted_p4b_02_helper_modules") == [], "helper_promotion_not_allowed")
    logs = parameters.get("existing_ads_log_set")
    _require(isinstance(logs, dict), "ads_log_boundary_missing")
    _require(logs.get("status") == "not_selected_as_unique_runtime_observation", "ads_log_selection_invalid")
    _require(logs.get("may_prove_at_most") == "host_forwarded_parameter_subset", "host_forwarded_wording_invalid")
    _require(logs.get("proves_dll_internal_consumption") is False, "dll_consumption_claim")

    pe = document.get(STAGES[2])
    _require(isinstance(pe, dict), "pe_stage_missing")
    _require(pe.get("status") == "static_ready_dynamic_blocked", "pe_status_invalid")
    _require(pe.get("machine") == "windows-x86_64", "pe_machine_invalid")
    _require(pe.get("exports") == ["AMI_Close", "AMI_GetWave", "AMI_Init"], "pe_exports_invalid")
    _require(pe.get("direct_import_modules") == ["kernel32.dll", "msvcrt.dll", "user32.dll"], "pe_imports_invalid")
    _require(pe.get("dynamic_dependency_closure") == "blocked_not_assessed", "dynamic_closure_claim")
    _require(pe.get("sidecar_resolution") == "blocked_not_assessed", "sidecar_claim")

    worker = document.get(STAGES[3])
    _require(isinstance(worker, dict), "worker_stage_missing")
    _require(worker.get("status") == "blocked_not_security_sandbox", "worker_status_invalid")
    _require(worker.get("bounded_process_and_artifact_mechanics") == "ready", "worker_mechanics_invalid")
    _require(worker.get("vendor_security_isolation") == "blocked", "worker_isolation_claim")
    _require(worker.get("vendor_worker_admitted") is False, "worker_admission_claim")

    runtime = document.get(STAGES[4])
    _require(runtime == {
        "status": "not_invoked_due_to_prior_gates",
        "dll_loaded": False,
        "ami_init_invoked": False,
        "ami_get_wave_invoked": False,
        "fresh_runtime_evidence": False,
    }, "runtime_noninvocation_invalid")
    stop = document.get("strict_stop")
    _require(isinstance(stop, dict), "strict_stop_missing")
    _require(stop.get("first_blocking_stage") == STAGES[0], "strict_stop_stage_invalid")
    _require(stop.get("reason") == "exact_hash_bound_vendor_private_runtime_grant_not_evidenced", "strict_stop_reason_invalid")
    required = stop.get("required_inputs")
    _require(isinstance(required, list) and len(required) == 5, "required_inputs_invalid")

    refs = [custody.get("asset_preflight"), adapter, pe.get("static_record"), worker.get("worker_source"), document.get("audit")]
    for reference in refs:
        _require(isinstance(reference, dict), "bound_reference_missing")
        relative = reference.get("path")
        digest = reference.get("sha256")
        _require(isinstance(relative, str) and BOUND_FILES.get(relative) == digest, f"bound_reference_invalid:{relative}")
        _require(_sha256(root / relative) == digest, f"bound_file_hash_drift:{relative}")

    worker_source = (root / "crates/sipi-ami-worker/src/lib.rs").read_text(encoding="utf-8")
    for token in (
        "security sandbox: its role is bounded process and artifact mechanics",
        "parse_and_bind_v1(&parameters, limits)",
        ".initialize(init, &binding, limits)",
    ):
        _require(token in worker_source, f"worker_contract_missing:{token}")

    non_claims = document.get("non_claims")
    _require(isinstance(non_claims, list) and {
        "not_vendor_runtime_rights",
        "not_typed_parameter_semantics",
        "not_dll_internal_parameter_consumption",
        "not_dynamic_dependency_closure",
        "not_security_sandbox_or_worker_admission",
        "not_ami_init_or_get_wave_evidence",
        "not_product_or_release_admission",
    } == set(non_claims), "non_claims_invalid")
    return {
        "schema": SCHEMA,
        "valid": True,
        "profile": profile["id"],
        "asset_count": len(ASSETS),
        "rights": "blocked",
        "parameter_subset": "blocked",
        "dynamic_closure": "blocked",
        "worker_admitted": False,
        "runtime_invoked": False,
    }


def verify_external_assets(document: dict[str, Any], asset_root: Path) -> None:
    _require(asset_root.is_absolute(), "asset_root_must_be_absolute")
    recorded = document[STAGES[0]]["assets"]
    for asset in recorded:
        path = asset_root / asset["logical_name"]
        _require(path.is_file() and not path.is_symlink(), f"external_asset_missing:{path.name}")
        _require(path.stat().st_size == asset["byte_length"], f"external_asset_length:{path.name}")
        _require(_sha256(path) == asset["sha256"], f"external_asset_hash:{path.name}")


def validate(root: Path = ROOT, asset_root: Path | None = None) -> dict[str, Any]:
    document = load_document(EVIDENCE if root == ROOT else root / EVIDENCE.relative_to(ROOT))
    result = verify_document(document, root)
    if asset_root is not None:
        verify_external_assets(document, asset_root)
        result["external_identity_checked"] = True
    else:
        result["external_identity_checked"] = False
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset-root", type=Path, help="absolute external ibis_ami directory")
    args = parser.parse_args()
    try:
        print(json.dumps(validate(asset_root=args.asset_root), sort_keys=True))
        return 0
    except (Lane3AdmissionError, OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
