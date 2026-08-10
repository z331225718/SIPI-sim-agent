"""Verify an external-only MATLAB runner observation without promoting R480."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import yaml

from observe_com_r480_matlab_runner import SCHEMA as REPORT_SCHEMA
from observe_com_r480_matlab_runner import ProbeError, validate_report


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.com.r480.matlab-runner-capability-preflight.v1"
PROFILE_ID = "com-r480-envelope-v1"
P5B_PATH = "docs/baselines/com-r480-reference-availability-preflight.v1.yaml"
P5B_SHA256 = "ca44d298350f1ab2c4d8f270450359290d4ec28868a6735508c7efe5b6b4a582"
EXPECTED_REPORT_SHA256 = "f6b1fc48d2749b22c6d2cb4c0ff0b9edfa7131237a5f06ad2cbec1872aa2df16"


class VerificationError(RuntimeError):
    pass


def _outside_root(path: Path) -> bool:
    try:
        path.resolve().relative_to(ROOT.resolve())
    except ValueError:
        return True
    return False


def _load_yaml(path: Path) -> dict:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise VerificationError("manifest_not_yaml_object")
    return value


def verify(manifest: object, report_path: Path) -> dict:
    if not _outside_root(report_path):
        raise VerificationError("report_must_remain_external")
    if not isinstance(manifest, dict) or set(manifest) != {"schema", "profile", "runner_observation", "reference_gate", "non_claims"}:
        raise VerificationError("manifest_shape_invalid")
    if manifest["schema"] != SCHEMA:
        raise VerificationError("manifest_schema_invalid")
    if manifest["profile"] != {"id": PROFILE_ID, "required": True, "availability_preflight": {"path": P5B_PATH, "content_sha256": P5B_SHA256}}:
        raise VerificationError("profile_binding_invalid")
    report_bytes = report_path.read_bytes()
    if hashlib.sha256(report_bytes).hexdigest() != EXPECTED_REPORT_SHA256:
        raise VerificationError("external_report_hash_mismatch")
    try:
        report = json.loads(report_bytes)
        validate_report(report)
    except (json.JSONDecodeError, ProbeError) as error:
        raise VerificationError("external_report_invalid") from error
    observation = manifest["runner_observation"]
    expected_observation = {
        "status": "indeterminate_startup_isolation_unproven",
        "external_report": {"schema": REPORT_SCHEMA, "content_sha256": EXPECTED_REPORT_SHA256, "custody": "external_only"},
        "runner": report["runner"],
        "builtin_identity": report["result"]["observed_identity"],
        "probe": {key: report["probe"][key] for key in ("id", "template_sha256", "timeout_seconds", "startup_isolation")},
        "result": {key: report["result"][key] for key in ("timed_out", "sentinel_observed", "license_runtime_observation")},
    }
    if observation != expected_observation:
        raise VerificationError("runner_observation_mismatch")
    expected_gate = {
        "status": "reference_generation_blocked",
        "remaining_blockers": [
            "startup_isolation_unproven",
            "oracle_authorization_unestablished",
            "exact_normalized_input_missing",
            "parameter_defaults_not_observed",
            "reference_metric_bundle_missing",
            "tolerance_and_alignment_policy_missing",
        ],
        "product_runtime": "forbidden",
        "product_api_created": False,
    }
    if manifest["reference_gate"] != expected_gate:
        raise VerificationError("reference_gate_not_fail_closed")
    if not isinstance(manifest["non_claims"], list) or len(manifest["non_claims"]) != 3 or not all(isinstance(item, str) and item for item in manifest["non_claims"]):
        raise VerificationError("non_claims_invalid")
    return {"valid": True, "profile_id": PROFILE_ID, "runner_status": "indeterminate", "reference_generation_status": "blocked", "product_api_created": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "docs" / "baselines" / "com-r480-matlab-runner-capability-preflight.v1.yaml")
    parser.add_argument("--external-report", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = verify(_load_yaml(args.manifest), args.external_report)
    except (OSError, VerificationError, yaml.YAMLError) as error:
        result = {"valid": False, "reason": str(error)}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
