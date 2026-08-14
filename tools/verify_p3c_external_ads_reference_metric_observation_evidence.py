"""Verify the fail-closed ADS-reference metric-rejection observation."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
import subprocess
import tarfile
import tempfile

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs/baselines/p3c-external-ads-reference-metric-observation-evidence.v1.yaml"
SCHEMA = "sipi.p3c-external-ads-reference-metric-observation-evidence.v1"
HEX = set("0123456789abcdef")


class VerificationError(ValueError):
    pass


def _hex(value: object, length: int = 64) -> bool:
    return isinstance(value, str) and len(value) == length and not (set(value) - HEX)


def _archive_inventory(paths: set[str]) -> dict[str, str]:
    archive = subprocess.run(["git", "archive", "--format=tar", "HEAD", "--", *sorted(paths)], cwd=ROOT, capture_output=True, check=False)
    if archive.returncode:
        raise VerificationError("metric_product_source_drift")
    with tempfile.TemporaryDirectory() as temporary:
        try:
            with tarfile.open(fileobj=io.BytesIO(archive.stdout), mode="r:") as payload:
                payload.extractall(temporary, filter="data")
        except tarfile.TarError as error:
            raise VerificationError("metric_product_source_drift") from error
        return {path: hashlib.sha256((Path(temporary) / path).read_bytes()).hexdigest() for path in paths}


def verify_document(document: object) -> dict[str, object]:
    if not isinstance(document, dict) or document.get("schema") != SCHEMA or document.get("status") != "external_reference_bound_metric_evaluation_rejected":
        raise VerificationError("metric_schema_or_status")
    if document.get("authority") != {"actor": "user", "decision_ref": "user-confirmed-2026-08-14-p3c-prbs9-ads-reference-bound-metric-evidence", "scope": "exact_ads_rx_reference_to_current_selected_s4p_candidate_metric_cli_only"}:
        raise VerificationError("metric_authority")
    observation = document.get("external_observation")
    required = {"schema", "custody", "report_path_retained", "report_byte_length", "report_content_sha256", "clean_archive_commit", "clean_archive_tree", "selected_source", "ads_canonical_triple_payload", "contract_sha256", "source_identity_checks", "fresh_custody_runs", "report_outcome", "cleanup_status", "release_build", "runner_sha256", "product_source_inventory"}
    if not isinstance(observation, dict) or set(observation) != required:
        raise VerificationError("metric_observation_shape")
    if observation.get("schema") != "sipi.p3c.external-ads-reference-metric-runner.v1" or observation.get("custody") != "external_only" or observation.get("report_path_retained") is not False or observation.get("report_byte_length") != 220 or observation.get("source_identity_checks") != "before_stage_after_equal" or observation.get("fresh_custody_runs") != 2 or observation.get("cleanup_status") != "complete":
        raise VerificationError("metric_observation_facts")
    if not all(_hex(observation.get(key), 40 if key in {"clean_archive_commit", "clean_archive_tree"} else 64) for key in {"report_content_sha256", "clean_archive_commit", "clean_archive_tree", "contract_sha256", "runner_sha256"}):
        raise VerificationError("metric_hashes")
    if observation.get("selected_source") != {"byte_length": 1834156, "sha256": "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47"}:
        raise VerificationError("metric_selected_source")
    if observation.get("ads_canonical_triple_payload") != {"byte_length": 1177344, "sha256": "5ec5211a273d313655f0b8ced35d58ea89d0bba113f5edc3fd9712218f46e726", "rx_column": "differential_voltage"}:
        raise VerificationError("metric_reference_identity")
    if observation.get("contract_sha256") != "f47329b6ddda01cbcde1f24e21cb93e03f8ef6139ea2d43ff74cad9e2049d2b5":
        raise VerificationError("metric_contract")
    archive_tree = subprocess.run(["git", "show", "-s", "--format=%T", observation["clean_archive_commit"]], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=False)
    if archive_tree.returncode or archive_tree.stdout.strip() != observation["clean_archive_tree"]:
        raise VerificationError("metric_clean_archive_identity")
    expected_outcome = {"outcome": "rejected", "runs": [{"status": "rejected", "stage": "cli", "exit_code": 3}, {"status": "rejected", "stage": "cli", "exit_code": 3}]}
    if observation.get("report_outcome") != expected_outcome:
        raise VerificationError("metric_rejection_outcome")
    if observation.get("release_build") != {"profile": "release", "target": "x86_64-pc-windows-msvc", "rustc_release": "1.97.0", "executable_sha256": "97e07c92ae5576e74f47229d9d2eae777e50578c639eff3b99d39a027b6c73f6"}:
        raise VerificationError("metric_release_build")
    inventory = observation.get("product_source_inventory")
    if not isinstance(inventory, dict) or len(inventory) < 30 or any(not isinstance(path, str) or not _hex(digest) for path, digest in inventory.items()):
        raise VerificationError("metric_inventory")
    if observation["runner_sha256"] != inventory.get("crates/sipi-p3c/tests/p3c_external_ads_reference_metric_runner.rs"):
        raise VerificationError("metric_runner_identity")
    expected_true = {"external_ads_reference_bound_to_metric_input", "external_reference_binding_evaluated", "product_compare_cli_invoked", "candidate_metric_evaluation_rejected"}
    expected_false = {"waveform_nrmse_evaluated", "sampled_eye_evaluated", "crossing_tie_evaluated", "candidate_waveform_eye_tie_metrics_accepted", "accepted_receiver", "acceptance_ready", "promotion_eligible", "release_ledger_promoted"}
    admission = document.get("admission")
    if not isinstance(admission, dict) or set(admission) != expected_true | expected_false or any(admission[key] is not True for key in expected_true) or any(admission[key] is not False for key in expected_false):
        raise VerificationError("metric_gate_promotion")
    if not isinstance(document.get("blockers"), list) or not isinstance(document.get("non_claims"), list) or any(token in str(document).lower() for token in ("file://", "http://", "https://", "waveform: [", "samples: [", "\\\\")):
        raise VerificationError("metric_evidence_leak")
    return {"valid": True, "metric_evaluation": "rejected", "release_admitted": False}


def verify_current_product_identity(document: dict[str, object]) -> None:
    observation = document["external_observation"]
    assert isinstance(observation, dict)
    inventory = observation["product_source_inventory"]
    assert isinstance(inventory, dict)
    if _archive_inventory(set(inventory)) != inventory:
        raise VerificationError("metric_product_source_drift")
    for tool in ("verify_p3c_external_ads_prbs9_reference.py", "verify_p3c_prbs9_metric_core_v2.py", "verify_p3c_prbs9_metric_artifact_cli.py", "verify_p3c_selected_s4p_candidate_observation_evidence.py"):
        result = subprocess.run(["python", "-B", f"tools/{tool}"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=False)
        if result.returncode:
            raise VerificationError("metric_prerequisite_drift")


def main() -> int:
    try:
        document = yaml.safe_load(DEFAULT.read_text(encoding="utf-8"))
        result = verify_document(document)
        verify_current_product_identity(document)
    except (OSError, ValueError, yaml.YAMLError, VerificationError) as error:
        print(f"external_ads_reference_metric_observation_failed:{error}", file=sys.stderr)
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main())
