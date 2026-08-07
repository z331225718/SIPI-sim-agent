from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "sipi-contracts" / "src"))

from sipi_contracts import AxisV1, ContractViolation, parse_axis


def axis(**changes):
    value = {
        "schema": "sipi.axis.v1",
        "kind": "time",
        "unit": "s",
        "dtype": "float64",
        "length": 4,
        "monotonicity": "increasing",
        "uniform": True,
        "sample_location": "sample",
        "start": 0.0,
        "step": 1.0,
        "extensions": {},
    }
    if "values" in changes or "values_artifact" in changes:
        value.pop("start")
        value.pop("step")
    value.update(changes)
    return value


def frequency_axis(**changes):
    value = axis(kind="frequency", unit="Hz", spectrum={"sidedness": "single", "has_dc": True, "has_nyquist": False})
    value.update(changes)
    return value


def artifact_ref(relative_path="values.npy"):
    return {
        "schema": "sipi.artifact-ref.v1",
        "content_schema": "sipi.axis-values.v1",
        "relative_path": relative_path,
        "mime_type": "application/octet-stream",
        "sha256": "a" * 64,
        "byte_length": 32,
        "producer": "fixture",
        "role": "data",
        "extensions": {},
    }


class AxisContractTests(unittest.TestCase):
    def test_uniform_axis_parses_and_is_immutable(self):
        raw = axis()
        model = parse_axis(raw)
        self.assertIsInstance(model, AxisV1)
        raw["start"] = 9.0
        self.assertEqual(model.to_wire()["start"], 0.0)

    def test_frequency_axis_requires_spectrum(self):
        parse_axis(frequency_axis())
        with self.assertRaisesRegex(ContractViolation, "spectrum"):
            parse_axis(axis(kind="frequency", unit="Hz"))
        with self.assertRaisesRegex(ContractViolation, "spectrum"):
            parse_axis(axis(spectrum={"sidedness": "single", "has_dc": True, "has_nyquist": False}))

    def test_uniform_axis_declaration_rules(self):
        with self.assertRaisesRegex(ContractViolation, "step"):
            parse_axis(axis(step=0.0))
        with self.assertRaises(ContractViolation):
            parse_axis(axis(uniform=False))
        with self.assertRaises(ContractViolation):
            parse_axis(axis(values=[0.0, 1.0, 2.0, 3.0]))

    def test_explicit_values_axis_rules(self):
        good = parse_axis(axis(uniform=False, values=[0.0, 1.0, 2.0, 3.0]))
        self.assertEqual(good.to_wire()["length"], 4)
        with self.assertRaisesRegex(ContractViolation, "uniform"):
            parse_axis(axis(values=[0.0, 1.0, 2.0, 3.0]))
        with self.assertRaisesRegex(ContractViolation, "length"):
            parse_axis(axis(uniform=False, values=[0.0, 1.0, 2.0]))
        with self.assertRaisesRegex(ContractViolation, "monotonicity"):
            parse_axis(axis(uniform=False, values=[3.0, 2.0, 1.0, 0.0]))

    def test_values_artifact_axis(self):
        parse_axis(axis(uniform=False, values_artifact=artifact_ref()))
        with self.assertRaisesRegex(ContractViolation, "uniform"):
            parse_axis(axis(values_artifact=artifact_ref()))
        with self.assertRaises(ContractViolation):
            parse_axis(axis(uniform=False, values_artifact=artifact_ref(relative_path="../escape.npy")))

    def test_unknown_fields_and_dtype(self):
        with self.assertRaises(ContractViolation):
            parse_axis(axis(dtype="complex128"))
        with self.assertRaises(ContractViolation):
            parse_axis({**axis(), "future_optional": True})


if __name__ == "__main__":
    unittest.main()
