"""Verify the required, external-only COM R480 acceptance contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.com.r480.acceptance.v1"
PROFILE_ID = "com-r480-envelope-v1"
REQUIRED_BY = "user-confirmed-2026-08-11-com-r480"
SOURCE_PATH = "schemas/r480-capability-envelope-v1.yaml"
EXPECTED_INPUTS = ["normalized_input_digest", "channel_role_manifest_digest", "parameter_set_digest"]
EXPECTED_STAGES = ["selected_channel_evidence", "equalizer_selection_evidence", "pdf_axes_and_density"]
EXPECTED_METRICS = [
    {"id": "com_db", "unit": "dB", "comparison_level": "scalar"},
    {"id": "erl_db", "unit": "dB", "comparison_level": "scalar"},
    {"id": "td_iln_db", "unit": "dB", "comparison_level": "scalar"},
]
EXPECTED_REFERENCE_GAPS = ["exact_normalized_input", "oracle_runtime_identity", "reference_metric_bundle_hash", "tolerance_and_alignment_policy"]


def _exact(value: object, keys: set[str]) -> bool:
    return isinstance(value, dict) and set(value) == keys


def _hex(value: object, length: int) -> bool:
    return isinstance(value, str) and len(value) == length and all(char in "0123456789abcdef" for char in value)


def _safe_path(value: object) -> bool:
    return isinstance(value, str) and bool(value) and "\\" not in value and not value.startswith("/") and not (len(value) >= 2 and value[0].isalpha() and value[1] == ":") and ".." not in value.split("/")


def _load(path: Path) -> dict:
    if yaml is None:
        raise RuntimeError("pyyaml is unavailable")
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise RuntimeError("COM acceptance contract must be a YAML object")
    return document


def _git(root: Path, *args: str, text: bool = True) -> str | bytes:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=text).stdout


def _verify_source(source: dict, source_root: Path, blockers: list[str]) -> bool:
    try:
        origin = str(_git(source_root, "remote", "get-url", "origin")).strip()
        tree = str(_git(source_root, "rev-parse", f"{source['commit']}^{{tree}}")).strip()
        blob = str(_git(source_root, "rev-parse", f"{source['commit']}:{source['path']}")).strip()
        payload = _git(source_root, "cat-file", "blob", blob, text=False)
    except (OSError, subprocess.CalledProcessError):
        blockers.append("external source Git object is unavailable")
        return False
    if origin != source["canonical_origin"] or tree != source["tree"]:
        blockers.append("external source anchor mismatch")
    if blob != source["git_blob"] or hashlib.sha256(payload).hexdigest() != source["content_sha256"]:
        blockers.append("external source object identity mismatch")
    return True


def verify_document(document: object, source_root: Path | None = None) -> dict:
    blockers: list[str] = []
    top = {"schema", "selection", "external_oracle", "external_materials", "product_contract", "authoritative_reference", "comparison", "non_claims"}
    if not _exact(document, top):
        return {"valid": False, "blockers": ["contract has unknown or missing top-level fields"]}
    if document["schema"] != SCHEMA:
        return {"valid": False, "blockers": ["contract schema mismatch"]}
    selection = document["selection"]
    if selection != {"profile_id": PROFILE_ID, "capability": "com", "required": True, "status": "user_selected", "decision_ref": REQUIRED_BY}:
        blockers.append("selection is invalid")
    oracle = document["external_oracle"]
    source_keys = {"canonical_origin", "commit", "tree", "object_format", "path", "git_blob", "content_sha256", "redistribution"}
    if not _exact(oracle, {"source", "role", "materialization", "product_fallback"}) or not _exact(oracle.get("source"), source_keys):
        blockers.append("external oracle boundary is invalid")
        source = None
    else:
        source = oracle["source"]
        if not (source.get("canonical_origin") == "https://github.com/z331225718/agent-com.git" and _hex(source.get("commit"), 40) and _hex(source.get("tree"), 40) and source.get("object_format") == "sha1" and source.get("path") == SOURCE_PATH and _hex(source.get("git_blob"), 40) and _hex(source.get("content_sha256"), 64) and source.get("redistribution") == "external_only" and oracle.get("role") == "external_comparison_observation_only" and oracle.get("materialization") == "external_clean_temp_only" and oracle.get("product_fallback") == "forbidden"):
            blockers.append("external oracle source or boundary is invalid")
    if document["external_materials"] != {"matlab_source": "external_quarantine", "workbook_data": "external_quarantine", "fixture_data": "external_quarantine", "product_material": "prohibited"}:
        blockers.append("external material boundary is invalid")
    product = document["product_contract"]
    if not _exact(product, {"status", "input_identity", "stage_observables", "metric_bundle"}) or product != {"status": "independent_clean_room_spec_required", "input_identity": EXPECTED_INPUTS, "stage_observables": EXPECTED_STAGES, "metric_bundle": EXPECTED_METRICS}:
        blockers.append("product contract scope is invalid")
    reference = document["authoritative_reference"]
    if reference != {"status": "missing", "required_before_compare": EXPECTED_REFERENCE_GAPS, "external_custody": "required"}:
        blockers.append("authoritative reference state is invalid")
    comparison = document["comparison"]
    if comparison != {"status": "blocked_missing_authoritative_reference", "result_status": "not_run", "product_self_comparison": "forbidden"}:
        blockers.append("comparison must remain fail-closed")
    non_claims = document["non_claims"]
    if not isinstance(non_claims, list) or not non_claims or not all(isinstance(item, str) and item for item in non_claims):
        blockers.append("non_claims are invalid")
    checked = False
    if source_root is None:
        blockers.append("external source root is required")
    elif source is not None:
        checked = _verify_source(source, source_root, blockers)
    return {"valid": not blockers, "profile_id": PROFILE_ID, "required": True, "authoritative_reference_status": "missing", "comparison_ready": False, "source_git_object_checked": checked, "blockers": blockers}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=ROOT / "docs" / "baselines" / "com-r480-acceptance.v1.yaml")
    parser.add_argument("--source-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = verify_document(_load(args.contract), args.source_root)
    except (OSError, RuntimeError) as error:
        print(json.dumps({"valid": False, "blockers": [str(error)]}, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
