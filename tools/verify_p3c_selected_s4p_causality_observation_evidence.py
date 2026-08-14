"""Verify selected-S4P bounded-causality external observation evidence."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs/baselines/p3c-selected-s4p-causality-observation-evidence.v1.yaml"
SCHEMA = "sipi.p3c-selected-s4p-causality-observation-evidence.v1"


class VerificationError(ValueError):
    pass


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def archive_inventory(paths: set[str]) -> dict[str, str]:
    completed = subprocess.run(["git", "archive", "--format=tar", "HEAD", "--", *sorted(paths)], cwd=ROOT, capture_output=True, check=False)
    if completed.returncode:
        raise VerificationError("causality_product_source_drift")
    with tempfile.TemporaryDirectory() as temporary:
        try:
            with tarfile.open(fileobj=io.BytesIO(completed.stdout), mode="r:") as archive:
                archive.extractall(temporary, filter="data")
        except tarfile.TarError as error:
            raise VerificationError("causality_product_source_drift") from error
        return {path: digest(Path(temporary) / path) for path in paths}


def verify_document(document: object) -> dict[str, object]:
    if not isinstance(document, dict) or document.get("schema") != SCHEMA or document.get("status") != "external_selected_s4p_bounded_causality_observed_candidate_route_pending":
        raise VerificationError("causality_schema_or_status_invalid")
    observation = document.get("external_observation")
    required = {"schema", "status", "custody", "report_path_retained", "report_byte_length", "report_content_sha256", "clean_archive_commit", "selected_source", "source_identity_checks", "fresh_custody_runs", "manifest_sha256s", "record_count", "outcome", "cleanup_status", "runner", "product_source_inventory"}
    if not isinstance(observation, dict) or set(observation) != required or observation.get("schema") != "sipi.p3c.sealed-selected-s4p-causality-observation.v1" or observation.get("status") != "observed" or observation.get("custody") != "external_only" or observation.get("report_path_retained") is not False or observation.get("report_byte_length") != 3342 or observation.get("report_content_sha256") != "a31bfb1807261f5af6c433429f828762aa90e0861e59175e81eae25deda750a9" or observation.get("clean_archive_commit") != "8e5d33d31982aa483c971615b91686ff8557c831" or observation.get("selected_source") != {"byte_length": 1834156, "sha256": "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47"} or observation.get("source_identity_checks") != "before_stage_after_equal" or observation.get("fresh_custody_runs") != 2 or observation.get("manifest_sha256s") != ["bd2319598fe5687e8c87c02da81bba495a52f428b5af5398a65d036776d7015e", "c4fe594837e0aa4992ee66664ddd2515edda774729206f843ba09ffb08735fb5"] or observation.get("record_count") != 2002 or observation.get("cleanup_status") != "complete":
        raise VerificationError("causality_observation_invalid")
    if observation.get("outcome") != {"causality_status": "admitted", "uniform_bin_count": 25601, "causal_sample_count": 51200, "sample_interval_bits": "3d712e0be826d695", "iteration_count": 32, "final_error_bits": "3f90f46429650cfa", "stop": "successive_error_difference", "causal_response_sha256": "d111d4024eb26436fa8cced56026ecb5231df888499d7d7e122379c01078d949"} or observation.get("runner") != {"source_sha256": "7e0ffec717d3b5fcf41f2fce6e96a54da1de8ee7209a479edac08f1685cbc543", "report_sha256": "5192a4b12e70c1edac43285720ad8464242a06cf171edea8888bfec310db7360"}:
        raise VerificationError("causality_outcome_invalid")
    inventory = observation.get("product_source_inventory")
    if not isinstance(inventory, dict) or not inventory or any(not isinstance(path, str) or not isinstance(value, str) or len(value) != 64 for path, value in inventory.items()):
        raise VerificationError("causality_inventory_invalid")
    true_keys = {"external_static_custody_observed", "selected_external_s4p_static_admitted", "selected_interpolation_invoked", "selected_interpolation_admitted", "selected_external_uniform_spectrum_observed", "external_selected_raw_periodic_transform_invoked", "external_selected_raw_periodic_transform_admitted", "external_selected_raw_periodic_response_observed", "external_selected_causality_invoked", "external_selected_causality_admitted", "external_selected_causality_observed"}
    false_keys = {"causal_impulse_admitted", "delay_extraction_implemented", "passivity_repair_implemented", "truncation_implemented", "linear_convolution_implemented", "candidate_waveform_generated", "external_reference_binding_evaluated", "candidate_metric_acceptance_evaluated", "accepted_receiver", "product_runtime_invoked", "p4b_ami_runtime_invoked", "p5_reference_evaluated", "release_ledger_promoted"}
    admission = document.get("admission")
    if not isinstance(admission, dict) or set(admission) != true_keys | false_keys or any(admission.get(key) is not True for key in true_keys) or any(admission.get(key) is not False for key in false_keys):
        raise VerificationError("causality_gate_promotion_invalid")
    blockers, claims = document.get("blockers"), document.get("non_claims")
    if not isinstance(blockers, list) or "bounded_causality_response_not_admitted_as_causal_impulse_or_fir" not in blockers or "truncation_and_linear_convolution_not_implemented" not in blockers or not isinstance(claims, list) or not any("not an admitted causal impulse" in item for item in claims if isinstance(item, str)):
        raise VerificationError("causality_nonclaim_or_blocker_relaxed")
    return {"valid": True, "causality_observed": True, "release_admitted": False}


def verify_current_product_identity(document: dict[str, object]) -> None:
    observation = document["external_observation"]
    assert isinstance(observation, dict)
    inventory = observation["product_source_inventory"]
    assert isinstance(inventory, dict)
    if archive_inventory(set(inventory)) != inventory:
        raise VerificationError("causality_product_source_drift")


def main() -> int:
    try:
        document = yaml.safe_load(DEFAULT.read_text(encoding="utf-8"))
        report = verify_document(document)
        verify_current_product_identity(document)
    except (OSError, ValueError, yaml.YAMLError, VerificationError) as error:
        print(f"selected_s4p_causality_observation_failed:{error}", file=sys.stderr)
        return 1
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
