"""Fail-closed policy for the ADS PCIe Gen5 dual-AMI observation record."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.p4b-ads-pcie-gen5-dual-ami-asset-preflight.v1"
DEFAULT = ROOT / "docs/baselines/p4b-ads-pcie-gen5-dual-ami-asset-preflight.v1.yaml"
HEX64 = set("0123456789abcdef")
ASSETS = {
    "pcie-gen5-ibis": ("ibis", "pcie_gen5.ibs", "shared_input_model"),
    "pcie-tx-ami": ("ami_text", "ctspcie_tx_gen5.ami", "tx_parameter_text"),
    "pcie-rx-ami": ("ami_text", "ctspcie_rx_gen5.ami", "rx_parameter_text"),
    "pcie-tx-dll": ("dll", "ctspcie_tx_win64.dll", "tx_primary_dynamic_library"),
    "pcie-rx-dll": ("dll", "ctspcie_rx_win64.dll", "rx_primary_dynamic_library"),
}
EXPECTED_IDENTITIES = {
    "pcie-gen5-ibis": (5537, "9ff15bf9a5ad685d0ad700b26287b5f50e1c6e1ff9c6808e5a0f0ef86896d665"),
    "pcie-tx-ami": (3280, "9272e241901d8fa749909e501c6625e508961f581e624c3f64d18a27a2408fb0"),
    "pcie-rx-ami": (7489, "9e6206eddd32ab9d1a2ec8237d84608509131f7c3fc309c4f90f44a87f8905c1"),
    "pcie-tx-dll": (370045, "05d299826a9c69ae8ac3d236d88adcad5860fc7e229243f1541d1734b8ed28ea"),
    "pcie-rx-dll": (8850494, "88a284f0967ad332f6230a8c5e791f47e9d22a05ae6778426c35707a18a3ab63"),
}
NON_CLAIMS = [
    "Not worker admission, runtime load, or GetWave evidence.",
    "Not a complete static or dynamic dependency closure.",
    "Not third-party rights, redistribution, packaging, release, or default-route evidence.",
    "Not IBIS/AMI compatibility, TX-to-RX composition, or numerical parity.",
    "Not PRBS, CDR, DFE, channel, eye, jitter, BER, or ADS acceptance.",
]


class PreflightError(RuntimeError):
    pass


def exact(value: Any, keys: set[str], reason: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise PreflightError(reason)
    return value


def sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= HEX64


def safe_name(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and not any(token in value for token in ("/", "\\", ":", ".."))


def set_digest(assets: dict[str, dict[str, Any]]) -> str:
    rows = [f"{asset_id}\t{assets[asset_id]['byte_length']}\t{assets[asset_id]['sha256']}" for asset_id in sorted(assets)]
    return hashlib.sha256(("\n".join(rows) + "\n").encode("ascii")).hexdigest()


def tracked_hashes(root: Path) -> set[str]:
    import subprocess

    result = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], check=True, capture_output=True)
    return {hashlib.sha256((root / raw.decode("utf-8")).read_bytes()).hexdigest() for raw in result.stdout.split(b"\0") if raw}


def verify_manifest(root: Path, document: dict[str, Any], *, hashes: set[str] | None = None) -> dict[str, Any]:
    exact(document, {"schema", "status", "asset_set", "owner_authorization", "external_observation", "non_claims"}, "document_fields_invalid")
    if document["schema"] != SCHEMA or document["status"] != "external_only_identity_observed_worker_blocked":
        raise PreflightError("status_invalid")
    asset_set = exact(document["asset_set"], {"id", "platform", "source_custody", "absolute_path_retained", "packaging", "product_asset", "release_input", "default_runtime", "worker_admission", "assets", "asset_set_digest", "bindings", "ibis_version", "static_abi_surface"}, "asset_set_fields_invalid")
    boundary = {"id": "ads-pcie-gen5-dual-ami-windows-x64-v1", "platform": "windows-x86_64", "source_custody": "unversioned_content_hash_only", "absolute_path_retained": False, "packaging": "prohibited", "product_asset": False, "release_input": False, "default_runtime": False, "worker_admission": "blocked_unverified_rights_and_runtime_closure", "ibis_version": "5.1"}
    if any(asset_set[key] != value for key, value in boundary.items()):
        raise PreflightError("asset_set_boundary_invalid")
    raw_assets = asset_set["assets"]
    if not isinstance(raw_assets, list) or len(raw_assets) != len(ASSETS):
        raise PreflightError("asset_allowlist_invalid")
    assets: dict[str, dict[str, Any]] = {}
    for asset in raw_assets:
        asset = exact(asset, {"id", "kind", "logical_name", "role", "byte_length", "sha256", "third_party_rights_status"}, "asset_fields_invalid")
        asset_id = asset["id"]
        if asset_id in assets or asset_id not in ASSETS or not safe_name(asset["logical_name"]):
            raise PreflightError("asset_identity_invalid")
        kind, name, role = ASSETS[asset_id]
        if (asset["kind"], asset["logical_name"], asset["role"]) != (kind, name, role) or (asset["byte_length"], asset["sha256"]) != EXPECTED_IDENTITIES[asset_id] or asset["third_party_rights_status"] != "unverified" or not sha256(asset["sha256"]):
            raise PreflightError("asset_identity_invalid")
        assets[asset_id] = asset
    if asset_set["asset_set_digest"] != set_digest(assets):
        raise PreflightError("asset_set_digest_invalid")
    expected_bindings = [
        {"model_id": "pcie_tx", "ibis_asset": "pcie-gen5-ibis", "ami_asset": "pcie-tx-ami", "dll_asset": "pcie-tx-dll", "ibis_declared_platform": "Windows_mingw64-g++_64", "ami_root": "whistler_tx", "ami_version": "6.1", "binding_status": "identity_observed_not_runtime_verified"},
        {"model_id": "pcie_rx", "ibis_asset": "pcie-gen5-ibis", "ami_asset": "pcie-rx-ami", "dll_asset": "pcie-rx-dll", "ibis_declared_platform": "Windows_mingw64-g++_64", "ami_root": "whistler_rx", "ami_version": "6.1", "binding_status": "identity_observed_not_runtime_verified"},
    ]
    if asset_set["bindings"] != expected_bindings:
        raise PreflightError("binding_invalid")
    abi = exact(asset_set["static_abi_surface"], {"machine", "exports", "normal_imports", "delay_imports", "dynamic_dependency_closure"}, "static_abi_invalid")
    if abi != {"machine": "windows-x86_64", "exports": ["AMI_Close", "AMI_GetWave", "AMI_Init"], "normal_imports": ["kernel32.dll", "msvcrt.dll", "user32.dll"], "delay_imports": [], "dynamic_dependency_closure": "blocked_not_assessed"}:
        raise PreflightError("static_abi_invalid")
    authorization = exact(document["owner_authorization"], {"actor", "decision_ref", "scope", "authorization_status"}, "owner_authorization_invalid")
    if authorization != {"actor": "user", "decision_ref": "user-approved-2026-08-11-p4b-dual-ami-external-observer", "scope": "external_oracle_candidate", "authorization_status": "scoped_owner_permission_only"}:
        raise PreflightError("owner_authorization_invalid")
    observation = exact(document["external_observation"], {"schema", "report_content_sha256", "custody", "report_path_retained"}, "observation_invalid")
    if observation["schema"] != "sipi.p4b-ads-pcie-gen5-dual-ami-asset-observation.v1" or not sha256(observation["report_content_sha256"]) or observation["custody"] != "external_only" or observation["report_path_retained"] is not False:
        raise PreflightError("observation_invalid")
    if document["non_claims"] != NON_CLAIMS:
        raise PreflightError("non_claims_invalid")
    actual = tracked_hashes(root) if hashes is None else hashes
    if {asset["sha256"] for asset in assets.values()} & actual or observation["report_content_sha256"] in actual:
        raise PreflightError("tracked_vendor_asset_leak")
    return {"schema": SCHEMA, "status": document["status"], "asset_count": len(assets), "worker_admitted": False, "runtime_evidence": False, "release_input": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT)
    arguments = parser.parse_args(argv)
    try:
        result = verify_manifest(ROOT, yaml.safe_load(arguments.manifest.read_text(encoding="utf-8")))
    except (OSError, ValueError, yaml.YAMLError, PreflightError) as error:
        print(json.dumps({"schema": SCHEMA, "status": "rejected", "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
