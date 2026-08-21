"""Verify the additive recovered-original-ADS T08 replay evidence."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "docs" / "baselines" / "p3c-exact-impulse-current-replay-evidence.v2.yaml"
SCHEMA = "sipi.p3c-exact-impulse-current-replay-evidence.v2"
STATUS = "external_only_two_fresh_current_replay_recovered_original_ads_observed_not_accepted"
COMMIT = "7f21b5fc8f3290b3726d64c1858bd8f013816920"
TREE = "adc84f2ffbe4d755032c452e8181e56603cccf53"
OBSERVER_PATH = "tools/observe_p3c_exact_impulse_current_replay_preparation_v2.py"
OBSERVER_SHA256 = "741984f7e12e4e6703f8751f9659cb46a0c8cc4693656ece0333e60655392160"
REPORT_SHA256 = "b22366e33c7fd58f83103b7f9b97191f18ab62745632f41d1995084fe6fd58f4"
REPORT_BYTES = 4256
BLOCKED_V1 = "docs/baselines/p3c-exact-impulse-current-replay-evidence.v1.yaml"
BLOCKED_V1_SHA256 = "5a9fda52a4dd209d4964000542c741d137596d42ce6cc2fd4bcde14a0581d325"
HEX = set("0123456789abcdef")
SOURCE_INVENTORY = {
    "crates/sipi-p3c/tests/p3c_external_ads_selected_highloss_waveform_only_runner.rs": "067a6c3c772f86c6737836f7c10dde1cf071340321c62323fb6f9cd236aa1200",
    "crates/sipi-p3c/src/prbs9_impulse_candidate_v2.rs": "d6182ab20dddc50acb89eef5b6232739eb6ee12a6cef2332505476f84ef680ac",
    "crates/sipi-ieee-com-sparam/src/interp_sparam_v1.rs": "d33d9196e5630f50cb3cfa4598bc2ee57ba34251380dc828baf2ffb4c1d45cac",
    "crates/sipi-ieee-com-sparam/src/s21_to_causal_v1.rs": "fe4976e544d78e743e000cad4efd9e3a147f7c5d30ae1a6789bb2bed8460a0ee",
    "crates/sipi-ieee-com-sparam/src/s21_to_truncated_v1.rs": "dc0923ee6398e990594e9b001993ecdbd9798f865546339e57f1b8417063b407",
    "crates/sipi-compare/src/selected_highloss_prbs9_waveform_only_v3.rs": "48f44cb7a0471ec312cfdbf5d8dbb0a8c998f8a0e9bf1d542ad959da518a63f3",
    "crates/sipi-cli/src/main.rs": "e19a687e9b210777afc94796236fd6ffd7541ab3a32734e7f93310e7441ad689",
}


class VerificationError(ValueError):
    """Evidence does not satisfy the fail-closed v2 contract."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _expect(actual: object, expected: object, reason: str) -> None:
    if actual != expected:
        raise VerificationError(reason)


def _digest(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= HEX


def _safe_extract(data: bytes, destination: Path) -> None:
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as archive:
        members = archive.getmembers()
        for member in members:
            name = Path(member.name)
            if name.is_absolute() or ".." in name.parts or member.issym() or member.islnk() or not (member.isdir() or member.isfile()):
                raise VerificationError("archive_member_invalid")
        archive.extractall(destination, filter="data")


def _archive_inventory(root: Path, paths: set[str]) -> dict[str, str]:
    result = subprocess.run(
        ["git", "-C", str(root), "archive", "--format=tar", COMMIT, "--", *sorted(paths)],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise VerificationError("clean_archive_unavailable")
    with tempfile.TemporaryDirectory(prefix="sipi-p3c-t08-v2-verify-") as temporary:
        destination = Path(temporary)
        _safe_extract(result.stdout, destination)
        values: dict[str, str] = {}
        for path in paths:
            candidate = destination / path
            if not candidate.is_file():
                raise VerificationError("clean_archive_path_missing")
            values[path] = _sha256(candidate)
        return values


def _verify_archive(root: Path, expected: dict[str, str]) -> None:
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", f"{COMMIT}^{{tree}}"],
        capture_output=True,
        check=False,
        text=True,
        encoding="ascii",
    )
    if result.returncode != 0 or result.stdout.strip() != TREE:
        raise VerificationError("clean_archive_tree_drift")
    if _archive_inventory(root, set(expected)) != expected:
        raise VerificationError("clean_archive_source_drift")


def _expected_custody() -> dict[str, Any]:
    source = {
        "logical_name": "channel_gen5_highloss.s4p",
        "byte_length": 1834156,
        "sha256": "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47",
    }
    dataset = {
        "logical_name": "p3c_prbs9.ds",
        "byte_length": 7107072,
        "sha256": "1375d8beec33b2688cf4ab305a6a472b9ae0260960b2128e199b760979d12310",
    }
    payload = {
        "logical_name": "canonical_waveform_le_f64.bin",
        "byte_length": 1177344,
        "sha256": "5ec5211a273d313655f0b8ced35d58ea89d0bba113f5edc3fd9712218f46e726",
    }
    declared = {
        "logical_name": "p3c_prbs9_ideal_load.ckt",
        "byte_length": 5246,
        "sha256": "2784e9e8d42c7ecdc3459b79a5f9cd79cc86131f839c86b1658e8d40b1d9aaf9",
    }
    actual = {
        "logical_name": "p3c_prbs9_ideal_load.ckt",
        "byte_length": 5254,
        "sha256": "c6d3df30e2f23dd9181426b2d834bab4cb5990d19a1e48a2b968eb9e79369765",
    }
    return {
        "manifest": {
            "schema": "sipi.p3c-external-ads-prbs9-reference-run.v1",
            "byte_length": 2479,
            "sha256": "37930afa7f151cd6ca317f17ebb544dfb9c5a56a4a4c455b35f0114dc4fb94f9",
            "ads_oracle_only": True,
            "custody": "external_only",
            "runtime_invoked": True,
            "product_runtime": False,
            "p4b_ami_runtime": False,
        },
        "source": source,
        "dataset": dataset,
        "canonical_payload": payload,
        "netlist_declared_by_manifest": declared,
        "netlist_actual_retained_bytes": actual,
        "runs": [
            {
                "label": "recovered_ads_ref01",
                "manifest_sha256": "37930afa7f151cd6ca317f17ebb544dfb9c5a56a4a4c455b35f0114dc4fb94f9",
                "source_sha256": source["sha256"],
                "dataset_sha256": dataset["sha256"],
                "actual_netlist_sha256": actual["sha256"],
                "canonical_payload_sha256": payload["sha256"],
            },
            {
                "label": "recovered_ads_ref02",
                "manifest_sha256": "37930afa7f151cd6ca317f17ebb544dfb9c5a56a4a4c455b35f0114dc4fb94f9",
                "source_sha256": source["sha256"],
                "dataset_sha256": dataset["sha256"],
                "actual_netlist_sha256": actual["sha256"],
                "canonical_payload_sha256": payload["sha256"],
            },
        ],
        "identity_checks": {
            "manifest_repeatability": "identical",
            "source_identity": "matched_selected_s4p",
            "dataset_identity": "matched_across_ref01_ref02",
            "actual_netlist_repeatability": "identical",
            "canonical_payload_repeatability": "identical",
            "manifest_declared_netlist_byte_identity": "mismatch",
            "manifest_declared_netlist_normalized_content_identity": "matched_after_lf_normalization",
            "netlist_identity_note": "manifest_declares_lf_bytes_while_retained_run_copy_is_crlf",
        },
    }


def verify_document(document: object, *, root: Path = ROOT, check_archive: bool = True) -> dict[str, object]:
    if not isinstance(document, dict):
        raise VerificationError("document_shape")
    _expect(document.get("schema"), SCHEMA, "schema")
    _expect(document.get("status"), STATUS, "status")
    _expect(
        document.get("authority"),
        {
            "actor": "project",
            "decision_ref": "task-t08-2026-08-21-exact-impulse-current-replay-recovered-original-ads",
            "scope": "exact_selected_s4p_recovered_original_ads_two_fresh_current_v2_impulse_replay_only",
        },
        "authority",
    )
    _expect(document.get("predecessor"), {"blocked_v1_path": BLOCKED_V1, "blocked_v1_sha256": BLOCKED_V1_SHA256, "blocked_v1_rewritten": False}, "predecessor")
    blocked = root / BLOCKED_V1
    if not blocked.is_file() or _sha256(blocked) != BLOCKED_V1_SHA256:
        raise VerificationError("blocked_v1_drift")

    baseline = document.get("baseline")
    if not isinstance(baseline, dict):
        raise VerificationError("baseline_shape")
    clean = baseline.get("clean_archive")
    _expect(clean, {"commit": COMMIT, "tree": TREE, "materialization": "git_archive_only", "archive_bytes_retained": False, "worktree_execution": "prohibited"}, "clean_archive")
    _expect(baseline.get("preparation_contract"), {"path": "docs/baselines/p3c-exact-impulse-current-replay-preparation.v1.yaml", "sha256": "9709f18df807381dd024d15e6979976e7b7d5ddb32aca953d43d2b8875d8bc36"}, "preparation_contract")
    _expect(baseline.get("preparation_spec"), {"path": "docs/clean-room/specs/p3c-exact-impulse-current-replay-preparation.v1.md", "sha256": "bc2746a2a6c075c0ce62d21c117f99183b60b205684130e817bb3dddaaba90c0"}, "preparation_spec")
    _expect(baseline.get("source_inventory"), SOURCE_INVENTORY, "source_inventory")
    if _sha256(root / baseline["preparation_contract"]["path"]) != baseline["preparation_contract"]["sha256"] or _sha256(root / baseline["preparation_spec"]["path"]) != baseline["preparation_spec"]["sha256"]:
        raise VerificationError("preparation_source_drift")
    if check_archive:
        _verify_archive(root, SOURCE_INVENTORY)

    _expect(document.get("observer"), {
        "path": OBSERVER_PATH,
        "sha256": OBSERVER_SHA256,
        "implementation": "additive_wrapper_v1_observer_rebound_to_current_clean_archive",
        "invocation": {
            "mode": "locked_offline_clean_archive_external_target",
            "command": "cargo test --locked --offline -p sipi-p3c --test p3c_external_ads_selected_highloss_waveform_only_runner -- --ignored p3c_external_ads_selected_highloss_waveform_only_runner_v2",
            "clean_archive_materialized": True,
            "clean_archive_bytes_retained": False,
            "external_target": True,
            "ads_runtime_invoked": False,
            "status": "prepared_observed_not_accepted",
            "cleanup_status": "complete",
        },
    }, "observer")
    observer_path = root / OBSERVER_PATH
    if not observer_path.is_file() or _sha256(observer_path) != OBSERVER_SHA256:
        raise VerificationError("observer_drift")

    _expect(document.get("external_report"), {
        "custody": "external_only",
        "format": "hash_only_json",
        "path_retained": False,
        "byte_length": REPORT_BYTES,
        "sha256": REPORT_SHA256,
        "child_report_sha256": "09ec29941fbddd9c6724e40e9603a877dc382aa010fbfe9445d2f23ea05ccf4f",
        "includes": ["clean_archive_identity", "source_identity", "reference_identity", "manifest_identity", "candidate_reference_digests", "strict_index_metric_bits"],
        "excludes": ["s4p_bytes", "ads_reference_bytes", "candidate_bytes", "waveform_arrays", "absolute_paths"],
    }, "external_report")

    _expect(document.get("inputs"), {
        "selected_s4p": {"logical_name": "channel_gen5_highloss.s4p", "byte_length": 1834156, "sha256": "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47", "custody": "external_only", "exact_identity_observed": True},
        "ads_reference": {"logical_name": "canonical_waveform_le_f64.bin", "byte_length": 1177344, "sha256": "5ec5211a273d313655f0b8ced35d58ea89d0bba113f5edc3fd9712218f46e726", "tuple_format": "little_endian_f64_time_tx_differential_rx_differential", "observed_column": "rx_differential", "samples": 49056, "sample_interval_bits": "3d712e0be826d695", "custody": "recovered_original_ads_external_only", "exact_identity_observed": True, "reconstructed_from_hash": False, "historical_summary_substituted": False},
        "product_cli": {"logical_name": "sipi.exe", "byte_length": 3975168, "sha256": "fd0a4b2115f6cfbe4d12a0ba507bc40e1577fda01a3a994f81b7581a5afc1c98", "custody": "external_only", "clean_archive_commit": COMMIT, "clean_archive_build": True, "cargo_profile": "release", "cargo_locked": True, "cargo_offline": True, "target_external": True, "bytes_tracked_in_repository": False},
    }, "inputs")

    _expect(document.get("recovered_original_ads_custody"), _expected_custody(), "manifest_audit")

    candidate = document.get("candidate_reference")
    if not isinstance(candidate, dict):
        raise VerificationError("candidate_reference_shape")
    expected_candidate = {
        "route": "ieee_bsd_impulse_only",
        "stages": ["sealed_selected_s4p_admission_v2", "ieee_bsd_interpolation_v1", "ieee_bsd_bounded_causality_v1", "ieee_bsd_truncation_v1", "prbs9_finite_edge_v2_direct_full_linear_convolution", "strict_index_waveform_only_compare_v3"],
        "fresh_replay_runs": 2,
        "fresh_custody_runs": 2,
        "record_count": 2002,
        "source_manifest_sha256s": ["06dec5fbcbe351bbd2835675d1580a193ae1a1b29d4543746c5c1c53d7931c9b", "21b91b86e287b0014dff0f5e03fd77e083719aa6e4dbb6852e7171c148439cc6"],
        "reference_manifest_sha256s": ["bea2bef233d9bde4152f47886e09a1d9ad4d14bb606c132e0a84583971b4cbbe", "e49cda9914986bd1e7550ad3083f053c9442729f9016d16cf6ebf71cc6428665"],
        "candidate_manifest_sha256s": ["9a8f30b9c2d9f7f1a9914b2377bb87243e750dda7371f93baa6eff98aa74c6c5", "a263f9ef00a79b3ebf90269fc247d62744efc7b19e99676f0c0c680f95f16d43"],
        "ads_canonical_triple_payload_sha256": "5ec5211a273d313655f0b8ced35d58ea89d0bba113f5edc3fd9712218f46e726",
        "reference_rx_payload_sha256": "2cf94baf436bd04ff86baeca7d03eab1e6d9a8ce019163d43987a0200eb1bfa5",
        "candidate_payload_sha256": "3bc73cc7f1bc09ec03c1266b5a3faa3353e9307e6832a81f51a8c1d55efcec3d",
        "reference_waveform_digest": "2e0ecb1e37bf7593e6774faaa7d5808a7c4acbf1ae8793f7afbda1b20bbc6e37",
        "candidate_waveform_digest": "a61375c6fd17edc484ca03697dedfa8f93d1376ed4571ea364f11df0c547baae",
        "waveform_nrmse_bits": "3f9dd184cd51df98",
        "waveform_nrmse_decimal": 0.02911956313297956,
        "waveform_nrmse_limit_bits": "3f847ae147ae147b",
        "waveform_nrmse_limit_decimal": 0.01,
        "within_one_percent": False,
        "within_selected_waveform_only_profile": False,
        "manifest_facts_equal_across_runs": True,
        "manifests_distinct_per_fresh_artifact_root": True,
        "cleanup_status": "complete",
    }
    _expect(candidate, expected_candidate, "candidate_reference")

    _expect(document.get("policy"), {
        "same_index": "required", "compared_period": "third", "start_index": 32704, "sample_count": 16352,
        "alignment": "prohibited", "delay_sweep": "prohibited", "gain_fit": "prohibited", "dc_removal": "prohibited",
        "polarity_flip": "prohibited", "resampling": "prohibited", "rational_fit": "prohibited", "parameter_scan": "prohibited",
        "tolerance_relaxation": "prohibited", "relative_rms_limit": 0.01,
    }, "policy")
    _expect(document.get("admission"), {
        "selected_s4p_identity_observed": True,
        "recovered_ads_payload_identity_observed": True,
        "recovered_ads_manifest_source_dataset_payload_identity_observed": True,
        "recovered_ads_manifest_netlist_byte_identity_observed": False,
        "locked_offline_release_build_observed": True,
        "external_replay_executed": True,
        "fresh_replay_custody_complete": True,
        "current_candidate_waveform_evaluated": True,
        "current_reference_binding_evaluated": True,
        "strict_index_compare_accepted": False,
        "causal_fir_admitted": False,
        "accepted_receiver": False,
        "p4b_ami_runtime_invoked": False,
        "p5_reference_evaluated": False,
        "release_ledger_promoted": False,
    }, "admission")
    _expect(document.get("blockers"), ["strict_index_waveform_nrmse_exceeds_fixed_one_percent_limit", "recovered_ads_manifest_declared_netlist_bytes_differ_from_retained_netlist_bytes", "accepted_receiver_stage_missing", "statistical_eye_contour_semantics_missing"], "blockers")
    _expect(document.get("non_claims"), [
        "This is a strict same-index waveform-only observation, not ADS solver parity or receiver acceptance.",
        "The recovered ADS payload was used as exact external bytes; it was not reconstructed from its hash and no historical summary replaced it.",
        "The retained netlist is byte-different from the manifest declaration only by line-ending representation; this does not promote the waveform result.",
        "No rational fit, delay or alignment search, gain or DC fitting, polarity transform, parameter scan, or tolerance relaxation was performed.",
        "No ADS simulator, P4B AMI runtime, P5 reference, receiver, or release promotion was invoked.",
    ], "non_claims")
    serialized = json.dumps(document, sort_keys=True, separators=(",", ":"))
    if any(token in serialized for token in ("file://", "http://", "https://", "C:/", "C:\\\\", "waveform:[", "samples:[")):
        raise VerificationError("path_or_payload_leak")
    return {"valid": True, "schema": SCHEMA, "status": STATUS, "nrmse": 0.02911956313297956, "within_one_percent": False, "release_promoted": False}


def main() -> int:
    try:
        document = yaml.safe_load(PATH.read_text(encoding="utf-8"))
        print(json.dumps(verify_document(document), sort_keys=True))
        return 0
    except (OSError, ValueError, yaml.YAMLError, VerificationError, subprocess.SubprocessError) as error:
        print(f"p3c_exact_impulse_current_replay_v2_evidence_failed:{error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
