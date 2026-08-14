"""Verify the current v2 strict-index residual diagnostic observation."""

from __future__ import annotations

import hashlib
import io
import subprocess
import tarfile
import tempfile
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "docs/baselines/p3c-selected-highloss-residual-diagnostic-v2-observation-evidence.v1.yaml"
SCHEMA = "sipi.p3c-selected-highloss-residual-diagnostic-v2-observation-evidence.v1"
COMMIT = "b61bb1abf0ad1a200d97bc818cbfe1b174abfa2e"
TREE = "2725e2d23ced8fd6ea05faed3bf7585e9018a446"
HEX = set("0123456789abcdef")


class VerificationError(ValueError):
    pass


def expect(value: object, expected: object, reason: str) -> None:
    if value != expected:
        raise VerificationError(reason)


def is_hex(value: object, length: int = 64) -> bool:
    return isinstance(value, str) and len(value) == length and not (set(value) - HEX)


def archive_inventory(paths: set[str]) -> dict[str, str]:
    result = subprocess.run(
        ["git", "archive", "--format=tar", "HEAD", "--", *sorted(paths)],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise VerificationError("source_drift")
    with tempfile.TemporaryDirectory() as temporary:
        with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:") as archive:
            archive.extractall(temporary, filter="data")
        return {
            path: hashlib.sha256((Path(temporary) / path).read_bytes()).hexdigest()
            for path in paths
        }


def verify(document: object, *, check_source: bool) -> dict[str, object]:
    if not isinstance(document, dict) or set(document) != {
        "schema", "status", "authority", "predecessor", "external_observation",
        "admission", "blockers", "non_claims",
    }:
        raise VerificationError("shape")
    expect(document["schema"], SCHEMA, "schema")
    expect(document["status"], "external_selected_finite_edge_v2_residual_diagnostic_observed_acceptance_unchanged", "status")
    authority = document["authority"]
    if authority != {
        "actor": "user",
        "decision_ref": "user-confirmed-2026-08-14-p3c-finite-edge-boundary-projection-v2",
        "scope": "selected_v2_candidate_strict_index_time_domain_diagnostic_only",
    }:
        raise VerificationError("authority")
    expect(document["predecessor"], {
        "source_projection_v2": "docs/baselines/p3c-prbs9-impulse-candidate-source-projection.v2.yaml",
        "candidate_waveform_v2": "docs/baselines/p3c-selected-highloss-waveform-only-v2-observation-evidence.v1.yaml",
    }, "predecessor")
    observation = document["external_observation"]
    if not isinstance(observation, dict):
        raise VerificationError("observation")
    expected = {
        "schema": "sipi.p3c.external-ads-selected-highloss-residual-v2-runner.v1",
        "custody": "external_only",
        "report_path_retained": False,
        "report_byte_length": 3698,
        "report_content_sha256": "8dffd68c1788039ad0967451f206e436f684f7943ff531cac8f3636dd4f5ee5a",
        "clean_archive_commit": COMMIT,
        "clean_archive_tree": TREE,
        "source_sha256": "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47",
        "ads_canonical_triple_payload_sha256": "5ec5211a273d313655f0b8ced35d58ea89d0bba113f5edc3fd9712218f46e726",
        "reference_rx_payload_sha256": "2cf94baf436bd04ff86baeca7d03eab1e6d9a8ce019163d43987a0200eb1bfa5",
        "candidate_prefix_sha256": "46b95963363de9439194ebcbf034088cdf984ea5c7d1b72ba3bb1ebf67a1ae3d",
        "fresh_runs": 2,
        "record_count": 2002,
        "fixed_period_windows": [[0, 16352], [16352, 32704], [32704, 49056]],
        "third_period_ui_residual_energy_sha256": "250970dc91a7f40c0cd39dbf8861670286c6bacc7d6ee5520c4b0be775af35e7",
        "third_period_maximum_energy_ui_offset": 346,
        "cleanup_status": "complete",
    }
    for key, value in expected.items():
        expect(observation.get(key), value, key)
    expect(observation.get("source_manifests"), [
        "865eb3278d210e85f0381a11ee891f62b688ccf599ef4e54f01cebf51310b3f1",
        "270732cbe8163316c8694e7805001a22ca0f03abb4dde9d8a9f26a8b874cea1a",
    ], "source_manifests")
    periods = observation.get("periods")
    if not isinstance(periods, list) or len(periods) != 3:
        raise VerificationError("periods")
    expected_periods = [
        ("3fd0119711422e56", "3fbee75fc93d18ff", "3fcbc114e8478b29", "bfbc2ecfae47e2c4", "3feba2b31caf847a", "e1ce554701280ad629a7a846a07b0be750c12b3a99261c003043b7fe9796eea7", "3fde0dc51f230179", 3369),
        ("3fc0fca907ad6765", "3fc0fbb3807b80fc", "3f6fa863c2be474a", "bee46da1a824d53b", "3f9dd184d3632100", "77ea01259456a224cac1274b7d9f81910cfd1e7a8d247005571d3b2081062991", "3f91817a41c2ea6c", 11069),
        ("3fc0fca907d2456d", "3fc0fbb3807b80fc", "3f6fa863bc91eb34", "bee46da444a42b5e", "3f9dd184cd51df98", "78fbfb975c07996ba0b27c3d388a57c45ebe8aaf1b5f5e4fe47f177bb874fe7c", "3f91817a41c2ea50", 11069),
    ]
    keys = ["reference_rms_bits", "candidate_rms_bits", "residual_rms_bits", "residual_mean_bits", "residual_nrmse_bits", "residual_sha256", "maximum_absolute_residual_bits", "maximum_absolute_residual_offset"]
    for period, values in zip(periods, expected_periods, strict=True):
        if not isinstance(period, dict) or set(period) != set(keys):
            raise VerificationError("period_shape")
        for key, value in zip(keys, values, strict=True):
            expect(period.get(key), value, f"period_{key}")
    inventory = observation.get("source_inventory")
    if not isinstance(inventory, dict) or len(inventory) != 30 or any(not isinstance(path, str) or not is_hex(digest) for path, digest in inventory.items()):
        raise VerificationError("inventory")
    commit_tree = subprocess.run(["git", "rev-parse", f"{COMMIT}^{{tree}}"], cwd=ROOT, capture_output=True, text=True, check=False)
    if commit_tree.returncode or commit_tree.stdout.strip() != TREE:
        raise VerificationError("archive_identity")
    if check_source and archive_inventory(set(inventory)) != inventory:
        raise VerificationError("source_drift")
    admission = document["admission"]
    expected_true = {
        "external_selected_v2_residual_diagnostic_invoked",
        "external_selected_v2_residual_diagnostic_repeatable",
        "current_v2_candidate_baseline_reproduced",
        "period_partition_residuals_observed",
        "third_period_diagnostic_matches_v3_nrmse",
    }
    expected_false = {
        "selected_highloss_waveform_only_profile_accepted",
        "acceptance_ready",
        "release_ledger_promoted",
    }
    if not isinstance(admission, dict) or set(admission) != expected_true | expected_false:
        raise VerificationError("admission_shape")
    if any(admission[key] is not True for key in expected_true) or any(admission[key] is not False for key in expected_false):
        raise VerificationError("admission")
    expect(document["blockers"], [
        "selected_highloss_waveform_nrmse_exceeds_fixed_one_percent_limit",
        "strict_v2_source_strobe_identity_not_observed_and_no_source_tolerance_authorized",
        "residual_spectral_distribution_observation_missing",
        "accepted_receiver_stage_missing",
        "statistical_eye_contour_semantics_missing",
    ], "blockers")
    if any(token in str(document).lower() for token in ("file://", "http://", "https://", "c:\\", "waveform: [", "residual: [", "samples: [")):
        raise VerificationError("leak")
    return {"valid": True, "accepted": False, "frequency_diagnostic": False}


def main() -> int:
    try:
        print(verify(yaml.safe_load(PATH.read_text(encoding="utf-8")), check_source=True))
    except (OSError, ValueError, yaml.YAMLError, VerificationError) as error:
        print(f"p3c_selected_highloss_residual_diagnostic_v2_observation_evidence_failed:{error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
