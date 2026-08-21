"""Verify the hash-bound, external-only P4A-03d asset consumer observation."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "baselines" / "p4a-03d-exact-asset-structural-consumer-evidence.v1.yaml"
SCHEMA = "sipi.p4a-03d.exact-asset-structural-consumer-evidence.v1"


class StructuralConsumerError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise StructuralConsumerError("document_not_mapping")
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise StructuralConsumerError(reason)


def _git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(ROOT), *args],
            check=True,
            capture_output=True,
            text=True,
            encoding="ascii",
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError) as error:
        raise StructuralConsumerError("source_git_identity_unavailable") from error


def verify_document(document: dict[str, Any]) -> dict[str, Any]:
    _require(document.get("schema") == SCHEMA, "schema_mismatch")
    _require(document.get("status") == "external_only_hash_bound_structural_consumer_observation", "status_mismatch")
    custody = document.get("custody", {})
    _require(custody.get("asset_path_is_product_policy") is False, "product_policy_claim")
    _require(custody.get("electrical_behavior_evaluated") is False, "electrical_claim")
    _require(custody.get("external_profile_admitted") is False, "profile_claim")
    _require(custody.get("runtime_invoked") is False, "runtime_claim")
    source = document.get("source_contract", {})
    _require(source.get("repository") == "SIPI-sim-agent", "source_repository_drift")
    _require(
        source.get("commit") == "b6071779d8164e685d15ddf45c19dcb6b2553c78"
        and source.get("tree") == "5f4859d40e9cfedb4445c0cc17e3bd4b1dfecdaa",
        "source_commit_drift",
    )
    _require(source.get("parser_path") == "crates/sipi-ibis/src/lib.rs", "parser_path_drift")
    _require(source.get("consumer_path") == "crates/sipi-ibis/tests/p4a_03d_model_declaration_runner.rs", "consumer_path_drift")
    _require(source.get("consumer_policy") == "sipi.p4a-03d.model-declaration.v1.typed-declaration-only", "consumer_policy_drift")
    _require(_git("cat-file", "-t", source["commit"]) == "commit", "source_commit_missing")
    _require(
        _git("rev-parse", f'{source["commit"]}^{{tree}}') == source["tree"],
        "source_tree_drift",
    )
    for path_key, blob_key in (("parser_path", "parser_blob"), ("consumer_path", "consumer_blob")):
        _require(
            _git("rev-parse", f'{source["commit"]}:{source[path_key]}') == source[blob_key]
            and _git("cat-file", "-t", source[blob_key]) == "blob",
            f"source_blob_drift:{path_key}",
        )
    asset = document.get("asset", {})
    _require(asset.get("relative_path") == "as4c512m16md4v-053bin.ibs", "asset_path_drift")
    _require(asset.get("byte_length") == 4215925, "asset_length_drift")
    _require(asset.get("sha256") == "d72cf62b56d67d30f4004f56ea3b79b4cb1241615692b147682f47540e615a0b", "asset_hash_drift")
    observation = document.get("consumer_observation", {})
    _require(observation.get("declaration_count") == 67, "declaration_count_drift")
    _require(observation.get("model_types") == {"Input": 27, "IO": 40}, "model_type_drift")
    _require(observation.get("policy") == source.get("consumer_policy"), "observation_policy_drift")
    output = observation.get("output", {})
    _require(output.get("external_only") is True, "output_custody_drift")
    _require(output.get("byte_length") == 1486, "output_length_drift")
    _require(output.get("sha256") == "8caca28058b7fc453f2459cd08dba42edb112d2abde0657ffc0c3c9e71732f2d", "output_hash_drift")
    non_claims = set(document.get("non_claims", []))
    for required in ("not_required_keyword_profile_acceptance", "not_electrical_behavior", "not_runtime_or_release_evidence"):
        _require(required in non_claims, f"non_claim_missing:{required}")
    return {"valid": True, "dynamic_checked": False}


def _contained(root: Path, relative: str) -> Path:
    root = root.resolve()
    path = (root / relative).resolve()
    _require(path == root / relative and path.is_file(), "asset_path_invalid_or_escaping")
    return path


def verify_external_inputs(document: dict[str, Any], asset_root: Path, runner_output: Path) -> dict[str, Any]:
    verify_document(document)
    asset = document["asset"]
    asset_path = _contained(asset_root, asset["relative_path"])
    output_path = runner_output.resolve()
    _require(output_path.is_file(), "runner_output_missing")
    _require(asset_path.stat().st_size == asset["byte_length"], "asset_length_mismatch")
    _require(sha256(asset_path) == asset["sha256"], "asset_hash_mismatch")
    output = document["consumer_observation"]["output"]
    _require(output_path.stat().st_size == output["byte_length"], "runner_output_length_mismatch")
    _require(sha256(output_path) == output["sha256"], "runner_output_hash_mismatch")
    try:
        report = json.loads(output_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise StructuralConsumerError("runner_output_invalid_json") from error
    _require(report == {"declaration_count": 67, "model_names": report.get("model_names"), "model_types": {"IO": 40, "Input": 27}, "policy": document["consumer_observation"]["policy"]}, "runner_output_fields_drift")
    _require(isinstance(report["model_names"], list) and len(report["model_names"]) == 67, "runner_model_names_invalid")
    return {"valid": True, "dynamic_checked": True}


def validate(asset_root: Path | None = None, runner_output: Path | None = None) -> dict[str, Any]:
    document = load_yaml(EVIDENCE)
    _require((asset_root is None) == (runner_output is None), "dynamic_inputs_must_be_complete")
    if asset_root is None:
        return verify_document(document)
    return verify_external_inputs(document, asset_root.resolve(), runner_output.resolve())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset-root", type=Path)
    parser.add_argument("--runner-output", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(validate(args.asset_root, args.runner_output), sort_keys=True))
        return 0
    except StructuralConsumerError as error:
        print(json.dumps({"valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
