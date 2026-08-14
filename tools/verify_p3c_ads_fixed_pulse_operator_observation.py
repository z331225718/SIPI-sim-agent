"""Verify the fixed external ADS pulse-operator observation evidence."""
from __future__ import annotations

import hashlib
import io
import subprocess
import tarfile
import tempfile
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "docs/baselines/p3c-ads-fixed-pulse-operator-observation-evidence.v1.yaml"
COMMIT = "8ffe954bc5fb45a87f428f9cce7e466820fffa16"
TREE = "ac5f4d9d1bbff82032a05a26cebf3ac627b57901"
HEX = set("0123456789abcdef")


class VerificationError(ValueError):
    pass


def fail(condition: bool, reason: str) -> None:
    if condition:
        raise VerificationError(reason)


def digest(value: object, size: int = 64) -> bool:
    return isinstance(value, str) and len(value) == size and not (set(value) - HEX)


def inventory(paths: set[str]) -> dict[str, str]:
    result = subprocess.run(["git", "archive", "--format=tar", "HEAD", "--", *sorted(paths)], cwd=ROOT, check=False, capture_output=True)
    if result.returncode:
        raise VerificationError("source_drift")
    with tempfile.TemporaryDirectory() as directory:
        with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:") as archive:
            archive.extractall(directory, filter="data")
        return {path: hashlib.sha256((Path(directory) / path).read_bytes()).hexdigest() for path in paths}


def verify(document: object, current: bool = True) -> dict[str, object]:
    fail(not isinstance(document, dict), "shape")
    required = {"schema", "status", "authority", "predecessor", "external_observation", "fixed_observation", "independent_audit", "admission", "blockers", "non_claims"}
    fail(set(document) != required, "shape")
    fail(document["schema"] != "sipi.p3c-ads-fixed-pulse-operator-observation-evidence.v1", "schema")
    fail(document["status"] != "external_ads_fixed_pulse_operator_observed_acceptance_unchanged", "status")
    authority = document["authority"]
    fail(authority != {"actor": "user", "decision_ref": "user-active-goal-continue-2026-08-14", "scope": "one_external_fixed_pulse_operator_observation_only"}, "authority")
    observation = document["external_observation"]
    exact = {
        "schema": "sipi.p3c.ads-fixed-pulse-operator-observation.v1", "custody": "external_only", "report_path_retained": False,
        "report_byte_length": 4733, "report_content_sha256": "e676e89d4a7235ec2f96abc6188a3238841fbb5d4cfcf4d6d05caa12a8221abd",
        "clean_archive_commit": COMMIT, "clean_archive_tree": TREE, "source_byte_length": 1834156,
        "source_sha256": "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47", "fresh_runs": 2,
        "ads_netlist_sha256": "5a9e7f1b0f969220832e2baa776640bc76ef5183ac8bf63e5a94b7a488cb1a82",
        "ads_canonical_payload_sha256": "04c1c1ebc601805e51a282dbeb888a4a7fc1a81b0c7b39e09371e29c7ca7b691",
        "runner_source_sha256": "6e6b601a17d5554ae5308cb988e884f8d6c864c2c211251870f4f8751587f7a2",
        "runner_report_sha256": "9d7277d139d98dc0c80879fdaf9a240900b6f5899845c0a883124bcffae83ff3",
        "record_count": 2002, "uniform_bin_count": 25601, "causality_iterations": 32,
        "causality_stop": "successive_error_difference", "retained_taps": 10871, "strict_identity": False,
        "cleanup_status": "complete",
    }
    fail(not isinstance(observation, dict), "observation")
    for key, value in exact.items():
        fail(observation.get(key) != value, key)
    fail(observation.get("source_manifests") != ["4e4f5e3bb87eedd41cf9fd7805cc00a41549841017936f9b4d5d5c62246e2f31", "126a882a7953fb77c94234df6bf65031e7c7c26f603b0001dc4dab74f78b717b"], "freshness")
    for key in ("input_sha256", "ads_tx_sha256", "ads_rx_sha256", "product_prefix_sha256", "residual_sha256"):
        fail(not digest(observation.get(key)), key)
    for key, value in {
        "pre_pulse_reference_rms_bits": "0000000000000000", "pre_pulse_product_rms_bits": "0000000000000000", "pre_pulse_residual_rms_bits": "0000000000000000",
        "post_pulse_reference_rms_bits": "3f71315e2e5dcd3d", "post_pulse_product_rms_bits": "3f712f502bac9a64", "post_pulse_residual_rms_bits": "3f1fb5a9082d3174", "post_pulse_nrmse_bits": "3f9d827486f044c1",
    }.items():
        fail(observation.get(key) != value, key)
    source = observation.get("source_inventory")
    fail(not isinstance(source, dict) or len(source) != 25 or any(not isinstance(path, str) or not digest(value) for path, value in source.items()), "inventory")
    tree = subprocess.run(["git", "rev-parse", f"{COMMIT}^{{tree}}"], cwd=ROOT, capture_output=True, text=True, check=False)
    fail(tree.returncode != 0 or tree.stdout.strip() != TREE, "archive")
    if current:
        fail(inventory(set(source)) != source, "source_drift")
    fixed = document["fixed_observation"]
    fail(fixed != {"pulse": {"start_index": 16353, "end_index_exclusive": 16385, "one_volt_sample_count": 32, "edge_seconds": 1.0e-16, "width_ui": 1}, "controller": {"imp_max_freq_hz": 40000000000.0, "imp_delta_freq_hz": 39062500.0, "imp_mode": 1, "passivity_enforced": True}, "comparison": "strict_same_global_sample_index_no_transform"}, "fixed")
    fail(document["independent_audit"] != {"reviewer": "Orca_reused_OpenCode_terminal", "status": "pending_platform_unavailable_terminal_exited", "result": "not_run"}, "audit")
    true = {"external_ads_fixed_pulse_operator_observed", "product_fixed_pulse_operator_invoked", "strict_sampled_operator_delta_evaluated", "prbssrc_removed_from_diagnostic_topology"}
    false = {"ads_internal_semantics_identified", "causality_cause_identified", "candidate_waveform_accepted", "release_ledger_promoted"}
    admission = document["admission"]
    fail(not isinstance(admission, dict) or set(admission) != true | false or any(admission[key] is not True for key in true) or any(admission[key] is not False for key in false), "gates")
    fail(document["blockers"] != ["ads_output_strobe_and_convolution_semantics_not_separated", "causality_policy_cause_not_identified", "selected_prbs9_waveform_nrmse_exceeds_fixed_one_percent_limit"], "blockers")
    forbidden = ("file://", "http://", "https://", "c:\\", "samples:", "waveform:", "residual: [")
    fail(any(token in str(document).lower() for token in forbidden), "leak")
    return {"valid": True, "accepted": False, "strict_identity": False}


if __name__ == "__main__":
    try:
        print(verify(yaml.safe_load(PATH.read_text(encoding="utf-8"))))
    except (OSError, ValueError, yaml.YAMLError, VerificationError) as error:
        print(f"p3c_ads_fixed_pulse_operator_observation_failed:{error}")
        raise SystemExit(1)
