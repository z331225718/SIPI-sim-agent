"""Verify the hash-only selected-S4P PRBS9 candidate observation evidence."""

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
DEFAULT = ROOT / "docs/baselines/p3c-selected-s4p-candidate-observation-evidence.v1.yaml"
SCHEMA = "sipi.p3c-selected-s4p-candidate-observation-evidence.v1"
HEX = set("0123456789abcdef")


class VerificationError(ValueError):
    pass


def _hex(value: object, length: int) -> bool:
    return isinstance(value, str) and len(value) == length and not (set(value) - HEX)


def _archive_inventory(paths: set[str]) -> dict[str, str]:
    archive = subprocess.run(["git", "archive", "--format=tar", "HEAD", "--", *sorted(paths)], cwd=ROOT, capture_output=True, check=False)
    if archive.returncode:
        raise VerificationError("candidate_product_source_drift")
    with tempfile.TemporaryDirectory() as temporary:
        try:
            with tarfile.open(fileobj=io.BytesIO(archive.stdout), mode="r:") as payload:
                payload.extractall(temporary, filter="data")
        except tarfile.TarError as error:
            raise VerificationError("candidate_product_source_drift") from error
        return {path: hashlib.sha256((Path(temporary) / path).read_bytes()).hexdigest() for path in paths}


def verify_document(document: object) -> dict[str, object]:
    if not isinstance(document, dict) or document.get("schema") != SCHEMA or document.get("status") != "external_selected_prbs9_candidate_waveform_observed_reference_compare_pending":
        raise VerificationError("candidate_schema_or_status")
    observation = document.get("external_observation")
    required = {"schema", "status", "custody", "report_path_retained", "report_byte_length", "report_content_sha256", "clean_archive_commit", "clean_archive_tree", "bridge_predecessor_commit", "selected_source", "source_identity_checks", "fresh_custody_runs", "manifest_sha256s", "release_build", "record_count", "outcome", "cleanup_status", "runner_sha256", "product_source_inventory"}
    if not isinstance(observation, dict) or set(observation) != required or observation.get("schema") != "sipi.p3c.sealed-selected-s4p-candidate-runner.v1" or observation.get("status") != "observed" or observation.get("custody") != "external_only" or observation.get("report_path_retained") is not False or observation.get("report_byte_length") != 2035 or observation.get("source_identity_checks") != "before_stage_after_equal" or observation.get("fresh_custody_runs") != 2 or observation.get("record_count") != 2002 or observation.get("cleanup_status") != "complete":
        raise VerificationError("candidate_observation_shape")
    if not all(_hex(observation.get(key), 64 if key not in {"clean_archive_commit", "clean_archive_tree", "bridge_predecessor_commit"} else 40) for key in {"report_content_sha256", "clean_archive_commit", "clean_archive_tree", "bridge_predecessor_commit", "runner_sha256"}):
        raise VerificationError("candidate_hash_invalid")
    if observation.get("selected_source") != {"byte_length": 1834156, "sha256": "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47"}:
        raise VerificationError("candidate_source_identity")
    manifests = observation.get("manifest_sha256s")
    if not isinstance(manifests, list) or len(manifests) != 2 or manifests[0] == manifests[1] or any(not _hex(value, 64) for value in manifests):
        raise VerificationError("candidate_freshness")
    if observation.get("release_build") != {"profile": "release", "target": "x86_64-pc-windows-msvc", "rustc_release": "1.97.0", "executable_sha256": "030f01392d1b6f3d82df55db31cbb35cd7cccd162b04dd5d3e20ff086928a066"}:
        raise VerificationError("candidate_release_build")
    expected = {"uniform_bin_count": 25601, "causal_sample_count": 51200, "iteration_count": 32, "retained_sample_count": 10871, "sample_interval_bits": "3d712e0be826d695", "dropped_l2_over_total_l2_bits": "3f625ac4b27fdb73", "tail": "nonzero_tail", "truncated_response_sha256": "c0b21cfe4d61ac3ce33a5695b198c0d4bf9ae1d80227dcc5b14a9ab37d9adf0b", "full_linear_sample_count": 59926, "strict_grid_prefix_sample_count": 49056, "third_period_sample_count": 16352, "multiply_accumulates": 533287776, "full_linear_response_sha256": "d4ddefab57014d6d2c588f60c69a63395076075361fcc8eb86e099c462bd8128", "strict_grid_prefix_sha256": "1f53dbd18262f098ee24c0aebb827c7b3c2b03bfca4eb85bb3276dd33c99a7fb", "third_period_sha256": "f478b7c626be3594fa9783226d6542350a47926296c80e3b3c14b01f2a1af732"}
    if observation.get("outcome") != expected:
        raise VerificationError("candidate_outcome")
    inventory = observation.get("product_source_inventory")
    if not isinstance(inventory, dict) or len(inventory) < 20 or any(not isinstance(path, str) or not _hex(digest, 64) for path, digest in inventory.items()):
        raise VerificationError("candidate_inventory")
    if observation["runner_sha256"] != inventory.get("crates/sipi-p3c/tests/p3c_sealed_s4p_external_candidate_runner.rs"):
        raise VerificationError("candidate_runner_identity")
    predecessor = document.get("historical_predecessor")
    if predecessor != {"evidence_commit": "8a2613b707c00d1a24661e7083fec722ce3feba3", "current_verifier_result": "source_drift", "exact_token": "truncation_product_source_drift"}:
        raise VerificationError("candidate_predecessor_drift")
    true_keys = {"selected_truncated_response_admitted_as_discrete_convolution_kernel", "external_selected_candidate_convolution_invoked", "external_selected_candidate_convolution_admitted", "candidate_waveform_generated", "external_selected_candidate_waveform_observed"}
    false_keys = {"causal_impulse_admitted", "delay_extraction_implemented", "passivity_repair_implemented", "external_reference_binding_evaluated", "candidate_metric_acceptance_evaluated", "accepted_receiver", "product_runtime_invoked", "p4b_ami_runtime_invoked", "p5_reference_evaluated", "release_ledger_promoted"}
    admission = document.get("admission")
    if not isinstance(admission, dict) or set(admission) != true_keys | false_keys or any(admission[key] is not True for key in true_keys) or any(admission[key] is not False for key in false_keys):
        raise VerificationError("candidate_gate_promotion")
    if any(word in str(document).lower() for word in ("\\\\", "file://", "http://", "https://", "waveform: [", "samples: [")):
        raise VerificationError("candidate_evidence_leak")
    return {"valid": True, "candidate_observed": True, "release_admitted": False}


def verify_current_product_identity(document: dict[str, object]) -> None:
    observation = document["external_observation"]
    assert isinstance(observation, dict)
    inventory = observation["product_source_inventory"]
    assert isinstance(inventory, dict)
    if _archive_inventory(set(inventory)) != inventory:
        raise VerificationError("candidate_product_source_drift")
    old = subprocess.run([sys.executable, "-B", "tools/verify_p3c_selected_s4p_truncation_observation_evidence.py"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=False)
    if old.returncode != 1 or old.stdout or old.stderr.strip() != "selected_s4p_truncation_observation_failed:truncation_product_source_drift":
        raise VerificationError("candidate_predecessor_drift_not_fail_closed")


def main() -> int:
    try:
        document = yaml.safe_load(DEFAULT.read_text(encoding="utf-8"))
        result = verify_document(document)
        verify_current_product_identity(document)
    except (OSError, ValueError, yaml.YAMLError, VerificationError) as error:
        print(f"selected_s4p_candidate_observation_failed:{error}", file=sys.stderr)
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
