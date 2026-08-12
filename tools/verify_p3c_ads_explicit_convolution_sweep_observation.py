"""Fail-closed verifier for the P3C external explicit ADS convolution sweep."""

from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import sys

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs" / "baselines" / "p3c-ads-explicit-convolution-sweep-observation.v1.yaml"
STATIC = ROOT / "docs" / "baselines" / "p3c-selected-four-port-static-bench.v1.yaml"
SCHEMA = "sipi.p3c-ads-explicit-convolution-sweep-observation.v1"
REPORT_SHA256 = "e992a607dd58cab38bb43e74b9c03ab4620db7ed2853436777ba8c9f8103cd65"
SOURCE_SHA256 = "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47"
RUNNER_SHA256 = "94b76e640a8ad823f6e66fc2f0aff8eb33771ca9c2a5ab14923e58b5bf1353bc"
SWEEP_SHA256 = "9fedb2c8477fa2bf58c5b107eb593b8d930989214363c62b526481bc1c24f183"
EXTERNAL_WAVEFORM_SHA256S = {
    "5ec5211a273d313655f0b8ced35d58ea89d0bba113f5edc3fd9712218f46e726",
    "402596d9f5ab37e37cc3f4927f55170ab007159376174453fc65b78e3a80d31c",
    "590161e828e1ce9d06d2cb5f224d2df4773e63311858b91b90d0820156caaf0f",
    "9849c3c47acfd455126cad5b1fc7e14dd8d35806439287df0a6a742cab272b8c",
    "2b93c986721aae5b80d58420a084395400e70a33364065a11a818dca4031f143",
    "5bd216843d1d7624dfc42077d0ff2eb8c1ef24effca41a29cd4d149c98433f8d",
    "9d137886b26593e05435102b848f38de6095d90a2e153f565399388f6eae8305",
    "6c3f294d3453faf84c4d37c112fcaab8634ff2e0f92de6b75abd6f8e91d61746",
    "05fce3991d50c2db89e8e8cd48038270c6bb830f92a312fc2fe3215e8350570f",
    "9231f2cecae97947e281ac00f9449e99524ed30d85b2fad38f40eb9f891f2e6e",
    "e73d62080c2894f227f0b15463221ff624bcebaf571d0995662e20393f21f990",
    "7a73a5d2fa12944ec7bcde21906bc767734651cf6c622dd08ccf134abe864273",
}


class VerificationError(ValueError):
    pass


def tracked_hashes() -> set[str]:
    paths = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"], check=True, capture_output=True).stdout.split(b"\0")
    return {hashlib.sha256((ROOT / path.decode("utf-8")).read_bytes()).hexdigest() for path in paths if path}


def content_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def external_custody_hashes() -> set[str]:
    return {REPORT_SHA256, SOURCE_SHA256} | EXTERNAL_WAVEFORM_SHA256S


def verify(document: object) -> dict[str, object]:
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise VerificationError("sweep_schema_invalid")
    if document.get("status") != "external_ads_explicit_convolution_candidate_observed_product_executor_policy_still_blocked":
        raise VerificationError("sweep_status_invalid")
    if document.get("external_observation") != {"custody": "external_only_hash_only", "report_path_retained": False, "report_byte_length": 7596, "report_content_sha256": REPORT_SHA256, "fresh_observations": 2, "canonical_repeatability": "identical"}:
        raise VerificationError("sweep_observation_binding_invalid")
    if document.get("source") != {"logical_name": "channel_gen5_highloss.s4p", "byte_length": 1834156, "sha256": SOURCE_SHA256, "asset_bytes_tracked": False}:
        raise VerificationError("sweep_source_binding_invalid")
    if document.get("runner") != {"logical_name": "run_p3c_external_ads_prbs9_reference.py", "sha256": RUNNER_SHA256} or document.get("sweep") != {"logical_name": "observe_p3c_ads_explicit_convolution_sweep.py", "sha256": SWEEP_SHA256}:
        raise VerificationError("sweep_tool_binding_invalid")
    if content_sha256(ROOT / "tools" / "run_p3c_external_ads_prbs9_reference.py") != RUNNER_SHA256 or content_sha256(ROOT / "tools" / "observe_p3c_ads_explicit_convolution_sweep.py") != SWEEP_SHA256:
        raise VerificationError("sweep_tool_source_drift")
    if document.get("explicit_ads_surface") != {"fmax_hz": 4.0e10, "source_edge_seconds": 1.0e-16, "imp_mode": 1, "imp_approx": False, "imp_enforce_passivity": True, "grid_lengths": [512, 1024, 2048, 4096, 8192, 16384], "no_frequency_range_extrapolation": True, "interpolation_and_extrapolation_algorithm_observed": False}:
        raise VerificationError("explicit_ads_surface_invalid")
    expected = [
        (512, 1.5625e8, 6.4e-9, 1.4427344750535527, False),
        (1024, 7.8125e7, 1.28e-8, 0.04200230109637168, False),
        (2048, 3.90625e7, 2.56e-8, 0.0, True),
        (4096, 1.953125e7, 5.12e-8, 0.013663706128436025, False),
        (8192, 9.765625e6, 1.024e-7, 0.03438979059648014, False),
        (16384, 4.8828125e6, 2.048e-7, 0.046874379619914745, False),
    ]
    candidates = document.get("candidates")
    if not isinstance(candidates, list) or [tuple(item.get(key) for key in ("grid_length", "delta_frequency_hz", "impulse_duration_seconds", "third_period_nrmse", "within_waveform_limit")) for item in candidates if isinstance(item, dict)] != expected:
        raise VerificationError("sweep_candidates_invalid")
    if document.get("selected_external_candidate") != {"grid_length": 2048, "delta_frequency_hz": 3.90625e7, "impulse_duration_seconds": 2.56e-8, "third_period_nrmse": 0.0, "adaptive_waveform_identity_match": True, "product_policy_selected": False}:
        raise VerificationError("sweep_selection_invalid")
    admission = {"external_ads_runtime_observed": True, "explicit_ads_candidate_observed": True, "product_deterministic_time_domain_policy_observed": False, "product_executor_implemented": False, "candidate_waveform_generated": False, "external_reference_binding_evaluated": False, "accepted_receiver": False, "product_runtime_invoked": False, "p4b_ami_runtime_invoked": False, "release_ledger_promoted": False}
    if document.get("admission") != admission:
        raise VerificationError("sweep_promotion_invalid")
    required_blockers = {"product_input_construction_and_impulse_grid_mapping_missing", "product_output_strobe_mapping_missing", "product_interpolation_and_extrapolation_algorithm_missing", "product_causality_and_passivity_algorithm_missing"}
    if not required_blockers <= set(document.get("blockers", [])):
        raise VerificationError("sweep_product_policy_blocker_missing")
    static = yaml.safe_load(STATIC.read_text(encoding="utf-8"))
    if static.get("implementation", {}).get("time_domain_executor") != "not_implemented":
        raise VerificationError("static_executor_promoted")
    if external_custody_hashes() & tracked_hashes():
        raise VerificationError("external_custody_leak")
    return {"valid": True, "selected_external_grid_length": 2048, "product_executor": "not_implemented"}


def main() -> int:
    try:
        print(verify(yaml.safe_load(DEFAULT.read_text(encoding="utf-8"))))
    except (OSError, ValueError, subprocess.CalledProcessError, yaml.YAMLError) as error:
        print(f"explicit_sweep_verification_failed:{error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
