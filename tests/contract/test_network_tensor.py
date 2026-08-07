from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "sipi-contracts" / "src"))

from sipi_contracts import ContractViolation, NetworkTensorV1, parse_network_tensor


def artifact_ref(relative_path="matrix.npy"):
    return {
        "schema": "sipi.artifact-ref.v1",
        "content_schema": "sipi.network-matrix.v1",
        "relative_path": relative_path,
        "mime_type": "application/octet-stream",
        "sha256": "b" * 64,
        "byte_length": 128,
        "producer": "fixture",
        "role": "data",
        "extensions": {},
    }


def tensor(**changes):
    value = {
        "schema": "sipi.network-tensor.v1",
        "parameter_kind": "S",
        "axis": {
            "schema": "sipi.axis.v1",
            "kind": "frequency",
            "unit": "Hz",
            "dtype": "float64",
            "length": 2,
            "monotonicity": "increasing",
            "uniform": True,
            "sample_location": "bin_center",
            "start": 1.0,
            "step": 1.0,
            "spectrum": {"sidedness": "single", "has_dc": False, "has_nyquist": False},
            "extensions": {},
        },
        "port_map": {
            "schema": "sipi.port-map.v1",
            "basis": "single_ended",
            "index_base": 0,
            "ports": [
                {"id": "p1", "external_index": 0, "kind": "signal", "polarity": 1, "extensions": {}},
                {"id": "p2", "external_index": 1, "kind": "signal", "polarity": -1, "extensions": {}},
            ],
            "extensions": {},
        },
        "data": artifact_ref(),
        "shape": {"frequency": 2, "output_ports": 2, "input_ports": 2},
        "complex_encoding": "interleaved",
        "dtype": "complex128",
        "byte_order": "little",
        "layout": "C",
        "z0": {"kind": "scalar", "value": 50.0, "extensions": {}},
        "wave_definition": "pseudo",
        "reader": {"source_reader": "scikit-rf", "reader_semantics": "s2p", "extensions": {}},
        "extensions": {},
    }
    value.update(changes)
    return value


class NetworkTensorContractTests(unittest.TestCase):
    def test_good_tensor_parses_and_is_immutable(self):
        raw = tensor()
        model = parse_network_tensor(raw)
        self.assertIsInstance(model, NetworkTensorV1)
        raw["shape"]["frequency"] = 9
        self.assertEqual(model.to_wire()["shape"]["frequency"], 2)

    def test_axis_must_be_frequency_and_shape_must_match(self):
        bad_axis = tensor()
        bad_axis["axis"]["kind"] = "time"
        with self.assertRaisesRegex(ContractViolation, "frequency"):
            parse_network_tensor(bad_axis)
        mismatch = tensor()
        mismatch["shape"]["frequency"] = 3
        with self.assertRaisesRegex(ContractViolation, "axis length"):
            parse_network_tensor(mismatch)

    def test_square_tensor_shape_rules(self):
        non_square = tensor()
        non_square["shape"]["output_ports"] = 1
        with self.assertRaisesRegex(ContractViolation, "square"):
            parse_network_tensor(non_square)
        ext = tensor(parameter_kind="EXT", parameter_kind_name="T")
        ext["shape"]["output_ports"] = 1
        ext["shape"]["input_ports"] = 2
        parse_network_tensor(ext)
        with self.assertRaisesRegex(ContractViolation, "parameter_kind_name"):
            parse_network_tensor(tensor(parameter_kind="EXT"))

    def test_complex_dtype_requires_interleaved(self):
        with self.assertRaisesRegex(ContractViolation, "interleaved"):
            parse_network_tensor(tensor(complex_encoding="split"))
        parse_network_tensor(tensor(dtype="float64", complex_encoding="split"))

    def test_z0_rules(self):
        with self.assertRaisesRegex(ContractViolation, "positive value"):
            parse_network_tensor(tensor(z0={"kind": "scalar", "extensions": {}}))
        with self.assertRaisesRegex(ContractViolation, "values_artifact"):
            parse_network_tensor(tensor(z0={"kind": "per_frequency", "extensions": {}}))
        parse_network_tensor(tensor(z0={"kind": "per_port", "values_artifact": artifact_ref("z0.npy"), "extensions": {}}))

    def test_port_reorder_rules(self):
        reorder = tensor()
        reorder["reader"]["port_reorder"] = [{"from": "p2", "to": "p1"}]
        parse_network_tensor(reorder)
        with self.assertRaisesRegex(ContractViolation, "itself"):
            parse_network_tensor(tensor(reader={"source_reader": "x", "reader_semantics": "y", "port_reorder": [{"from": "p1", "to": "p1"}], "extensions": {}}))
        with self.assertRaisesRegex(ContractViolation, "undeclared"):
            parse_network_tensor(tensor(reader={"source_reader": "x", "reader_semantics": "y", "port_reorder": [{"from": "p1", "to": "missing"}], "extensions": {}}))


if __name__ == "__main__":
    unittest.main()
