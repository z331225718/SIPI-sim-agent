"""Verify the hash-only selected v3 waveform-only external observation."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
import subprocess
import tarfile
import tempfile

import yaml


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/baselines/p3c-external-ads-selected-highloss-waveform-only-observation-evidence.v3.yaml"
SCHEMA = "sipi.p3c-external-ads-selected-highloss-waveform-only-observation-evidence.v3"
HEX = set("0123456789abcdef")
RUN_KEYS = {"source_manifest_sha256", "reference_manifest_sha256", "candidate_manifest_sha256", "record_count", "candidate_prefix_sha256", "reference_rx_payload_sha256", "candidate_payload_sha256", "reference_waveform_digest", "candidate_waveform_digest", "waveform_nrmse_bits", "waveform_nrmse_limit_bits", "within_waveform_nrmse_limit", "within_selected_waveform_only_profile"}
EXPECTED = {"record_count": 2002, "candidate_prefix_sha256": "939b7062795430f2f92702e8e2eb070d84636a42a589adcf89aee0b0f48a8769", "reference_rx_payload_sha256": "2cf94baf436bd04ff86baeca7d03eab1e6d9a8ce019163d43987a0200eb1bfa5", "candidate_payload_sha256": "b6260b4a566b0e270c78ec56c624206e48c65d8140ba47e78af1e28cfef49353", "reference_waveform_digest": "2e0ecb1e37bf7593e6774faaa7d5808a7c4acbf1ae8793f7afbda1b20bbc6e37", "candidate_waveform_digest": "44585aac33e8393cc20c6c49d2ead97e4604d75abeaebc56786b57a0f5ea9b88", "waveform_nrmse_bits": "3f9c4139b95fcc93", "waveform_nrmse_limit_bits": "3f847ae147ae147b", "within_waveform_nrmse_limit": False, "within_selected_waveform_only_profile": False}


class VerificationError(ValueError):
    pass


def _hex(value: object, size: int = 64) -> bool:
    return isinstance(value, str) and len(value) == size and not (set(value) - HEX)


def _inventory(paths: set[str]) -> dict[str, str]:
    archive = subprocess.run(["git", "archive", "--format=tar", "HEAD", "--", *sorted(paths)], cwd=ROOT, capture_output=True, check=False)
    if archive.returncode:
        raise VerificationError("waveform_only_product_source_drift")
    with tempfile.TemporaryDirectory() as temporary:
        with tarfile.open(fileobj=io.BytesIO(archive.stdout), mode="r:") as payload:
            payload.extractall(temporary, filter="data")
        return {path: hashlib.sha256((Path(temporary) / path).read_bytes()).hexdigest() for path in paths}


def verify_document(document: object) -> dict[str, object]:
    required = {"schema", "status", "authority", "predecessors", "external_observation", "admission", "blockers", "non_claims"}
    if not isinstance(document, dict) or set(document) != required or document.get("schema") != SCHEMA or document.get("status") != "external_reference_bound_selected_highloss_waveform_only_metrics_observed_not_accepted":
        raise VerificationError("waveform_only_evidence_shape")
    observation = document["external_observation"]
    needed = {"schema", "status", "custody", "report_path_retained", "report_byte_length", "report_content_sha256", "clean_archive_commit", "clean_archive_tree", "runner_preparation_commit", "runner_envelope_fix_commit", "runner_report_encoding_fix_commit", "selected_source", "ads_canonical_triple_payload", "contract_sha256", "source_reference_identity_checks", "fresh_custody_runs", "runs", "cleanup_status", "release_build", "runner_sha256", "product_source_inventory"}
    if not isinstance(observation, dict) or set(observation) != needed or observation.get("schema") != "sipi.p3c.external-ads-selected-highloss-waveform-only-runner.v3" or observation.get("status") != "observed_not_accepted" or observation.get("custody") != "external_only" or observation.get("report_path_retained") is not False or observation.get("report_byte_length") != 2413 or observation.get("report_content_sha256") != "d1302327ccf2cfa3120905eecb29a0c5719f5d798a6300ecd7db71615de87387" or observation.get("contract_sha256") != "db0d9a663b311105be329d79060f05a5179f40fd7eccf448faf85d45b73da64a" or observation.get("source_reference_identity_checks") != "before_stage_after_equal" or observation.get("fresh_custody_runs") != 2 or observation.get("cleanup_status") != "complete":
        raise VerificationError("waveform_only_observation_shape")
    if observation.get("clean_archive_commit") != "830225851030ce9935972d329705f13b5542c23b" or observation.get("clean_archive_tree") != "e9ab046f421d8a0ea8e7b2b890f69a65631d419a" or observation.get("runner_preparation_commit") != "5a8f725b29d561fdf5b19d61b212fd2c1a71cb02" or observation.get("runner_envelope_fix_commit") != "e3df4112608fff02910b8ccbcbe09d1555fff040" or observation.get("runner_report_encoding_fix_commit") != "830225851030ce9935972d329705f13b5542c23b":
        raise VerificationError("waveform_only_archive_binding")
    if observation.get("release_build") != {"profile": "release", "target": "x86_64-pc-windows-msvc", "rustc_release": "1.97.0", "executable_sha256": "fe5c36dfaf1d95b90dc73406b569ad1819faa49ed4e59ce31b806bf34b0fbde8"}:
        raise VerificationError("waveform_only_release_build")
    if observation.get("selected_source") != {"byte_length": 1834156, "sha256": "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47"} or observation.get("ads_canonical_triple_payload") != {"byte_length": 1177344, "sha256": "5ec5211a273d313655f0b8ced35d58ea89d0bba113f5edc3fd9712218f46e726", "rx_column": "differential_voltage"}:
        raise VerificationError("waveform_only_input_identity")
    runs = observation.get("runs")
    if not isinstance(runs, list) or len(runs) != 2 or any(not isinstance(run, dict) or set(run) != RUN_KEYS for run in runs):
        raise VerificationError("waveform_only_runs_shape")
    if any(run.get(key) != value for run in runs for key, value in EXPECTED.items()):
        raise VerificationError("waveform_only_metric_fact")
    for key in ("source_manifest_sha256", "reference_manifest_sha256", "candidate_manifest_sha256"):
        if runs[0][key] == runs[1][key] or any(not _hex(run[key]) for run in runs):
            raise VerificationError("waveform_only_freshness")
    if not all(run["within_waveform_nrmse_limit"] is run["within_selected_waveform_only_profile"] for run in runs):
        raise VerificationError("waveform_only_gate_consistency")
    inventory = observation.get("product_source_inventory")
    if not isinstance(inventory, dict) or len(inventory) < 30 or any(not isinstance(path, str) or not _hex(digest) for path, digest in inventory.items()):
        raise VerificationError("waveform_only_inventory_shape")
    if observation.get("runner_sha256") != inventory.get("crates/sipi-p3c/tests/p3c_external_ads_selected_highloss_waveform_only_runner.rs"):
        raise VerificationError("waveform_only_runner_identity")
    admission = document.get("admission")
    true_keys = {"selected_highloss_waveform_only_contract_ready", "external_ads_reference_bound_to_v3_waveform_input", "external_reference_binding_evaluated", "product_waveform_only_cli_invoked", "waveform_nrmse_evaluated"}
    false_keys = {"sampled_eye_evaluated", "crossing_tie_evaluated", "selected_highloss_waveform_only_profile_accepted", "accepted_receiver", "acceptance_ready", "promotion_eligible", "release_ledger_promoted"}
    if not isinstance(admission, dict) or set(admission) != true_keys | false_keys or any(admission[key] is not True for key in true_keys) or any(admission[key] is not False for key in false_keys):
        raise VerificationError("waveform_only_gate_promotion")
    if any(token in str(document).lower() for token in ("\\\\", "file://", "http://", "https://", "samples: [", "waveform: [")):
        raise VerificationError("waveform_only_evidence_leak")
    return {"valid": True, "waveform_nrmse_evaluated": True, "profile_accepted": False}


def verify_current(document: dict[str, object]) -> None:
    observation = document["external_observation"]
    assert isinstance(observation, dict)
    inventory = observation["product_source_inventory"]
    assert isinstance(inventory, dict)
    if _inventory(set(inventory)) != inventory:
        raise VerificationError("waveform_only_product_source_drift")


def main() -> int:
    try:
        document = yaml.safe_load(EVIDENCE.read_text(encoding="utf-8"))
        result = verify_document(document)
        verify_current(document)
    except (OSError, ValueError, yaml.YAMLError, VerificationError) as error:
        print(f"external_ads_selected_highloss_waveform_only_observation_failed:{error}")
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
