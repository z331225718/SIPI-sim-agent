from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from observe_com_r480_matlab_runner import SCHEMA as REPORT_SCHEMA
from observe_com_r480_matlab_runner import EXPRESSION, PROBE_ID, TIMEOUT_SECONDS, _sha256
from verify_com_r480_matlab_runner_preflight import EXPECTED_REPORT_SHA256, VerificationError, verify


def report() -> dict:
    return {
        "schema": REPORT_SCHEMA,
        "status": "indeterminate",
        "runner": {"logical_name": "matlab", "platform": "windows-x86_64", "executable_sha256": "4b0fcf8112211ad1ae6ef5e51df0801d7afbe89c4daaac45473a46e1de16e633", "executable_byte_length": 458288},
        "probe": {"id": PROBE_ID, "template_sha256": _sha256(("-batch\0" + EXPRESSION).encode("utf-8")), "timeout_seconds": TIMEOUT_SECONDS, "cwd": "external_empty_temp", "matlabpath": "cleared", "matlab_prefdir": "external_temporary", "startup_isolation": "unproven"},
        "result": {"timed_out": False, "process_tree_terminated": False, "exit_code": 0, "sentinel_observed": True, "observed_identity": {"release": "2024b", "version": "24.2.0.2712019 (R2024b)", "platform": "PCWIN64"}, "stdout_sha256": "276c3a4c20cad8b08cbe81daa24d653cc8cef39aba670d401d21e45162aa58f5", "stderr_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "license_runtime_observation": "unknown"},
        "non_claims": ["No agent-com, MATLAB source, workbook, fixture, parameter, or R480 input was read or executed.", "This report does not establish oracle authorization, R480 execution, a reference result, or parity."],
    }


class MatlabRunnerPreflightTests(unittest.TestCase):
    def manifest(self) -> dict:
        return yaml.safe_load((ROOT / "docs" / "baselines" / "com-r480-matlab-runner-capability-preflight.v1.yaml").read_text(encoding="utf-8"))

    def external_report(self) -> Path:
        path = Path(tempfile.mkdtemp()) / "report.json"
        path.write_text(json.dumps(report(), sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        self.assertEqual(_sha256(path.read_bytes()), EXPECTED_REPORT_SHA256)
        return path

    def test_external_indeterminate_runner_remains_blocked(self) -> None:
        result = verify(self.manifest(), self.external_report())
        self.assertTrue(result["valid"])
        self.assertEqual(result["runner_status"], "indeterminate")
        self.assertEqual(result["reference_generation_status"], "blocked")

    def test_hash_and_promotion_mismatch_fail_closed(self) -> None:
        path = self.external_report()
        path.write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "external_report_hash_mismatch"):
            verify(self.manifest(), path)
        invalid = self.manifest()
        invalid["reference_gate"]["status"] = "reference_generation_ready"
        with self.assertRaisesRegex(RuntimeError, "reference_gate_not_fail_closed"):
            verify(invalid, self.external_report())

    def test_product_runtime_or_internal_report_is_rejected(self) -> None:
        invalid = self.manifest()
        invalid["reference_gate"]["product_runtime"] = "allowed"
        with self.assertRaisesRegex(RuntimeError, "reference_gate_not_fail_closed"):
            verify(invalid, self.external_report())
        with self.assertRaisesRegex(RuntimeError, "report_must_remain_external"):
            verify(self.manifest(), ROOT / "runner-report-test.json")


if __name__ == "__main__":
    unittest.main()
