from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path


PATH = Path(__file__).with_name("aggregate_com_tp0v_r2024b_v4_replay.py")
SPEC = importlib.util.spec_from_file_location("aggregate_com_tp0v_r2024b_v4_replay", PATH)
assert SPEC and SPEC.loader
aggregate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(aggregate)


def _vectors() -> list[dict]:
    return [{"name": name, "values": [0.0, 1.0] if name == "time_s" else [1.0, 2.0]} for name in aggregate.VECTOR_NAMES]


def _cases() -> list[dict]:
    metrics = {name: 1.0 for name in aggregate.SCALAR_NAMES}
    return [{"case_index": aggregate.SELECTED_CASE_INDEX, "metrics": dict(metrics), "vectors": copy.deepcopy(_vectors()), "vector_payload_present": True, "vector_binding": {"case_index": aggregate.SELECTED_CASE_INDEX, "port": aggregate.SELECTED_PORT, "package_testcase_index": aggregate.PACKAGE_TESTCASE_INDEX}}]


def _report(engine: str, index: int) -> dict:
    run_id = f"{engine}-{index:02d}"
    cases = _cases()
    route = "public_root_sipi_com_run" if engine == "rust" else "pinned_agent_com_matlab_core_uninstrumented"
    repeats = []
    for repeat_index in (1, 2):
        repeats.append({
            "repeat_index": repeat_index,
            "nonce": f"{index:02d}{repeat_index:02d}" + "a" * 60,
            "status": "passed",
            "route": route,
            "source_inventory_unchanged": True,
            "cases": copy.deepcopy(cases),
            "case_wall_clock_s": [1.0 + index] if engine == "rust" else [10.0 + index],
            "semantic_wall_clock_s": 1.0 + index if engine == "rust" else 10.0 + index,
            "diagnostic_wall_clock_s": 2.0 + index if engine == "rust" else 11.0 + index,
            "sidecar": {"schema": "sipi.com.normal-erl-array-sidecar.v1" if engine == "rust" else "sipi.com.normal-erl-array-trace.v1", "selected_case_index": aggregate.SELECTED_CASE_INDEX, "package_testcase_index": aggregate.PACKAGE_TESTCASE_INDEX, "selected_port": aggregate.SELECTED_PORT, "ports": [1, 2], "raw_f64": True, "case_to_port": [{"case_index": aggregate.SELECTED_CASE_INDEX, "port": aggregate.SELECTED_PORT, "package_testcase_index": aggregate.PACKAGE_TESTCASE_INDEX}]},
            "parameter_bridge": {"passed": True} if engine == "matlab" else {},
        })
    return {
        "schema": aggregate.REPLAY_SCHEMA,
        "diagnostic_only": True,
        "formal_record": False,
        "status": "passed",
        "engine": engine,
        "run_id": run_id,
        "nonce": f"{index:02d}" + ("b" if engine == "matlab" else "c") * 62,
        "candidate": aggregate.CANDIDATE_RECEIPT,
        "candidate_gate_parent": aggregate.CANDIDATE_GATE_PARENT,
        "upstream": aggregate.UPSTREAM_RECEIPT,
        "comparison_contract": {"vectors": list(aggregate.VECTOR_NAMES), "prohibited_transforms": list(aggregate.PROHIBITED_TRANSFORMS), "scalar_case_scope": {"selected_case_index": aggregate.SELECTED_CASE_INDEX, "package_testcase_index": aggregate.PACKAGE_TESTCASE_INDEX, "case_count": len(aggregate.CASE_INDICES)}, "selected_case_index": aggregate.SELECTED_CASE_INDEX, "package_testcase_index": aggregate.PACKAGE_TESTCASE_INDEX, "selected_port": aggregate.SELECTED_PORT, "case_to_port": [{"case_index": aggregate.SELECTED_CASE_INDEX, "port": aggregate.SELECTED_PORT, "package_testcase_index": aggregate.PACKAGE_TESTCASE_INDEX}]},
        "d3": {"status": "not_evaluated_configuration_disables_tdiln", "global_d3_enabled": True, "selected_configs": [{"COMPUTE_TDILN": 0}]},
        "roots": {"candidate": f"{run_id}:candidate", "build": f"{run_id}:build", "repeats": [f"{run_id}:repeat-01", f"{run_id}:repeat-02"], "path_redacted": True},
        "repeats": repeats,
        "gates": {"internal_exact_repeat": True, "mat_bridge": engine == "rust" or True},
        "performance": {"instrumented_trace_included": False, "semantic_timing_source": "un-instrumented_semantic_invocation_only", "diagnostic_trace_timing_recorded": True},
    }


class AggregateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.reports = [_report("matlab", 1), _report("matlab", 2), _report("rust", 1), _report("rust", 2)]

    def test_four_replays_and_vectors_pass(self) -> None:
        result = aggregate.aggregate_documents(self.reports)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["blockers"], [])
        self.assertTrue(result["gates"]["performance_each_case_rust_strictly_faster"])

    def test_duplicate_top_level_nonce_is_rejected(self) -> None:
        reports = copy.deepcopy(self.reports)
        reports[1]["nonce"] = reports[0]["nonce"]
        with self.assertRaises(ValueError):
            aggregate.aggregate_documents(reports)

    def test_vector_drift_is_blocked_not_silently_fixed(self) -> None:
        reports = copy.deepcopy(self.reports)
        for repeat in reports[2]["repeats"]:
            repeat["cases"][0]["vectors"][1]["values"][1] = 1.1
        result = aggregate.aggregate_documents(reports)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("pair_1_vector_surface_drift", result["blockers"])

    def test_missing_per_case_timing_blocks_performance(self) -> None:
        reports = copy.deepcopy(self.reports)
        reports[2]["repeats"][0]["case_wall_clock_s"] = None
        with self.assertRaises(ValueError):
            aggregate.aggregate_documents(reports)

    def test_second_exact_repeat_is_also_a_performance_gate(self) -> None:
        reports = copy.deepcopy(self.reports)
        reports[2]["repeats"][1]["case_wall_clock_s"] = [20.0]
        reports[2]["repeats"][1]["semantic_wall_clock_s"] = 20.0
        result = aggregate.aggregate_documents(reports)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("pair_1_repeat_2_case_0_rust_not_faster", result["blockers"])

    def test_global_d3_cannot_be_disabled(self) -> None:
        reports = copy.deepcopy(self.reports)
        reports[0]["d3"]["global_d3_enabled"] = False
        with self.assertRaises(ValueError):
            aggregate.aggregate_documents(reports)

    def test_case_port_swap_is_rejected(self) -> None:
        reports = copy.deepcopy(self.reports)
        reports[0]["repeats"][0]["cases"][0]["vector_binding"]["port"] = 2
        with self.assertRaises(ValueError):
            aggregate.aggregate_documents(reports)


if __name__ == "__main__":
    unittest.main()
