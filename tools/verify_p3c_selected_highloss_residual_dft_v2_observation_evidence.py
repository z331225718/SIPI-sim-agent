"""Verify the fixed current-v2 residual DFT observation evidence."""
from __future__ import annotations
import hashlib, io, subprocess, tarfile, tempfile
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "docs/baselines/p3c-selected-highloss-residual-dft-v2-observation-evidence.v1.yaml"
COMMIT = "7f1dc8fe37d70cb42d299ced53a06a1b810e6f6d"
TREE = "78765e46408bda291466c059063d993111565ced"
HEX = set("0123456789abcdef")

class VerificationError(ValueError): pass
def fail_if(condition: bool, reason: str) -> None:
    if condition: raise VerificationError(reason)
def digest(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and not (set(value) - HEX)
def inventory(paths: set[str]) -> dict[str, str]:
    result = subprocess.run(["git", "archive", "--format=tar", "HEAD", "--", *sorted(paths)], cwd=ROOT, capture_output=True, check=False)
    if result.returncode: raise VerificationError("source_drift")
    with tempfile.TemporaryDirectory() as directory:
        with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:") as archive: archive.extractall(directory, filter="data")
        return {path: hashlib.sha256((Path(directory) / path).read_bytes()).hexdigest() for path in paths}
def verify(document: object, current: bool = True) -> dict[str, object]:
    fail_if(not isinstance(document, dict), "shape")
    required = {"schema", "status", "authority", "predecessor", "external_observation", "admission", "blockers", "non_claims"}
    fail_if(set(document) != required, "shape")
    fail_if(document["schema"] != "sipi.p3c-selected-highloss-residual-dft-v2-observation-evidence.v1", "schema")
    fail_if(document["status"] != "external_selected_v2_residual_spectral_distribution_observed_acceptance_unchanged", "status")
    observation = document["external_observation"]
    fail_if(not isinstance(observation, dict), "observation")
    exact = {"schema": "sipi.p3c.external-ads-selected-highloss-residual-dft-v2-runner.v1", "custody": "external_only", "report_path_retained": False, "report_byte_length": 3605, "report_content_sha256": "24256d63b269aec2e130903dc88efc0a928fd3c49aa99241506afe6edd21ff85", "clean_archive_commit": COMMIT, "clean_archive_tree": TREE, "fresh_runs": 2, "record_count": 2002, "time_nrmse_bits": "3f9dd184cd51df98", "frequency_nrmse_bits": "3f9dd184cd51df99", "maximum_residual_energy_bin": 65, "cleanup_status": "complete"}
    for key, value in exact.items(): fail_if(observation.get(key) != value, key)
    fail_if(observation.get("fixed_dft") != {"samples": 16352, "sample_interval_bits": "3d712e0be826d695", "window": "rectangular", "forward_sign": "negative", "normalization": "none", "factorization": [32, 7, 73], "bands": [[0, 1], [1, 256], [256, 639], [639, 8177]]}, "dft")
    fail_if(observation.get("source_manifests") != ["52b98a806628449d2b9c75c786bf9dc9700885d8885a38cbc3215653df6852a5", "100fe11e401cf070bc75299a751300f1b4da7a597da0b866793d00f8c679729c"], "freshness")
    for key in ("source_sha256", "ads_canonical_triple_payload_sha256", "reference_rx_payload_sha256", "candidate_prefix_sha256", "reference_spectrum_sha256", "candidate_spectrum_sha256", "residual_spectrum_sha256"):
        fail_if(not digest(observation.get(key)), key)
    bands = observation.get("bands")
    fail_if(not isinstance(bands, list) or len(bands) != 4 or any(not isinstance(band, dict) or set(band) != {"reference_energy_bits", "candidate_energy_bits", "residual_energy_bits", "residual_to_reference_sqrt_bits"} or any(not isinstance(value, str) or len(value) != 16 for value in band.values()) for band in bands), "bands")
    source = observation.get("source_inventory")
    fail_if(not isinstance(source, dict) or len(source) != 30 or any(not isinstance(path, str) or not digest(value) for path, value in source.items()), "inventory")
    tree = subprocess.run(["git", "rev-parse", f"{COMMIT}^{{tree}}"], cwd=ROOT, capture_output=True, text=True, check=False)
    fail_if(tree.returncode != 0 or tree.stdout.strip() != TREE, "archive")
    if current: fail_if(inventory(set(source)) != source, "source_drift")
    admission = document["admission"]
    true = {"selected_residual_dft_diagnostic_defined", "external_selected_v2_residual_dft_invoked", "current_v2_candidate_baseline_reproduced", "residual_spectral_distribution_observed", "parseval_integrity_verified"}
    false = {"selected_highloss_waveform_only_profile_accepted", "acceptance_ready", "release_ledger_promoted"}
    fail_if(not isinstance(admission, dict) or set(admission) != true | false or any(admission[key] is not True for key in true) or any(admission[key] is not False for key in false), "gates")
    fail_if(any(token in str(document).lower() for token in ("file://", "http://", "https://", "c:\\", "waveform: [", "spectrum: [")), "leak")
    return {"valid": True, "accepted": False, "cause_identified": False}
def main() -> int:
    try: print(verify(yaml.safe_load(PATH.read_text(encoding="utf-8"))))
    except (OSError, ValueError, yaml.YAMLError, VerificationError) as error: print(f"p3c_selected_highloss_residual_dft_v2_observation_evidence_failed:{error}"); return 1
    return 0
if __name__ == "__main__": raise SystemExit(main())
