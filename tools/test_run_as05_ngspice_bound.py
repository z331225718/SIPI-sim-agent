"""Preparation checks for the clean-archive AS-05 ngspice runner."""

from __future__ import annotations

import tempfile
import unittest
from unittest import mock
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_as05_ngspice_bound as runner


class RunAs05NgspiceBoundTests(unittest.TestCase):
    def test_fixture_generation_is_ascii_and_stable(self) -> None:
        with tempfile.TemporaryDirectory(prefix="sipi-as05-prep-test-") as temporary:
            records = runner.fixture_records(Path(temporary))
        self.assertEqual([item["id"] for item in records], [item[0] for item in runner.FIXTURES])
        self.assertEqual({item["generated_by_runner"] for item in records}, {runner.FIXTURE_GENERATOR})
        self.assertTrue(all(item["bytes"] > 0 and len(item["sha256"]) == 64 for item in records))

    def test_runner_contract_does_not_embed_machine_paths(self) -> None:
        source = Path(runner.__file__).read_text(encoding="utf-8")
        self.assertNotIn("C:\\Users\\z3312\\tools\\agent-spice-solvers", source)
        self.assertIn("--candidate-archive-sha256", source)
        self.assertIn("--ngspice-sha256", source)

    def test_external_roots_reject_drive_relative_and_unc(self) -> None:
        self.assertFalse(runner.safe_absolute(Path("C:relative\\upstream")))
        self.assertFalse(runner.safe_absolute(Path("//server/share/upstream")))

    def test_fixtures_drive_nontrivial_output_node(self) -> None:
        self.assertTrue(all("R1 IN OUT" in item[2] and "C1 OUT 0" in item[2] for item in runner.FIXTURES))

    def test_solver_post_identity_version_drift_is_detected(self) -> None:
        pre = runner.tool_identity(Path(sys.executable), "python", ("--version",))
        post = dict(pre)
        post["version_output_sha256"] = "0" * 64
        self.assertFalse(runner.identity_equal(pre, post))

    def test_dirty_runtime_archive_custody_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="as05-runner-custody-") as temporary:
            root = Path(temporary)
            runtime = root / "runtime.py"
            archive = root / "archive.py"
            runtime.write_bytes(b"runtime")
            archive.write_bytes(b"archive")
            self.assertFalse(runner.runner_custody(runtime, archive, runner.sha(b"runtime")))

    def test_toolchain_preidentity_sampling_order(self) -> None:
        calls = []
        def fake_identity(path, role, version_args):
            calls.append(role)
            return {"role": role}
        with mock.patch.object(runner, "tool_identity", side_effect=fake_identity):
            runner.toolchain_identities(Path("git"), Path("cargo"), Path("rustc"), Path("python"))
        self.assertEqual(calls, ["git", "cargo", "rustc", "python"])

    def test_report_sha_accepts_real_path_and_is_bounded(self) -> None:
        with tempfile.TemporaryDirectory(prefix="as05-report-sha-") as temporary:
            path = Path(temporary) / "report.json"
            path.write_bytes(b"{}\n")
            self.assertEqual(runner.report_sha(path), runner.sha(b"{}\n"))


if __name__ == "__main__":
    unittest.main()
