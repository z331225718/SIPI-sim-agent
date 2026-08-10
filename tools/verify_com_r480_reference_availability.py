"""Verify the fail-closed R480 authoritative-reference availability preflight."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.com.r480.reference-availability-preflight.v1"
PROFILE_ID = "com-r480-envelope-v1"
ORIGIN = "https://github.com/z331225718/agent-com.git"
SOURCE_PATH = "schemas/r480-capability-envelope-v1.yaml"
CONTRACT_PATH = "docs/baselines/com-r480-acceptance.v1.yaml"
CONTRACT_SHA256 = "e90fca0d14968a04e09df90cd8bd4fcc7f749abfa07ad2b4b29dc297351ef03b"
EXPECTED_FIELDS = [
    "normalized_input_digest",
    "channel_role_manifest_digest",
    "parameter_set_digest",
    "oracle_runtime_identity",
    "reference_metric_bundle_hash",
    "tolerance_and_alignment_policy",
]
EXPECTED_BLOCKERS = [
    "oracle_runner_not_observed",
    "oracle_toolchain_not_observed",
    "exact_normalized_input_missing",
    "parameter_defaults_not_observed",
    "reference_metric_bundle_missing",
    "tolerance_and_alignment_policy_missing",
]


class PreflightError(RuntimeError):
    pass


def _exact(value: object, keys: set[str]) -> bool:
    return isinstance(value, dict) and set(value) == keys


def _hex(value: object, length: int) -> bool:
    return isinstance(value, str) and len(value) == length and all(char in "0123456789abcdef" for char in value)


def _load(path: Path) -> dict:
    if yaml is None:
        raise PreflightError("pyyaml_unavailable")
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise PreflightError("preflight_not_yaml_object")
    return value


def _git(root: Path, *args: str, text: bool = True) -> str | bytes:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=text).stdout


def _verify_source(source: dict, source_root: Path, blockers: list[str]) -> bool:
    try:
        if str(_git(source_root, "status", "--porcelain")).strip():
            blockers.append("external_source_worktree_not_clean")
            return False
        origin = str(_git(source_root, "remote", "get-url", "origin")).strip()
        commit = str(_git(source_root, "rev-parse", "HEAD")).strip()
        tree = str(_git(source_root, "rev-parse", f"{source['commit']}^{{tree}}")).strip()
        blob = str(_git(source_root, "rev-parse", f"{source['commit']}:{source['path']}")).strip()
        payload = _git(source_root, "cat-file", "blob", blob, text=False)
    except (OSError, subprocess.CalledProcessError):
        blockers.append("external_source_git_object_unavailable")
        return False
    if origin != ORIGIN or commit != source["commit"] or tree != source["tree"]:
        blockers.append("external_source_anchor_mismatch")
    if blob != source["git_blob"] or hashlib.sha256(payload).hexdigest() != source["content_sha256"]:
        blockers.append("external_source_object_identity_mismatch")
    return True


def verify_document(document: object, source_root: Path | None = None) -> dict:
    blockers: list[str] = []
    top_keys = {"schema", "profile", "source", "availability", "expected_reference_bundle", "preflight", "non_claims"}
    if not _exact(document, top_keys):
        return {"valid": False, "blockers": ["preflight_has_unknown_or_missing_top_level_fields"]}
    if document["schema"] != SCHEMA:
        return {"valid": False, "blockers": ["preflight_schema_mismatch"]}

    profile = document["profile"]
    expected_profile = {
        "id": PROFILE_ID,
        "required": True,
        "required_by": "user-confirmed-2026-08-11-com-r480",
        "acceptance_contract": {"path": CONTRACT_PATH, "content_sha256": CONTRACT_SHA256},
    }
    if profile != expected_profile:
        blockers.append("profile_binding_invalid")

    source = document["source"]
    source_keys = {"canonical_origin", "commit", "tree", "object_format", "path", "git_blob", "content_sha256", "materialization"}
    if not _exact(source, source_keys):
        blockers.append("source_shape_invalid")
    elif not (
        source["canonical_origin"] == ORIGIN
        and _hex(source["commit"], 40)
        and _hex(source["tree"], 40)
        and source["object_format"] == "sha1"
        and source["path"] == SOURCE_PATH
        and _hex(source["git_blob"], 40)
        and _hex(source["content_sha256"], 64)
        and source["materialization"] == "external_clean_temp_only"
    ):
        blockers.append("source_identity_invalid")

    availability = document["availability"]
    expected_availability = {
        "oracle_runner": {"status": "not_observed", "authorization": "external_oracle_only_required", "product_runtime": "forbidden"},
        "oracle_toolchain": {"status": "not_observed", "authorization": "external_oracle_only_required"},
        "normalized_input": {"status": "missing", "custody": "external_only"},
        "parameter_defaults": {"status": "not_observed", "material_boundary": "external_quarantine_not_read"},
        "reference_metric_bundle": {"status": "missing", "custody": "external_only"},
        "tolerance_and_alignment_policy": {"status": "missing"},
    }
    if availability != expected_availability:
        blockers.append("availability_must_remain_unobserved_or_missing")

    bundle = document["expected_reference_bundle"]
    if bundle != {"custody": "external_only", "required_identity_fields": EXPECTED_FIELDS, "product_asset": "prohibited"}:
        blockers.append("reference_bundle_boundary_invalid")

    preflight = document["preflight"]
    if preflight != {"status": "reference_generation_blocked", "runtime_invoked": False, "product_api_created": False, "blockers": EXPECTED_BLOCKERS}:
        blockers.append("preflight_must_remain_blocked")

    non_claims = document["non_claims"]
    if not isinstance(non_claims, list) or len(non_claims) != 3 or not all(isinstance(item, str) and item for item in non_claims):
        blockers.append("non_claims_invalid")

    checked = False
    if source_root is None:
        blockers.append("external_source_root_required")
    elif _exact(source, source_keys):
        checked = _verify_source(source, source_root, blockers)

    return {
        "valid": not blockers,
        "profile_id": PROFILE_ID,
        "reference_generation_status": "blocked",
        "product_api_created": False,
        "runtime_invoked": False,
        "source_git_object_checked": checked,
        "blockers": blockers,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight", type=Path, default=ROOT / "docs" / "baselines" / "com-r480-reference-availability-preflight.v1.yaml")
    parser.add_argument("--source-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = verify_document(_load(args.preflight), args.source_root)
    except (OSError, PreflightError, subprocess.SubprocessError) as error:
        report = {"valid": False, "blockers": [str(error)]}
    print(json.dumps(report, sort_keys=True))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
