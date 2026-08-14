"""Verify immutable selected-S4P raw-periodic external observation evidence."""

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
DEFAULT = ROOT / "docs" / "baselines" / "p3c-selected-s4p-raw-periodic-observation-evidence.v1.yaml"
SCHEMA = "sipi.p3c-selected-s4p-raw-periodic-observation-evidence.v1"
INVENTORY = {
    "Cargo.lock",
    "Cargo.toml",
    "crates/sipi-artifacts/src/lib.rs",
    "crates/sipi-channel/src/p3c_fixed_four_port_bench_v1.rs",
    "crates/sipi-ieee-com-sparam/Cargo.toml",
    "crates/sipi-ieee-com-sparam/NOTICE-IEEE-802-COM.md",
    "crates/sipi-ieee-com-sparam/SOURCE-MAP.md",
    "crates/sipi-ieee-com-sparam/src/interp_sparam_v1.rs",
    "crates/sipi-ieee-com-sparam/src/lib.rs",
    "crates/sipi-ieee-com-sparam/src/s21_to_raw_periodic_v1.rs",
    "crates/sipi-p3c/Cargo.toml",
    "crates/sipi-p3c/src/lib.rs",
    "crates/sipi-p3c/tests/p3c_sealed_s4p_external_raw_periodic_runner.rs",
    "crates/sipi-touchstone/src/lib.rs",
    "crates/sipi-touchstone/src/selected_four_port_v1.rs",
    "crates/sipi-types/src/lib.rs",
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
        raise VerificationError("raw_periodic_product_source_drift")
    with tempfile.TemporaryDirectory() as temporary:
        try:
            with tarfile.open(fileobj=io.BytesIO(completed.stdout), mode="r:") as archive:
                archive.extractall(temporary, filter="data")
        except tarfile.TarError as error:
            raise VerificationError("raw_periodic_product_source_drift") from error
        return {path: digest(Path(temporary) / path) for path in INVENTORY}


EXPECTED_OBSERVATION = {
    "schema": "sipi.p3c.sealed-selected-s4p-raw-periodic-observation.v1",
    "status": "observed",
    "custody": "external_only",
    "report_path_retained": False,
    "report_byte_length": 3480,
    "report_content_sha256": "b96a90333d23d3a9b9177c94ec72c0656477420573910db43f3424b0ef9e8bd0",
    "clean_archive_commit": "ffb29589950515073d2f2a2da9732e92f5c98da6",
    "selected_source": {
        "byte_length": 1834156,
        "sha256": "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47",
    },
    "source_identity_checks": "before_stage_after_equal",
    "fresh_custody_runs": 2,
    "manifest_sha256s": [
        "26eca8e8361874ea0a440784702f1678c29678473ee7a072f63b9d503afcdd68",
        "dbc282a8b0bb2a0bdfc5b709cc879b308662d9e8978dbe2a65f1f8c8da403f41",
    ],
    "record_count": 2002,
    "outcome": {
        "raw_periodic_status": "admitted",
        "uniform_bin_count": 25601,
        "raw_sample_count": 51200,
        "frequency_step_bits": "417312d000000000",
        "sample_interval_bits": "3d712e0be826d695",
        "endpoint_imaginary_residue_bits": "00059671589f8d45",
        "inverse_imaginary_residue_bits": "3c22544746104795",
        "endpoint_imaginary_residue_bound_bits": "3dca49efbe2db7a4",
        "inverse_imaginary_residue_bound_bits": "3d7644d126d40f3c",
        "uniform_spectrum_sha256": "07e0ee6371326063f8b7747f61b92f2433bf6263a51be8f74f4e5adef83939e8",
        "raw_response_sha256": "4077e5a734ee9509267a85622830144aab31b69ed1eb86ed744eba1ab552ba3d",
    },
    "cleanup_status": "complete",
    "runner": {
        "source_sha256": "a94b707ffbc0259fde81c2845c74a59b389a87d050dac7ddab9c6a2cc657a2fe",
        "report_sha256": "222cbd139397feb43393a4551f2ecf7a37287ccaeb5eb3bc4dd3230fd5b8adca",
    },
}

EXPECTED_INVENTORY = {
    "Cargo.lock": "3c2e71b21ec09e65a90fd1b42dd0353147607ea4d1645210d3ead3e094aea762",
    "Cargo.toml": "ccfb303fa9c3593a19d5f9c240b7d9aebddbf33bfd658d5a444ba06734cc3ca2",
    "crates/sipi-artifacts/src/lib.rs": "85b475ec865779dbe3e21b54759ca9075b8a4516714d7192ba4b214075861997",
    "crates/sipi-channel/src/p3c_fixed_four_port_bench_v1.rs": "248bf24c494d9c956a96e2781f35f546d5de9f70f6157457da7a54aeb60baa70",
    "crates/sipi-ieee-com-sparam/Cargo.toml": "044d3d837957f99bf3429d7c51cf1b32129ae2744d921bd95def313a0aa1942b",
    "crates/sipi-ieee-com-sparam/NOTICE-IEEE-802-COM.md": "bddd0b824dd61554c17c53ccd6fc0f2065ef8de5007928908c8323e8bb04eca9",
    "crates/sipi-ieee-com-sparam/SOURCE-MAP.md": "ca5c2ce22c16e420d8ccdb784486979eda602c10a9494b7f271aab32d47e5f75",
    "crates/sipi-ieee-com-sparam/src/interp_sparam_v1.rs": "9a95daf6e964cd121d6c8c442c152ab846ccd39b58ecfaa53dd22f0ea73db15a",
    "crates/sipi-ieee-com-sparam/src/lib.rs": "d9835a6c023bf42db4ad5f2d8bf8fe1f4825719675fdf546d3d0e998a80d33e1",
    "crates/sipi-ieee-com-sparam/src/s21_to_raw_periodic_v1.rs": "db1ca2b97038c4e5c56260f152abe19dddd27a9c73f6975f8c63d728d376f43b",
    "crates/sipi-p3c/Cargo.toml": "b783524b83cc3d950d6fb1666767a2c38bf162066fc114d30881412ee774b47d",
    "crates/sipi-p3c/src/lib.rs": "aaf4b40fcc17d4ff2ae4ab512ecf7d68416dea6aaa8c4254521ae1ab57813b36",
    "crates/sipi-p3c/tests/p3c_sealed_s4p_external_raw_periodic_runner.rs": "a94b707ffbc0259fde81c2845c74a59b389a87d050dac7ddab9c6a2cc657a2fe",
    "crates/sipi-touchstone/src/lib.rs": "359b0c44894d6cf2b03eca19626d180a9f921695a71681e901c5bcb0c77fc5cc",
    "crates/sipi-touchstone/src/selected_four_port_v1.rs": "53b11a0cf08b0505c190b244c47f13e22f7b2b3c1f6ea712b6aba533a8805f80",
    "crates/sipi-types/src/lib.rs": "b54f9e937bab7fc7830e56ef4f2ec861caf1ffed7a5718cf45bae92397ee5576",
}


def verify_document(document: object) -> dict[str, object]:
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise VerificationError("raw_periodic_schema_invalid")
    if document.get("status") != "external_selected_s4p_raw_periodic_observed_causality_and_candidate_route_pending":
        raise VerificationError("raw_periodic_status_invalid")
    if document.get("external_observation") != EXPECTED_OBSERVATION:
        raise VerificationError("raw_periodic_observation_invalid")
    admission = document.get("admission")
    true_keys = {
        "external_static_custody_observed",
        "selected_external_s4p_static_admitted",
        "selected_interpolation_invoked",
        "selected_interpolation_admitted",
        "selected_external_uniform_spectrum_observed",
        "external_selected_raw_periodic_transform_invoked",
        "external_selected_raw_periodic_transform_admitted",
        "external_selected_raw_periodic_response_observed",
    }
    false_keys = {
        "causal_impulse_admitted",
        "causality_enforcement_implemented",
        "delay_extraction_implemented",
        "passivity_repair_implemented",
        "truncation_implemented",
        "linear_convolution_implemented",
        "candidate_waveform_generated",
        "external_reference_binding_evaluated",
        "candidate_metric_acceptance_evaluated",
        "accepted_receiver",
        "product_runtime_invoked",
        "p4b_ami_runtime_invoked",
        "p5_reference_evaluated",
        "release_ledger_promoted",
    }
    if not isinstance(admission, dict) or set(admission) != true_keys | false_keys:
        raise VerificationError("raw_periodic_admission_shape_invalid")
    if any(admission.get(key) is not True for key in true_keys) or any(admission.get(key) is not False for key in false_keys):
        raise VerificationError("raw_periodic_gate_promotion_invalid")
    blockers = document.get("blockers")
    if not isinstance(blockers, list) or "raw_periodic_response_is_not_a_causal_impulse_or_fir" not in blockers or "linear_convolution_and_candidate_waveform_route_not_implemented" not in blockers:
        raise VerificationError("raw_periodic_blocker_relaxed")
    claims = document.get("non_claims")
    if not isinstance(claims, list) or not any("not a causal impulse" in item for item in claims if isinstance(item, str)):
        raise VerificationError("raw_periodic_nonclaim_missing")
    return {"valid": True, "raw_periodic_observed": True, "release_admitted": False}


def verify_current_product_identity() -> None:
    if archive_inventory() != EXPECTED_INVENTORY:
        raise VerificationError("raw_periodic_product_source_drift")


def main() -> int:
    try:
        report = verify_document(yaml.safe_load(DEFAULT.read_text(encoding="utf-8")))
        verify_current_product_identity()
    except (OSError, ValueError, yaml.YAMLError, VerificationError) as error:
        print(f"selected_s4p_raw_periodic_observation_failed:{error}", file=sys.stderr)
        return 1
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
