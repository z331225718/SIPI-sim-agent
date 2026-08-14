"""Verify the fixed selected raw-to-bounded causality transfer-delta evidence."""
from __future__ import annotations

import hashlib
import io
import subprocess
import tarfile
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "docs/baselines/p3c-selected-causality-transfer-delta-observation.v1.yaml"
COMMIT = "637edac0f9f7be1ebc93e39dc2747ca71c44b4d1"
TREE = "5a1c0922c4b9bab0efc169d75a263d7d745bcf33"
HEX = set("0123456789abcdef")


class VerificationError(ValueError):
    pass


def fail_if(condition: bool, reason: str) -> None:
    if condition:
        raise VerificationError(reason)


def digest(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and not (set(value) - HEX)


def inventory(paths: set[str]) -> dict[str, str]:
    result = subprocess.run(
        ["git", "archive", "--format=tar", "HEAD", "--", *sorted(paths)],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise VerificationError("source_drift")
    with tempfile.TemporaryDirectory() as directory:
        with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:") as archive:
            archive.extractall(directory, filter="data")
        return {
            path: hashlib.sha256((Path(directory) / path).read_bytes()).hexdigest()
            for path in paths
        }


def verify(document: object, current: bool = True) -> dict[str, object]:
    fail_if(not isinstance(document, dict), "shape")
    required = {"schema", "status", "authority", "predecessor", "external_observation", "fixed_observation", "admission", "blockers", "non_claims"}
    fail_if(set(document) != required, "shape")
    fail_if(document["schema"] != "sipi.p3c-selected-causality-transfer-delta-observation-evidence.v1", "schema")
    fail_if(document["status"] != "external_selected_raw_to_bounded_causality_transfer_delta_observed_acceptance_unchanged", "status")
    observation = document["external_observation"]
    fail_if(not isinstance(observation, dict), "observation")
    exact = {
        "schema": "sipi.p3c.sealed-s4p-causality-transfer-delta-runner.v1",
        "custody": "external_only",
        "report_path_retained": False,
        "report_byte_length": 4176,
        "report_content_sha256": "a78bc9ebbce2cbea120982cb60cad60f38ccc34120502da599927c201b630182",
        "clean_archive_commit": COMMIT,
        "clean_archive_tree": TREE,
        "source_byte_length": 1834156,
        "source_sha256": "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47",
        "fresh_runs": 2,
        "record_count": 2002,
        "uniform_bin_count": 25601,
        "raw_sample_count": 51200,
        "bounded_sample_count": 51200,
        "sample_interval_bits": "3d712e0be826d695",
        "frequency_step_bits": "417312d000000000",
        "iteration_count": 32,
        "final_error_bits": "3f90f46429650cfa",
        "stop": "successive_error_difference",
        "cleanup_status": "complete",
    }
    for key, value in exact.items():
        fail_if(observation.get(key) != value, key)
    fail_if(observation.get("source_manifests") != [
        "ee8f63d55a96f6f4458737e131388ddb15c9ca5cd0211d7d2fe75f5f6b752255",
        "c0a6709ee8c166f9b9f5773ee4fe7460ea93b25831c68f0424c830d984c3e191",
    ], "freshness")
    for key in ("raw_response_sha256", "bounded_response_sha256", "raw_spectrum_sha256", "bounded_spectrum_sha256", "delta_spectrum_sha256"):
        fail_if(not digest(observation.get(key)), key)
    bracket = observation.get("residual_peak_frequency_bracket")
    expected_bracket = [
        {"index": 203, "raw_re_bits": "bfb0b988e62987dd", "raw_im_bits": "3fbf0f8afc02b66a", "bounded_re_bits": "bfaf2e7eec150906", "bounded_im_bits": "3fbfa5060fe40ff3", "delta_re_bits": "3f72249701f035a0", "delta_im_bits": "3f62af627c2b3120"},
        {"index": 204, "raw_re_bits": "bf83b227836ed856", "raw_im_bits": "3fc17e6c476e255d", "bounded_re_bits": "bf72fbcaa4e26612", "bounded_im_bits": "3fc1874b5613e892", "delta_re_bits": "3f74688461fb4a9a", "delta_im_bits": "3f31be1d4b866a00"},
    ]
    fail_if(bracket != expected_bracket, "bracket")
    expected_bands = [
        {"raw_energy_bits": "3dd6fc2ca43e3b11", "bounded_energy_bits": "3dd6f011eb7b0f88", "delta_energy_bits": "3c99861cf82e4e21"},
        {"raw_energy_bits": "3e47f3caca9a990a", "bounded_energy_bits": "3e47f3b2ed79a9ed", "delta_energy_bits": "3d94e15ceb16d19d"},
        {"raw_energy_bits": "3d99442c2a620f0c", "bounded_energy_bits": "3d9a0e4f26f1f96e", "delta_energy_bits": "3d84cd4f32a4c889"},
        {"raw_energy_bits": "3b930f6e2bbdd780", "bounded_energy_bits": "3d321e3eb55980fa", "delta_energy_bits": "3d321e596271a773"},
    ]
    fail_if(observation.get("bands") != expected_bands, "bands")
    fixed = document["fixed_observation"]
    fail_if(fixed.get("dft") != {"samples": 51200, "one_sided_bins": 25601, "sample_interval_bits": "3d712e0be826d695", "frequency_step_bits": "417312d000000000", "window": "rectangular", "forward_sign": "negative", "normalization": "none", "factorization": [32, 32, 2, 25], "bands": [[0, 1], [1, 801], [801, 2001], [2001, 25601]]}, "dft")
    fail_if(fixed.get("residual_peak_frequency_bracket_bins") != [203, 204], "bracket_policy")
    source = observation.get("source_inventory")
    fail_if(not isinstance(source, dict) or len(source) != 31 or any(not isinstance(path, str) or not digest(value) for path, value in source.items()), "inventory")
    tree = subprocess.run(["git", "rev-parse", f"{COMMIT}^{{tree}}"], cwd=ROOT, capture_output=True, text=True, check=False)
    fail_if(tree.returncode != 0 or tree.stdout.strip() != TREE, "archive")
    if current:
        fail_if(inventory(set(source)) != source, "source_drift")
    true = {"raw_to_causal_transfer_delta_defined", "raw_to_causal_transfer_delta_invoked", "raw_to_causal_transfer_delta_observed", "residual_peak_frequency_bracket_observed"}
    false = {"causality_cause_identified", "causality_policy_changed", "candidate_waveform_generated", "external_reference_binding_evaluated", "acceptance_ready", "release_ledger_promoted"}
    admission = document["admission"]
    fail_if(not isinstance(admission, dict) or set(admission) != true | false or any(admission[key] is not True for key in true) or any(admission[key] is not False for key in false), "gates")
    forbidden = ("file://", "http://", "https://", "c:\\", "raw_samples:", "bounded_samples:", "spectrum: [")
    fail_if(any(token in str(document).lower() for token in forbidden), "leak")
    return {"valid": True, "accepted": False, "cause_identified": False}


def main() -> int:
    try:
        print(verify(yaml.safe_load(PATH.read_text(encoding="utf-8"))))
    except (OSError, ValueError, yaml.YAMLError, VerificationError) as error:
        print(f"p3c_selected_causality_transfer_delta_observation_failed:{error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
