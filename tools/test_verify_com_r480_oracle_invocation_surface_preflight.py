from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from observe_com_r480_oracle_invocation_surface import SCHEMA as REPORT_SCHEMA
from verify_com_r480_oracle_invocation_surface_preflight import VerificationError, verify


def report() -> dict:
    return {
        "schema": REPORT_SCHEMA,
        "status": "runner_interface_partially_observed",
        "source": {"canonical_origin": "https://github.com/z331225718/agent-com.git", "commit": "5272ffe74702cd585054d975559b06f8afae7b6e", "tree": "7094ab6e84989b218730c52432c70da10261f8ea", "object_format": "sha1"},
        "tool": {"path": "tools/run_matlab_oracle.py", "git_blob": "36d4fa55f6eaf9ecdd72ba2cebfbc1b01908e8bc", "content_sha256": "db63ed42375ac990cb53d9926f603e050b652b0706c079f2e4456a5d97d87d42", "byte_length": 30851},
        "surface": {"argparse_constructor_observed": False, "declared_cli_options": ["--config", "--fext", "--fixture-manifest", "--force", "--instrumented-source", "--matlab", "--next", "--no-fext", "--no-next", "--output-dir", "--runs", "--set-com-setting", "--set-parameter", "--target-frequency-ghz", "--thru"], "dry_run_surface": "not_observed", "dynamic_invocation_dependencies": "unknown", "entrypoint_guard_observed": True, "file_io_api_observed": True, "help_surface": "not_observed", "subprocess_launch_api_observed": True},
        "execution": {"authorized": False, "invoked": False, "status": "dynamic_invocation_not_authorized_or_not_safe"},
        "non_claims": ["The runner was parsed as an external Git blob and was not imported or executed.", "No MATLAB, workbook, fixture, parameter, input, result, default, formula, or code fragment is recorded.", "This does not establish a runnable oracle, an authoritative reference, or COM parity."],
    }


class OracleInvocationSurfacePreflightTests(unittest.TestCase):
    def manifest(self) -> dict:
        return yaml.safe_load((ROOT / "docs" / "baselines" / "com-r480-oracle-invocation-surface-preflight.v1.yaml").read_text(encoding="utf-8"))

    def external_report(self) -> tuple[Path, str]:
        path = Path(tempfile.mkdtemp()) / "report.json"
        path.write_text(json.dumps(report(), sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        return path, hashlib.sha256(path.read_bytes()).hexdigest()

    def test_static_surface_stays_non_executing_and_blocked(self) -> None:
        path, digest = self.external_report()
        manifest = self.manifest()
        manifest["observation"]["external_report"]["content_sha256"] = digest
        with patch("verify_com_r480_oracle_invocation_surface_preflight.REPORT_SHA256", digest):
            result = verify(manifest, path)
        self.assertTrue(result["valid"])
        self.assertFalse(result["execution_invoked"])

    def test_execution_or_reference_promotion_fails_closed(self) -> None:
        path, digest = self.external_report()
        manifest = self.manifest()
        manifest["observation"]["external_report"]["content_sha256"] = digest
        invalid = copy.deepcopy(manifest)
        invalid["execution"]["authorized"] = True
        with patch("verify_com_r480_oracle_invocation_surface_preflight.REPORT_SHA256", digest):
            with self.assertRaisesRegex(RuntimeError, "execution_mismatch"):
                verify(invalid, path)
        invalid = copy.deepcopy(manifest)
        invalid["reference_gate"]["status"] = "reference_generation_ready"
        with patch("verify_com_r480_oracle_invocation_surface_preflight.REPORT_SHA256", digest):
            with self.assertRaisesRegex(RuntimeError, "reference_gate_not_fail_closed"):
                verify(invalid, path)

    def test_report_hash_and_internal_path_fail_closed(self) -> None:
        path, digest = self.external_report()
        manifest = self.manifest()
        manifest["observation"]["external_report"]["content_sha256"] = digest
        with patch("verify_com_r480_oracle_invocation_surface_preflight.REPORT_SHA256", "0" * 64):
            with self.assertRaisesRegex(RuntimeError, "external_report_hash_mismatch"):
                verify(manifest, path)
        with self.assertRaisesRegex(RuntimeError, "report_must_remain_external"):
            verify(manifest, ROOT / "no-external-report.json")


if __name__ == "__main__":
    unittest.main()
