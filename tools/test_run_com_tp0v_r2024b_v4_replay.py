from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


PATH = Path(__file__).with_name("run_com_tp0v_r2024b_v4_replay.py")
SPEC = importlib.util.spec_from_file_location("run_com_tp0v_r2024b_v4_replay", PATH)
assert SPEC and SPEC.loader
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def vectors(values: dict[str, list[float]]):
    return [{"name": name, "values": samples} for name, samples in values.items()]


class V4RunnerTests(unittest.TestCase):
    def test_public_root_command_has_no_direct_crate_route(self) -> None:
        command = runner.root_command(Path("sipi.exe"), Path("config.xlsx"), Path("thru.s4p"), Path("fext.s4p"), Path("next.s4p"), Path("out"))
        self.assertEqual(command[1:3], ["com", "run"])
        self.assertNotIn("sipi-agent-com-direct", " ".join(command))

    def test_vector_tolerance_is_absolute_plus_reference_relative(self) -> None:
        left = vectors({name: [0.0, 1.0] for name in runner.VECTOR_NAMES})
        right = vectors({name: [0.0, 1.0] for name in runner.VECTOR_NAMES})
        right[1]["values"][1] += runner.VECTOR_TOLERANCE["impedance_ohm"]["absolute"]
        self.assertTrue(runner.compare_vectors(left, right)["passed"])

    def test_vector_shape_order_and_first_sample_are_strict(self) -> None:
        left = vectors({name: [0.0, 1.0] for name in runner.VECTOR_NAMES})
        wrong_order = list(reversed(left))
        self.assertFalse(runner.compare_vectors(left, wrong_order)["passed"])
        short = vectors({name: [0.0] for name in runner.VECTOR_NAMES})
        self.assertFalse(runner.compare_vectors(left, short)["passed"])

    def test_time_requires_finite_strict_monotonic_samples(self) -> None:
        left = vectors({name: [0.0, 1.0] for name in runner.VECTOR_NAMES})
        non_monotonic = vectors({name: [0.0, 0.0] for name in runner.VECTOR_NAMES})
        self.assertFalse(runner.compare_vectors(left, non_monotonic)["passed"])
        non_finite = vectors({name: [0.0, float("inf")] for name in runner.VECTOR_NAMES})
        self.assertFalse(runner.compare_vectors(left, non_finite)["passed"])

    def test_exact_repeat_keeps_float_representation(self) -> None:
        first = [{"case_index": 0, "metrics": {"x": 1.0}, "vectors": []}]
        second = [{"case_index": 0, "metrics": {"x": 1}, "vectors": []}]
        self.assertFalse(runner.exact_repeat(first, second))

    def test_matlab_repeat_includes_bridge(self) -> None:
        repeats = [
            {"cases": [], "parameter_bridge": {"passed": True, "sha": "a"}},
            {"cases": [], "parameter_bridge": {"passed": True, "sha": "b"}},
        ]
        self.assertFalse(runner.repeat_payload_exact(repeats, "matlab"))

    def test_nonce_derivation_is_stable_and_distinct(self) -> None:
        first = runner._derived_nonce("a" * 64, 1)
        second = runner._derived_nonce("a" * 64, 2)
        self.assertEqual(len(first), 64)
        self.assertNotEqual(first, second)

    def test_main_routes_matlab_trace_worker_without_reparsing_replay_args(self) -> None:
        observed: list[Path] = []
        original = runner._matlab_trace_worker
        try:
            runner._matlab_trace_worker = observed.append
            self.assertEqual(runner.main(["--matlab-trace-worker", "trace-spec.json"]), 0)
        finally:
            runner._matlab_trace_worker = original
        self.assertEqual(observed, [Path("trace-spec.json")])

    def test_normal_erl_sidecar_reads_raw_f64_and_rejects_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ports = []
            for port in (1, 2):
                vectors = {}
                for name in runner.VECTOR_NAMES:
                    values = [0.0, 1.0] if name == "time_s" else [1.0, 2.0]
                    raw = b"".join(__import__("struct").pack("<d", value) for value in values)
                    relative = f"port-{port}\\{name}.f64le"
                    target = root / f"port-{port}" / f"{name}.f64le"
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(raw)
                    vectors[name] = {"file": relative, "dtype": "f64le", "shape": [2], "bytes": len(raw), "sha256": runner.sha256_bytes(raw)}
                ports.append({"port": port, "available": True, "vectors": vectors})
            # The production sidecar writes canonical sorted JSON; object
            # member order must not be mistaken for vector order.
            (root / "manifest.json").write_text(json.dumps({"schema": "sipi.com.normal-erl-array-sidecar.v1", "diagnostic_only": True, "ports": ports}, sort_keys=True), encoding="utf-8")
            result = runner._read_f64le_sidecar(root, schema="sipi.com.normal-erl-array-sidecar.v1")
            self.assertEqual(result[1][0]["name"], "time_s")
            self.assertEqual(runner.CASE_TO_PORT, {0: 1})
            self.assertEqual(runner._selected_sidecar_vectors(result), result[1])
            legacy_manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            legacy_manifest["schema"] = "sipi.com.normal-erl-array-trace.v1"
            legacy_manifest["package_testcase_index"] = 0
            for entry in legacy_manifest["ports"]:
                for receipt in entry["vectors"].values():
                    receipt.pop("sha256")
            (root / "manifest.json").write_text(json.dumps(legacy_manifest), encoding="utf-8")
            runner._enrich_trace_hash_receipts(root)
            enriched = runner._read_f64le_sidecar(root, schema="sipi.com.normal-erl-array-trace.v1")
            expected_raw = b"".join(__import__("struct").pack("<d", value) for value in [1.0, 2.0])
            self.assertEqual(enriched[2][1]["sha256"], runner.sha256_bytes(expected_raw))
            ports[0]["vectors"]["time_s"]["file"] = "../escape.f64le"
            enriched_manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            enriched_manifest["ports"] = ports
            (root / "manifest.json").write_text(json.dumps(enriched_manifest), encoding="utf-8")
            with self.assertRaises(RuntimeError):
                runner._read_f64le_sidecar(root, schema="sipi.com.normal-erl-array-trace.v1")


if __name__ == "__main__":
    unittest.main()
