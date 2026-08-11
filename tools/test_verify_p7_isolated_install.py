"""Product-owned tests for P7-04a same-host isolated-prefix admission."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p7_install", ROOT / "tools" / "verify_p7_isolated_install.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


def digest(character: str) -> str:
    return character * 64


class IsolatedInstallTests(unittest.TestCase):
    def prior_report(self) -> dict:
        return {
            "schema": GATE.ARCHIVE_SCHEMA,
            "structural_admission": "conformant",
            "composition_evidence_status": "incomplete",
            "promotion_status": "blocked",
            "archive_sha256": digest("a"),
            "archive_bytes": 7,
            "policy_sha256": digest("b"),
            "composition_report_sha256": digest("c"),
            "source_commit": "d" * 40,
            "entries": [
                {"role": "main_executable", "bytes": 3, "content_sha256": digest("e")},
                {"role": "mit_license", "bytes": 4, "content_sha256": digest("f")},
            ],
            "static_pe_binding": "same_executable_bytes_as_composition_stage",
            "limitations": [],
        }

    def test_report_requires_blocked_exact_admission(self) -> None:
        self.assertEqual(GATE.parse_prior_report(self.prior_report())["archive_bytes"], 7)
        report = self.prior_report()
        report["promotion_status"] = "approved"
        with self.assertRaises(GATE.InstallError):
            GATE.parse_prior_report(report)

    def test_environment_is_minimal_and_drops_injection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            environment = GATE.scrubbed_environment(
                {
                    "SystemRoot": "C:\\Windows",
                    "PYTHONPATH": "poison",
                    "VIRTUAL_ENV": "poison",
                    "CONDA_PREFIX": "poison",
                    "CARGO_HOME": "poison",
                    "RUSTUP_HOME": "poison",
                    "MATLABPATH": "poison",
                    "PATH": "poison",
                },
                Path(directory),
            )
        self.assertEqual(set(environment), {"SystemRoot", "WINDIR", "PATH", "TEMP", "TMP"})
        self.assertNotIn("poison", "|".join(environment.values()))
        self.assertEqual(GATE.sanitization_policy_sha256(), GATE.sanitization_policy_sha256())

    def test_response_contract_rejects_multiline_and_missing_diagnostic(self) -> None:
        success = b'{"schema":"sipi.cli.response.v1","status":"ok"}\n'
        self.assertEqual(len(GATE.response_digest(success, b"", 0, False)), 2)
        with self.assertRaises(GATE.InstallError):
            GATE.response_digest(b'{"schema":"sipi.cli.response.v1","status":"unsupported"}\n', b"", 0, False)
        with self.assertRaises(GATE.InstallError):
            GATE.response_digest(success + success, b"", 0, False)
        with self.assertRaises(GATE.InstallError):
            GATE.response_digest(success, b"", 4, True)

    def test_prefix_and_report_must_be_external_new_locations(self) -> None:
        with self.assertRaises(GATE.InstallError):
            GATE.require_external(ROOT / "install", ROOT)
        with tempfile.TemporaryDirectory() as directory:
            prefix = Path(directory) / "existing"
            prefix.mkdir()
            self.assertTrue(prefix.exists())
            with self.assertRaises(GATE.InstallError):
                if prefix.exists() or prefix.is_symlink():
                    raise GATE.InstallError("install_prefix_not_new")
            report = Path(directory) / "report.json"
            report.write_text(json.dumps({"old": True}), encoding="utf-8")
            with self.assertRaises(GATE.InstallError):
                GATE.write_new_external_report(report, ROOT, {"schema": GATE.SCHEMA})


if __name__ == "__main__":
    unittest.main()
