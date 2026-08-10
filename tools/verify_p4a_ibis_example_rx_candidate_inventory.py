"""Record and verify the observer-only P4A-01a example_rx IBIS inventory."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.ibis-example-rx-candidate-inventory.v1"
PROFILE_ID = "ibis-ami-example-rx-raw-abi-v1"
DEFAULT_MANIFEST = ROOT / "docs" / "baselines" / "ibis-example-rx-candidate-inventory.v1.yaml"
IBS_PATH = "models/ibisami/example_rx.ibs"
ALLOWED_TABLE_FAMILIES = ("GND Clamp", "Power Clamp")
EXPECTED_WINDOWS_X64 = "Windows_VisualStudio_64"


class InventoryError(RuntimeError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(root: Path, *arguments: str, text: bool = False) -> str | bytes:
    result = subprocess.run(["git", "-C", str(root), *arguments], capture_output=True, check=False)
    if result.returncode != 0:
        raise InventoryError("git_object_unavailable")
    return result.stdout.decode("utf-8").strip() if text else result.stdout


def git_text(root: Path, *arguments: str) -> str:
    return str(git(root, *arguments, text=True))


def blob_record(root: Path, commit: str, path: str) -> dict[str, Any]:
    data = bytes(git(root, "cat-file", "blob", f"{commit}:{path}"))
    return {
        "path": path,
        "git_blob": git_text(root, "rev-parse", f"{commit}:{path}"),
        "byte_length": len(data),
        "content_sha256": sha256(data),
        "bytes": data,
    }


def _keyword(line: str) -> tuple[str, str] | None:
    match = re.match(r"^\s*\[([^\]]+)\]\s*(.*)$", line)
    return None if match is None else (match.group(1).strip(), match.group(2).strip())


def parse_ibis_observation(data: bytes) -> dict[str, Any]:
    """Extract bounded P4A-01 facts; this is not a product IBIS parser."""
    try:
        lines = data.decode("ascii").splitlines()
    except UnicodeDecodeError as error:
        raise InventoryError("ibis_not_ascii") from error
    ibis_version = component = None
    models: list[dict[str, str]] = []
    table_families: list[str] = []
    corner_sources: list[str] = []
    pin_models: set[str] = set()
    executables: list[dict[str, str]] = []
    mode: str | None = None
    current_model: dict[str, str] | None = None
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("|"):
            continue
        parsed = _keyword(raw)
        if parsed is not None:
            name, value = parsed
            mode = name
            if name == "IBIS Ver":
                ibis_version = value
            elif name == "Component":
                component = value
            elif name == "Model":
                current_model = {"name": value, "model_type": ""}
                models.append(current_model)
            elif name in ALLOWED_TABLE_FAMILIES:
                table_families.append(name)
            elif name in {"Package", "Temperature_Range", "Voltage_Range"}:
                corner_sources.append(name)
            continue
        fields = line.split()
        if mode == "Model" and current_model is not None and fields and fields[0] == "Model_type" and len(fields) >= 2:
            current_model["model_type"] = fields[1]
        elif mode == "Pin" and len(fields) >= 3 and not fields[0].lower().startswith("signal"):
            pin_models.add(fields[2])
        elif mode == "Algorithmic Model" and len(fields) >= 4 and fields[0] == "Executable":
            executables.append({"platform": fields[1], "dll_name": fields[2], "ami_name": fields[3]})
        elif mode == "Model" and fields and fields[0] == "C_comp":
            if "C_comp" not in corner_sources:
                corner_sources.append("C_comp")
    if not isinstance(ibis_version, str) or not ibis_version or not isinstance(component, str) or not component:
        raise InventoryError("ibis_required_header_missing")
    if not models or any(not model["name"] or not model["model_type"] for model in models):
        raise InventoryError("ibis_model_missing")
    if not pin_models or not executables:
        raise InventoryError("ibis_binding_metadata_missing")
    return {
        "ibis_version": ibis_version,
        "component": component,
        "models": sorted(models, key=lambda item: item["name"]),
        "pin_model_selectors": sorted(pin_models),
        "corner_sources": sorted(corner_sources),
        "table_families": sorted(set(table_families)),
        "algorithmic_executables": sorted(executables, key=lambda item: item["platform"]),
    }


def _profile(document: dict[str, Any]) -> dict[str, Any]:
    profiles = document.get("profiles")
    if not isinstance(profiles, list):
        raise InventoryError("acceptance_profiles_invalid")
    profile = next((item for item in profiles if isinstance(item, dict) and item.get("id") == PROFILE_ID), None)
    if not isinstance(profile, dict):
        raise InventoryError("candidate_profile_missing")
    return profile


def _asset_map(profile: dict[str, Any]) -> dict[str, dict[str, Any]]:
    assets = profile.get("assets")
    if not isinstance(assets, list):
        raise InventoryError("candidate_assets_invalid")
    result = {asset.get("path"): asset for asset in assets if isinstance(asset, dict) and isinstance(asset.get("path"), str)}
    if set(result) != {"models/ibisami/example_rx.ami", IBS_PATH, "models/ibisami/example_rx.dll"}:
        raise InventoryError("candidate_assets_invalid")
    return result


def materialize_manifest(pybert_root: Path) -> dict[str, Any]:
    acceptance = yaml.safe_load((ROOT / "acceptance-profiles.v1.yaml").read_text(encoding="utf-8"))
    if not isinstance(acceptance, dict):
        raise InventoryError("acceptance_profiles_invalid")
    profile = _profile(acceptance)
    source = profile.get("source")
    decision = profile.get("acceptance")
    if not isinstance(source, dict) or not isinstance(decision, dict) or source.get("repository") != "pybert-f6ba031" or decision.get("status") != "candidate" or decision.get("required_by") is not None:
        raise InventoryError("candidate_profile_not_pending")
    repositories = acceptance.get("repositories")
    repository = next((item for item in repositories if isinstance(item, dict) and item.get("id") == source.get("repository")), None) if isinstance(repositories, list) else None
    if not isinstance(repository, dict) or not isinstance(repository.get("commit"), str):
        raise InventoryError("candidate_repository_invalid")
    commit = repository["commit"]
    assets = _asset_map(profile)
    records: dict[str, dict[str, Any]] = {}
    for path, asset in assets.items():
        record = blob_record(pybert_root, commit, path)
        if record["git_blob"] != asset.get("git_blob") or record["content_sha256"] != asset.get("content_sha256"):
            raise InventoryError("candidate_asset_git_identity_mismatch")
        records[path] = record
    observed = parse_ibis_observation(records[IBS_PATH]["bytes"])
    windows_x64 = next((item for item in observed["algorithmic_executables"] if item["platform"] == EXPECTED_WINDOWS_X64), None)
    if not isinstance(windows_x64, dict):
        raise InventoryError("windows_x64_binding_missing")
    authorized_name = Path("models/ibisami/example_rx.dll").name
    return {
        "schema": SCHEMA,
        "status": "candidate_not_required_preflight_passed",
        "promotion_eligible": False,
        "profile": {"id": PROFILE_ID, "required_by": None, "boundary": "oracle_only"},
        "source": {
            "repository": source["repository"],
            "commit": commit,
            "origin_sha256": sha256(git_text(pybert_root, "remote", "get-url", "origin").encode("utf-8")),
        },
        "assets": [
            {key: value for key, value in records[path].items() if key != "bytes"}
            for path in sorted(records)
        ],
        "ibis_observation": observed,
        "windows_x64_asset_binding": {
            "declared_dll_name": windows_x64["dll_name"],
            "authorized_asset_name": authorized_name,
            "status": "blocked_declared_filename_not_authorized_asset_name" if windows_x64["dll_name"] != authorized_name else "name_matched_not_runtime_verified",
        },
        "non_claims": [
            "The example is not user-confirmed required and this inventory does not change that state.",
            "The observation is external-only and does not copy an IBIS, AMI, or DLL asset into the product.",
            "No parser, electrical semantics, host behavior, or release conclusion follows from this preflight.",
        ],
    }


def verify_manifest(pybert_root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    if manifest.get("schema") != SCHEMA or manifest.get("status") != "candidate_not_required_preflight_passed" or manifest.get("promotion_eligible") is not False:
        raise InventoryError("manifest_status_invalid")
    expected = materialize_manifest(pybert_root)
    if manifest != expected:
        raise InventoryError("manifest_drift")
    validate_static_scope(manifest)
    binding = manifest["windows_x64_asset_binding"]
    return {
        "schema": SCHEMA,
        "status": "candidate_not_required_preflight_passed",
        "profile_id": PROFILE_ID,
        "required": False,
        "promotion_eligible": False,
        "asset_binding_status": binding["status"],
        "non_claims": ["No IBIS parser, electrical behavior, AMI host, or release capability is accepted."],
    }


def validate_static_scope(manifest: dict[str, Any]) -> None:
    """Check the fixed non-promotion invariants independently of Git I/O."""
    if manifest.get("schema") != SCHEMA or manifest.get("status") != "candidate_not_required_preflight_passed" or manifest.get("promotion_eligible") is not False:
        raise InventoryError("manifest_status_invalid")
    profile = manifest.get("profile")
    if profile != {"id": PROFILE_ID, "required_by": None, "boundary": "oracle_only"}:
        raise InventoryError("candidate_profile_scope_invalid")
    observation = manifest["ibis_observation"]
    if observation["table_families"] != list(ALLOWED_TABLE_FAMILIES) or observation["models"] != [{"name": "example_rx", "model_type": "Input"}] or observation["pin_model_selectors"] != ["example_rx"]:
        raise InventoryError("unexpected_observation_scope")
    binding = manifest["windows_x64_asset_binding"]
    if binding["status"] != "blocked_declared_filename_not_authorized_asset_name":
        raise InventoryError("asset_binding_status_invalid")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pybert-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--write-manifest", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        manifest = materialize_manifest(args.pybert_root) if args.write_manifest else yaml.safe_load(args.manifest.read_text(encoding="utf-8"))
        if args.write_manifest:
            args.manifest.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
        report = verify_manifest(args.pybert_root, manifest)
    except (OSError, yaml.YAMLError, InventoryError) as error:
        report = {"schema": SCHEMA, "status": "rejected", "reason": str(error)}
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":"))
    if args.report:
        args.report.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if report["status"] == "candidate_not_required_preflight_passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
