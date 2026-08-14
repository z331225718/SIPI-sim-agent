"""Verify the external finite-edge v2 waveform-only observation evidence."""

from __future__ import annotations

import hashlib
import io
import subprocess
import tarfile
import tempfile
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "docs/baselines/p3c-selected-highloss-waveform-only-v2-observation-evidence.v1.yaml"
SCHEMA = "sipi.p3c-selected-highloss-waveform-only-v2-observation-evidence.v1"
COMMIT = "f2555d6125237708107830f125f966e4add20e70"
TREE = "87a0eeb899ddb7bc0a870cf5743ec7676e897280"
HEX = set("0123456789abcdef")


class VerificationError(ValueError): pass


def expect(value: object, expected: object, reason: str) -> None:
    if value != expected: raise VerificationError(reason)


def archive_inventory(paths: set[str]) -> dict[str, str]:
    result = subprocess.run(["git", "archive", "--format=tar", "HEAD", "--", *sorted(paths)], cwd=ROOT, capture_output=True, check=False)
    if result.returncode: raise VerificationError("source_drift")
    with tempfile.TemporaryDirectory() as temporary:
        with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:") as archive: archive.extractall(temporary, filter="data")
        return {path: hashlib.sha256((Path(temporary) / path).read_bytes()).hexdigest() for path in paths}


def verify_document(document: object) -> dict[str, object]:
    if not isinstance(document, dict) or document.get("schema") != SCHEMA: raise VerificationError("schema")
    expect(document.get("status"), "external_selected_finite_edge_v2_candidate_waveform_observed_not_accepted", "status")
    observation = document.get("external_observation")
    if not isinstance(observation, dict): raise VerificationError("observation")
    expected = {"schema": "sipi.p3c.external-ads-selected-highloss-waveform-only-v2-runner.v1", "custody": "external_only", "report_path_retained": False, "report_byte_length": 2416, "report_content_sha256": "09ec29941fbddd9c6724e40e9603a877dc382aa010fbfe9445d2f23ea05ccf4f", "clean_archive_commit": COMMIT, "clean_archive_tree": TREE, "fresh_runs": 2, "record_count": 2002, "waveform_nrmse_bits": "3f9dd184cd51df98", "waveform_nrmse_limit_bits": "3f847ae147ae147b", "within_waveform_nrmse_limit": False, "within_selected_waveform_only_profile": False, "cleanup_status": "complete"}
    for key, value in expected.items(): expect(observation.get(key), value, key)
    inventory = observation.get("source_inventory")
    if not isinstance(inventory, dict) or len(inventory) != 7 or any(not isinstance(key, str) or not isinstance(value, str) or len(value) != 64 or set(value) - HEX for key, value in inventory.items()): raise VerificationError("inventory")
    expected_true = {"external_selected_v2_candidate_convolution_invoked", "external_selected_v2_candidate_convolution_admitted", "current_v2_candidate_waveform_evaluated"}
    expected_false = {"selected_highloss_waveform_only_profile_accepted", "accepted_receiver", "acceptance_ready", "release_ledger_promoted"}
    admission = document.get("admission")
    if not isinstance(admission, dict) or set(admission) != expected_true | expected_false or any(admission[key] is not True for key in expected_true) or any(admission[key] is not False for key in expected_false): raise VerificationError("gates")
    expect(document.get("blockers"), ["selected_highloss_waveform_nrmse_exceeds_fixed_one_percent_limit", "strict_v2_source_strobe_identity_not_observed_and_no_source_tolerance_authorized", "accepted_receiver_stage_missing", "statistical_eye_contour_semantics_missing"], "blockers")
    if any(token in str(document).lower() for token in ("file://", "http://", "https://", "c:\\", "waveform: [", "samples: [")): raise VerificationError("leak")
    return {"valid": True, "accepted": False, "candidate_evaluated": True}


def verify_current_source(document: dict[str, object]) -> None:
    tree = subprocess.run(["git", "rev-parse", f"{COMMIT}^{{tree}}"], cwd=ROOT, capture_output=True, text=True, check=False)
    observation = document["external_observation"]
    assert isinstance(observation, dict)
    inventory = observation["source_inventory"]
    assert isinstance(inventory, dict)
    if tree.returncode or tree.stdout.strip() != TREE or archive_inventory(set(inventory)) != inventory: raise VerificationError("source_drift")


def main() -> int:
    try:
        document = yaml.safe_load(PATH.read_text(encoding="utf-8")); result = verify_document(document); verify_current_source(document)
    except (OSError, ValueError, yaml.YAMLError, VerificationError) as error:
        print(f"p3c_selected_highloss_waveform_only_v2_observation_evidence_failed:{error}"); return 1
    print(result); return 0


if __name__ == "__main__": raise SystemExit(main())
