"""Verify the external-only required RC pulse TRAN acceptance contract."""

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
SCHEMA = "sipi.tran.rc-pulse.acceptance.v1"
SHA1_LENGTH = 40
SHA256_LENGTH = 64
EXPECTED_OBSERVABLES = ["time_axis_seconds", "voltage_in_volts", "voltage_out_volts"]
EXPECTED_OUT_OF_SCOPE = ["op", "ac", "other_nodes", "measurements", "netlist_text_compatibility", "engine_cli_route"]
EXPECTED_MISSING_INPUTS = ["sample_alignment", "time_tolerance", "voltage_tolerances", "initial_condition_policy", "oracle_environment"]


def _exact(value: object, keys: set[str]) -> bool:
    return isinstance(value, dict) and set(value) == keys


def _hex(value: object, length: int) -> bool:
    return isinstance(value, str) and len(value) == length and all(char in "0123456789abcdef" for char in value)


def _safe_path(value: object) -> bool:
    return isinstance(value, str) and bool(value) and "\\" not in value and not value.startswith("/") and not (len(value) >= 2 and value[0].isalpha() and value[1] == ":") and ".." not in value.split("/")


def _git(root: Path, *args: str, text: bool = True) -> str | bytes:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=text).stdout


def _load(path: Path) -> dict:
    if yaml is None:
        raise RuntimeError("pyyaml is unavailable")
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise RuntimeError("acceptance contract must be a YAML object")
    return document


def _verify_external_object(source: dict, source_root: Path, blockers: list[str]) -> bool:
    try:
        origin = str(_git(source_root, "remote", "get-url", "origin")).strip()
        tree = str(_git(source_root, "rev-parse", f"{source['commit']}^{{tree}}")).strip()
        blob = str(_git(source_root, "rev-parse", f"{source['commit']}:{source['path']}")).strip()
        payload = _git(source_root, "cat-file", "blob", blob, text=False)
    except (OSError, subprocess.CalledProcessError):
        blockers.append("external source Git object is unavailable")
        return False
    if origin != source["canonical_origin"]:
        blockers.append("external source origin mismatch")
    if tree != source["tree"]:
        blockers.append("external source tree mismatch")
    if blob != source["git_blob"] or hashlib.sha256(payload).hexdigest() != source["content_sha256"]:
        blockers.append("external source fixture identity mismatch")
    return True


def verify_document(document: object, source_root: Path | None = None, *, require_ready: bool = False) -> dict:
    blockers: list[str] = []
    required_top = {"schema", "selection", "source", "scope", "oracle", "acceptance", "non_claims"}
    if not _exact(document, required_top):
        return {"valid": False, "blockers": ["acceptance contract has unknown or missing top-level fields"]}
    if document["schema"] != SCHEMA:
        return {"valid": False, "blockers": ["acceptance contract schema mismatch"]}

    selection = document["selection"]
    if not _exact(selection, {"profile_id", "capability", "required", "status", "decision_ref"}) or selection != {
        "profile_id": "tran-rc-pulse-v1",
        "capability": "tran",
        "required": True,
        "status": "user_selected",
        "decision_ref": selection.get("decision_ref") if isinstance(selection, dict) else None,
    } or not isinstance(selection.get("decision_ref"), str) or not selection["decision_ref"]:
        blockers.append("selection is invalid")

    source = document["source"]
    source_keys = {"canonical_origin", "commit", "tree", "object_format", "path", "git_blob", "content_sha256", "redistribution", "license_evidence"}
    if not _exact(source, source_keys) or not isinstance(source.get("canonical_origin"), str) or not source["canonical_origin"].startswith("https://") or not _hex(source.get("commit"), SHA1_LENGTH) or not _hex(source.get("tree"), SHA1_LENGTH) or source.get("object_format") != "sha1" or not _safe_path(source.get("path")) or not _hex(source.get("git_blob"), SHA1_LENGTH) or not _hex(source.get("content_sha256"), SHA256_LENGTH) or source.get("redistribution") != "external_only" or not _safe_path(source.get("license_evidence")):
        blockers.append("source anchor is invalid")

    scope = document["scope"]
    if not _exact(scope, {"analysis", "observables", "out_of_scope"}) or scope.get("analysis") != "tran" or scope.get("observables") != EXPECTED_OBSERVABLES or scope.get("out_of_scope") != EXPECTED_OUT_OF_SCOPE:
        blockers.append("scope is invalid")

    oracle = document["oracle"]
    if not _exact(oracle, {"mode", "execution_status", "product_fallback", "environment_status"}) or oracle != {
        "mode": "external_git_object_only",
        "execution_status": "not_invoked",
        "product_fallback": "forbidden",
        "environment_status": "pending_owner_confirmation",
    }:
        blockers.append("oracle boundary is invalid")

    acceptance = document["acceptance"]
    acceptance_keys = {"status", "acceptance_ready", "sample_alignment", "time_axis", "voltage_in", "voltage_out", "failure_handling", "missing_owner_inputs"}
    time_keys = {"comparison", "tolerance_seconds"}
    voltage_keys = {"comparison", "absolute_tolerance_volts", "relative_tolerance"}
    pending = (
        _exact(acceptance, acceptance_keys)
        and acceptance.get("status") == "blocked_missing_tolerance"
        and acceptance.get("acceptance_ready") is False
        and acceptance.get("sample_alignment") == "pending_owner_confirmation"
        and _exact(acceptance.get("time_axis"), time_keys)
        and acceptance["time_axis"] == {"comparison": "pending_owner_confirmation", "tolerance_seconds": None}
        and _exact(acceptance.get("voltage_in"), voltage_keys)
        and _exact(acceptance.get("voltage_out"), voltage_keys)
        and acceptance["voltage_in"] == {"comparison": "pending_owner_confirmation", "absolute_tolerance_volts": None, "relative_tolerance": None}
        and acceptance["voltage_out"] == {"comparison": "pending_owner_confirmation", "absolute_tolerance_volts": None, "relative_tolerance": None}
        and acceptance.get("failure_handling") == "pending_owner_confirmation"
        and acceptance.get("missing_owner_inputs") == EXPECTED_MISSING_INPUTS
    )
    if not pending:
        blockers.append("acceptance state is invalid or prematurely ready")
    if require_ready:
        blockers.append("acceptance is blocked_missing_tolerance")

    non_claims = document["non_claims"]
    if not isinstance(non_claims, list) or not non_claims or not all(isinstance(item, str) and item for item in non_claims):
        blockers.append("non_claims are invalid")
    checked = False
    if source_root is None:
        blockers.append("external source root is required")
    elif isinstance(source, dict):
        checked = _verify_external_object(source, source_root, blockers)
    return {
        "valid": not blockers,
        "profile_id": "tran-rc-pulse-v1",
        "required": True,
        "acceptance_ready": False,
        "source_git_object_checked": checked,
        "blockers": blockers,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=ROOT / "docs" / "baselines" / "tran-rc-pulse-acceptance.v1.yaml")
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--require-ready", action="store_true")
    args = parser.parse_args()
    try:
        report = verify_document(_load(args.contract), args.source_root, require_ready=args.require_ready)
    except (OSError, RuntimeError) as error:
        print(json.dumps({"valid": False, "blockers": [str(error)]}, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
