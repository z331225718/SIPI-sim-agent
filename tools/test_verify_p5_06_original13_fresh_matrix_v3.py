from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.run_p5_06_original13_fresh_matrix import CHANNELS, CONFIG_PATHS, METRICS, UPSTREAM
from tools.run_p5_06_original13_fresh_matrix_v3 import CANDIDATE, HARNESS, MATLAB_RELEASE, SCHEMA, TIMING_SCOPE, WORKER, file_identity
from tools.verify_p5_06_original13_fresh_matrix import WORKBOOKS
from tools.verify_p5_06_original13_fresh_matrix_v3 import VerificationError, verify


def receipt(role: str) -> dict:
    value = "1" * 64
    output = {"role": role, "executable": f"{role}.exe", "file_sha256": value, "version_sha256": value, "path_redacted": True}
    if role == "matlab":
        output.update({"executable": "matlab.exe", "release": MATLAB_RELEASE, "launch_mode": "python_engine_per_workbook_noFigureWindows_singleCompThread"})
    return output


def matrix_metrics(index: int) -> list[dict]:
    # 28 cases and 303 scalar slots, matching the formal matrix coverage gate.
    count = 16 if index == 0 else 1
    result = []
    for case in range(count):
        global_case = case if index == 0 else 15 + index
        names = METRICS if global_case < 25 else ("COM_dB",)
        result.append({name: float(global_case) for name in names})
    return result


def report(engine: str, nonce: str, duration: int = 100) -> dict:
    records = []
    for index, path in enumerate(CONFIG_PATHS):
        metrics = matrix_metrics(index)
        materialization = {"comparison": "not_run_for_rust_result_replay"}
        if engine == "matlab":
            materialization = {
                "comparison": "equal", "first_difference": None, "pinned_sha256": "2" * 64, "rust_sha256": "2" * 64,
                "parameter_shape": [2, 2], "parameter_slot_digest": "3" * 64, "parameter_mat_bytes": 10, "parameter_mat_sha256": "4" * 64,
            }
        records.append({
            "workbook_index": index, "workbook": {"path": path, "bytes": WORKBOOKS[path][0], "sha256": WORKBOOKS[path][1]},
            "status": "passed", "exit_code": 0, "timed_out": False, "execution_wall_ns": duration + index,
            "timing_scope": TIMING_SCOPE, "detail_sha256": "5" * 64, "source_inventory_unchanged": True,
            "config_materialization": materialization, "case_count": len(metrics), "metrics": metrics,
        })
    return {
        "schema": SCHEMA, "engine": engine, "run_id": f"original13-v3-{engine}-{nonce}", "nonce": nonce, "root_id": ("a" if engine == "matlab" else "b") + nonce[1:],
        "status": "fresh_matrix_run", "timing_clock": "perf_counter_ns", "timing_scope": TIMING_SCOPE,
        "total_execution_wall_ns": sum(item["execution_wall_ns"] for item in records), "host_fingerprint": "6" * 64, "selection_count": 13,
        "source": {
            "upstream": {"commit": UPSTREAM[0], "tree": UPSTREAM[1], "archive_sha256": UPSTREAM[2], "archive_bytes": UPSTREAM[3]},
            "candidate": {"commit": CANDIDATE[0], "tree": CANDIDATE[1], "archive_sha256": CANDIDATE[2], "archive_bytes": CANDIDATE[3]},
            "rust_binary": {"bytes": 1, "sha256": "7" * 64},
            "toolchain": {role: receipt(role) for role in ("cargo", "rustc", "uv", "matlab", "python")},
            "gate_tools": {"runner": file_identity(Path(__file__).with_name("run_p5_06_original13_fresh_matrix_v3.py")), "worker": file_identity(WORKER), "matlab_harness": file_identity(HARNESS)},
        },
        "channels": [{"role": role, "path": path, "bytes": size, "sha256": sha} for role, path, size, sha in CHANNELS],
        "records": records,
        "claims": {"acceptance": False, "performance_acceptance": False, "release": False, "s_parameter_fit": False, "one_final_fd_to_td_impulse": True},
    }


class V3Tests(unittest.TestCase):
    def test_valid_full_matrix(self):
        self.assertTrue(verify(report("matlab", "0" * 64)))

    def test_r2026_is_rejected(self):
        item = report("matlab", "0" * 64)
        item["source"]["toolchain"]["matlab"]["release"] = "R2026a"
        with self.assertRaises(VerificationError):
            verify(item)

    def test_partial_matrix_is_rejected(self):
        item = report("rust", "0" * 64)
        item["records"] = item["records"][:-1]
        with self.assertRaises(VerificationError):
            verify(item)

    def test_aggregate_rejects_one_slow_workbook(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports = [
                ("matlab-a.json", report("matlab", "1" * 64, 200)), ("matlab-b.json", report("matlab", "2" * 64, 210)),
                ("rust-a.json", report("rust", "3" * 64, 100)), ("rust-b.json", report("rust", "4" * 64, 110)),
            ]
            for name, item in reports:
                (root / name).write_text(json.dumps(item), encoding="utf-8")
            command = [sys.executable, str(Path(__file__).with_name("aggregate_p5_06_original13_fresh_matrix_v3.py")), "--matlab-report", str(root / "matlab-a.json"), "--matlab-report", str(root / "matlab-b.json"), "--rust-report", str(root / "rust-a.json"), "--rust-report", str(root / "rust-b.json"), "--output", str(root / "accepted.json")]
            self.assertEqual(subprocess.run(command, check=False).returncode, 0)
            self.assertEqual(json.loads((root / "accepted.json").read_text())["status"], "accepted_stage1")
            slow = reports[-1][1]
            slow["records"][7]["execution_wall_ns"] = 10000
            slow["total_execution_wall_ns"] = sum(record["execution_wall_ns"] for record in slow["records"])
            (root / "rust-b-slow.json").write_text(json.dumps(slow), encoding="utf-8")
            blocked = [
                sys.executable, str(Path(__file__).with_name("aggregate_p5_06_original13_fresh_matrix_v3.py")),
                "--matlab-report", str(root / "matlab-a.json"), "--matlab-report", str(root / "matlab-b.json"),
                "--rust-report", str(root / "rust-a.json"), "--rust-report", str(root / "rust-b-slow.json"),
                "--output", str(root / "blocked.json"),
            ]
            self.assertEqual(subprocess.run(blocked, check=False).returncode, 0)
            self.assertEqual(json.loads((root / "blocked.json").read_text())["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
