from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import struct

from tools.run_com_normal_erl_finite_trace_diagnostic import compare_case, vector_residuals


def vector(token: str) -> dict[str, object]:
    return {"count": 2, "sha256": token * 64}


def matlab_summary() -> dict[str, object]:
    return {"cases": [{"ERL": 20.0, "ERL11": 20.0, "ERL22": 21.0, "Z11est": 100.0, "Z22est": 100.0}], "last_warning": {"identifier": "", "message": ""}}


def rust_result() -> dict[str, object]:
    ports = [{"port": 1, "sample_count": 2, "time_sha256": "a" * 64, "impedance_sha256": "b" * 64, "ptdr_sha256": "c" * 64, "gated_sha256": "d" * 64, "erl_db": 20.0, "avg_port_impedance_ohm": 100.0}, {"port": 2, "sample_count": 2, "time_sha256": "a" * 64, "impedance_sha256": "b" * 64, "ptdr_sha256": "c" * 64, "gated_sha256": "d" * 64, "erl_db": 21.0, "avg_port_impedance_ohm": 100.0}]
    return {"cases": [{"metrics": {"ERL": 20.0}, "diagnostics": {"normal_erl": {"s_parameter_model_fit": False, "ports": ports}}}]}


class FiniteNormalErlTraceTests(unittest.TestCase):
    def test_matching_first_package_trace_is_accepted(self) -> None:
        source = matlab_summary()
        trace = [{"port": 1, "available": True, "vectors": {"time_s": vector("a"), "impedance_ohm": vector("b"), "ptdr": vector("c"), "gated": vector("d")}}, {"port": 2, "available": True, "vectors": {"time_s": vector("a"), "impedance_ohm": vector("b"), "ptdr": vector("c"), "gated": vector("d")}}]
        result = compare_case(source, matlab_summary(), trace, rust_result())
        self.assertTrue(result["array_digest_identity"])
        self.assertTrue(result["scalar_passed"])

    def test_scalar_drift_is_visible(self) -> None:
        source = matlab_summary()
        source["cases"][0]["ERL"] = 19.0
        trace = [{"port": 1, "available": True, "vectors": {"time_s": vector("a"), "impedance_ohm": vector("b"), "ptdr": vector("c"), "gated": vector("d")}}, {"port": 2, "available": True, "vectors": {"time_s": vector("a"), "impedance_ohm": vector("b"), "ptdr": vector("c"), "gated": vector("d")}}]
        result = compare_case(source, source, trace, rust_result())
        self.assertFalse(result["scalar_passed"])

    def test_residual_observation_uses_little_endian_values(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            matlab = root / "matlab"
            rust = root / "rust"
            for port in (1, 2):
                for directory in (matlab / f"port-{port}", rust / f"port-{port}"):
                    directory.mkdir(parents=True, exist_ok=True)
                for name in ("time_s", "impedance_ohm", "ptdr", "gated"):
                    (matlab / f"port-{port}" / f"{name}.f64le").write_bytes(struct.pack("<2d", 1.0, 2.0))
                    (rust / f"port-{port}" / f"{name}.f64le").write_bytes(struct.pack("<2d", 1.0, 2.25))
            observations = vector_residuals(matlab, rust)
            self.assertEqual(len(observations), 8)
            self.assertEqual(observations[0]["max_abs"], 0.25)
            self.assertAlmostEqual(observations[0]["rms"], 0.25 / 2.0**0.5)


if __name__ == "__main__":
    unittest.main()
