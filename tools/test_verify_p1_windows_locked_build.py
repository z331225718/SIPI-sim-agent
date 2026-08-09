"""Focused contract tests for the P1-11 external build gate."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p1_gate", ROOT / "tools" / "verify_p1_windows_locked_build.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


class WindowsLockedBuildGateTests(unittest.TestCase):
    def test_inventory_baselines_are_hash_bound(self) -> None:
        entries = GATE.load_inventory(ROOT)
        self.assertEqual([entry["id"] for entry in entries], ["sipi.capabilities.v1"])

    def test_cli_response_requires_exact_success_shape(self) -> None:
        valid = {
            "exit_code": 0,
            "stdout": b'{"schema":"sipi.cli.response.v1","status":"ok"}\n',
            "stderr": b"",
        }
        self.assertEqual(GATE.parse_cli_response(valid, "ok")["status"], "ok")
        invalid = dict(valid, stdout=b"human output\n")
        with self.assertRaises(GATE.GateError):
            GATE.parse_cli_response(invalid, "ok")

    def test_scrubbed_environment_removes_python_injection(self) -> None:
        environment = GATE.scrubbed_environment(
            {"PATH": "x", "PYTHONPATH": "bad", "PYTHONHOME": "bad", "CONDA_PREFIX": "bad"}
        )
        self.assertEqual(environment, {"PATH": "x"})
