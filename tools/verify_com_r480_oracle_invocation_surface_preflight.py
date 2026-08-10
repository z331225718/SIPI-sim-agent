"""Verify the external-only static R480 oracle invocation-surface preflight."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import yaml

from observe_com_r480_oracle_invocation_surface import ObservationError, SCHEMA as REPORT_SCHEMA, validate_report


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.com.r480.oracle-invocation-surface-preflight.v1"
PROFILE_ID = "com-r480-envelope-v1"
REPORT_SHA256 = "b4fd1ff3600463c2761cb30ff28f0ace258eada66be880ff0a74a06ccb66f44f"


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
    if not isinstance(manifest, dict) or set(manifest) != {"schema", "profile", "observation", "execution", "reference_gate", "non_claims"}:
        raise VerificationError("manifest_shape_invalid")
    if manifest["schema"] != SCHEMA:
        raise VerificationError("manifest_schema_invalid")
    profile = manifest["profile"]
    if not isinstance(profile, dict) or profile.get("id") != PROFILE_ID or not isinstance(profile.get("runner_capability_preflight"), dict) or set(profile["runner_capability_preflight"]) != {"path", "content_sha256"}:
        raise VerificationError("profile_binding_invalid")
    if profile["runner_capability_preflight"]["path"] != "docs/baselines/com-r480-matlab-runner-capability-preflight.v1.yaml" or not isinstance(profile["runner_capability_preflight"]["content_sha256"], str) or len(profile["runner_capability_preflight"]["content_sha256"]) != 64:
        raise VerificationError("runner_preflight_binding_invalid")
    bound_preflight = ROOT / profile["runner_capability_preflight"]["path"]
    if not bound_preflight.is_file() or hashlib.sha256(bound_preflight.read_bytes()).hexdigest() != profile["runner_capability_preflight"]["content_sha256"]:
        raise VerificationError("runner_preflight_hash_mismatch")
    raw = report_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != REPORT_SHA256:
        raise VerificationError("external_report_hash_mismatch")
    try:
        report = json.loads(raw)
        validate_report(report)
    except (json.JSONDecodeError, ObservationError) as error:
        raise VerificationError("external_report_invalid") from error
    observation = manifest["observation"]
    expected = {
        "status": "runner_interface_partially_observed",
        "external_report": {"schema": REPORT_SCHEMA, "content_sha256": REPORT_SHA256, "custody": "external_only"},
        "tool": report["tool"],
        "surface": report["surface"],
    }
    if observation != expected:
        raise VerificationError("observation_mismatch")
    if manifest["execution"] != report["execution"]:
        raise VerificationError("execution_mismatch")
    expected_gate = {
        "status": "reference_generation_blocked",
        "remaining_blockers": ["startup_isolation_unproven", "oracle_execution_amendment_missing", "exact_normalized_input_missing", "parameter_defaults_not_observed", "reference_metric_bundle_missing", "tolerance_and_alignment_policy_missing"],
        "product_api_created": False,
    }
    if manifest["reference_gate"] != expected_gate:
        raise VerificationError("reference_gate_not_fail_closed")
    if not isinstance(manifest["non_claims"], list) or len(manifest["non_claims"]) != 3 or not all(isinstance(item, str) and item for item in manifest["non_claims"]):
        raise VerificationError("non_claims_invalid")
    return {"valid": True, "profile_id": PROFILE_ID, "runner_interface_status": "partially_observed", "reference_generation_status": "blocked", "execution_invoked": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "docs" / "baselines" / "com-r480-oracle-invocation-surface-preflight.v1.yaml")
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
