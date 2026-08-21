"""Fail-closed P4B vendor AMI runtime admission preflight.

This gate composes only existing hash/structure evidence.  It deliberately
reports a blocked result: static PE imports are an observed fact, never a
substitute for dynamic dependency closure or fresh runtime evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.p4b-ads-pcie-gen5-dual-ami-runtime-preflight.v1"
DEFAULT = ROOT / "docs/baselines/p4b-ads-pcie-gen5-dual-ami-runtime-preflight.v1.yaml"
HEX64 = set("0123456789abcdef")

ASSETS = {
    "pcie-gen5-ibis": ("ibis", "pcie_gen5.ibs", "shared_input_model", 5537, "9ff15bf9a5ad685d0ad700b26287b5f50e1c6e1ff9c6808e5a0f0ef86896d665"),
    "pcie-tx-ami": ("ami_text", "ctspcie_tx_gen5.ami", "tx_parameter_text", 3280, "9272e241901d8fa749909e501c6625e508961f581e624c3f64d18a27a2408fb0"),
    "pcie-rx-ami": ("ami_text", "ctspcie_rx_gen5.ami", "rx_parameter_text", 7489, "9e6206eddd32ab9d1a2ec8237d84608509131f7c3fc309c4f90f44a87f8905c1"),
    "pcie-tx-dll": ("dll", "ctspcie_tx_win64.dll", "tx_primary_dynamic_library", 370045, "05d299826a9c69ae8ac3d236d88adcad5860fc7e229243f1541d1734b8ed28ea"),
    "pcie-rx-dll": ("dll", "ctspcie_rx_win64.dll", "rx_primary_dynamic_library", 8850494, "88a284f0967ad332f6230a8c5e791f47e9d22a05ae6778426c35707a18a3ab63"),
}
ASSET_SET_DIGEST = "7da0e7c0367e7174945eadfa1c49dc88e9cd99e5a2309b64b884721e54290bf7"
EVIDENCE = {
    "docs/baselines/p4b-ads-pcie-gen5-dual-ami-asset-preflight.v1.yaml": "7e9281833b13a38be8d523619afc5f4e163e330a314325e8ff3ea4f3faa13dcd",
    "docs/baselines/p4b-dual-ami-pe-loader-declarations.v1.yaml": "b9b12a4c5bb03daabc3c8172d44cefce2feabe834d9628eee9a2428f669af1ab",
    "docs/baselines/p4b-07-authorized-fixture-abi-observation-evidence.v1.yaml": "7d978499a925057c7f618f924d1102508a74f601ce4c3c6c9f4c460bfe1f80b8",
    "docs/baselines/audits/2026-08-11-p4b-ami-private-worker.md": "364799d23b44576ad61422ec026a8192553ff2121a533fac5940131c10e3c004",
}
NON_CLAIMS = [
    "exact identity is not third_party_rights_or_redistribution_permission",
    "static PE imports are not complete static_or_dynamic_dependency_closure",
    "static PE imports cannot substitute for fresh runtime evidence",
    "AMI text and IBIS identity are not AMI_parameter_compatibility",
    "mock worker readiness is not vendor_worker_admission",
    "prior external fixture probes are not product_runtime_or_profile_parity",
    "no vendor DLL or AMI asset is packaged_or_promoted",
]


class PreflightError(RuntimeError):
    pass


def _exact(value: Any, keys: set[str], reason: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise PreflightError(reason)
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_text(path: Path) -> str:
    return _sha256(path).lower()


def _hex64(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= HEX64


def _safe_name(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and not any(token in value for token in ("/", "\\", ":", ".."))


def _tracked_hashes(root: Path) -> set[str]:
    result = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], check=True, capture_output=True)
    return {_sha256(root / raw.decode("utf-8")) for raw in result.stdout.split(b"\0") if raw}


def _verify_evidence(root: Path, bindings: Any) -> None:
    if not isinstance(bindings, list) or len(bindings) != len(EVIDENCE):
        raise PreflightError("evidence_bindings_invalid")
    seen: set[str] = set()
    for item in bindings:
        item = _exact(item, {"id", "path", "sha256", "claim"}, "evidence_binding_fields_invalid")
        path = item["path"]
        if path in seen or path not in EVIDENCE or not _hex64(item["sha256"]):
            raise PreflightError("evidence_binding_identity_invalid")
        if item["sha256"] != EVIDENCE[path] or not (root / path).is_file() or _sha256_text(root / path) != item["sha256"]:
            raise PreflightError("evidence_binding_hash_mismatch")
        seen.add(path)
    if seen != set(EVIDENCE):
        raise PreflightError("evidence_binding_set_invalid")


def _verify_asset_identity(value: Any) -> None:
    value = _exact(value, {"status", "basis", "asset_set_digest", "assets"}, "asset_identity_fields_invalid")
    if value["status"] != "ready" or value["basis"] != "exact_logical_name_byte_length_sha256_and_existing_binding_observed":
        raise PreflightError("asset_identity_status_invalid")
    if value["asset_set_digest"] != ASSET_SET_DIGEST or not isinstance(value["assets"], list) or len(value["assets"]) != len(ASSETS):
        raise PreflightError("asset_identity_digest_invalid")
    seen: set[str] = set()
    for asset in value["assets"]:
        asset = _exact(asset, {"id", "kind", "logical_name", "byte_length", "sha256", "binding", "identity_status", "rights_status"}, "asset_identity_entry_invalid")
        asset_id = asset["id"]
        if asset_id in seen or asset_id not in ASSETS:
            raise PreflightError("asset_identity_id_invalid")
        expected = ASSETS[asset_id]
        if tuple(asset[key] for key in ("kind", "logical_name", "binding", "byte_length", "sha256")) != expected:
            raise PreflightError("asset_identity_exact_mismatch")
        if not _safe_name(asset["logical_name"]) or not _hex64(asset["sha256"]):
            raise PreflightError("asset_identity_safe_name_or_hash_invalid")
        if asset["identity_status"] != "ready" or asset["rights_status"] != "blocked":
            raise PreflightError("asset_identity_gate_promotion")
        seen.add(asset_id)


def _verify_rights(value: Any) -> None:
    value = _exact(value, {"status", "reason", "owner_authorization", "third_party_rights_status", "applies_to", "required_inputs"}, "rights_fields_invalid")
    if value["status"] != "blocked" or value["reason"] != "exact_external_asset_rights_are_not_evidenced" or value["third_party_rights_status"] != "unverified":
        raise PreflightError("rights_gate_promotion")
    expected_owner = {"actor": "user", "decision_ref": "user-approved-2026-08-11-p4b-dual-ami-external-observer", "scope": "external_oracle_candidate", "authorization_status": "scoped_owner_permission_only"}
    if value["owner_authorization"] != expected_owner or value["applies_to"] != list(ASSETS) or not isinstance(value["required_inputs"], list) or len(value["required_inputs"]) != 3:
        raise PreflightError("rights_authorization_invalid")


def _verify_parameter_compatibility(value: Any) -> None:
    value = _exact(value, {"status", "reason", "observed_bindings", "observed_spec_version", "required_inputs"}, "parameter_compatibility_fields_invalid")
    if value["status"] != "blocked" or value["reason"] != "parameter_contract_and_ami_init_binding_missing" or value["observed_spec_version"] != "5.1":
        raise PreflightError("parameter_compatibility_gate_promotion")
    expected = [
        {"model_id": "pcie_tx", "ibis_asset": "pcie-gen5-ibis", "ami_asset": "pcie-tx-ami", "dll_asset": "pcie-tx-dll", "ibis_declared_platform": "Windows_mingw64-g++_64", "ami_root": "whistler_tx", "declared_model_version": "6.1", "compatibility_status": "blocked"},
        {"model_id": "pcie_rx", "ibis_asset": "pcie-gen5-ibis", "ami_asset": "pcie-rx-ami", "dll_asset": "pcie-rx-dll", "ibis_declared_platform": "Windows_mingw64-g++_64", "ami_root": "whistler_rx", "declared_model_version": "6.1", "compatibility_status": "blocked"},
    ]
    if value["observed_bindings"] != expected or not isinstance(value["required_inputs"], list) or len(value["required_inputs"]) != 4:
        raise PreflightError("parameter_compatibility_binding_invalid")


def _verify_static_pe(value: Any) -> None:
    value = _exact(value, {"status", "basis", "runtime_evidence_substitute", "dlls", "cannot_establish", "required_inputs"}, "static_pe_fields_invalid")
    if value["status"] != "ready" or value["basis"] != "p4b05c_external_static_declaration_only" or value["runtime_evidence_substitute"] is not False:
        raise PreflightError("static_pe_gate_promotion")
    expected = {
        "pcie-tx-dll": {"byte_length": 370045, "sha256": ASSETS["pcie-tx-dll"][4], "machine": "windows-x86_64", "exports": ["AMI_Close", "AMI_GetWave", "AMI_Init"], "normal_import_modules": ["kernel32.dll", "msvcrt.dll", "user32.dll"], "normal_import_symbol_count": 120, "normal_import_symbol_manifest_sha256": "469f3d78f21a24f7788f925f01ce0e8778ccf9e70567442aacf751ea1690c040", "delay_imports": [], "bound_imports": [], "export_forwarders": [], "embedded_manifests": [], "tls_directory": "present", "clr_directory": "absent", "dynamic_loader_capability_indicators": []},
        "pcie-rx-dll": {"byte_length": 8850494, "sha256": ASSETS["pcie-rx-dll"][4], "machine": "windows-x86_64", "exports": ["AMI_Close", "AMI_GetWave", "AMI_Init"], "normal_import_modules": ["kernel32.dll", "msvcrt.dll", "user32.dll"], "normal_import_symbol_count": 126, "normal_import_symbol_manifest_sha256": "1009c13ac574a286de77d1d5685f312be86f239d81633eddc2d0ab2f4dfe74ab", "delay_imports": [], "bound_imports": [], "export_forwarders": [], "embedded_manifests": [], "tls_directory": "present", "clr_directory": "absent", "dynamic_loader_capability_indicators": []},
    }
    if value["dlls"] != expected or not isinstance(value["cannot_establish"], list) or len(value["cannot_establish"]) != 5 or not isinstance(value["required_inputs"], list) or len(value["required_inputs"]) != 1:
        raise PreflightError("static_pe_declaration_invalid")


def _verify_blocked_surfaces(document: dict[str, Any]) -> None:
    closure = _exact(document["dynamic_dependency_closure"], {"status", "reason", "static_imports_are_not_closure", "transitive_non_system_modules", "system_resolution", "loaded_module_observation", "sidecar_resolution", "closure_status", "required_inputs"}, "closure_fields_invalid")
    if closure["status"] != "blocked" or closure["reason"] != "p4b05c_explicitly_blocked_not_assessed" or closure["static_imports_are_not_closure"] is not True or closure["closure_status"] != "blocked_not_assessed" or any(closure[key] != "not_observed" for key in ("transitive_non_system_modules", "system_resolution", "loaded_module_observation", "sidecar_resolution")) or len(closure["required_inputs"]) != 4:
        raise PreflightError("closure_gate_promotion")
    worker = _exact(document["isolated_worker"], {"status", "product_owned_mock_readiness", "vendor_runtime_readiness", "worker_admission", "required_inputs"}, "worker_fields_invalid")
    if worker["status"] != "blocked" or worker["worker_admission"] != "blocked":
        raise PreflightError("worker_gate_promotion")
    if worker["product_owned_mock_readiness"] != {"hash_pinned_input_and_worker": "ready", "cooperative_cancel_and_deadline": "ready", "parent_timeout_recovery": "ready", "atomic_success_publication": "ready"}:
        raise PreflightError("worker_mock_readiness_invalid")
    if worker["vendor_runtime_readiness"] != {"sandbox": "blocked", "close_on_forced_termination": "blocked", "dynamic_dependency_closure": "blocked", "vendor_runtime_invocation": "blocked", "rights_bound_admission": "blocked"} or len(worker["required_inputs"]) != 3:
        raise PreflightError("worker_vendor_readiness_invalid")
    runtime = _exact(document["fresh_runtime_observation"], {"status", "reason", "product_runtime_invoked", "isolated_worker_invoked", "prior_p4b07", "required_inputs"}, "runtime_fields_invalid")
    if runtime["status"] != "blocked" or runtime["reason"] != "prior_observation_is_external_hash_only_and_not_product_runtime" or runtime["product_runtime_invoked"] is not False or runtime["isolated_worker_invoked"] is not False or len(runtime["required_inputs"]) != 4:
        raise PreflightError("runtime_gate_promotion")
    if runtime["prior_p4b07"] != {"custody": "two_fresh_external_materializations", "result": "raw_output_hash_only", "tx_probe_status": "success", "rx_probe_status": "probe_crash", "product_runtime": False, "worker_admission": False}:
        raise PreflightError("prior_runtime_observation_invalid")


def verify_manifest(root: Path, document: dict[str, Any], *, hashes: set[str] | None = None) -> dict[str, Any]:
    document = _exact(document, {"schema", "status", "profile", "asset_identity", "rights", "parameter_compatibility", "static_pe_imports", "dynamic_dependency_closure", "isolated_worker", "fresh_runtime_observation", "evidence_bindings", "non_claims", "next_inputs"}, "document_fields_invalid")
    if document["schema"] != SCHEMA or document["status"] != "blocked_external_rights_or_runtime_evidence_missing":
        raise PreflightError("schema_or_status_invalid")
    profile = _exact(document["profile"], {"id", "platform", "custody", "packaging", "product_asset", "release_input", "default_runtime", "worker_admission", "runtime_admission", "promotion_status"}, "profile_fields_invalid")
    expected_profile = {"id": "ads-pcie-gen5-dual-ami-windows-x64-v1", "platform": "windows-x86_64", "custody": "external_only_hash_only", "packaging": "prohibited", "product_asset": False, "release_input": False, "default_runtime": False, "worker_admission": "blocked", "runtime_admission": "blocked", "promotion_status": "blocked"}
    if profile != expected_profile:
        raise PreflightError("profile_gate_promotion")
    _verify_asset_identity(document["asset_identity"])
    _verify_rights(document["rights"])
    _verify_parameter_compatibility(document["parameter_compatibility"])
    _verify_static_pe(document["static_pe_imports"])
    _verify_blocked_surfaces(document)
    _verify_evidence(root, document["evidence_bindings"])
    if document["non_claims"] != NON_CLAIMS or not isinstance(document["next_inputs"], list) or len(document["next_inputs"]) != 4:
        raise PreflightError("non_claims_or_next_inputs_invalid")
    actual = _tracked_hashes(root) if hashes is None else hashes
    if actual & {asset[4] for asset in ASSETS.values()}:
        raise PreflightError("tracked_vendor_asset_leak")
    if any(document["profile"][key] is True for key in ("product_asset", "release_input", "default_runtime")):
        raise PreflightError("profile_admission_promoted")
    return {
        "schema": SCHEMA,
        "status": document["status"],
        "component_status": {"asset_identity": "ready", "rights": "blocked", "parameter_compatibility": "blocked", "static_pe_imports": "ready", "dynamic_dependency_closure": "blocked", "isolated_worker": "blocked", "fresh_runtime_observation": "blocked"},
        "worker_admitted": False,
        "runtime_ready": False,
        "release_input": False,
        "static_imports_substitute_runtime": False,
        "next_inputs": document["next_inputs"],
    }


def verify(document: dict[str, Any] | None = None, *, root: Path = ROOT, hashes: set[str] | None = None) -> dict[str, Any]:
    if document is None:
        document = yaml.safe_load((root / DEFAULT.relative_to(ROOT)).read_text(encoding="utf-8"))
    return verify_manifest(root, document, hashes=hashes)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT)
    args = parser.parse_args(argv)
    try:
        result = verify_manifest(ROOT, yaml.safe_load(args.manifest.read_text(encoding="utf-8")))
    except (OSError, ValueError, yaml.YAMLError, PreflightError) as error:
        print(json.dumps({"schema": SCHEMA, "status": "rejected", "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
