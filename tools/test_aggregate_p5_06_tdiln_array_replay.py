from __future__ import annotations

import copy
import unittest

from tools.aggregate_p5_06_tdiln_array_replay import aggregate
from tools.run_p5_06_original13_fresh_matrix import CONFIG_PATHS
from tools.run_p5_06_tdiln_array_replay import RAYON_THREADS, SCHEMA


def _hash(token: str) -> str:
    return token * 64


def _tool(name: str, token: str) -> dict[str, object]:
    return {"name": name, "bytes": 1, "sha256": _hash(token)}


def _receipt(role: str, token: str) -> dict[str, object]:
    return {"role": role, "executable": f"{role}.exe", "file_sha256": _hash(token), "version_sha256": _hash(chr(ord(token) + 1)), "path_redacted": True}


def report(run: str, nonce: str, matlab_seconds: float = 10.0, rust_seconds: float = 5.0) -> dict[str, object]:
    records = []
    for index in range(len(CONFIG_PATHS)):
        records.append({
            "workbook_index": index,
            "status": "passed_diagnostic",
            "matlab_summary_sha256": _hash("a"),
            "rust_result_sha256": _hash("b"),
            "rust_result_semantic_sha256": _hash("c"),
            "rust_production_result_sha256": _hash("d"),
            "rust_production_result_semantic_sha256": _hash("e"),
            "matlab_core_seconds": matlab_seconds,
            "rust_wall_seconds": rust_seconds,
            "rust_not_slower": True,
            "speedup": matlab_seconds / rust_seconds,
            "array_status": "passed_diagnostic",
            "array_case_count": 1,
        })
    return {
        "schema": SCHEMA,
        "diagnostic_only": True,
        "status": "passed_replay",
        "run_id": f"tdiln-array-{run}",
        "nonce": _hash(nonce),
        "source": {
            "candidate": {"commit": "a", "tree": "b", "archive_sha256": _hash("c"), "archive_bytes": 1},
            "upstream": {"commit": "d", "tree": "e", "archive_sha256": _hash("f"), "archive_bytes": 1},
            "rust_binary": _tool("sipi-com-direct-run.exe", "a"),
            "rust_production_binary": _tool("sipi-com-direct-run.exe", "b"),
            "gate_tools": {"runner": _tool("runner.py", "c"), "diagnostic_runner": _tool("diagnostic.py", "d"), "matlab_harness": _tool("harness.m", "e"), "array_comparator": _tool("compare.py", "f")},
            "toolchain": {role: _receipt(role, token) for role, token in zip(("cargo", "rustc", "uv", "matlab", "python"), ("a", "b", "c", "d", "e"), strict=True)},
        },
        "host": {"system": "Windows", "machine": "AMD64", "logical_cpus": RAYON_THREADS, "rayon_threads": RAYON_THREADS},
        "matrix": {"workbook_count": len(CONFIG_PATHS), "records": records, "diagnostic_report_sha256": _hash("f")},
        "performance_policy": {"rust_not_slower_required": True, "scope": "default-production Rust process plus normal artifacts; TDILN diagnostic sidecar I/O excluded; MATLAB source core after engine start"},
        "claims": {"tdiln_named_intermediate_checkpoint_parity": True, "performance_acceptance_checkpoint": True, "full_result_graph": False, "complete_warning_catalog": False, "channel_s_parameter_fit": False, "release": False},
    }


class TdilnArrayReplayAggregateTests(unittest.TestCase):
    def test_two_matching_fast_replays_are_accepted(self) -> None:
        result = aggregate(report("one", "a"), report("two", "b"), _hash("1"), _hash("2"))
        self.assertEqual(result["status"], "accepted_diagnostic_checkpoint")
        self.assertTrue(result["gates"]["total_rust_not_slower"])

    def test_worst_rust_must_beat_best_matlab_across_replays(self) -> None:
        result = aggregate(report("one", "a", 10.0, 9.0), report("two", "b", 8.0, 7.9), _hash("1"), _hash("2"))
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["gates"]["per_workbook_rust_not_slower"])

    def test_semantic_result_drift_blocks(self) -> None:
        first = report("one", "a")
        second = report("two", "b")
        second["matrix"]["records"][0]["rust_result_semantic_sha256"] = _hash("e")
        result = aggregate(first, second, _hash("1"), _hash("2"))
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["gates"]["rust_semantic_repeat_exact"])

    def test_source_drift_is_rejected(self) -> None:
        first = report("one", "a")
        second = copy.deepcopy(report("two", "b"))
        second["source"]["candidate"]["tree"] = "different"
        with self.assertRaisesRegex(ValueError, "source, host, or policy drift"):
            aggregate(first, second, _hash("1"), _hash("2"))


if __name__ == "__main__":
    unittest.main()
