"""Verify the fail-closed P4A electrical-load and IBIS discovery record."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.p4a-electrical-ibis-discovery.v1"
DEFAULT_MANIFEST = ROOT / "docs" / "baselines" / "p4a-electrical-ibis-discovery.v1.yaml"
ALLOWED_CLOAD_PLACEMENTS = {"across_pair", "each_leg_to_reference", "total_differential_equivalent"}


class DiscoveryError(RuntimeError):
    pass


def _reject_absolute_or_parent(value: str) -> None:
    if Path(value).is_absolute() or ".." in Path(value).parts:
        raise DiscoveryError("absolute_or_parent_path_forbidden")


def _expect_keys(value: dict[str, Any], keys: set[str], reason: str) -> None:
    if set(value) != keys:
        raise DiscoveryError(reason)


def validate_manifest(document: dict[str, Any]) -> dict[str, Any]:
    _expect_keys(document, {"schema", "status", "promotion_eligible", "electrical_load_candidate", "local_candidates", "public_discovery", "non_claims"}, "manifest_shape_invalid")
    if document["schema"] != SCHEMA or document["status"] != "candidate_discovery_preflight_passed" or document["promotion_eligible"] is not False:
        raise DiscoveryError("manifest_status_invalid")

    load = document["electrical_load_candidate"]
    if not isinstance(load, dict):
        raise DiscoveryError("electrical_load_candidate_invalid")
    _expect_keys(load, {"profile_id", "required", "status", "differential_resistance", "load_capacitance", "blocked_by"}, "electrical_load_candidate_shape_invalid")
    if load["profile_id"] != "rx-electrical-load-diff100-cload1pf-v1" or load["required"] is not False or load["status"] != "candidate_blocked_missing_c_load_placement":
        raise DiscoveryError("electrical_load_candidate_status_invalid")
    resistor = load["differential_resistance"]
    if resistor != {"value_ohm": 100.0, "placement": "across_pair", "terminals": ["p", "n"]}:
        raise DiscoveryError("differential_resistance_invalid")
    capacitor = load["load_capacitance"]
    if not isinstance(capacitor, dict):
        raise DiscoveryError("load_capacitance_invalid")
    _expect_keys(capacitor, {"value_pf", "placement", "allowed_placements", "reference_net"}, "load_capacitance_shape_invalid")
    if capacitor["value_pf"] != 1.0 or capacitor["placement"] != "pending_owner_choice" or set(capacitor["allowed_placements"]) != ALLOWED_CLOAD_PLACEMENTS or capacitor["reference_net"] is not None:
        raise DiscoveryError("load_capacitance_placement_invalid")
    if load["blocked_by"] != ["explicit_c_load_placement", "reference_net_when_each_leg_to_reference", "stimulus_and_observable_acceptance_contract"]:
        raise DiscoveryError("electrical_load_blockers_invalid")

    local = document["local_candidates"]
    if not isinstance(local, list) or len(local) != 2:
        raise DiscoveryError("local_candidates_invalid")
    by_id = {item.get("id"): item for item in local if isinstance(item, dict)}
    example = by_id.get("pybert-example-rx-ibis-ami")
    minimal = by_id.get("sipi-minimal-ibis-test-fixture")
    if example is None or minimal is None or len(by_id) != 2:
        raise DiscoveryError("local_candidate_identity_invalid")
    if example.get("boundary") != "oracle_only" or example.get("status") != "candidate_blocked_declared_windows_x64_dll_identity" or example.get("inventory_ref") != "docs/baselines/ibis-example-rx-candidate-inventory.v1.yaml":
        raise DiscoveryError("example_rx_candidate_invalid")
    _reject_absolute_or_parent(str(example["inventory_ref"]))
    assets = example.get("assets")
    if not isinstance(assets, list) or {item.get("path") for item in assets if isinstance(item, dict)} != {"models/ibisami/example_rx.ibs", "models/ibisami/example_rx.ami", "models/ibisami/example_rx.dll"}:
        raise DiscoveryError("example_rx_assets_invalid")
    for asset in assets:
        if not isinstance(asset, dict) or set(asset) != {"path", "git_blob", "content_sha256"}:
            raise DiscoveryError("example_rx_asset_shape_invalid")
        _reject_absolute_or_parent(asset["path"])
        if len(asset["git_blob"]) != 40 or len(asset["content_sha256"]) != 64:
            raise DiscoveryError("example_rx_asset_identity_invalid")
    if minimal != {"id": "sipi-minimal-ibis-test-fixture", "boundary": "synthetic_test_only", "status": "not_an_external_acceptance_asset", "tracked_path": "native/crates/sipi-circuit/tests/fixtures/ami/minimal.ibs", "prohibited_uses": ["required_profile", "oracle_asset", "product_runtime_asset"]}:
        raise DiscoveryError("synthetic_fixture_scope_invalid")
    _reject_absolute_or_parent(minimal["tracked_path"])

    public = document["public_discovery"]
    if not isinstance(public, list) or len(public) != 1 or not isinstance(public[0], dict):
        raise DiscoveryError("public_discovery_invalid")
    source = public[0]
    expected_public = {
        "id": "ibis-open-forum-model-suppliers",
        "source_url": "https://ibis.org/~ibisorg/models/",
        "kind": "model_supplier_directory",
        "candidate_kind": "pure_ibs_asset",
        "status": "candidate_unverified_no_asset_selected",
        "license_status": "unknown_until_exact_asset_license_is_verified",
        "bytes_fetched": False,
        "git_or_release_import": "forbidden",
    }
    if source != expected_public:
        raise DiscoveryError("public_discovery_scope_invalid")
    if not isinstance(document["non_claims"], list) or len(document["non_claims"]) != 4:
        raise DiscoveryError("non_claims_invalid")
    return {
        "schema": SCHEMA,
        "status": "candidate_discovery_preflight_passed",
        "electrical_profile": load["profile_id"],
        "required": False,
        "c_load_placement": "pending_owner_choice",
        "local_candidate_count": 2,
        "public_candidate_count": 1,
        "promotion_eligible": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        document = yaml.safe_load(args.manifest.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise DiscoveryError("manifest_invalid")
        report = validate_manifest(document)
    except (OSError, yaml.YAMLError, DiscoveryError, KeyError, TypeError) as error:
        report = {"schema": SCHEMA, "status": "rejected", "reason": str(error)}
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":"))
    if args.report:
        args.report.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if report["status"] == "candidate_discovery_preflight_passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
