"""Focused tests for the additive v5 clean-archive diagnostic runner."""

from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from tools import run_com_workbook_accm_replay_v5 as runner


class WorkbookAccmV5Tests(unittest.TestCase):
    @staticmethod
    def _runtime_proof() -> dict[str, object]:
        module = {
            "relative_path": "src/agent_com/__init__.py",
            "basename": "__init__.py",
            "bytes": 1,
            "sha256": "a" * 64,
            "root_contained": True,
            "path_redacted": True,
        }
        external = {
            "relative_path": None,
            "basename": "runtime.pyd",
            "bytes": 1,
            "sha256": "b" * 64,
            "root_contained": False,
            "path_redacted": True,
            "regular_file": True,
            "reparse_checked": True,
            "identity": runner.REGULAR_NONREPARSE_IDENTITY,
        }
        return {
            "environment": {
                "cleared": list(runner.UPSTREAM_ENV_CLEARED_KEYS),
                "pythonpath_mode": "materialized_archive_src",
                "pythonno_user_site": True,
                "uv_no_config": True,
                "uv_virtual_env": {
                    "present": False,
                    "relative_path": None,
                    "basename": None,
                    "root_contained": False,
                    "path_redacted": True,
                    "identity": runner.UV_VENV_ABSENT_IDENTITY,
                },
            },
            "agent_com": {
                "module": "agent_com",
                "contained_in_materialized_archive": True,
                "module_file": module,
                "package_source_inventory": {"count": 1, "total_bytes": 1, "sha256": "c" * 64},
            },
            "numpy": {**external, "module": "numpy", "version": "1"},
            "scipy": {**external, "module": "scipy", "version": "1"},
        }

    def _probe_payload(self) -> dict[str, object]:
        return {
            "config_sha256": "a" * 64,
            "port_order": [1, 3, 2, 4],
            "runtime_proof": self._runtime_proof(),
            "cases": [{"metrics": {}, "winner": {}, "port_order": [1, 3, 2, 4]}],
        }

    def test_tokens_and_archive_paths_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            runner.token("not-a-nonce")
        with self.assertRaises(ValueError):
            runner.safe_member("../escape")
        with self.assertRaises(ValueError):
            runner.safe_member("C:/escape")
        with self.assertRaises(ValueError):
            runner.safe_member("a//b")

    def test_upstream_probe_is_real_command_and_parses_cases(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            completed = type("Completed", (), {"returncode": 0, "stdout": json.dumps(self._probe_payload()), "stderr": ""})()
            with patch.object(runner, "bounded", return_value=completed) as bounded:
                result = runner.run_upstream_probe(root, Path("python.exe"), [0.0, 0.001])
            command = bounded.call_args.args[0]
            self.assertEqual(result["runtime"], "executed_clean_archive_external_python_env")
            self.assertEqual(result["cases"][0]["metrics"], {})
            self.assertEqual(result["runtime_proof"]["agent_com"]["module"], "agent_com")
            self.assertIn("python.exe", command[0])

    def test_raw_subprocess_bytes_are_receipted_without_host_decode(self) -> None:
        completed = type("Completed", (), {"returncode": 1, "stdout": b"\x80", "stderr": b"\xff"})()
        receipt = runner.capture_receipt(completed)
        self.assertEqual(receipt["exit"], 1)
        self.assertEqual(receipt["stdout_sha256"], runner.digest(b"\x80"))
        self.assertEqual(receipt["stderr_sha256"], runner.digest(b"\xff"))

    def test_path_redaction_rejects_any_drive_and_parent(self) -> None:
        with self.assertRaises(ValueError):
            runner.assert_report_path_free({"value": "Z:\\Users\\runner\\scratch"})
        with self.assertRaises(ValueError):
            runner.assert_report_path_free({"value": "../outside"})

    def test_upstream_uv_failure_falls_back_to_external_python(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            failed = type("Completed", (), {"returncode": 1, "stdout": b"", "stderr": b"offline dependency failure"})()
            success = type("Completed", (), {"returncode": 0, "stdout": json.dumps(self._probe_payload()).encode(), "stderr": b""})()
            with patch.object(runner, "bounded", side_effect=[failed, success]) as bounded:
                result = runner.run_upstream_probe(root, Path("python.exe"), [0.0, 0.001], uv=Path("uv.exe"))
            self.assertEqual(result["runtime"], "executed_clean_archive_external_python_env")
            self.assertEqual(len(result["attempts"]), 2)
            self.assertEqual(bounded.call_count, 2)

    def test_upstream_probe_rejects_module_escape_proof(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = self._probe_payload()
            payload["runtime_proof"]["agent_com"]["module_file"]["relative_path"] = "outside.py"
            completed = type("Completed", (), {"returncode": 0, "stdout": json.dumps(payload), "stderr": ""})()
            with patch.object(runner, "bounded", return_value=completed):
                result = runner.run_upstream_probe(root, Path("python.exe"), [0.0, 0.001])
            self.assertNotIn("cases", result)
            self.assertIn("artifact invalid", result["blocker"])

    def test_upstream_probe_rejects_environment_proof_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = self._probe_payload()
            payload["runtime_proof"]["environment"]["uv_no_config"] = False
            completed = type("Completed", (), {"returncode": 0, "stdout": json.dumps(payload), "stderr": ""})()
            with patch.object(runner, "bounded", return_value=completed):
                result = runner.run_upstream_probe(root, Path("python.exe"), [0.0, 0.001])
            self.assertNotIn("cases", result)
            self.assertIn("artifact invalid", result["blocker"])

    def test_upstream_environment_clears_host_virtualenv_and_python_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inherited = {
                "VIRTUAL_ENV": str(root / "host-venv"),
                "PYTHONHOME": "host-python-home",
                "PYTHONPATH": "host-python-path",
                "PYTHONUNTRUSTED": "host-python-value",
            }
            with patch.dict(runner.os.environ, inherited, clear=False):
                uv_environment = runner.upstream_environment(root, direct=False)
                direct_environment = runner.upstream_environment(root, direct=True)
            self.assertNotIn("VIRTUAL_ENV", uv_environment)
            self.assertNotIn("PYTHONHOME", uv_environment)
            self.assertNotIn("PYTHONPATH", uv_environment)
            self.assertNotIn("PYTHONUNTRUSTED", uv_environment)
            self.assertEqual(uv_environment["PYTHONNOUSERSITE"], "1")
            self.assertNotIn("VIRTUAL_ENV", direct_environment)
            self.assertNotIn("PYTHONHOME", direct_environment)
            self.assertNotIn("PYTHONUNTRUSTED", direct_environment)
            self.assertEqual(direct_environment["PYTHONPATH"], str((root / "src").resolve()))

    def test_archive_uv_virtual_env_receipt_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".venv").mkdir()
            receipt = runner.uv_virtual_env_receipt(root, {"VIRTUAL_ENV": str(root / ".venv")})
            self.assertEqual(
                receipt,
                {
                    "present": True,
                    "relative_path": ".venv",
                    "basename": ".venv",
                    "root_contained": True,
                    "path_redacted": True,
                    "identity": runner.UV_PROJECT_VENV_IDENTITY,
                },
            )
            runner.validate_uv_virtual_env_receipt(receipt)

    def test_external_uv_virtual_env_receipt_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            external = Path(directory) / "external-venv"
            root.mkdir()
            external.mkdir()
            with self.assertRaises(ValueError):
                runner.uv_virtual_env_receipt(root, {"VIRTUAL_ENV": str(external)})

    def test_symlink_or_reparse_uv_virtual_env_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            venv = root / ".venv"
            venv.mkdir()
            with patch.object(runner, "is_reparse_point", return_value=True):
                with self.assertRaises(ValueError):
                    runner.uv_virtual_env_receipt(root, {"VIRTUAL_ENV": str(venv)})

    def test_uv_virtual_env_receipt_is_path_free(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".venv").mkdir()
            receipt = runner.uv_virtual_env_receipt(root, {"VIRTUAL_ENV": str(root / ".venv")})
            runner.assert_report_path_free(receipt)
            self.assertNotIn(str(root), json.dumps(receipt))

    def test_runtime_proof_binds_independent_source_identity(self) -> None:
        proof = self._runtime_proof()
        expected = {
            "module_file": deepcopy(proof["agent_com"]["module_file"]),
            "package_source_inventory": deepcopy(proof["agent_com"]["package_source_inventory"]),
        }
        runner.validate_runtime_proof(proof, expected)
        expected["module_file"]["sha256"] = "d" * 64
        with self.assertRaises(ValueError):
            runner.validate_runtime_proof(proof, expected)

    def test_build_environment_clears_inherited_flags(self) -> None:
        inherited = {key: "host-controlled" for key in runner.BUILD_ENV_CLEARED_KEYS}
        inherited.update({"CARGO_TARGET_CUSTOM_RUSTFLAGS": "host-controlled", "CARGO_TARGET_CUSTOM_RUSTDOCFLAGS": "host-controlled", "CARGO_TARGET_CUSTOM_LINKER": "host-controlled"})
        with patch.dict(runner.os.environ, inherited, clear=False):
            environment = runner.runtime_environment(Path("rustc.exe"), Path("target"))
        self.assertTrue(all(key not in environment for key in runner.BUILD_ENV_CLEARED_KEYS))
        self.assertNotIn("CARGO_TARGET_CUSTOM_RUSTFLAGS", environment)
        self.assertNotIn("CARGO_TARGET_CUSTOM_RUSTDOCFLAGS", environment)
        self.assertNotIn("CARGO_TARGET_CUSTOM_LINKER", environment)
        self.assertEqual(environment["CARGO_INCREMENTAL"], "0")
        self.assertEqual(environment["CARGO_NET_OFFLINE"], "true")
        self.assertEqual(environment["RUSTC"], "rustc.exe")

    def test_fresh_scratch_receipt_binds_nonce_and_marker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            nonce = "b" * 64
            receipt = runner.fresh_scratch_root(parent / f"scratch-{nonce}", "a" * 64, nonce)
            self.assertTrue(receipt["nonce_bound"])
            self.assertTrue(receipt["reparse_ancestors_checked"])
            self.assertEqual(receipt["marker"]["bytes"], len(f"sipi-com-workbook-accm-v5\nrun_id={'a' * 64}\nnonce={nonce}\n".encode("ascii")))

    def test_compare_case_does_not_infer_candidate_port_order(self) -> None:
        comparison = runner.compare_case(
            {"metrics": {}, "winner": {}, "port_order": runner.PORT_ORDER},
            {"metrics": {}, "winner": {}, "port_order": None},
        )
        self.assertFalse(comparison["port_order_match"])
        self.assertFalse(comparison["port_order_observed"])
        self.assertEqual(comparison["port_order_status"], "not_observed")

    def test_run_one_requires_fresh_caller_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "existing"
            root.mkdir()
            with self.assertRaises(FileExistsError):
                runner.run_one(Path(directory), Path(directory), root, Path("cargo.exe"), Path("python.exe"), "a" * 64, "b" * 64)

    def test_run_one_rejects_equal_run_id_and_nonce(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "fresh"
            with self.assertRaises(ValueError):
                runner.run_one(Path(directory), Path(directory), root, Path("cargo.exe"), Path("python.exe"), "a" * 64, "a" * 64)


if __name__ == "__main__":
    unittest.main()
