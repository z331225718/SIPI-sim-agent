"""Fail closed on receiver topology mixing or candidate promotion."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.receiver-topology-and-acceptance.v1"
PROFILE_ID = "ibis-ami-example-rx-raw-abi-v1"
MANIFEST = ROOT / "docs" / "baselines" / "receiver-topology-and-acceptance.v1.yaml"
ACCEPTANCE = ROOT / "acceptance-profiles.v1.yaml"
STAGE_KINDS = {"electrical_load", "ibis_receiver_model", "ami_receiver_algorithm", "rx_chain"}


class TopologyError(RuntimeError):
    pass


def load(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TopologyError("document_invalid")
    return value


def candidate_profile(document: dict[str, Any]) -> dict[str, Any]:
    profiles = document.get("profiles")
    if not isinstance(profiles, list):
        raise TopologyError("acceptance_profiles_invalid")
    profile = next((item for item in profiles if isinstance(item, dict) and item.get("id") == PROFILE_ID), None)
    if not isinstance(profile, dict):
        raise TopologyError("candidate_profile_missing")
    return profile


def verify_document(manifest: dict[str, Any], acceptance: dict[str, Any]) -> dict[str, Any]:
    required_top = {"schema", "status", "composition", "stage_kinds", "candidate_profiles", "non_claims"}
    if set(manifest) != required_top or manifest.get("schema") != SCHEMA or manifest.get("status") != "topology_contract_pending_required_profile" or manifest.get("composition") != "explicit_profile_only":
        raise TopologyError("manifest_scope_invalid")
    stages = manifest.get("stage_kinds")
    if not isinstance(stages, dict) or set(stages) != STAGE_KINDS:
        raise TopologyError("stage_kind_set_invalid")
    for kind, definition in stages.items():
        if not isinstance(definition, dict) or set(definition) != {"role", "handoff", "units", "current_status"} or definition.get("current_status") != "not_supported" or not all(isinstance(definition[key], str) and definition[key] for key in ("role", "handoff", "units")):
            raise TopologyError(f"stage_definition_invalid:{kind}")
    profiles = manifest.get("candidate_profiles")
    if not isinstance(profiles, list) or len(profiles) != 1 or not isinstance(profiles[0], dict):
        raise TopologyError("candidate_profile_set_invalid")
    candidate = profiles[0]
    expected_keys = {"profile_id", "rx_kind", "required", "boundary", "source_asset_path", "associated_ibis_asset", "composition_status", "asset_identity_status", "observable", "blocked_by"}
    if set(candidate) != expected_keys or candidate.get("profile_id") != PROFILE_ID or candidate.get("rx_kind") != "ami_receiver_algorithm" or candidate.get("required") is not False or candidate.get("boundary") != "oracle_only" or candidate.get("composition_status") != "not_composed" or candidate.get("asset_identity_status") != "blocked_declared_filename_not_authorized_asset_name":
        raise TopologyError("candidate_scope_invalid")
    if not isinstance(candidate.get("blocked_by"), list) or len(candidate["blocked_by"]) < 4 or not all(isinstance(item, str) and item for item in candidate["blocked_by"]):
        raise TopologyError("candidate_blockers_invalid")
    profile = candidate_profile(acceptance)
    profile_acceptance = profile.get("acceptance")
    source = profile.get("source")
    assets = profile.get("assets")
    if not isinstance(profile_acceptance, dict) or not isinstance(source, dict) or not isinstance(assets, list):
        raise TopologyError("acceptance_profile_shape_invalid")
    paths = {asset.get("path") for asset in assets if isinstance(asset, dict)}
    if profile.get("boundary") != "oracle_only" or profile_acceptance.get("status") != "candidate" or profile_acceptance.get("required_by") is not None or source.get("path") != candidate["source_asset_path"] or candidate["associated_ibis_asset"] not in paths:
        raise TopologyError("acceptance_profile_drift")
    non_claims = manifest.get("non_claims")
    if not isinstance(non_claims, list) or len(non_claims) < 4 or not all(isinstance(item, str) and item for item in non_claims):
        raise TopologyError("non_claims_invalid")
    return {"valid": True, "schema": SCHEMA, "composition": "explicit_profile_only", "candidate_required": False, "supported_stage_count": 0}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--acceptance", type=Path, default=ACCEPTANCE)
    args = parser.parse_args()
    try:
        report = verify_document(load(args.manifest), load(args.acceptance))
    except (OSError, yaml.YAMLError, TopologyError) as error:
        report = {"valid": False, "schema": SCHEMA, "reason": str(error)}
    print(json.dumps(report, sort_keys=True))
    return 0 if report["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
