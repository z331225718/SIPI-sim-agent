"""Verify immutable external selected-S4P uniform-spectrum observation evidence."""

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
DEFAULT = ROOT / "docs" / "baselines" / "p3c-selected-s4p-uniform-spectrum-observation-evidence.v1.yaml"
SCHEMA = "sipi.p3c-selected-s4p-uniform-spectrum-observation-evidence.v1"
INVENTORY = {
    "Cargo.lock",
    "crates/sipi-artifacts/src/lib.rs",
    "crates/sipi-channel/src/p3c_fixed_four_port_bench_v1.rs",
    "crates/sipi-ieee-com-sparam/Cargo.toml",
    "crates/sipi-ieee-com-sparam/src/interp_sparam_v1.rs",
    "crates/sipi-p3c/Cargo.toml",
    "crates/sipi-p3c/src/lib.rs",
    "crates/sipi-p3c/tests/p3c_sealed_s4p_external_uniform_spectrum_runner.rs",
    "crates/sipi-touchstone/src/selected_four_port_v1.rs",
}


class VerificationError(ValueError):
    pass


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def archive_inventory() -> dict[str, str]:
    completed = subprocess.run(
        ["git", "archive", "--format=tar", "HEAD", "--", *sorted(INVENTORY)],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        raise VerificationError("uniform_spectrum_product_source_drift")
    with tempfile.TemporaryDirectory() as temporary:
        try:
            with tarfile.open(fileobj=io.BytesIO(completed.stdout), mode="r:") as archive:
                archive.extractall(temporary, filter="data")
        except tarfile.TarError as error:
            raise VerificationError("uniform_spectrum_product_source_drift") from error
        return {path: digest(Path(temporary) / path) for path in INVENTORY}


EXPECTED_OBSERVATION = {
    "schema": "sipi.p3c.sealed-selected-s4p-uniform-spectrum-observation.v1",
    "status": "observed",
    "custody": "external_only",
    "report_path_retained": False,
    "report_byte_length": 2458,
    "report_content_sha256": "7f615eacd92179be172fbf1e8f585742a25b9b8f2904517fea24a9d66372e47b",
    "clean_archive_commit": "5cca95c512db68b71cfaa3c3186d83e7d3d7351f",
    "selected_source": {
        "byte_length": 1834156,
        "sha256": "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47",
    },
    "source_identity_checks": "before_stage_after_equal",
    "fresh_custody_runs": 2,
    "manifest_sha256s": [
        "87db36b7c02de92168c3f7059c4a649572f2faabf8efa521662decbdf2bcead4",
        "29ca18553a0cbc15b4ad2a268eaef8a0e0add7f5dc8cd9cf6be2eaceac50219f",
    ],
    "record_count": 2002,
    "outcome": {
        "interpolation_status": "admitted",
        "bin_count": 25601,
        "frequency_step_bits": "417312d000000000",
        "dc_real_bits": "3fddf6d654b71fcc",
        "dc_imaginary_bits": "0000000000000000",
        "nyquist_real_bits": "000efe1add365007",
        "nyquist_imaginary_bits": "00059671589f8d45",
        "spectrum_sha256": "07e0ee6371326063f8b7747f61b92f2433bf6263a51be8f74f4e5adef83939e8",
    },
    "cleanup_status": "complete",
    "runner": {
        "source_sha256": "e28cbd3c8d2f64567a87171d6be66a77ba457bf27dd3bd53eaeff7baeb732f2d",
        "report_sha256": "bc8b0c3a858e7b526cd95e975536447501612fed5af49d8d1c817935f9b36a7d",
    },
}

EXPECTED_INVENTORY = {
    "Cargo.lock": "ed5404cc53939380b3885aef48b5d555bab0f3a1e0b3d022a3273d9c95d7cca5",
    "crates/sipi-artifacts/src/lib.rs": "85b475ec865779dbe3e21b54759ca9075b8a4516714d7192ba4b214075861997",
    "crates/sipi-channel/src/p3c_fixed_four_port_bench_v1.rs": "248bf24c494d9c956a96e2781f35f546d5de9f70f6157457da7a54aeb60baa70",
    "crates/sipi-ieee-com-sparam/Cargo.toml": "96a5dedc94ca40fba02342eb3dd971d8bd3371a5ba48e4a5cbf91173b7c77720",
    "crates/sipi-ieee-com-sparam/src/interp_sparam_v1.rs": "9a95daf6e964cd121d6c8c442c152ab846ccd39b58ecfaa53dd22f0ea73db15a",
    "crates/sipi-p3c/Cargo.toml": "b783524b83cc3d950d6fb1666767a2c38bf162066fc114d30881412ee774b47d",
    "crates/sipi-p3c/src/lib.rs": "aaf4b40fcc17d4ff2ae4ab512ecf7d68416dea6aaa8c4254521ae1ab57813b36",
    "crates/sipi-p3c/tests/p3c_sealed_s4p_external_uniform_spectrum_runner.rs": "e28cbd3c8d2f64567a87171d6be66a77ba457bf27dd3bd53eaeff7baeb732f2d",
    "crates/sipi-touchstone/src/selected_four_port_v1.rs": "53b11a0cf08b0505c190b244c47f13e22f7b2b3c1f6ea712b6aba533a8805f80",
}


def verify_document(document: object) -> dict[str, object]:
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise VerificationError("uniform_spectrum_schema_invalid")
    if document.get("status") != "external_selected_s4p_uniform_spectrum_observed_raw_transform_policy_pending":
        raise VerificationError("uniform_spectrum_status_invalid")
    if document.get("external_observation") != EXPECTED_OBSERVATION:
        raise VerificationError("uniform_spectrum_observation_invalid")
    admission = document.get("admission")
    true_keys = {
        "external_static_custody_observed",
        "selected_external_s4p_static_admitted",
        "selected_interpolation_invoked",
        "selected_interpolation_admitted",
        "selected_external_uniform_spectrum_observed",
    }
    required_false = {
        "s21_to_impulse_direct_port_implemented",
        "ifft_implemented",
        "causality_enforcement_implemented",
        "delay_extraction_implemented",
        "passivity_repair_implemented",
        "truncation_implemented",
        "convolution_implemented",
        "candidate_waveform_generated",
        "external_reference_binding_evaluated",
        "candidate_metric_acceptance_evaluated",
        "accepted_receiver",
        "product_runtime_invoked",
        "p4b_ami_runtime_invoked",
        "p5_reference_evaluated",
        "release_ledger_promoted",
    }
    if not isinstance(admission, dict) or set(admission) != true_keys | required_false:
        raise VerificationError("uniform_spectrum_admission_shape_invalid")
    if any(admission.get(key) is not True for key in true_keys) or any(admission.get(key) is not False for key in required_false):
        raise VerificationError("uniform_spectrum_gate_promotion_invalid")
    blockers = document.get("blockers")
    if not isinstance(blockers, list) or "raw_impulse_ifft_policy_not_implemented" not in blockers or "candidate_convolution_and_waveform_route_not_implemented" not in blockers:
        raise VerificationError("uniform_spectrum_blocker_relaxed")
    claims = document.get("non_claims")
    if not isinstance(claims, list) or not any("causal impulse" in claim for claim in claims if isinstance(claim, str)):
        raise VerificationError("uniform_spectrum_nonclaim_missing")
    return {"valid": True, "interpolation_admitted": True, "release_admitted": False}


def verify_current_product_identity() -> None:
    if archive_inventory() != EXPECTED_INVENTORY:
        raise VerificationError("uniform_spectrum_product_source_drift")


def main() -> int:
    try:
        report = verify_document(yaml.safe_load(DEFAULT.read_text(encoding="utf-8")))
        verify_current_product_identity()
    except (OSError, ValueError, yaml.YAMLError, VerificationError) as error:
        print(f"selected_s4p_uniform_spectrum_observation_failed:{error}", file=sys.stderr)
        return 1
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
