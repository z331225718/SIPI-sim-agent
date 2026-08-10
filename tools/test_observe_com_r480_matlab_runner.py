from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from observe_com_r480_matlab_runner import EXPRESSION, PROBE_ID, SCHEMA, TIMEOUT_SECONDS, _sha256, validate_report


def valid_report() -> dict:
    return {
        "schema": SCHEMA,
        "status": "indeterminate",
        "runner": {"logical_name": "matlab", "platform": "windows-x86_64", "executable_sha256": "a" * 64, "executable_byte_length": 1},
        "probe": {"id": PROBE_ID, "template_sha256": _sha256(("-batch\0" + EXPRESSION).encode("utf-8")), "timeout_seconds": TIMEOUT_SECONDS, "cwd": "external_empty_temp", "matlabpath": "cleared", "matlab_prefdir": "external_temporary", "startup_isolation": "unproven"},
        "result": {"timed_out": True, "process_tree_terminated": True, "exit_code": -1, "sentinel_observed": False, "observed_identity": None, "stdout_sha256": "b" * 64, "stderr_sha256": "c" * 64, "license_runtime_observation": "unknown"},
        "non_claims": ["No agent-com, MATLAB source, workbook, fixture, parameter, or R480 input was read or executed.", "This report does not establish oracle authorization, R480 execution, a reference result, or parity."],
    }


class MatlabRunnerProbeTests(unittest.TestCase):
    def test_indeterminate_report_is_valid(self) -> None:
        validate_report(valid_report())

    def test_candidate_promotion_and_isolation_relaxation_fail(self) -> None:
        report = valid_report()
        invalid = copy.deepcopy(report)
        invalid["status"] = "runner_candidate_available"
        with self.assertRaisesRegex(RuntimeError, "report_status_invalid"):
            validate_report(invalid)
        invalid = copy.deepcopy(report)
        invalid["probe"]["startup_isolation"] = "proven"
        with self.assertRaisesRegex(RuntimeError, "probe_isolation_invalid"):
            validate_report(invalid)

    def test_identity_and_output_leaks_fail(self) -> None:
        report = valid_report()
        invalid = copy.deepcopy(report)
        invalid["runner"]["executable_byte_length"] = 0
        with self.assertRaisesRegex(RuntimeError, "runner_identity_invalid"):
            validate_report(invalid)
        invalid = copy.deepcopy(report)
        invalid["result"]["license_runtime_observation"] = "success"
        with self.assertRaisesRegex(RuntimeError, "result_identity_invalid"):
            validate_report(invalid)


if __name__ == "__main__":
    unittest.main()
