"""Verify hash-only ADS source-only v2 observation evidence."""

from __future__ import annotations

import hashlib
import io
import subprocess
import tarfile
import tempfile
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "docs/baselines/p3c-ads-prbssrc-source-only-v2-observation-evidence.v1.yaml"
SCHEMA = "sipi.p3c-ads-prbssrc-source-only-v2-observation-evidence.v1"
ARCHIVE_COMMIT = "993bb11a99c9fe79ecf4f8eded80ed8a2e71ad60"
ARCHIVE_TREE = "bcd301aaafa1a92edb7560ce93a207e19453f199"
HEX = set("0123456789abcdef")


class VerificationError(ValueError):
    pass


def _expect(value: object, expected: object, reason: str) -> None:
    if value != expected:
        raise VerificationError(reason)


def _hex(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and not (set(value) - HEX)


def _archive_inventory(paths: set[str]) -> dict[str, str]:
    result = subprocess.run(["git", "archive", "--format=tar", "HEAD", "--", *sorted(paths)], cwd=ROOT, capture_output=True, check=False)
    if result.returncode:
        raise VerificationError("source_drift")
    with tempfile.TemporaryDirectory() as temporary:
        with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:") as archive:
            archive.extractall(temporary, filter="data")
        return {path: hashlib.sha256((Path(temporary) / path).read_bytes()).hexdigest() for path in paths}


def verify_document(document: object) -> dict[str, object]:
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise VerificationError("schema_invalid")
    _expect(document.get("status"), "external_ads_source_only_v2_observed_strict_bitwise_identity_not_established", "status_invalid")
    observation = document.get("external_observation")
    if not isinstance(observation, dict):
        raise VerificationError("observation_shape")
    expected = {
        "schema": "sipi.p3c.ads-prbssrc-source-only-v2-observation.v1",
        "status": "observed",
        "custody": "external_only",
        "report_path_retained": False,
        "report_byte_length": 6484,
        "report_content_sha256": "566a60e654b9f9b1d22fc8a998b587a53209e0076845b153c8866138006ec1a5",
        "clean_archive_commit": ARCHIVE_COMMIT,
        "clean_archive_tree": ARCHIVE_TREE,
        "fixed_mapping": "ads_loaded_differential_equals_0.5_times_product_finite_edge_projection_v2",
        "ads_inclusive_samples": 49057,
        "canonical_half_open_samples": 49056,
        "fresh_runs": 2,
        "netlist_sha256": "638e6c24d65fd2adc92ea7f6b52cb6f3477d837f2290579a5562e97d42c0cdc1",
        "canonical_payload_sha256": "c30e226b1133737f35886e86f4bf50c6f49e78fe35859922435ad12009edce1f",
        "period_nrmse_bits": ["3e53244c8f3b792f", "3e9d085d3f575331", "3e774941faa1f303"],
        "cleanup_status": "complete",
    }
    for key, value in expected.items():
        _expect(observation.get(key), value, f"observation_{key}")
    for key in ("netlist_sha256", "canonical_payload_sha256", "report_content_sha256"):
        if not _hex(observation.get(key)):
            raise VerificationError("identity_hash")
    _expect(document.get("strict_numeric_result"), {"exact_bitwise_identity_observed": False, "interior_exact_bitwise_identity_observed": True, "boundary_exact_bitwise_identity_observed": False, "no_source_policy_mutation_authorized": True}, "strict_numeric_result")
    expected_true = {"external_ads_source_only_v2_observation_invoked", "external_ads_source_only_v2_observation_repeatable"}
    expected_false = {"product_projection_v2_source_strobe_match_observed", "product_source_policy_changed_by_observation", "current_v2_candidate_waveform_evaluated", "selected_highloss_waveform_only_profile_accepted", "causal_fir_admitted", "accepted_receiver", "acceptance_ready", "release_ledger_promoted"}
    admission = document.get("admission")
    if not isinstance(admission, dict) or set(admission) != expected_true | expected_false or any(admission[key] is not True for key in expected_true) or any(admission[key] is not False for key in expected_false):
        raise VerificationError("gate_promotion")
    _expect(document.get("blockers"), ["strict_v2_source_strobe_identity_not_observed_and_no_source_tolerance_authorized", "v2_candidate_waveform_observation_missing", "accepted_receiver_stage_missing", "statistical_eye_contour_semantics_missing"], "blockers")
    inventory = observation.get("source_inventory")
    if not isinstance(inventory, dict) or len(inventory) != 3 or any(not isinstance(path, str) or not _hex(value) for path, value in inventory.items()):
        raise VerificationError("inventory_shape")
    if any(token in str(document).lower() for token in ("file://", "http://", "https://", "c:\\", "waveform: [", "samples: [")):
        raise VerificationError("evidence_leak")
    return {"valid": True, "strict_bitwise_identity": False, "candidate_evaluated": False}


def verify_current_source_identity(document: dict[str, object]) -> None:
    tree = subprocess.run(["git", "rev-parse", f"{ARCHIVE_COMMIT}^{{tree}}"], cwd=ROOT, capture_output=True, text=True, check=False)
    observation = document["external_observation"]
    assert isinstance(observation, dict)
    inventory = observation["source_inventory"]
    assert isinstance(inventory, dict)
    if tree.returncode or tree.stdout.strip() != ARCHIVE_TREE or _archive_inventory(set(inventory)) != inventory:
        raise VerificationError("source_drift")


def main() -> int:
    try:
        document = yaml.safe_load(PATH.read_text(encoding="utf-8"))
        result = verify_document(document)
        verify_current_source_identity(document)
    except (OSError, ValueError, yaml.YAMLError, VerificationError) as error:
        print(f"p3c_ads_prbssrc_source_only_v2_observation_evidence_failed:{error}")
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
