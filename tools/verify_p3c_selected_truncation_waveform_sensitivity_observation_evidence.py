"""Verify the hash-only selected truncation sensitivity observation."""

from __future__ import annotations

import hashlib
import io
import subprocess
import tarfile
import tempfile
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs/baselines/p3c-selected-truncation-waveform-sensitivity-observation-evidence.v1.yaml"
SCHEMA = "sipi.p3c-selected-truncation-waveform-sensitivity-observation-evidence.v1"
ARCHIVE_COMMIT = "4df6d891ab8ba3363926fc0909a2e83246c2ce6f"
ARCHIVE_TREE = "3756661425d2759aaa7e7e96ad608d7d8ba49be9"
HEX = set("0123456789abcdef")


class VerificationError(ValueError):
    pass


def _hex(value: object, length: int = 64) -> bool:
    return isinstance(value, str) and len(value) == length and not (set(value) - HEX)


def _expect_equal(value: object, expected: object, reason: str) -> None:
    if value != expected:
        raise VerificationError(reason)


def _archive_inventory(paths: set[str]) -> dict[str, str]:
    archive = subprocess.run(
        ["git", "archive", "--format=tar", "HEAD", "--", *sorted(paths)],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if archive.returncode:
        raise VerificationError("truncation_sensitivity_product_source_drift")
    with tempfile.TemporaryDirectory() as temporary:
        try:
            with tarfile.open(fileobj=io.BytesIO(archive.stdout), mode="r:") as payload:
                payload.extractall(temporary, filter="data")
        except tarfile.TarError as error:
            raise VerificationError("truncation_sensitivity_product_source_drift") from error
        return {
            path: hashlib.sha256((Path(temporary) / path).read_bytes()).hexdigest()
            for path in paths
        }


def verify_document(document: object) -> dict[str, object]:
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise VerificationError("schema_invalid")
    _expect_equal(
        document.get("status"),
        "external_selected_truncation_waveform_sensitivity_observed_acceptance_unchanged",
        "status_invalid",
    )
    _expect_equal(
        document.get("authority"),
        {
            "actor": "user",
            "decision_ref": "user-confirmed-ui-boundary-right-continuous-projection-2026-08-14",
            "scope": "selected_full_bounded_causality_third_period_diagnostic_only",
        },
        "authority_invalid",
    )
    predecessors = document.get("predecessors")
    if not isinstance(predecessors, dict) or set(predecessors) != {"core", "runner", "oob_sensitivity"}:
        raise VerificationError("predecessor_shape")
    _expect_equal(predecessors["core"].get("status"), "product_owned_external_diagnostic_core_implemented_external_observation_pending", "core_predecessor")
    _expect_equal(predecessors["runner"].get("status"), "external_only_two_fresh_selected_full_causal_and_truncated_observation_prepared_not_run", "runner_predecessor")

    observation = document.get("external_observation")
    required = {
        "schema", "status", "custody", "report_path_retained", "report_byte_length",
        "report_content_sha256", "clean_archive_commit", "clean_archive_tree", "runner_sha256",
        "release_build", "selected_source", "ads_reference_input", "source_reference_identity_checks",
        "fresh_custody_runs", "source_manifest_sha256s", "record_count", "causality_iterations",
        "bounded_causal_response_sha256", "retained_taps", "truncated_baseline",
        "full_bounded_causality_diagnostic", "cleanup_status", "product_source_inventory",
    }
    if not isinstance(observation, dict) or set(observation) != required:
        raise VerificationError("observation_shape")
    _expect_equal(observation.get("schema"), "sipi.p3c.selected-truncation-waveform-sensitivity-runner.v1", "runner_schema")
    _expect_equal(observation.get("status"), "observed", "runner_status")
    _expect_equal(observation.get("custody"), "external_only", "custody")
    _expect_equal(observation.get("report_path_retained"), False, "report_retention")
    _expect_equal(observation.get("report_byte_length"), 1662, "report_length")
    _expect_equal(observation.get("report_content_sha256"), "6af54b68a04ad78b47e5f8329bd50c7038c7289eccd7b90920e14d9906e80051", "report_hash")
    _expect_equal(observation.get("clean_archive_commit"), ARCHIVE_COMMIT, "archive_commit")
    _expect_equal(observation.get("clean_archive_tree"), ARCHIVE_TREE, "archive_tree")
    if not _hex(observation.get("runner_sha256")):
        raise VerificationError("runner_hash")
    _expect_equal(observation.get("release_build"), {"profile": "release", "target": "x86_64-pc-windows-msvc", "rustc_release": "1.97.0", "executable_sha256": "4240d3bea944d5626c590e6c2a3b55bfd82b46a40e30ea51f2ef3c78e467cd1e"}, "release_build")
    _expect_equal(observation.get("selected_source"), {"byte_length": 1834156, "sha256": "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47"}, "source")
    _expect_equal(observation.get("ads_reference_input"), {"canonical_triple_payload_sha256": "5ec5211a273d313655f0b8ced35d58ea89d0bba113f5edc3fd9712218f46e726", "extracted_rx_payload_sha256": "2cf94baf436bd04ff86baeca7d03eab1e6d9a8ce019163d43987a0200eb1bfa5", "custody_recovery": "two_fresh_external_ads_v2_runs_identical"}, "reference_input")
    _expect_equal(observation.get("source_reference_identity_checks"), "before_stage_after_equal", "identity_checks")
    _expect_equal(observation.get("fresh_custody_runs"), 2, "fresh_runs")
    manifests = observation.get("source_manifest_sha256s")
    if not isinstance(manifests, list) or len(manifests) != 2 or manifests[0] == manifests[1] or any(not _hex(value) for value in manifests):
        raise VerificationError("manifest_freshness")
    _expect_equal(observation.get("record_count"), 2002, "record_count")
    _expect_equal(observation.get("causality_iterations"), 32, "causality_iterations")
    _expect_equal(observation.get("bounded_causal_response_sha256"), "f0f6ef483944dd19ba01bd1285319b1bae7610bb87f010a7289259cbba1ecb6a", "causal_digest")
    _expect_equal(observation.get("retained_taps"), 10871, "retained_taps")
    _expect_equal(observation.get("truncated_baseline"), {"prefix_sha256": "939b7062795430f2f92702e8e2eb070d84636a42a589adcf89aee0b0f48a8769", "waveform_nrmse_bits": "3f9c4139b95fcc93"}, "truncated_baseline")
    _expect_equal(observation.get("full_bounded_causality_diagnostic"), {"third_period_sha256": "9821ec6df888862d91fd9ae7a880d2d994c171cde0ac310492b22eb3833cfef4", "waveform_nrmse_bits": "3f9c3312e1103fee"}, "full_diagnostic")
    _expect_equal(observation.get("cleanup_status"), "complete", "cleanup")
    inventory = observation.get("product_source_inventory")
    if not isinstance(inventory, dict) or len(inventory) != 38 or any(not isinstance(path, str) or not _hex(digest) for path, digest in inventory.items()):
        raise VerificationError("inventory_shape")
    _expect_equal(inventory.get("crates/sipi-p3c/tests/p3c_selected_truncation_waveform_sensitivity_external_runner.rs"), observation["runner_sha256"], "runner_inventory")

    expected_true = {"selected_truncation_waveform_sensitivity_diagnostic_defined", "external_full_causal_third_period_diagnostic_invoked", "current_truncated_baseline_reproduced", "truncation_waveform_sensitivity_observed"}
    expected_false = {"bounded_causal_response_admitted_as_kernel", "causal_fir_admitted", "truncation_policy_changed", "full_branch_candidate_or_accepted", "external_reference_binding_evaluated", "candidate_metric_acceptance_evaluated", "selected_highloss_waveform_only_profile_accepted", "accepted_receiver", "acceptance_ready", "promotion_eligible", "release_ledger_promoted"}
    admission = document.get("admission")
    if not isinstance(admission, dict) or set(admission) != expected_true | expected_false or any(admission[key] is not True for key in expected_true) or any(admission[key] is not False for key in expected_false):
        raise VerificationError("gate_promotion")
    _expect_equal(document.get("blockers"), ["bounded_causal_response_diagnostic_variant_not_authorized_as_candidate_kernel", "truncation_policy_change_requires_owner_decision", "waveform_only_product_source_drift", "selected_waveform_nrmse_exceeds_fixed_one_percent_limit", "accepted_receiver_stage_missing", "statistical_eye_contour_semantics_missing"], "blockers")
    if any(token in str(document).lower() for token in ("\\\\", "file://", "http://", "https://", "samples: [", "waveform: [", "spectrum: [")):
        raise VerificationError("evidence_leak")
    return {"valid": True, "truncation_sensitivity_observed": True, "product_policy_changed": False, "release_admitted": False}


def verify_current_product_identity(document: dict[str, Any]) -> None:
    observation = document["external_observation"]
    inventory = observation["product_source_inventory"]
    tree = subprocess.run(["git", "rev-parse", f"{ARCHIVE_COMMIT}^{{tree}}"], cwd=ROOT, capture_output=True, text=True, check=False)
    if tree.returncode or tree.stdout.strip() != ARCHIVE_TREE:
        raise VerificationError("truncation_sensitivity_product_source_drift")
    if _archive_inventory(set(inventory)) != inventory:
        raise VerificationError("truncation_sensitivity_product_source_drift")


def main() -> int:
    try:
        document = yaml.safe_load(DEFAULT.read_text(encoding="utf-8"))
        result = verify_document(document)
        verify_current_product_identity(document)
    except (OSError, ValueError, yaml.YAMLError, VerificationError) as error:
        print(f"selected_truncation_waveform_sensitivity_observation_failed:{error}")
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
