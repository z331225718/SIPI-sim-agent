"""Verify the hash-only ADS PRBSsrc source-only observation evidence."""

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
PATH = ROOT / "docs/baselines/p3c-ads-prbssrc-source-only-matched-load-observation-evidence.v1.yaml"
SCHEMA = "sipi.p3c-ads-prbssrc-source-only-matched-load-observation-evidence.v1"
ARCHIVE_COMMIT = "e7488eedccb8d71f070937780eab40a670b83d03"
ARCHIVE_TREE = "1d35a504bbc8a2f88d591e26228e93ce01c49190"
HEX = set("0123456789abcdef")


class VerificationError(ValueError):
    pass


def _hex(value: object, length: int = 64) -> bool:
    return isinstance(value, str) and len(value) == length and not (set(value) - HEX)


def _expect(value: object, expected: object, reason: str) -> None:
    if value != expected:
        raise VerificationError(reason)


def _archive_inventory(paths: set[str]) -> dict[str, str]:
    result = subprocess.run(["git", "archive", "--format=tar", "HEAD", "--", *sorted(paths)], cwd=ROOT, capture_output=True, check=False)
    if result.returncode:
        raise VerificationError("source_only_observation_source_drift")
    with tempfile.TemporaryDirectory() as temporary:
        try:
            with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:") as archive:
                archive.extractall(temporary, filter="data")
        except tarfile.TarError as error:
            raise VerificationError("source_only_observation_source_drift") from error
        return {path: hashlib.sha256((Path(temporary) / path).read_bytes()).hexdigest() for path in paths}


def verify_document(document: object) -> dict[str, object]:
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise VerificationError("schema_invalid")
    _expect(document.get("status"), "external_ads_source_only_matched_load_observed_product_policy_unchanged", "status_invalid")
    _expect(document.get("authority"), {"actor": "user", "decision_ref": "user-confirmed-2026-08-14-p3c-source-only-matched-load", "scope": "external_ads_source_only_strobe_observation_not_product_policy_or_channel_acceptance"}, "authority_invalid")
    predecessor = document.get("predecessor")
    if not isinstance(predecessor, dict) or predecessor.get("charter", {}).get("status") != "specified_owner_confirmed_external_runner_pending":
        raise VerificationError("predecessor_invalid")
    observation = document.get("external_observation")
    required = {"schema", "status", "custody", "report_path_retained", "report_byte_length", "report_content_sha256", "clean_archive_commit", "clean_archive_tree", "ads_product", "ads_python_version", "fixed_mapping", "ads_inclusive_samples", "canonical_half_open_samples", "fresh_runs", "netlist_sha256", "canonical_payload_sha256", "period_nrmse_bits", "third_period", "third_period_ui_boundary", "third_period_ui_interior", "cleanup_status", "source_inventory"}
    if not isinstance(observation, dict) or set(observation) != required:
        raise VerificationError("observation_shape")
    _expect(observation.get("schema"), "sipi.p3c.ads-prbssrc-source-only-observation.v1", "runner_schema")
    _expect(observation.get("status"), "observed", "runner_status")
    _expect(observation.get("custody"), "external_only", "custody")
    _expect(observation.get("report_path_retained"), False, "report_retention")
    _expect(observation.get("report_byte_length"), 8910, "report_length")
    _expect(observation.get("report_content_sha256"), "17d9d1dc59bf76f285c211e9b4db2856ae47868ad43035d034158aed2b6e2773", "report_hash")
    _expect(observation.get("clean_archive_commit"), ARCHIVE_COMMIT, "archive_commit")
    _expect(observation.get("clean_archive_tree"), ARCHIVE_TREE, "archive_tree")
    _expect(observation.get("ads_product"), "keysight_ads_2026_update1", "ads_product")
    _expect(observation.get("ads_python_version"), "3.13.2", "ads_python_version")
    _expect(observation.get("fixed_mapping"), "ads_loaded_differential_equals_0.5_times_product_projection", "mapping")
    _expect(observation.get("ads_inclusive_samples"), 49057, "inclusive_count")
    _expect(observation.get("canonical_half_open_samples"), 49056, "half_open_count")
    _expect(observation.get("fresh_runs"), 2, "fresh_runs")
    if any(not _hex(observation.get(key)) for key in ("netlist_sha256", "canonical_payload_sha256")):
        raise VerificationError("identity_hash")
    _expect(observation.get("netlist_sha256"), "638e6c24d65fd2adc92ea7f6b52cb6f3477d837f2290579a5562e97d42c0cdc1", "netlist_hash")
    _expect(observation.get("canonical_payload_sha256"), "c30e226b1133737f35886e86f4bf50c6f49e78fe35859922435ad12009edce1f", "payload_hash")
    _expect(observation.get("period_nrmse_bits"), ["3fcff7fae8cb112f", "3fd004001b2ab3db", "3fd00401631b60af"], "period_nrmse")
    _expect(observation.get("third_period"), {"nrmse_bits": "3fd00401631b60af", "residual_sha256": "09c23aa84a6237035afdb031ec732f4cd938e07426a7866c02fc47b4d89c555b", "common_mode_sha256": "f0c18774d9f6613750f7c679f39e3a7e791ddd8704edcfa00b48b057af8a1543", "common_mode_max_absolute_bits": "3cc2000000000000"}, "third_period")
    _expect(observation.get("third_period_ui_boundary"), {"sample_count": 511, "nrmse_bits": "3ff6a648844b4de4", "residual_sha256": "c14b2199ccda8bd81ccf9b8cc1b3b4c0b159c372972ab6c73b47ed28a1e95f3c", "max_absolute_residual_bits": "3ff0000000000000", "max_absolute_residual_first_index": 34816}, "boundary")
    _expect(observation.get("third_period_ui_interior"), {"sample_count": 15841, "nrmse_bits": "0000000000000000", "residual_sha256": "f416f1232170b120a2f06f14edfbc86d29230a8070e8ce49cbb0a948cf09de76", "max_absolute_residual_bits": "0000000000000000", "max_absolute_residual_first_index": 32705}, "interior")
    _expect(observation.get("cleanup_status"), "complete", "cleanup")
    inventory = observation.get("source_inventory")
    if not isinstance(inventory, dict) or len(inventory) != 5 or any(not isinstance(path, str) or not _hex(value) for path, value in inventory.items()):
        raise VerificationError("inventory_shape")
    expected_true = {"external_ads_source_only_matched_load_observed", "ads_prbssrc_strobe_semantics_observed", "right_continuous_projection_strict_diagnostic_evaluated", "source_only_observation_repeatable"}
    expected_false = {"product_source_policy_changed", "product_source_policy_admitted", "source_explains_full_channel_residual", "candidate_waveform_accepted", "causalization_policy_changed", "accepted_receiver", "release_ledger_promoted"}
    admission = document.get("admission")
    if not isinstance(admission, dict) or set(admission) != expected_true | expected_false or any(admission[key] is not True for key in expected_true) or any(admission[key] is not False for key in expected_false):
        raise VerificationError("gate_promotion")
    _expect(document.get("blockers"), ["owner_product_source_discretization_policy_decision_pending", "source_only_observation_does_not_establish_full_channel_residual_causation", "selected_waveform_nrmse_exceeds_fixed_one_percent_limit", "accepted_receiver_stage_missing", "statistical_eye_contour_semantics_missing"], "blockers")
    if any(token in str(document).lower() for token in ("file://", "http://", "https://", "c:\\", "waveform: [", "samples: [")):
        raise VerificationError("evidence_leak")
    return {"valid": True, "source_only_observed": True, "product_policy_changed": False, "release_admitted": False}


def verify_current_source_identity(document: dict[str, Any]) -> None:
    observation = document["external_observation"]
    inventory = observation["source_inventory"]
    tree = subprocess.run(["git", "rev-parse", f"{ARCHIVE_COMMIT}^{{tree}}"], cwd=ROOT, capture_output=True, text=True, check=False)
    if tree.returncode or tree.stdout.strip() != ARCHIVE_TREE or _archive_inventory(set(inventory)) != inventory:
        raise VerificationError("source_only_observation_source_drift")


def main() -> int:
    try:
        document = yaml.safe_load(PATH.read_text(encoding="utf-8"))
        result = verify_document(document)
        verify_current_source_identity(document)
    except (OSError, ValueError, yaml.YAMLError, VerificationError) as error:
        print(f"p3c_ads_prbssrc_source_only_observation_evidence_failed:{error}")
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
