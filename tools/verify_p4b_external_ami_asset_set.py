"""Fail-closed admission policy for external AMI asset sets."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.p4b-external-ami-asset-set.v1"
DEFAULT_MANIFEST = ROOT / "docs" / "baselines" / "p4b-external-ami-asset-set.v1.yaml"
EVIDENCE_PATHS = {
    "docs/baselines/m5b-ami-vendor-fixture-preflight.v1.json",
    "docs/baselines/m5b-ami-authorized-dll-closure-preflight.v1.json",
    "docs/baselines/ibis-example-rx-candidate-inventory.v1.yaml",
}
ASSET_KINDS = {"dll", "ibis", "ami_text", "non_system_dependency"}
RIGHTS_STATUSES = {"unverified", "evidenced", "legal_reviewed"}
USAGE_SCOPES = {"discovery_only", "external_oracle_compare", "external_worker_candidate"}
HEX64 = set("0123456789abcdef")


class AssetSetError(RuntimeError):
    pass


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= HEX64


def relative_source_path(value: Any) -> bool:
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts


def safe_logical_name(value: Any) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and "/" not in value
        and "\\" not in value
        and ":" not in value
        and value not in {".", ".."}
    )


def git_tracked_hashes(root: Path) -> set[str]:
    completed = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"], check=False, capture_output=True
    )
    if completed.returncode:
        raise AssetSetError("git_inventory_unavailable")
    result: set[str] = set()
    for raw_path in completed.stdout.split(b"\0"):
        if not raw_path:
            continue
        path = raw_path.decode("utf-8")
        file_path = root / path
        if not file_path.is_file():
            raise AssetSetError("tracked_file_unavailable")
        result.add(hashlib.sha256(file_path.read_bytes()).hexdigest())
    return result


def _expect_keys(value: Any, expected: set[str], reason: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise AssetSetError(reason)
    return value


def _verify_source(source: Any) -> dict[str, Any]:
    source = _expect_keys(source, {"repository", "commit", "path", "git_blob"}, "asset_source_invalid")
    if (
        source["repository"] != "pybert-f6ba031"
        or source["commit"] != "f6ba0311350fc67bd90fa13b8d578312f956d7e7"
        or not relative_source_path(source["path"])
        or not isinstance(source["git_blob"], str)
        or len(source["git_blob"]) != 40
    ):
        raise AssetSetError("asset_source_invalid")
    return source


def _verify_asset(asset: Any, seen_ids: set[str], seen_hashes: set[str]) -> dict[str, Any]:
    if not isinstance(asset, dict):
        raise AssetSetError("asset_invalid")
    allowed = {"id", "kind", "logical_name", "role", "byte_length", "sha256", "source", "third_party_rights_status", "usage_scope"}
    if asset.get("kind") == "dll":
        allowed |= {"declared_name", "architecture"}
    if set(asset) != allowed:
        raise AssetSetError("asset_fields_invalid")
    asset_id = asset.get("id")
    if not isinstance(asset_id, str) or not asset_id or asset_id in seen_ids:
        raise AssetSetError("asset_id_invalid")
    if asset.get("kind") not in ASSET_KINDS or not safe_logical_name(asset.get("logical_name")):
        raise AssetSetError("asset_kind_invalid")
    if not isinstance(asset.get("role"), str) or not asset["role"]:
        raise AssetSetError("asset_role_invalid")
    if not isinstance(asset.get("byte_length"), int) or asset["byte_length"] <= 0 or not is_sha256(asset.get("sha256")):
        raise AssetSetError("asset_identity_invalid")
    if asset["sha256"] in seen_hashes:
        raise AssetSetError("ambiguous_duplicate_asset_hash")
    if asset.get("third_party_rights_status") not in RIGHTS_STATUSES:
        raise AssetSetError("rights_status_invalid")
    scopes = asset.get("usage_scope")
    if not isinstance(scopes, list) or not scopes or len(scopes) != len(set(scopes)) or not set(scopes) <= USAGE_SCOPES:
        raise AssetSetError("usage_scope_invalid")
    if "external_worker_candidate" in scopes and asset["third_party_rights_status"] == "unverified":
        raise AssetSetError("worker_scope_requires_rights_evidence")
    if asset["kind"] == "dll":
        if asset.get("architecture") != "windows-x86_64" or not safe_logical_name(asset.get("declared_name")):
            raise AssetSetError("dll_metadata_invalid")
    _verify_source(asset["source"])
    seen_ids.add(asset_id)
    seen_hashes.add(asset["sha256"])
    return asset


def _verify_evidence(root: Path, evidence: Any) -> None:
    if not isinstance(evidence, list) or len(evidence) != len(EVIDENCE_PATHS):
        raise AssetSetError("prior_evidence_invalid")
    seen: set[str] = set()
    for entry in evidence:
        entry = _expect_keys(entry, {"path", "sha256"}, "prior_evidence_invalid")
        path = entry["path"]
        if path not in EVIDENCE_PATHS or path in seen or not is_sha256(entry["sha256"]):
            raise AssetSetError("prior_evidence_invalid")
        if digest(root / path) != entry["sha256"]:
            raise AssetSetError("prior_evidence_hash_mismatch")
        seen.add(path)


def _verify_cross_evidence(root: Path, assets: dict[str, dict[str, Any]]) -> None:
    vendor = json.loads((root / "docs/baselines/m5b-ami-vendor-fixture-preflight.v1.json").read_text(encoding="utf-8"))
    inventory = yaml.safe_load((root / "docs/baselines/ibis-example-rx-candidate-inventory.v1.yaml").read_text(encoding="utf-8"))
    vendor_assets = {item["kind"]: item for item in vendor.get("fixture", {}).get("assets", []) if isinstance(item, dict)}
    expected = {"ibs": "example-rx-ibis", "ami": "example-rx-ami-text", "dll": "example-rx-dll"}
    for kind, asset_id in expected.items():
        asset = assets.get(asset_id)
        observed = vendor_assets.get(kind)
        if not asset or not isinstance(observed, dict):
            raise AssetSetError("prior_evidence_asset_missing")
        source = asset["source"]
        if source["path"] != observed.get("path") or source["git_blob"] != observed.get("blob") or asset["sha256"] != observed.get("sha256") or asset["byte_length"] != observed.get("byteLength"):
            raise AssetSetError("prior_evidence_asset_mismatch")
    binding = inventory.get("windows_x64_asset_binding") if isinstance(inventory, dict) else None
    dll = assets["example-rx-dll"]
    if not isinstance(binding, dict) or binding.get("declared_dll_name") != dll.get("declared_name") or binding.get("authorized_asset_name") != dll.get("logical_name"):
        raise AssetSetError("prior_binding_evidence_mismatch")


def verify_manifest(root: Path, manifest: dict[str, Any], *, tracked_hashes: set[str] | None = None) -> dict[str, Any]:
    _expect_keys(manifest, {"schema", "status", "asset_set", "owner_authorization", "prior_observation_evidence", "non_claims"}, "manifest_fields_invalid")
    if manifest["schema"] != SCHEMA or manifest["status"] != "external_only_admission_blocked":
        raise AssetSetError("manifest_status_invalid")
    asset_set = _expect_keys(asset_set := manifest["asset_set"], {"id", "platform", "custody", "packaging", "product_asset", "release_input", "default_runtime", "worker_admission", "assets", "non_system_dependency_closure", "bindings"}, "asset_set_fields_invalid")
    if asset_set["id"] != "pybert-example-rx-windows-x64-v1" or asset_set["platform"] != "windows-x86_64" or asset_set["custody"] != "external_only" or asset_set["packaging"] != "prohibited" or any(asset_set[key] is not False for key in ("product_asset", "release_input", "default_runtime")) or asset_set["worker_admission"] != "blocked_identity_role_mismatch":
        raise AssetSetError("asset_set_boundary_invalid")
    raw_assets = asset_set["assets"]
    if not isinstance(raw_assets, list) or len(raw_assets) < 3:
        raise AssetSetError("asset_set_assets_invalid")
    seen_ids: set[str] = set()
    seen_hashes: set[str] = set()
    assets = {asset["id"]: _verify_asset(asset, seen_ids, seen_hashes) for asset in raw_assets}
    if set(assets) != {"example-rx-ibis", "example-rx-ami-text", "example-rx-dll"}:
        raise AssetSetError("asset_set_assets_invalid")
    closure = _expect_keys(asset_set["non_system_dependency_closure"], {"status", "entries"}, "closure_invalid")
    if closure["status"] != "blocked_not_admitted" or closure["entries"] != []:
        raise AssetSetError("closure_invalid")
    bindings = asset_set["bindings"]
    expected_binding = {"ibis_asset": "example-rx-ibis", "ami_text_asset": "example-rx-ami-text", "dll_asset": "example-rx-dll", "status": "blocked_declared_dll_name_does_not_match_authorized_asset_name"}
    if bindings != [expected_binding]:
        raise AssetSetError("asset_binding_invalid")
    authorization = _expect_keys(manifest["owner_authorization"], {"actor", "decision_ref", "scope", "authorization_status"}, "owner_authorization_invalid")
    if authorization != {"actor": "user", "decision_ref": "docs/baselines/m5b-ami-vendor-fixture-preflight.v1.json", "scope": "external_oracle_compare", "authorization_status": "scoped_owner_permission_only"}:
        raise AssetSetError("owner_authorization_invalid")
    _verify_evidence(root, manifest["prior_observation_evidence"])
    _verify_cross_evidence(root, assets)
    claims = manifest["non_claims"]
    if not isinstance(claims, list) or len(claims) < 4 or any(not isinstance(item, str) or not item for item in claims):
        raise AssetSetError("non_claims_invalid")
    actual_hashes = git_tracked_hashes(root) if tracked_hashes is None else tracked_hashes
    if seen_hashes & actual_hashes:
        raise AssetSetError("tracked_vendor_asset_leak")
    return {
        "schema": SCHEMA,
        "status": "external_only_admission_blocked",
        "asset_set_id": asset_set["id"],
        "asset_count": len(assets),
        "worker_admitted": False,
        "packaging": "prohibited",
        "third_party_rights": "unverified",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--report", type=Path)
    arguments = parser.parse_args(argv)
    try:
        document = yaml.safe_load(arguments.manifest.read_text(encoding="utf-8"))
        report = verify_manifest(ROOT, document)
    except (AssetSetError, OSError, ValueError, yaml.YAMLError, json.JSONDecodeError) as error:
        report = {"schema": SCHEMA, "status": "rejected", "reason": str(error)}
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":"))
    if arguments.report:
        arguments.report.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if report["status"] == "external_only_admission_blocked" else 2


if __name__ == "__main__":
    raise SystemExit(main())
