"""Verify the hash-only P4B-02 external AMI parameter-subset observation."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "docs/baselines/p4b-02-ads-pcie-gen5-parameter-subset-observation.v1.json"
SCHEMA = "sipi.p4b-02.ami-parameter-subset-observation.v1"
STATUS = "external_only_host_forwarded_parameter_subset_observed_dll_consumption_unproven"
DECISION = "external_asset_oracle"
EXPECTED = {
    "tx": {
        "byte_len": 3280,
        "role": "tx",
        "root_name": "whistler_tx",
        "selected_count": 8,
        "selected_paths_sha256": "01e3177c3430c93d754b6f96360da7515a8171dfea5eec103a22d58606b7b7bf",
        "source_sha256": "9272e241901d8fa749909e501c6625e508961f581e624c3f64d18a27a2408fb0",
        "subset_digest": "3aacacef9c2cccf217e33bba24578543f42e29be74f187e97554529a7f3b88bf",
        "tree_digest": "85421869e459942647f9767e570f41e5ffa5952cec8220b563f40b79e7836410",
    },
    "rx": {
        "byte_len": 7489,
        "role": "rx",
        "root_name": "whistler_rx",
        "selected_count": 30,
        "selected_paths_sha256": "e43dd3de7649393841abfeb18bf919ac8a2f35fa018155f0565097869585227c",
        "source_sha256": "9e6206eddd32ab9d1a2ec8237d84608509131f7c3fc309c4f90f44a87f8905c1",
        "subset_digest": "22fa25e1d8c5c7290083f2c5be238fdb230fde62c2a01a000a36c14014820aae",
        "tree_digest": "c78ad0b4991b48d7b6ccd86b70da7658c1c79e0906085b636920e7d49850d8f9",
    },
}
LIMITS = {
    "parse_max_input_bytes": 1048576,
    "parse_max_nesting_depth": 64,
    "parse_max_nodes": 8192,
    "parse_max_token_bytes": 8192,
    "profile_max_depth": 16,
    "profile_max_entries": 256,
    "profile_max_metadata_forms": 2048,
    "profile_max_selected": 64,
    "profile_max_value_bytes": 4096,
}


class ObservationError(RuntimeError):
    pass


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ObservationError(reason)


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ObservationError(f"load_failed:{path}") from error
    _require(isinstance(value, dict), "document_not_mapping")
    return value


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise ObservationError(f"read_failed:{path}") from error


def validate(path: Path | None = None) -> dict[str, Any]:
    path = EVIDENCE if path is None else path
    document = _load(path)
    _require(document.get("schema") == SCHEMA, "schema_invalid")
    _require(document.get("status") == STATUS, "status_invalid")
    _require(document.get("decision") == DECISION, "decision_invalid")
    _require(
        document.get("policy") == "sipi.p4b-02.ami-parameter-subset.v1.host-forwarded-only",
        "policy_invalid",
    )
    _require(
        document.get("tree_policy") == "sipi.p4b-02.ami-parameter-tree.v1.selected-ads-profile",
        "tree_policy_invalid",
    )
    _require(document.get("fresh_reads") == 2, "fresh_read_count_invalid")
    profiles = document.get("profiles")
    _require(isinstance(profiles, dict), "profiles_missing")
    for role, expected in EXPECTED.items():
        profile = profiles.get(role)
        _require(isinstance(profile, dict), f"profile_missing:{role}")
        for key, value in expected.items():
            _require(profile.get(key) == value, f"{role}_{key}_invalid")
        _require(profile.get("limits") == LIMITS, f"{role}_limits_invalid")

    runtime = document.get("runtime_observation")
    _require(
        runtime
        == {
            "ami_get_wave_invoked": False,
            "ami_init_invoked": False,
            "dll_loaded": False,
            "selected_values_emitted": False,
        },
        "runtime_claim_invalid",
    )
    _require(
        document.get("non_claims")
        == [
            "host_forwarded_subset_identity_only",
            "vendor_dll_consumption_unproven",
            "ami_runtime_acceptance_unproven",
            "rights_and_dynamic_closure_not_established",
        ],
        "non_claims_invalid",
    )
    serialized = json.dumps(document, sort_keys=True)
    _require("value_token" not in serialized and "default_token" not in serialized, "raw_value_leak")
    return {
        "schema": SCHEMA,
        "valid": True,
        "status": STATUS,
        "tx_selected_count": EXPECTED["tx"]["selected_count"],
        "rx_selected_count": EXPECTED["rx"]["selected_count"],
        "dll_loaded": False,
        "ami_init_invoked": False,
        "ami_get_wave_invoked": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, default=EVIDENCE)
    args = parser.parse_args()
    try:
        print(json.dumps(validate(args.evidence), sort_keys=True))
        return 0
    except ObservationError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    sys.exit(main())
