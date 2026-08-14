"""Verify the fail-closed ADS-reference metric-rejection reason observation."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
import subprocess
import tarfile
import tempfile

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs/baselines/p3c-external-ads-reference-metric-rejection-reason-evidence.v1.yaml"
HISTORICAL = ROOT / "docs/baselines/p3c-external-ads-reference-metric-observation-evidence.v1.yaml"
SCHEMA = "sipi.p3c-external-ads-reference-metric-rejection-reason-evidence.v1"
HEX = set("0123456789abcdef")


class VerificationError(ValueError):
    pass


def _hex(value: object, length: int = 64) -> bool:
    return isinstance(value, str) and len(value) == length and not (set(value) - HEX)


def _archive_inventory(paths: set[str]) -> dict[str, str]:
    archive = subprocess.run(["git", "archive", "--format=tar", "HEAD", "--", *sorted(paths)], cwd=ROOT, capture_output=True, check=False)
    if archive.returncode:
        raise VerificationError("metric_reason_product_source_drift")
    with tempfile.TemporaryDirectory() as temporary:
        try:
            with tarfile.open(fileobj=io.BytesIO(archive.stdout), mode="r:") as payload:
                payload.extractall(temporary, filter="data")
        except tarfile.TarError as error:
            raise VerificationError("metric_reason_product_source_drift") from error
        return {path: hashlib.sha256((Path(temporary) / path).read_bytes()).hexdigest() for path in paths}


def verify_document(document: object) -> dict[str, object]:
    if not isinstance(document, dict) or document.get("schema") != SCHEMA or document.get("status") != "external_reference_bound_direct_metric_core_rejection_reason_observed":
        raise VerificationError("metric_reason_schema_or_status")
    if document.get("authority") != {"actor": "user", "decision_ref": "user-continuation-2026-08-14", "scope": "reason_only_external_metric_diagnostic_without_contract_amendment"}:
        raise VerificationError("metric_reason_authority")
    if document.get("supersedes_historical_observation") != {"path": "docs/baselines/p3c-external-ads-reference-metric-observation-evidence.v1.yaml", "content_sha256": "06c66d82fff4ea7b1d1a369556c86f37bf657ce04e6f84f316e9a94260f69e9e", "current_verifier_result": "metric_product_source_drift", "historical_rejection_cause": "unobserved"}:
        raise VerificationError("metric_reason_historical_binding")
    observation = document.get("external_observation")
    required = {"schema", "custody", "report_path_retained", "report_byte_length", "report_content_sha256", "clean_archive_commit", "clean_archive_tree", "selected_source", "ads_canonical_triple_payload", "contract_sha256", "source_identity_checks", "fresh_custody_runs", "report_outcome", "cleanup_status", "release_build", "runner_sha256", "product_source_inventory"}
    if not isinstance(observation, dict) or set(observation) != required:
        raise VerificationError("metric_reason_observation_shape")
    if observation.get("schema") != "sipi.p3c.external-ads-reference-metric-runner.v1" or observation.get("custody") != "external_only" or observation.get("report_path_retained") is not False or observation.get("report_byte_length") != 780 or observation.get("source_identity_checks") != "before_stage_after_equal" or observation.get("fresh_custody_runs") != 2 or observation.get("cleanup_status") != "complete":
        raise VerificationError("metric_reason_observation_facts")
    if not all(_hex(observation.get(key), 40 if key in {"clean_archive_commit", "clean_archive_tree"} else 64) for key in {"report_content_sha256", "clean_archive_commit", "clean_archive_tree", "contract_sha256", "runner_sha256"}):
        raise VerificationError("metric_reason_hashes")
    if observation.get("selected_source") != {"byte_length": 1834156, "sha256": "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47"}:
        raise VerificationError("metric_reason_selected_source")
    if observation.get("ads_canonical_triple_payload") != {"byte_length": 1177344, "sha256": "5ec5211a273d313655f0b8ced35d58ea89d0bba113f5edc3fd9712218f46e726", "rx_column": "differential_voltage"} or observation.get("contract_sha256") != "f47329b6ddda01cbcde1f24e21cb93e03f8ef6139ea2d43ff74cad9e2049d2b5":
        raise VerificationError("metric_reason_reference_or_contract")
    archive_tree = subprocess.run(["git", "show", "-s", "--format=%T", observation["clean_archive_commit"]], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=False)
    if archive_tree.returncode or archive_tree.stdout.strip() != observation["clean_archive_tree"]:
        raise VerificationError("metric_reason_clean_archive_identity")
    expected_run = {"status": "rejected", "stage": "cli", "exit_code": 3, "direct_core_reason": "zero_reference_eye_width", "cli_stdout_byte_length": 139, "cli_stdout_sha256": "ec76b0cc0e9d04abb36f31b680969ed1bd674b08cad1474a55dce6b627d03bd6", "cli_stderr_byte_length": 267, "cli_stderr_sha256": "3e067de4d9fc655dd6ba03ca92e2aea6dc9905b1a2496ce5d53a7b7dd2a2e34d"}
    if observation.get("report_outcome") != {"outcome": "rejected", "runs": [expected_run, expected_run]}:
        raise VerificationError("metric_reason_rejection_outcome")
    if observation.get("release_build") != {"profile": "release", "target": "x86_64-pc-windows-msvc", "rustc_release": "1.97.0", "executable_sha256": "34b6a17a6bfbf4b4b57c97a4907fc7fc40d3eb105d010100d374d4f3f7a46791"}:
        raise VerificationError("metric_reason_release_build")
    inventory = observation.get("product_source_inventory")
    if not isinstance(inventory, dict) or len(inventory) < 30 or any(not isinstance(path, str) or not _hex(digest) for path, digest in inventory.items()):
        raise VerificationError("metric_reason_inventory")
    if observation["runner_sha256"] != inventory.get("crates/sipi-p3c/tests/p3c_external_ads_reference_metric_runner.rs"):
        raise VerificationError("metric_reason_runner_identity")
    expected_true = {"external_ads_reference_bound_to_metric_input", "external_reference_binding_evaluated", "direct_metric_core_diagnostic_invoked", "metric_rejection_reason_observed", "product_compare_cli_invoked"}
    expected_false = {"candidate_metric_evaluation_rejected", "waveform_nrmse_evaluated", "sampled_eye_evaluated", "crossing_tie_evaluated", "candidate_waveform_eye_tie_metrics_accepted", "accepted_receiver", "acceptance_ready", "promotion_eligible", "release_ledger_promoted"}
    admission = document.get("admission")
    if not isinstance(admission, dict) or set(admission) != expected_true | expected_false or any(admission[key] is not True for key in expected_true) or any(admission[key] is not False for key in expected_false):
        raise VerificationError("metric_reason_gate_promotion")
    if not isinstance(document.get("blockers"), list) or not isinstance(document.get("non_claims"), list) or any(token in str(document).lower() for token in ("file://", "http://", "https://", "waveform: [", "samples: [", "index:", "\\\\")):
        raise VerificationError("metric_reason_evidence_leak")
    return {"valid": True, "direct_metric_core_reason": "zero_reference_eye_width", "release_admitted": False}


def verify_current_product_identity(document: dict[str, object]) -> None:
    observation = document["external_observation"]
    assert isinstance(observation, dict)
    inventory = observation["product_source_inventory"]
    assert isinstance(inventory, dict)
    if _archive_inventory(set(inventory)) != inventory:
        raise VerificationError("metric_reason_product_source_drift")
    historical = hashlib.sha256(HISTORICAL.read_bytes()).hexdigest()
    if historical != document["supersedes_historical_observation"]["content_sha256"]:
        raise VerificationError("metric_reason_historical_content_drift")
    result = subprocess.run(["python", "-B", "tools/verify_p3c_external_ads_reference_metric_observation_evidence.py"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=False)
    if result.returncode != 1 or result.stdout or result.stderr.strip() != "external_ads_reference_metric_observation_failed:metric_product_source_drift":
        raise VerificationError("metric_reason_historical_drift_not_preserved")


def main() -> int:
    try:
        document = yaml.safe_load(DEFAULT.read_text(encoding="utf-8"))
        result = verify_document(document)
        verify_current_product_identity(document)
    except (OSError, ValueError, yaml.YAMLError, VerificationError) as error:
        print(f"external_ads_reference_metric_rejection_reason_evidence_failed:{error}", file=sys.stderr)
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main())
