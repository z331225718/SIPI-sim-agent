"""Verify hash-only evidence for the strict ADS pre-to-final axis comparison."""

from __future__ import annotations

import hashlib
import io
import subprocess
import tarfile
import tempfile
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "docs/baselines/p3c-ads-pre-final-spectrum-comparison-observation-evidence.v1.yaml"
COMMIT = "b52b2b114eb5befbfaf6eac41455ca9796ae7685"
TREE = "a40f0d3126f535f5a9ac5bbe2db226751581aead"
INVENTORY = {
    "tools/run_p3c_external_ads_fixed_pulse_pre_final_spectrum.py": "b4a9b8926038ca8317212936b37986e21354c6933840eb46e575fe9d62e6cf8c",
    "tools/observe_p3c_ads_pre_final_spectrum_comparison.py": "64603699141353cd44e249104b96ea6eefc9cf478a277910af5eb06d3b88fed3",
    "tools/run_p3c_external_ads_fixed_pulse_passivity_surface.py": "dd5c60b8364d2b9ad6f17dafdfd1c55cc4be4dcae11aa495a024337f5b4e723f",
}


class VerificationError(ValueError):
    pass


def fail(condition: bool, reason: str) -> None:
    if condition:
        raise VerificationError(reason)


def archive_inventory() -> dict[str, str]:
    result = subprocess.run(["git", "archive", "--format=tar", COMMIT], cwd=ROOT, check=True, capture_output=True)
    with tempfile.TemporaryDirectory() as directory:
        with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:") as archive:
            archive.extractall(directory, filter="data")
        return {path: hashlib.sha256((Path(directory) / path).read_bytes()).hexdigest() for path in INVENTORY}


def verify(document: object, current: bool = True) -> dict[str, object]:
    fail(not isinstance(document, dict), "shape")
    required = {"schema", "status", "authority", "predecessor", "external_observation", "independent_audit", "admission", "blockers", "non_claims"}
    fail(set(document) != required, "shape")
    fail(document["schema"] != "sipi.p3c.ads-pre-final-spectrum-comparison-observation-evidence.v1", "schema")
    fail(document["status"] != "external_ads_pre_to_final_spectrum_axis_mismatch_observed", "status")
    fail(document["authority"] != {"actor": "user", "decision_ref": "user-authorized-spectrum-payload-comparison-2026-08-14", "scope": "one_fixed_external_ads_dataset_pre_to_final_strict_axis_comparison_only"}, "authority")
    fail(document["predecessor"] != {"path": "docs/baselines/p3c-ads-passivity-action-surface-observation-evidence.v1.yaml", "result": "documented_pre_correction_surface_observed_correction_magnitude_unevaluated"}, "predecessor")
    observation = document["external_observation"]
    expected = {
        "schema": "sipi.p3c.ads-pre-final-spectrum-comparison-observation.v1", "custody": "external_only", "report_path_retained": False,
        "report_byte_length": 1714, "report_content_sha256": "48ceab1617d8fec8b94a0da5d6f1e7382eeede50f5086aee53d5bd4e01cc66b3",
        "clean_archive_commit": COMMIT, "clean_archive_tree": TREE, "source_byte_length": 1_834_156,
        "source_sha256": "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47",
        "ads_help_byte_length": 150_522, "ads_help_sha256": "45372e9c7c79492bf6023a4e860f05a20caf0ef5e2a083407c119909afc187bf",
        "runner_source_sha256": INVENTORY["tools/run_p3c_external_ads_fixed_pulse_pre_final_spectrum.py"],
        "observer_source_sha256": INVENTORY["tools/observe_p3c_ads_pre_final_spectrum_comparison.py"],
        "predecessor_runner_sha256": INVENTORY["tools/run_p3c_external_ads_fixed_pulse_passivity_surface.py"],
        "fresh_runs": 2, "ads_netlist_byte_length": 1760,
        "ads_netlist_sha256": "6f720d8375726b1d7b0c42fbc7579372c1fea0ca5929c21d9823ccae4c2838e8",
        "pre_final_axis_comparison": {
            "matrix_dimension": 4, "members_per_surface": 16, "outcome": "pre_final_axis_not_identical",
            "s0": {"point_count": 1024, "first_frequency_bits": "0000000000000000", "last_frequency_bits": "42229bb708380000", "first_step_bits": "4182a05f20000000", "axis_sha256": "113345df1bc9be1d2848904f66bfacdab743b6eed925c80936bab92c8e467b04"},
            "fft_imp": {"point_count": 4096, "first_frequency_bits": "0000000000000000", "last_frequency_bits": "42229f351a0e0000", "first_step_bits": "4162a05f20000000", "axis_sha256": "c89382203cdebf38fbcf18a98025138e4be6b0dab9acc3889becca55cf0f9705"},
        },
        "cleanup_status": "complete",
    }
    fail(observation != expected, "observation")
    tree = subprocess.run(["git", "rev-parse", f"{COMMIT}^{{tree}}"], cwd=ROOT, check=False, capture_output=True, text=True)
    fail(tree.returncode != 0 or tree.stdout.strip() != TREE, "archive")
    if current:
        fail(archive_inventory() != INVENTORY, "source_drift")
    fail(document["independent_audit"] != {"reviewer": "Orca_reused_OpenCode_terminal", "terminal": "term_2de7cb74-b803-4e20-bb5b-4803777c24f8", "status": "pending_read_only_audit"}, "audit")
    true = {"saved_pre_to_final_spectrum_comparison_evaluated", "strict_pre_to_final_axis_identity_evaluated"}
    false = {"full_matrix_delta_observed", "selected_hdiff_delta_observed", "passivity_correction_surface_delta_evaluated", "passivity_algorithm_or_repair_implemented", "waveform_mismatch_cause_identified", "candidate_waveform_accepted", "release_ledger_promoted"}
    admission = document["admission"]
    fail(not isinstance(admission, dict) or set(admission) != true | false or any(admission[key] is not True for key in true) or any(admission[key] is not False for key in false), "gates")
    fail(document["blockers"] != ["pre_to_final_frequency_axes_not_identical", "complex_payload_delta_not_evaluable_without_transform_policy", "ads_passivity_algorithm_not_observed_or_ported", "waveform_mismatch_cause_not_identified"], "blockers")
    forbidden = ("file://", "http://", "https://", "c:\\", "spectrum: [", "waveform: [", "freqresp")
    fail(any(token in str(document).lower() for token in forbidden), "leak")
    return {"valid": True, "axis_comparable": False, "accepted": False}


if __name__ == "__main__":
    try:
        print(verify(yaml.safe_load(PATH.read_text(encoding="utf-8"))))
    except (OSError, ValueError, yaml.YAMLError, VerificationError) as error:
        print(f"p3c_ads_pre_final_spectrum_comparison_failed:{error}")
        raise SystemExit(1)
