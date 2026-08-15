"""Verify hash-only evidence for the ADS exact common-node observation."""

from __future__ import annotations

import hashlib
import io
import subprocess
import tarfile
import tempfile
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "docs/baselines/p3c-ads-pre-final-common-node-observation-evidence.v1.yaml"
COMMIT = "4da75e1d27f56163e5eae4c898f96702935bdf6c"
TREE = "ed3870cba5cfb477d47287bbfdff89216846232e"
INVENTORY = {
    "tools/run_p3c_external_ads_pre_final_common_nodes.py": "1ebb17d01733a86c24344fe9cc8f11e09dccc877954812af9a3248be9d8dddaa",
    "tools/observe_p3c_ads_pre_final_common_nodes.py": "28251dc6785d9ff9211823d8e19ef08f0a979136d99fb8cd75e5d576ca732135",
    "tools/extract_p3c_ads_pre_final_common_nodes.py": "5865ccbc3ba6bf3e1997b9659e26154314cf084dd5d4150d234c748371751525",
    "tools/run_p3c_external_ads_fixed_pulse_passivity_surface.py": "dd5c60b8364d2b9ad6f17dafdfd1c55cc4be4dcae11aa495a024337f5b4e723f",
}


class VerificationError(ValueError):
    pass


def fail(condition: bool, reason: str) -> None:
    if condition:
        raise VerificationError(reason)


def archive_inventory() -> dict[str, str]:
    result = subprocess.run(["git", "archive", "--format=tar", COMMIT], cwd=ROOT, check=True, capture_output=True)
    with tempfile.TemporaryDirectory() as directory:
        with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:") as archive:
            archive.extractall(directory, filter="data")
        return {path: hashlib.sha256((Path(directory) / path).read_bytes()).hexdigest() for path in INVENTORY}


def verify(document: object, current: bool = True) -> dict[str, object]:
    fail(not isinstance(document, dict), "shape")
    required = {"schema", "status", "authority", "predecessor", "external_observation", "independent_audit", "admission", "blockers", "non_claims"}
    fail(set(document) != required, "shape")
    fail(document["schema"] != "sipi.p3c.ads-pre-final-common-node-observation-evidence.v1", "schema")
    fail(document["status"] != "external_ads_pre_to_final_exact_common_node_delta_observed", "status")
    fail(document["authority"] != {"actor": "user", "decision_ref": "user-approved-exact-common-node-2026-08-15", "scope": "one_fixed_ads_exact_common_node_s0_to_final_observation_only"}, "authority")
    fail(document["predecessor"] != {"path": "docs/baselines/p3c-ads-pre-final-spectrum-comparison-observation-evidence.v1.yaml", "result": "full_axes_not_identical_historical_common_nodes_independently_observed"}, "predecessor")
    observation = document["external_observation"]
    expected = {
        "schema": "sipi.p3c.ads-pre-final-common-node-observation.v1", "custody": "external_only", "report_path_retained": False,
        "report_byte_length": 2323, "report_content_sha256": "96fff5959ea1dc1031aa5b4113b9817c71b7ca511941b269dde4d93083a77a2b",
        "clean_archive_commit": COMMIT, "clean_archive_tree": TREE, "source_byte_length": 1_834_156,
        "source_sha256": "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47",
        "ads_help_byte_length": 150_522, "ads_help_sha256": "45372e9c7c79492bf6023a4e860f05a20caf0ef5e2a083407c119909afc187bf",
        "ads_dataset_api": {"python": {"byte_length": 91_136, "sha256": "8c3fda8eb64fd1ccec107c3903a24060715604cca8b8649743cac5d0df271384"}, "api_doc": {"byte_length": 62_006, "sha256": "86577ec72abb6d49926722968043d7b3d639eabc624c031bfd015f827a32894f"}},
        "runner_source_sha256": INVENTORY["tools/run_p3c_external_ads_pre_final_common_nodes.py"],
        "observer_source_sha256": INVENTORY["tools/observe_p3c_ads_pre_final_common_nodes.py"],
        "extractor_source_sha256": INVENTORY["tools/extract_p3c_ads_pre_final_common_nodes.py"],
        "predecessor_runner_sha256": INVENTORY["tools/run_p3c_external_ads_fixed_pulse_passivity_surface.py"],
        "fresh_runs": 2,
        "ads_netlist": {"netlist_byte_length": 1760, "netlist_sha256": "6f720d8375726b1d7b0c42fbc7579372c1fea0ca5929c21d9823ccae4c2838e8"},
        "common_node_comparison": {
            "common_node_count": 1024, "mapping": "fft_imp_index_equals_4_times_s0_index",
            "full_matrix": {"s0_sha256": "26d44f9bb433134bfbbb98271f4e1fd375f05ca3bd173e8184170d73d220bcf4", "fft_imp_sha256": "26a42470f16e967ecd527ec9ff76cb38a794cbc7c7415a2ec047d7426c808dbe", "delta_sha256": "994fdbe6e2c6d2313a7fc291971b9754d44404fc33434e76e5bb2bdd30f24c58", "l2_squared_bits": "3a109ea071545747", "max_abs_bits": "3cba4e4efeda34de", "max_row": 4, "max_column": 4, "max_common_index": 292},
            "selected_hdiff": {"s0_sha256": "53af1ada3aa95c757a5f4ae5302101b80ba1a69b75a531f9d6619730c49b2a3e", "fft_imp_sha256": "ab70dc6d404112b5771316362af84b0da472217e43ec35ff2d98d14f215ba1d2", "delta_sha256": "2487a722bafe0b06919e7cb30121fdc3ddf7dd0db681728b94590192ee400c55", "l2_squared_bits": "3991d3c0f1964ac0", "max_abs_bits": "3c96a09e667f3bcd", "max_common_index": 14},
        },
        "cleanup_status": "complete",
    }
    fail(observation != expected, "observation")
    tree = subprocess.run(["git", "rev-parse", f"{COMMIT}^{{tree}}"], cwd=ROOT, check=False, capture_output=True, text=True)
    fail(tree.returncode != 0 or tree.stdout.strip() != TREE, "archive")
    if current:
        fail(archive_inventory() != INVENTORY, "source_drift")
    fail(document["independent_audit"] != {"reviewer": "Orca_reused_OpenCode_terminal", "terminal": "term_2de7cb74-b803-4e20-bb5b-4803777c24f8", "status": "completed", "result": "no_high_or_critical_findings", "report": "docs/baselines/audits/2026-08-15-p3c-ads-pre-final-common-node-observation.md"}, "audit")
    true = {"pre_final_exact_common_nodes_evaluated", "full_matrix_common_node_delta_observed", "selected_hdiff_common_node_delta_observed"}
    false = {"full_axis_identity_evaluated", "passivity_correction_surface_delta_evaluated", "passivity_algorithm_or_repair_implemented", "waveform_mismatch_cause_identified", "candidate_waveform_accepted", "release_ledger_promoted"}
    admission = document["admission"]
    fail(not isinstance(admission, dict) or set(admission) != true | false or any(admission[key] is not True for key in true) or any(admission[key] is not False for key in false), "gates")
    fail(document["blockers"] != ["full_pre_to_final_axis_identity_remains_false", "final_only_frequency_nodes_not_compared", "ads_passivity_algorithm_not_observed_or_ported", "waveform_mismatch_cause_not_identified"], "blockers")
    forbidden = ("file://", "http://", "https://", "c:\\", "spectrum: [", "waveform: [", "freqresp")
    fail(any(token in str(document).lower() for token in forbidden), "leak")
    return {"valid": True, "common_nodes": 1024, "accepted": False}


if __name__ == "__main__":
    try:
        print(verify(yaml.safe_load(PATH.read_text(encoding="utf-8"))))
    except (OSError, ValueError, yaml.YAMLError, VerificationError) as error:
        print(f"p3c_ads_pre_final_common_node_failed:{error}")
        raise SystemExit(1)
