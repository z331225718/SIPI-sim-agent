"""Verify the hash-only selected OOB zero-extension sensitivity observation."""

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
DEFAULT = ROOT / "docs/baselines/p3c-selected-oob-zero-extension-sensitivity-observation-evidence.v1.yaml"
SCHEMA = "sipi.p3c-selected-oob-zero-extension-sensitivity-observation-evidence.v1"
ARCHIVE_COMMIT = "1ac62e143beed0cc4dae92c06f2ff92683a71a7e"
ARCHIVE_TREE = "9914e874d9993f14f542b0330d923546775d5285"
HEX = set("0123456789abcdef")


class VerificationError(ValueError):
    pass


def _hex(value: object, length: int = 64) -> bool:
    return isinstance(value, str) and len(value) == length and not (set(value) - HEX)


def _archive_inventory(paths: set[str]) -> dict[str, str]:
    archive = subprocess.run(
        ["git", "archive", "--format=tar", "HEAD", "--", *sorted(paths)],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if archive.returncode:
        raise VerificationError("oob_product_source_drift")
    with tempfile.TemporaryDirectory() as temporary:
        try:
            with tarfile.open(fileobj=io.BytesIO(archive.stdout), mode="r:") as payload:
                payload.extractall(temporary, filter="data")
        except tarfile.TarError as error:
            raise VerificationError("oob_product_source_drift") from error
        return {
            path: hashlib.sha256((Path(temporary) / path).read_bytes()).hexdigest()
            for path in paths
        }


def _expect_equal(value: object, expected: object, reason: str) -> None:
    if value != expected:
        raise VerificationError(reason)


def verify_document(document: object) -> dict[str, object]:
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise VerificationError("schema_invalid")
    _expect_equal(
        document.get("status"),
        "external_selected_oob_extension_sensitivity_observed_acceptance_unchanged",
        "status_invalid",
    )
    _expect_equal(
        document.get("authority"),
        {
            "actor": "user",
            "decision_ref": "user-continuation-2026-08-14",
            "scope": "selected_strict_gt_40ghz_positive_zero_sensitivity_only",
        },
        "authority_invalid",
    )
    predecessors = document.get("predecessors")
    if not isinstance(predecessors, dict) or predecessors.get("core", {}).get("status") != "product_owned_selected_oob_zero_extension_diagnostic_implemented_external_observation_pending" or predecessors.get("runner", {}).get("status") != "external_only_two_fresh_baseline_and_zero_oob_observation_prepared_not_run" or predecessors.get("waveform_only_history", {}).get("status") != "historical_waveform_only_observation_source_drifted_current_external_binding_unavailable":
        raise VerificationError("predecessor_invalid")

    observation = document.get("external_observation")
    required = {
        "schema", "status", "custody", "report_path_retained", "report_byte_length",
        "report_content_sha256", "clean_archive_commit", "clean_archive_tree", "runner_sha256",
        "release_build", "selected_source", "ads_reference_input", "source_reference_identity_checks",
        "fresh_custody_runs", "source_manifest_sha256s", "record_count", "baseline",
        "strict_gt_40ghz_positive_zero", "cleanup_status", "product_source_inventory",
    }
    if not isinstance(observation, dict) or set(observation) != required:
        raise VerificationError("observation_shape")
    _expect_equal(observation.get("schema"), "sipi.p3c.selected-oob-zero-extension-runner.v1", "runner_schema")
    _expect_equal(observation.get("status"), "observed", "runner_status")
    _expect_equal(observation.get("custody"), "external_only", "custody")
    _expect_equal(observation.get("report_path_retained"), False, "report_retention")
    _expect_equal(observation.get("report_byte_length"), 1975, "report_length")
    _expect_equal(observation.get("report_content_sha256"), "b4d6a81de0e52f46302a8636f38ff5aa1cf3d581bb7c45886cae61a775dd440a", "report_hash")
    _expect_equal(observation.get("clean_archive_commit"), ARCHIVE_COMMIT, "archive_commit")
    _expect_equal(observation.get("clean_archive_tree"), ARCHIVE_TREE, "archive_tree")
    if not _hex(observation.get("runner_sha256")):
        raise VerificationError("runner_hash")
    release_build = observation.get("release_build")
    _expect_equal(release_build, {"profile": "release", "target": "x86_64-pc-windows-msvc", "rustc_release": "1.97.0", "executable_sha256": "da3322c41965888cb0077a5ad382df2353dc2cb9bf45e9bafccc0004ce9bd078"}, "release_build")
    _expect_equal(observation.get("selected_source"), {"byte_length": 1834156, "sha256": "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47"}, "source")
    _expect_equal(observation.get("ads_reference_input"), {"canonical_triple_payload_sha256": "5ec5211a273d313655f0b8ced35d58ea89d0bba113f5edc3fd9712218f46e726", "extracted_rx_payload_sha256": "2cf94baf436bd04ff86baeca7d03eab1e6d9a8ce019163d43987a0200eb1bfa5", "custody_recovery": "two_fresh_external_ads_v2_runs_identical"}, "reference_input")
    _expect_equal(observation.get("source_reference_identity_checks"), "before_stage_after_equal", "identity_checks")
    _expect_equal(observation.get("fresh_custody_runs"), 2, "fresh_runs")
    manifests = observation.get("source_manifest_sha256s")
    if not isinstance(manifests, list) or len(manifests) != 2 or manifests[0] == manifests[1] or any(not _hex(value) for value in manifests):
        raise VerificationError("manifest_freshness")
    _expect_equal(observation.get("record_count"), 2002, "record_count")
    expected_baseline = {"uniform_spectrum_sha256": "2a47c9553916198e851f48ca8d95cae0f6473b0708ad5eeac2338ce76650faae", "causality_iterations": 32, "retained_taps": 10871, "candidate_prefix_sha256": "939b7062795430f2f92702e8e2eb070d84636a42a589adcf89aee0b0f48a8769", "waveform_nrmse_bits": "3f9c4139b95fcc93"}
    expected_zero = {"uniform_spectrum_sha256": "0745da06253c0a3959c3ee5ff5f839850fa72ce1d584bb547ddab4291a68cf98", "causality_iterations": 32, "retained_taps": 10871, "candidate_prefix_sha256": "5acaa446035be90ad10e80c2789eff13f50da36932b99393fdc7b0c144561ec8", "waveform_nrmse_bits": "3f9c41397b246bb2"}
    _expect_equal(observation.get("baseline"), expected_baseline, "baseline_outcome")
    _expect_equal(observation.get("strict_gt_40ghz_positive_zero"), expected_zero, "zero_oob_outcome")
    _expect_equal(observation.get("cleanup_status"), "complete", "cleanup")
    inventory = observation.get("product_source_inventory")
    if not isinstance(inventory, dict) or len(inventory) != 37 or any(not isinstance(path, str) or not _hex(digest) for path, digest in inventory.items()):
        raise VerificationError("inventory_shape")
    _expect_equal(inventory.get("crates/sipi-p3c/tests/p3c_selected_oob_zero_extension_external_runner.rs"), observation["runner_sha256"], "runner_inventory")

    expected_true = {"selected_oob_zero_extension_diagnostic_defined", "external_oob_extension_sensitivity_invoked", "baseline_current_candidate_reproduced", "oob_extension_sensitivity_observed"}
    expected_false = {"zero_oob_variant_admitted_as_product_policy", "product_interpolation_policy_changed", "external_reference_binding_evaluated", "candidate_metric_acceptance_evaluated", "selected_highloss_waveform_only_profile_accepted", "accepted_receiver", "acceptance_ready", "promotion_eligible", "release_ledger_promoted"}
    admission = document.get("admission")
    if not isinstance(admission, dict) or set(admission) != expected_true | expected_false or any(admission[key] is not True for key in expected_true) or any(admission[key] is not False for key in expected_false):
        raise VerificationError("gate_promotion")
    _expect_equal(document.get("blockers"), ["zero_oob_diagnostic_variant_not_authorized_as_product_policy", "waveform_only_product_source_drift", "selected_waveform_nrmse_exceeds_fixed_one_percent_limit", "accepted_receiver_stage_missing", "statistical_eye_contour_semantics_missing"], "blockers")
    if any(token in str(document).lower() for token in ("\\\\", "file://", "http://", "https://", "samples: [", "waveform: [", "spectrum: [")):
        raise VerificationError("evidence_leak")
    return {"valid": True, "oob_sensitivity_observed": True, "product_policy_changed": False, "release_admitted": False}


def verify_current_product_identity(document: dict[str, object]) -> None:
    observation = document["external_observation"]
    assert isinstance(observation, dict)
    inventory = observation["product_source_inventory"]
    assert isinstance(inventory, dict)
    tree = subprocess.run(["git", "rev-parse", f"{ARCHIVE_COMMIT}^{{tree}}"], cwd=ROOT, capture_output=True, text=True, check=False)
    if tree.returncode or tree.stdout.strip() != ARCHIVE_TREE:
        raise VerificationError("oob_product_source_drift")
    if _archive_inventory(set(inventory)) != inventory:
        raise VerificationError("oob_product_source_drift")


def main() -> int:
    try:
        document = yaml.safe_load(DEFAULT.read_text(encoding="utf-8"))
        result = verify_document(document)
        verify_current_product_identity(document)
    except (OSError, ValueError, yaml.YAMLError, VerificationError) as error:
        print(f"selected_oob_zero_extension_observation_failed:{error}")
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
