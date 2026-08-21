"""Verify the fresh current-head external residual DFT observation."""
from __future__ import annotations

import hashlib
import io
import subprocess
import tarfile
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "docs/baselines/p3c-selected-highloss-residual-dft-v2-current-head-observation-evidence.v1.yaml"
COMMIT = "97b0f271abcb7df02a3a9b259c4dafee86f3a783"
TREE = "7ae439ec366e30e050931ecb1f18f360e66540c1"
HEX = set("0123456789abcdef")


class VerificationError(ValueError):
    pass


def fail_if(condition: bool, reason: str) -> None:
    if condition:
        raise VerificationError(reason)


def digest(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and not (set(value) - HEX)


def inventory(paths: set[str], revision: str = COMMIT) -> dict[str, str]:
    result = subprocess.run(
        ["git", "archive", "--format=tar", revision, "--", *sorted(paths)],
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


def verify(document: object, current: bool = False) -> dict[str, object]:
    fail_if(not isinstance(document, dict), "shape")
    required = {
        "schema",
        "status",
        "authority",
        "predecessor",
        "external_observation",
        "admission",
        "blockers",
        "non_claims",
    }
    fail_if(set(document) != required, "shape")
    fail_if(
        document["schema"]
        != "sipi.p3c-selected-highloss-residual-dft-v2-current-head-observation-evidence.v1",
        "schema",
    )
    fail_if(
        document["status"]
        != "external_selected_v2_residual_spectral_distribution_observed_current_clean_archive",
        "status",
    )
    observation = document["external_observation"]
    fail_if(not isinstance(observation, dict), "observation")
    exact = {
        "schema": "sipi.p3c.external-ads-selected-highloss-residual-dft-v2-runner.v1",
        "custody": "external_only",
        "report_path_retained": False,
        "report_byte_length": 3605,
        "report_content_sha256": "24256d63b269aec2e130903dc88efc0a928fd3c49aa99241506afe6edd21ff85",
        "clean_archive_commit": COMMIT,
        "clean_archive_tree": TREE,
        "fresh_runs": 2,
        "record_count": 2002,
        "time_nrmse_bits": "3f9dd184cd51df98",
        "frequency_nrmse_bits": "3f9dd184cd51df99",
        "maximum_residual_energy_bin": 65,
        "cleanup_status": "complete",
    }
    for key, value in exact.items():
        fail_if(observation.get(key) != value, key)
    fail_if(
        observation.get("fixed_dft")
        != {
            "samples": 16352,
            "sample_interval_bits": "3d712e0be826d695",
            "window": "rectangular",
            "forward_sign": "negative",
            "normalization": "none",
            "factorization": [32, 7, 73],
            "bands": [[0, 1], [1, 256], [256, 639], [639, 8177]],
        },
        "dft",
    )
    fail_if(
        observation.get("source_manifests")
        != [
            "52b98a806628449d2b9c75c786bf9dc9700885d8885a38cbc3215653df6852a5",
            "100fe11e401cf070bc75299a751300f1b4da7a597da0b866793d00f8c679729c",
        ],
        "freshness",
    )
    identity = {
        "source_sha256": "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47",
        "ads_canonical_triple_payload_sha256": "5ec5211a273d313655f0b8ced35d58ea89d0bba113f5edc3fd9712218f46e726",
        "reference_rx_payload_sha256": "2cf94baf436bd04ff86baeca7d03eab1e6d9a8ce019163d43987a0200eb1bfa5",
        "candidate_prefix_sha256": "46b95963363de9439194ebcbf034088cdf984ea5c7d1b72ba3bb1ebf67a1ae3d",
        "reference_spectrum_sha256": "d6284475a6a6226c089d29844962a27f3aa66b1dd2720d448cfa8afed42a51de",
        "candidate_spectrum_sha256": "a3980d7b2a7b6b9031c6d4836f2149e4b7b18c7802bee412802179e2f1a9227f",
        "residual_spectrum_sha256": "5528d65ac6344adbece92cd494129d50f12df454a9b70bfbfb6e4d15de64cfe9",
    }
    for key, value in identity.items():
        fail_if(observation.get(key) != value or not digest(observation.get(key)), key)
    bands = observation.get("bands")
    expected_bands = [
        {
            "reference_energy_bits": "3eac2af8c261f3bf",
            "candidate_energy_bits": "3eab92753b2d6821",
            "residual_energy_bits": "3dda150a0058278d",
            "residual_to_reference_sqrt_bits": "3f85c60a006e3b22",
        },
        {
            "reference_energy_bits": "3f9205e8112c702a",
            "candidate_energy_bits": "3f9205d8fda9dc8c",
            "residual_energy_bits": "3edaf65a79c85d0e",
            "residual_to_reference_sqrt_bits": "3f9391d7e7d0cca1",
        },
        {
            "reference_energy_bits": "3ec94879f8d1b113",
            "candidate_energy_bits": "3ec9cb713e03275f",
            "residual_energy_bits": "3eaedf25e5cc9178",
            "residual_to_reference_sqrt_bits": "3fe1ae1b4250cb96",
        },
        {
            "reference_energy_bits": "3edfd3826e41ba44",
            "candidate_energy_bits": "3e1a95b0d79fefa7",
            "residual_energy_bits": "3edfd115600f2e39",
            "residual_to_reference_sqrt_bits": "3feffec7c0db812d",
        },
    ]
    fail_if(
        bands != expected_bands
        or any(
            not isinstance(band, dict)
            or any(
                not isinstance(value, str)
                or len(value) != 16
                or set(value) - HEX
                for value in band.values()
            )
            for band in (bands if isinstance(bands, list) else [])
        ),
        "bands",
    )
    source = observation.get("source_inventory")
    fail_if(
        not isinstance(source, dict)
        or len(source) != 30
        or any(not isinstance(path, str) or not digest(value) for path, value in source.items()),
        "inventory",
    )
    tree = subprocess.run(
        ["git", "rev-parse", f"{COMMIT}^{{tree}}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    fail_if(tree.returncode != 0 or tree.stdout.strip() != TREE, "archive")
    if current:
        ancestry = subprocess.run(
            ["git", "merge-base", "--is-ancestor", COMMIT, "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        fail_if(ancestry.returncode != 0, "head_lineage")
        fail_if(inventory(set(source), "HEAD") != source, "source_drift")
    fail_if(
        document["authority"]
        != {
            "actor": "product",
            "decision_ref": "fixed-p3c-04ar-diagnostic-policy-v1",
            "scope": "current_v2_candidate_third_period_dft_diagnostic_only",
        },
        "authority",
    )
    fail_if(
        document["predecessor"]
        != "docs/baselines/p3c-selected-highloss-residual-dft-v2-observation-evidence.v1.yaml",
        "predecessor",
    )
    admission = document["admission"]
    true = {
        "selected_residual_dft_diagnostic_defined",
        "external_selected_v2_residual_dft_invoked",
        "current_v2_candidate_baseline_reproduced",
        "residual_spectral_distribution_observed",
        "parseval_integrity_verified",
    }
    false = {
        "selected_highloss_waveform_only_profile_accepted",
        "acceptance_ready",
        "release_ledger_promoted",
    }
    fail_if(
        not isinstance(admission, dict)
        or set(admission) != true | false
        or any(admission[key] is not True for key in true)
        or any(admission[key] is not False for key in false),
        "gates",
    )
    fail_if(
        document["blockers"]
        != [
            "selected_highloss_waveform_nrmse_exceeds_fixed_one_percent_limit",
            "strict_v2_source_strobe_identity_not_observed_and_no_source_tolerance_authorized",
            "residual_spectral_distribution_does_not_identify_physical_cause",
            "accepted_receiver_stage_missing",
            "statistical_eye_contour_semantics_missing",
        ],
        "blockers",
    )
    fail_if(
        document["non_claims"]
        != [
            "The bands only describe the raw current residual; they do not select, correct, filter, or inverse-transform a candidate.",
            "This is not an ADS/COM parity, causality, interpolation, passivity, source, receiver, acceptance, or release result.",
            "No path, waveform, residual vector, spectrum bin, external report, or uv.lock content is retained.",
        ],
        "non_claims",
    )
    fail_if(
        any(token in str(document).lower() for token in ("file://", "http://", "https://", "c:\\", "waveform: [", "spectrum: [")),
        "leak",
    )
    return {"valid": True, "accepted": False, "cause_identified": False}


def main() -> int:
    try:
        print(verify(yaml.safe_load(PATH.read_text(encoding="utf-8")), current=True))
    except (OSError, ValueError, yaml.YAMLError, VerificationError) as error:
        print(f"p3c_selected_highloss_residual_dft_current_head_evidence_failed:{error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
