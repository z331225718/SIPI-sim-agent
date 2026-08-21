"""Verify hash-bound, external-only P4B-08c ADS topology observation."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/baselines/p4b-08c-ads-netlist-topology-semantic-response-evidence.v1.yaml"
SCHEMA = "sipi.p4b-08c.ads-netlist-topology-semantic-response-evidence.v1"
PYBERT_COMMIT = "f6ba0311350fc67bd90fa13b8d578312f956d7e7"


class TopologyObservationError(ValueError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TopologyObservationError("document_not_mapping")
    return value


def _hex(value: object, length: int = 64) -> bool:
    return isinstance(value, str) and len(value) == length and all(char in "0123456789abcdef" for char in value)


def _require(value: object, expected: object, reason: str) -> None:
    if value != expected:
        raise TopologyObservationError(reason)


def _close(value: object, expected: float) -> bool:
    try:
        return math.isclose(float(value), expected, rel_tol=0.0, abs_tol=1e-15)
    except (TypeError, ValueError):
        return False


def verify_document(document: object) -> dict[str, object]:
    if not isinstance(document, dict):
        raise TopologyObservationError("document_not_mapping")
    _require(document.get("schema"), SCHEMA, "schema")
    _require(document.get("status"), "external_only_topology_and_semantic_response_observed", "status")
    custody = document.get("custody")
    if custody != {"product_assets": False, "product_policy": False, "release_input": False, "runtime_invoked": False, "external_roots": "cli_injected_only"}:
        raise TopologyObservationError("custody")

    oracle = document.get("source_oracle")
    if not isinstance(oracle, dict) or oracle.get("commit") != PYBERT_COMMIT or not _hex(oracle.get("tree"), 40) or oracle.get("license_conclusion") != "NOASSERTION":
        raise TopologyObservationError("source_oracle")
    if oracle.get("license_evidence") != [
        {"path": "LICENSE", "blob": "64d198ba43675ede5fbdef1ec918a63954951640", "byte_length": 1466},
        {"path": "NOTICE", "blob": "d179d695538ffe55e7ca6ba8e31ea8e6b6279cad", "byte_length": 679},
    ]:
        raise TopologyObservationError("license_evidence")
    files = oracle.get("files")
    expected_blobs = {
        "src/pybert_web/ads_bench.py": "663bdfabfc9a1c7dae31d544e108ec8d8980996b",
        "src/pybert/utility/channel_topology.py": "f28e9975311d6ac1e24802b053216e516181673b",
        "src/pybert/utility/sparam.py": "8599a80943860f6811436e235074172e4d7c7220",
        "tests/test_ads_bench.py": "311c44562685f4dac2abf813b5e4db5675b71c7f",
    }
    if not isinstance(files, list) or {entry.get("path"): entry.get("blob") for entry in files} != expected_blobs:
        raise TopologyObservationError("source_blob_set")

    inputs = document.get("external_inputs")
    if not isinstance(inputs, dict) or inputs.get("workspace_relative_root") != "ADS/MyWorkspace_wrk":
        raise TopologyObservationError("external_input_root")
    netlist = inputs.get("netlist")
    if netlist != {"path": "netlist.log", "byte_length": 7858, "sha256": "676838f9bff5f92cd0e645da7db20b3adf3399cab015300d1d3b34e8098f3983", "git_object": False, "registry_status": "not_registered", "rights_status": "not_authorized_for_product_use"}:
        raise TopologyObservationError("netlist_identity")
    expected_inputs = [
        ("tx_drv", "ibis_ami/s4p/pcie_tx_drv_Typ.s4p", 7776278, "3b72c3b235fbf4eff7ecec4c1490a052677b8caac6c355bcb187d41e156791c1", "ads-pcie-gen5-s4p-tx-typ"),
        ("SnP1", "data/channel_gen5_highloss.s4p", 1834156, "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47", None),
        ("rx_fe", "ibis_ami/s4p/pcie_rx_fe_Typ.s4p", 6258154, "0f5f4dfe39012144abf859ec91db647fd1be4d36f41f3befbf24bf62f9775f7f", "ads-pcie-gen5-s4p-rx-typ"),
    ]
    chain = inputs.get("s4p_chain")
    if not isinstance(chain, list) or len(chain) != len(expected_inputs):
        raise TopologyObservationError("s4p_chain_shape")
    for entry, expected in zip(chain, expected_inputs):
        name, path, length, digest, material_id = expected
        if entry.get("name") != name or entry.get("path") != path or entry.get("byte_length") != length or entry.get("sha256") != digest or entry.get("registry_material_id") != material_id or entry.get("rights_status") != "not_authorized_for_product_use":
            raise TopologyObservationError(f"s4p_identity:{name}")
        if entry.get("registry_status") not in {"external_only", "not_registered"}:
            raise TopologyObservationError(f"s4p_registry_status:{name}")

    topology = document.get("topology")
    expected_blocks = [
        {"name": "tx_drv", "nodes": ["N__2", "N__9", "N__11", "N__3"], "input_pair": ["N__2", "N__9"], "output_pair": ["N__11", "N__3"], "port_order": [1, 2, 3, 4], "port_map": {"1": "N__2", "2": "N__9", "3": "N__11", "4": "N__3"}},
        {"name": "SnP1", "nodes": ["N__11", "N__7", "N__3", "N__4"], "input_pair": ["N__11", "N__3"], "output_pair": ["N__7", "N__4"], "port_order": [1, 3, 2, 4], "port_map": {"1": "N__11", "2": "N__7", "3": "N__3", "4": "N__4"}},
        {"name": "rx_fe", "nodes": ["N__7", "N__4", "N__1", "N__8"], "input_pair": ["N__7", "N__4"], "output_pair": ["N__1", "N__8"], "port_order": [1, 2, 3, 4], "port_map": {"1": "N__7", "2": "N__4", "3": "N__1", "4": "N__8"}},
    ]
    if not isinstance(topology, dict) or topology.get("source_pair") != ["N__2", "N__9"] or topology.get("load_pair") != ["N__1", "N__8"] or topology.get("differential_path") is not True or topology.get("z0_ohm") != 100.0 or topology.get("blocks") != expected_blocks:
        raise TopologyObservationError("topology")

    response = document.get("semantic_response")
    expected_ops = ["renumber_for_topology", "cascade", "se2gmm", "extract_sdd21", "convert_sdd_abcd_to_open_circuit_vdiff"]
    if not isinstance(response, dict) or response.get("intent") != "ami_init_channel_response" or response.get("conversion_policy") != "mixed_mode_sdd_to_open_circuit_vdiff" or response.get("operations") != expected_ops or response.get("block_count") != 3 or response.get("z0_ohm") != 100.0:
        raise TopologyObservationError("semantic_contract")
    if response.get("low_frequency_observation") != {"frequency_index": 0, "frequency_hz": 0.0, "sdd21_abs": 0.5990020074930338, "sdd21_db": -4.451434442307726, "open_circuit_vdiff_abs": 0.9256036352607088, "open_circuit_vdiff_db": -0.6714989676739803}:
        raise TopologyObservationError("low_frequency_observation")
    artifacts = response.get("generated_artifacts_external_only")
    if not isinstance(artifacts, dict) or artifacts.get("network") != {"relative_path": "semantic_channel_a88d83b4ae7e2993.s2p", "format": "s2p", "byte_length": 841295, "sha256": "0f9df9ccdc9ce22e1735dce7123c028e009808b94c23816a7dc17aa1101b7af3"} or artifacts.get("metadata") != {"relative_path": "semantic_channel_a88d83b4ae7e2993.json", "format": "json", "byte_length": 2247, "sha256": "6560788b22ead8ef50c84f52937b95afa806206c96f676844d5849031c638a5e"}:
        raise TopologyObservationError("artifact_identity")

    admission = document.get("admission")
    if not isinstance(admission, dict) or admission.get("port_mapping_observed") is not True or admission.get("semantic_response_observed") is not True or any(admission.get(key) is not False for key in ("typed_edge_to_channel", "ami_matrix_construction", "victim_aggressor_columns", "matrix_time_step", "impulse_conversion_policy", "rights_admitted", "product_runtime_invoked", "release_admitted")):
        raise TopologyObservationError("admission")
    blockers = document.get("blockers")
    if not isinstance(blockers, list) or "central_channel_s4p_not_registered_or_product_authorized" not in blockers or "victim_aggressor_column_semantics_not_frozen" not in blockers:
        raise TopologyObservationError("blockers")
    return {"valid": True, "dynamic_checked": False}


def _file_identity(root: Path, relative: str) -> tuple[int, str]:
    path = root / Path(relative)
    if not path.is_file() or path.is_symlink():
        raise TopologyObservationError(f"external_file_missing:{relative}")
    data = path.read_bytes()
    return len(data), hashlib.sha256(data).hexdigest()


def verify_external_inputs(document: dict[str, Any], ads_root: Path) -> dict[str, object]:
    verify_document(document)
    if not ads_root.is_absolute():
        raise TopologyObservationError("ads_root_must_be_absolute_cli_path")
    inputs = document["external_inputs"]
    assert isinstance(inputs, dict)
    observed: list[dict[str, object]] = []
    netlist = inputs["netlist"]
    assert isinstance(netlist, dict)
    length, digest = _file_identity(ads_root, str(netlist["path"]))
    if length != netlist["byte_length"] or digest != netlist["sha256"]:
        raise TopologyObservationError("external_netlist_identity")
    observed.append({"path": netlist["path"], "byte_length": length, "sha256": digest})
    for entry in inputs["s4p_chain"]:
        length, digest = _file_identity(ads_root, str(entry["path"]))
        if length != entry["byte_length"] or digest != entry["sha256"]:
            raise TopologyObservationError(f"external_s4p_identity:{entry['name']}")
        observed.append({"path": entry["path"], "byte_length": length, "sha256": digest})
    return {"valid": True, "dynamic_checked": True, "external_files": observed}


def verify_generated_outputs(document: dict[str, Any], output_root: Path) -> dict[str, object]:
    verify_document(document)
    if not output_root.is_absolute():
        raise TopologyObservationError("output_root_must_be_absolute_cli_path")
    artifacts = document["semantic_response"]["generated_artifacts_external_only"]
    assert isinstance(artifacts, dict)
    network = artifacts["network"]
    metadata = artifacts["metadata"]
    assert isinstance(network, dict) and isinstance(metadata, dict)
    network_path = output_root / str(network["relative_path"])
    metadata_path = output_root / str(metadata["relative_path"])
    for path, descriptor in ((network_path, network), (metadata_path, metadata)):
        if not path.is_file() or path.is_symlink():
            raise TopologyObservationError(f"generated_output_missing:{path.name}")
        data = path.read_bytes()
        if len(data) != descriptor["byte_length"] or hashlib.sha256(data).hexdigest() != descriptor["sha256"]:
            raise TopologyObservationError(f"generated_output_identity:{path.name}")

    try:
        metadata_value = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise TopologyObservationError("generated_metadata_parse") from error
    expected_topology = document["topology"]
    expected_observation = document["semantic_response"]["low_frequency_observation"]
    first_block = expected_topology["blocks"][0]
    expected_operations = ["renumber_for_topology", "cascade", "se2gmm", "extract_sdd21", "convert_sdd_abcd_to_open_circuit_vdiff"]
    if metadata_value.get("intent") != "ami_init_channel_response" or metadata_value.get("source_context") != "ads_netlist" or metadata_value.get("source_signal") != "mixed_mode_sdd_power_wave" or metadata_value.get("output_signal") != "ami_init_channel_response" or metadata_value.get("conversion_policy") != "mixed_mode_sdd_to_open_circuit_vdiff" or metadata_value.get("operations") != expected_operations or metadata_value.get("input_pair") != expected_topology["source_pair"] or metadata_value.get("output_pair") != expected_topology["load_pair"] or metadata_value.get("port_order") != first_block["port_order"] or metadata_value.get("port_map") != first_block["port_map"] or metadata_value.get("z0_ohm") != 100.0:
        raise TopologyObservationError("generated_metadata_contract")
    diagnostics = metadata_value.get("diagnostics")
    expected_diagnostic_blocks = []
    for block, input_entry in zip(expected_topology["blocks"], document["external_inputs"]["s4p_chain"]):
        expected_diagnostic_blocks.append({"name": block["name"], "path": input_entry["path"], "port_order": block["port_order"], "input_pair": block["input_pair"], "output_pair": block["output_pair"]})
    actual_diagnostic_blocks = diagnostics.get("blocks") if isinstance(diagnostics, dict) else None
    if isinstance(actual_diagnostic_blocks, list):
        normalized_diagnostic_blocks = []
        for actual in actual_diagnostic_blocks:
            if not isinstance(actual, dict):
                raise TopologyObservationError("generated_metadata_blocks")
            normalized = dict(actual)
            path = str(normalized.get("path", "")).replace("\\", "/")
            normalized["path"] = next((entry["path"] for entry in expected_diagnostic_blocks if path.endswith("/" + entry["path"]) or path == entry["path"]), path)
            normalized_diagnostic_blocks.append(normalized)
    else:
        normalized_diagnostic_blocks = None
    if not isinstance(diagnostics, dict) or diagnostics.get("block_count") != 3 or normalized_diagnostic_blocks != expected_diagnostic_blocks or not _close(diagnostics.get("sdd21_low_frequency_abs"), expected_observation["sdd21_abs"]) or not _close(diagnostics.get("sdd21_low_frequency_db"), expected_observation["sdd21_db"]) or not _close(diagnostics.get("open_circuit_vdiff_low_frequency_abs"), expected_observation["open_circuit_vdiff_abs"]) or not _close(diagnostics.get("open_circuit_vdiff_low_frequency_db"), expected_observation["open_circuit_vdiff_db"]):
        raise TopologyObservationError("generated_metadata_observation")

    rows: list[list[float]] = []
    for line in network_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("!") or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) != 9:
            raise TopologyObservationError("generated_network_shape")
        try:
            rows.append([float(value) for value in fields])
        except ValueError as error:
            raise TopologyObservationError("generated_network_numeric") from error
    index = int(expected_observation["frequency_index"])
    if index >= len(rows) or rows[index][0] != expected_observation["frequency_hz"]:
        raise TopologyObservationError("generated_frequency_axis")
    s21_abs = math.hypot(rows[index][3], rows[index][4])
    if not math.isclose(s21_abs, expected_observation["open_circuit_vdiff_abs"], rel_tol=0.0, abs_tol=1e-15):
        raise TopologyObservationError("generated_low_frequency_value")
    return {"output_checked": True, "output_files": [network["relative_path"], metadata["relative_path"]], "frequency_index": index, "frequency_hz": rows[index][0]}


def verify_pybert_source(document: dict[str, Any], pybert_root: Path) -> dict[str, object]:
    verify_document(document)
    if not pybert_root.is_absolute():
        raise TopologyObservationError("pybert_root_must_be_absolute_cli_path")
    oracle = document["source_oracle"]
    assert isinstance(oracle, dict)
    commit = str(oracle["commit"])
    def git(*args: str) -> str:
        result = subprocess.run(["git", "-C", str(pybert_root), *args], capture_output=True, text=True, encoding="utf-8", check=False)
        if result.returncode:
            raise TopologyObservationError("pybert_git_identity")
        return result.stdout.strip()
    if git("rev-parse", "HEAD") != commit or git("rev-parse", f"{commit}^{{tree}}") != oracle["tree"]:
        raise TopologyObservationError("pybert_commit_or_tree")
    for entry in [*oracle["files"], *oracle["license_evidence"]]:
        if git("rev-parse", f"{commit}:{entry['path']}") != entry["blob"]:
            raise TopologyObservationError(f"pybert_blob:{entry['path']}")
        if "byte_length" in entry and git("cat-file", "-s", f"{commit}:{entry['path']}") != str(entry["byte_length"]):
            raise TopologyObservationError(f"pybert_blob_size:{entry['path']}")
    return {"valid": True, "pybert_source_checked": True}


def validate(root: Path = ROOT, *, ads_root: Path | None = None, pybert_root: Path | None = None, output_root: Path | None = None) -> dict[str, object]:
    supplied = [ads_root is not None, pybert_root is not None, output_root is not None]
    if any(supplied) and not all(supplied):
        raise TopologyObservationError("dynamic_mode_requires_ads_pybert_output_roots")
    document = load_yaml(EVIDENCE)
    result = verify_document(document)
    if all(supplied):
        assert ads_root is not None and pybert_root is not None and output_root is not None
        result.update(verify_external_inputs(document, ads_root))
        result.update(verify_pybert_source(document, pybert_root))
        result.update(verify_generated_outputs(document, output_root))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ads-root", type=Path, help="absolute external ADS workspace root")
    parser.add_argument("--pybert-root", type=Path, help="absolute external PyBERT Git root")
    parser.add_argument("--output-root", type=Path, help="absolute external generated semantic-output root")
    arguments = parser.parse_args()
    try:
        result = validate(ROOT, ads_root=arguments.ads_root, pybert_root=arguments.pybert_root, output_root=arguments.output_root)
        print(json.dumps({"schema": SCHEMA, **result}, sort_keys=True))
        return 0
    except (OSError, TopologyObservationError, yaml.YAMLError) as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
