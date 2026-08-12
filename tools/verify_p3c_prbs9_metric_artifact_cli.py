"""Fail closed on the P3C PRBS9 sealed-artifact metric CLI boundary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs/baselines/p3c-prbs9-metric-artifact-cli.v1.yaml"
PUBLICATION = ROOT / "docs/baselines/release-capability-publication.v1.yaml"
SCHEMA = "sipi.p3c-prbs9-metric-artifact-cli.v1"
CONTRACT_SHA256 = "f47329b6ddda01cbcde1f24e21cb93e03f8ef6139ea2d43ff74cad9e2049d2b5"


class ArtifactCliError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ArtifactCliError("document_not_mapping")
    return value


def source(root: Path) -> str:
    return (root / "crates/sipi-cli/src/main.rs").read_text(encoding="utf-8")


def verify_document(document: object, *, root: Path = ROOT) -> dict[str, Any]:
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise ArtifactCliError("schema_invalid")
    if document.get("status") != "product_owned_sealed_artifact_metric_route_specified_not_profile_accepted":
        raise ArtifactCliError("status_invalid")
    command = document.get("command")
    if command != {
        "id": "compare.prbs9-metrics.run",
        "route": ["compare", "prbs9-metrics"],
        "stdin_schema": "sipi.compare.prbs9-metric-artifacts-request.v1",
        "contract_v2_content_sha256": CONTRACT_SHA256,
        "artifact_root_assumption": "caller_selected_sipi_published_root_no_hostile_concurrent_writer",
    }:
        raise ArtifactCliError("command_binding_drift")
    if document.get("request_boundary") != {
        "fields": ["schema", "contract_sha256", "reference", "candidate"],
        "reference_candidate_fields": ["artifact_id", "manifest_sha256"],
        "deny_unknown_fields": True,
        "forbidden": ["waveform_values", "path", "url", "axis", "seed", "tolerance", "alignment", "profile_override"],
    }:
        raise ArtifactCliError("request_boundary_drift")
    if document.get("artifact_boundary") != {
        "exact_files": ["success.json", "waveform.json", "waveform.f64le"],
        "manifest_maximum_bytes": 65536,
        "waveform_metadata_maximum_bytes": 4096,
        "waveform_payload_exact_bytes": 392448,
        "artifact_total_payload_maximum_bytes": 396544,
        "quantity": "differential_voltage",
        "unit": "volts_differential",
        "timebase_profile": "prbs9-v2-32gtps-osr32-three-period-half-open",
        "sample_count": 49056,
        "encoding": "ieee754-binary64-little-endian",
        "rejects": ["symlink_or_reparse", "path_escape", "unsealed", "extra_or_missing_file", "manifest_drift", "payload_hash_or_length_drift", "nonfinite_sample"],
    }:
        raise ArtifactCliError("artifact_boundary_drift")
    expected_admission = {
        "external_ads_runtime_observed": False,
        "candidate_waveform_eye_jitter_acceptance_evaluated": False,
        "accepted_receiver": False,
        "acceptance_ready": False,
        "promotion_eligible": False,
        "product_runtime_invoked": False,
        "p4b_ami_runtime_invoked": False,
        "release_ledger_promoted": False,
    }
    if document.get("admission") != expected_admission:
        raise ArtifactCliError("admission_gate_drift")
    source_text = source(root)
    required = (
        "compare.prbs9-metrics.run",
        "parse_prbs9_metric_artifacts_request_v1",
        "consume_exact_verified_v1",
        "(\"waveform.json\", 4096),\n                (\"waveform.f64le\", PRBS9_WAVEFORM_ARTIFACT_BYTE_LENGTH_V1),",
        "VerifiedConsumptionPolicyV1::try_new(65_536, 396_544)",
        "parse_prbs9_waveform_artifact_v1",
        "f64::from_le_bytes",
        "compare_prbs9_metrics_v2",
        "external_reference_binding\\\":\\\"not_evaluated",
        "external_profile_acceptance\\\":\\\"not_evaluated",
    )
    if any(token not in source_text for token in required):
        raise ArtifactCliError("implementation_binding_drift")
    publication = json.loads((root / PUBLICATION.relative_to(ROOT)).read_text(encoding="utf-8"))
    row = next((item for item in publication.get("rows", []) if item.get("id") == "prbs9-metric-artifact-compare"), None)
    if not isinstance(row, dict) or row.get("acceptance_state") != "specified" or row.get("external_oracle") is not False:
        raise ArtifactCliError("publication_gate_drift")
    required_blockers = {
        "caller_supplied_artifact_identity_only",
        "external_reference_binding_not_implemented",
        "candidate_profile_acceptance_not_evaluated",
        "accepted_receiver_stage_missing",
    }
    if not required_blockers.issubset(set(row.get("blockers", []))):
        raise ArtifactCliError("publication_gate_drift")
    return {"schema": SCHEMA, "status": document["status"], "release_promoted": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=DEFAULT)
    arguments = parser.parse_args(argv)
    try:
        result = verify_document(load_yaml(arguments.baseline))
    except (OSError, ValueError, yaml.YAMLError, ArtifactCliError) as error:
        print(json.dumps({"schema": SCHEMA, "status": "rejected", "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
