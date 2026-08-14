"""Verify the hash-only selected-S4P truncation observation evidence."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs/baselines/p3c-selected-s4p-truncation-observation-evidence.v1.yaml"
SCHEMA = "sipi.p3c-selected-s4p-truncation-observation-evidence.v1"
HEX = set("0123456789abcdef")


class VerificationError(ValueError):
    pass


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hex(value: object, length: int) -> bool:
    return isinstance(value, str) and len(value) == length and not (set(value) - HEX)


def _archive_inventory(paths: set[str]) -> dict[str, str]:
    archive = subprocess.run(
        ["git", "archive", "--format=tar", "HEAD", "--", *sorted(paths)],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if archive.returncode:
        raise VerificationError("truncation_product_source_drift")
    with tempfile.TemporaryDirectory() as temporary:
        try:
            with tarfile.open(fileobj=io.BytesIO(archive.stdout), mode="r:") as payload:
                payload.extractall(temporary, filter="data")
        except tarfile.TarError as error:
            raise VerificationError("truncation_product_source_drift") from error
        return {path: _digest(Path(temporary) / path) for path in paths}


def verify_document(document: object) -> dict[str, object]:
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise VerificationError("truncation_schema_invalid")
    if document.get("status") != "external_selected_s4p_truncation_observed_causal_fir_and_candidate_route_pending":
        raise VerificationError("truncation_status_invalid")
    observation = document.get("external_observation")
    required = {"schema", "status", "custody", "report_path_retained", "report_byte_length", "report_content_sha256", "clean_archive_commit", "selected_source", "source_identity_checks", "fresh_custody_runs", "manifest_sha256s", "record_count", "outcome", "cleanup_status", "runner", "product_source_inventory"}
    if not isinstance(observation, dict) or set(observation) != required:
        raise VerificationError("truncation_observation_shape_invalid")
    if observation.get("schema") != "sipi.p3c.sealed-selected-s4p-truncation-runner.v1" or observation.get("status") != "observed" or observation.get("custody") != "external_only" or observation.get("report_path_retained") is not False or observation.get("report_byte_length") != 1196 or not _hex(observation.get("report_content_sha256"), 64) or not _hex(observation.get("clean_archive_commit"), 40) or observation.get("selected_source") != {"byte_length": 1834156, "sha256": "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47"} or observation.get("source_identity_checks") != "before_stage_after_equal" or observation.get("fresh_custody_runs") != 2 or observation.get("record_count") != 2002 or observation.get("cleanup_status") != "complete":
        raise VerificationError("truncation_observation_identity_invalid")
    manifests = observation.get("manifest_sha256s")
    if not isinstance(manifests, list) or len(manifests) != 2 or manifests[0] == manifests[1] or any(not _hex(value, 64) for value in manifests):
        raise VerificationError("truncation_fresh_custody_invalid")
    outcome = observation.get("outcome")
    expected_outcome = {"truncation_status", "uniform_bin_count", "causal_sample_count", "iteration_count", "retained_sample_count", "sample_interval_bits", "dropped_l2_over_total_l2_bits", "tail", "truncated_response_sha256"}
    if not isinstance(outcome, dict) or set(outcome) != expected_outcome or outcome != {"truncation_status": "admitted", "uniform_bin_count": 25601, "causal_sample_count": 51200, "iteration_count": 32, "retained_sample_count": 10871, "sample_interval_bits": "3d712e0be826d695", "dropped_l2_over_total_l2_bits": "3f625ac4b27fdb73", "tail": "nonzero_tail", "truncated_response_sha256": "c0b21cfe4d61ac3ce33a5695b198c0d4bf9ae1d80227dcc5b14a9ab37d9adf0b"}:
        raise VerificationError("truncation_outcome_invalid")
    runner = observation.get("runner")
    if not isinstance(runner, dict) or set(runner) != {"source_sha256", "report_sha256"} or any(not _hex(value, 64) for value in runner.values()) or runner["report_sha256"] != observation["report_content_sha256"]:
        raise VerificationError("truncation_runner_invalid")
    inventory = observation.get("product_source_inventory")
    if not isinstance(inventory, dict) or not inventory or any(not isinstance(path, str) or not _hex(value, 64) for path, value in inventory.items()):
        raise VerificationError("truncation_inventory_invalid")
    admission = document.get("admission")
    true_keys = {"external_static_custody_observed", "selected_external_s4p_static_admitted", "selected_interpolation_invoked", "selected_interpolation_admitted", "selected_external_uniform_spectrum_observed", "external_selected_raw_periodic_transform_invoked", "external_selected_raw_periodic_transform_admitted", "external_selected_raw_periodic_response_observed", "external_selected_causality_invoked", "external_selected_causality_admitted", "external_selected_causality_observed", "external_selected_truncation_invoked", "external_selected_truncation_admitted", "external_selected_truncation_observed"}
    false_keys = {"causal_impulse_admitted", "delay_extraction_implemented", "passivity_repair_implemented", "linear_convolution_implemented", "candidate_waveform_generated", "external_reference_binding_evaluated", "candidate_metric_acceptance_evaluated", "accepted_receiver", "product_runtime_invoked", "p4b_ami_runtime_invoked", "p5_reference_evaluated", "release_ledger_promoted"}
    if not isinstance(admission, dict) or set(admission) != true_keys | false_keys or any(admission.get(key) is not True for key in true_keys) or any(admission.get(key) is not False for key in false_keys):
        raise VerificationError("truncation_gate_promotion_invalid")
    blockers, claims = document.get("blockers"), document.get("non_claims")
    if not isinstance(blockers, list) or "bounded_causality_response_not_admitted_as_causal_impulse_or_fir" not in blockers or "linear_convolution_and_prbs9_source_policy_not_implemented" not in blockers or not isinstance(claims, list) or not any("not an admitted causal impulse" in value for value in claims if isinstance(value, str)):
        raise VerificationError("truncation_nonclaim_or_blocker_relaxed")
    return {"valid": True, "truncation_observed": True, "release_admitted": False}


def verify_current_product_identity(document: dict[str, object]) -> None:
    observation = document["external_observation"]
    assert isinstance(observation, dict)
    inventory = observation["product_source_inventory"]
    assert isinstance(inventory, dict)
    if _archive_inventory(set(inventory)) != inventory:
        raise VerificationError("truncation_product_source_drift")


def main() -> int:
    try:
        document = yaml.safe_load(DEFAULT.read_text(encoding="utf-8"))
        result = verify_document(document)
        verify_current_product_identity(document)
    except (OSError, ValueError, yaml.YAMLError, VerificationError) as error:
        print(f"selected_s4p_truncation_observation_failed:{error}", file=sys.stderr)
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
