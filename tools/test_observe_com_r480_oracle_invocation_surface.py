from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from observe_com_r480_oracle_invocation_surface import ObservationError, _scan, validate_report


def valid_report() -> dict:
    return {
        "schema": "sipi.com.r480.oracle-invocation-surface-report.v1",
        "status": "runner_interface_partially_observed",
        "source": {"canonical_origin": "https://github.com/z331225718/agent-com.git", "commit": "5272ffe74702cd585054d975559b06f8afae7b6e", "tree": "7094ab6e84989b218730c52432c70da10261f8ea", "object_format": "sha1"},
        "tool": {"path": "tools/run_matlab_oracle.py", "git_blob": "36d4fa55f6eaf9ecdd72ba2cebfbc1b01908e8bc", "content_sha256": "db63ed42375ac990cb53d9926f603e050b652b0706c079f2e4456a5d97d87d42", "byte_length": 30851},
        "surface": {"declared_cli_options": ["--config", "--dry-run"], "argparse_constructor_observed": True, "help_surface": "not_executed", "dry_run_surface": "declared_but_not_executed", "subprocess_launch_api_observed": True, "file_io_api_observed": True, "entrypoint_guard_observed": True, "dynamic_invocation_dependencies": "unknown"},
        "execution": {"authorized": False, "invoked": False, "status": "dynamic_invocation_not_authorized_or_not_safe"},
        "non_claims": ["The runner was parsed as an external Git blob and was not imported or executed.", "No MATLAB, workbook, fixture, parameter, input, result, default, formula, or code fragment is recorded.", "This does not establish a runnable oracle, an authoritative reference, or COM parity."],
    }


class OracleInvocationSurfaceTests(unittest.TestCase):
    def test_synthetic_ast_scan_only_extracts_bounded_surface(self) -> None:
        surface = _scan(b"import argparse, subprocess\np=argparse.ArgumentParser()\np.add_argument('--config')\np.add_argument('--dry-run')\nsubprocess.run(['matlab'])\nopen('external', 'r')\nif __name__ == '__main__': pass\n")
        self.assertEqual(surface["declared_cli_options"], ["--config", "--dry-run"])
        self.assertTrue(surface["subprocess_launch_api_observed"])
        self.assertTrue(surface["file_io_api_observed"])

    def test_execution_promotion_fails_closed(self) -> None:
        report = valid_report()
        validate_report(report)
        invalid = copy.deepcopy(report)
        invalid["execution"]["authorized"] = True
        with self.assertRaisesRegex(RuntimeError, "execution_must_remain_blocked"):
            validate_report(invalid)
        invalid = copy.deepcopy(report)
        invalid["status"] = "oracle_ready"
        with self.assertRaisesRegex(RuntimeError, "report_status_invalid"):
            validate_report(invalid)

    def test_surface_content_is_constrained(self) -> None:
        invalid = valid_report()
        invalid["surface"]["declared_cli_options"].append("plain-text-source-fragment")
        with self.assertRaisesRegex(RuntimeError, "surface_invalid"):
            validate_report(invalid)


if __name__ == "__main__":
    unittest.main()
