from __future__ import annotations

import ast
import hashlib
import json
import shutil
import sys
import tarfile
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import run_as_02_03_numeric_bound_v3 as runner
from tools import run_as_02_03_numeric_bound_v2 as legacy_runner
from tools import aggregate_as_02_03_numeric_bound_v3 as aggregator


class RunnerBootstrapTests(unittest.TestCase):
    def test_candidate_identity_is_explicit_not_self_referential(self):
        source = Path(runner.__file__).read_text(encoding="utf-8")
        self.assertNotIn("CANDIDATE_COMMIT =", source)
        self.assertIn("--candidate-commit", source)
        self.assertIn("candidate commit/tree binding mismatch", source)
        self.assertIn("candidate archive SHA binding mismatch", source)

    def test_wrapper_policy_is_fail_closed(self):
        self.assertTrue(runner.WRAPPER_POLICY["clear_inherited_rustc_wrapper"])
        self.assertTrue(runner.WRAPPER_POLICY["clear_inherited_rustc_workspace_wrapper"])
        self.assertEqual(runner.WRAPPER_POLICY["rustc_wrapper"], "unset")
        self.assertEqual(runner.WRAPPER_POLICY["rustc_workspace_wrapper"], "unset")

    def test_governing_v2_v3_fixture_and_as03_profile_are_identical(self):
        self.assertEqual(runner.FIXTURE, legacy_runner.FIXTURE)
        self.assertEqual(hashlib.sha256(runner.FIXTURE.encode("ascii")).hexdigest(), "4da06c257a0f0108e4391d65f894b6bb0d62a24a8f00f82f0f0734e061f5de70")
        tree = ast.parse(Path(legacy_runner.__file__).read_text(encoding="utf-8"))
        legacy_args = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "args" for target in node.targets) and isinstance(node.value, ast.List):
                values = [item.value for item in node.value.elts if isinstance(item, ast.Constant)]
                if values[:2] == ["--n-poles-real", "1"]:
                    legacy_args = tuple(values)
                    break
        self.assertEqual(legacy_args, runner.AS03_ARGS)
        self.assertEqual(runner.AS02_ARGS, ("--rms-target", "1", "--max-order", "1", "--min-order", "1", "--max-order-step", "1", "--cascade-samples", "8"))
        self.assertEqual(set(runner.profile_for("AS-02", "x")), {"fixture_sha256", "as02_args", "as02_profile"})
        self.assertNotIn("as03_profile", runner.profile_for("AS-02", "x"))
        self.assertEqual(set(runner.profile_for("AS-03", "x")), {"fixture_sha256", "as03_args", "as03_profile"})

    def test_explicit_root_is_create_new_and_external(self):
        parent = Path(tempfile.mkdtemp(prefix="as03-prep-"))
        try:
            root = parent / "fresh"
            materialized = runner._fresh_root(root, "test root")
            self.assertEqual(materialized, root.resolve())
            with self.assertRaises(RuntimeError):
                runner._fresh_root(root, "test root")
        finally:
            shutil.rmtree(parent, ignore_errors=True)

    def test_repo_relative_temp_root_is_rejected(self):
        with self.assertRaises(RuntimeError):
            runner._fresh_root(runner.ROOT / "as03-prep-root-must-not-exist", "test root")

    def test_archive_and_output_custody_are_fail_closed(self):
        source = Path(runner.__file__).read_text(encoding="utf-8")
        self.assertIn("member.issym()", source)
        self.assertIn("member.islnk()", source)
        self.assertIn('report_target.open("x"', source)
        self.assertIn('"--offline"', source)
        self.assertIn("CARGO_BUILD_", source)

    def test_root_inside_upstream_is_rejected(self):
        with self.assertRaises(RuntimeError):
            runner._fresh_root(runner.UPSTREAM_ROOT / "as03-prep-root-must-not-exist", "test root")

    def test_reparse_and_access_errors_fail_closed(self):
        with patch.object(runner.Path, "lstat", side_effect=PermissionError("denied")):
            with self.assertRaises(RuntimeError):
                runner._has_reparse_component(Path("C:/denied"))
        with patch.object(runner, "_has_reparse_component", return_value=True):
            with self.assertRaises(RuntimeError):
                runner._fresh_root(Path(tempfile.gettempdir()) / "as03-reparse-root", "test root")

    def test_tool_identity_drift_and_nonzero_are_blocked(self):
        cargo = Path.home() / ".cargo/bin/cargo.exe"
        pre = {"schema": "sipi.path-free-tool-identity.v1", "role": "cargo", "executable": "cargo.exe", "path_redacted": True, "file_sha256": "1" * 64, "version_sha256": "2" * 64, "exit_code": 0}
        changed = {**pre, "file_sha256": "3" * 64}
        with patch.object(runner, "_tool_snapshot", side_effect=[pre, changed]):
            with self.assertRaises(RuntimeError):
                runner.tool_identity(cargo, "cargo", ("--version",))
        with patch.object(runner.subprocess, "run", return_value=SimpleNamespace(returncode=1, stdout=b"", stderr=b"bad")):
            with self.assertRaises(RuntimeError):
                runner._tool_snapshot(cargo, "cargo", ("--version",))

    def test_git_timeout_and_archive_members_are_blocked(self):
        with tempfile.TemporaryDirectory(prefix="as03-git-timeout-") as directory:
            run_root = Path(directory) / "run"
            run_root.mkdir()
            with patch.object(runner.subprocess, "check_output", side_effect=runner.subprocess.TimeoutExpired("git", 1)):
                with self.assertRaises(RuntimeError):
                    runner.archive(runner.ROOT, "HEAD", run_root / "archive", run_root)
        destination = Path(tempfile.mkdtemp(prefix="as03-members-"))
        try:
            root = destination.resolve()
            regular = tarfile.TarInfo("ok.txt")
            regular.size = 0
            symlink = tarfile.TarInfo("link")
            symlink.type = tarfile.SYMTYPE
            escape = tarfile.TarInfo("../escape")
            duplicate = tarfile.TarInfo("ok.txt")
            for member_set in ([regular, symlink], [regular, escape], [regular, duplicate]):
                with self.assertRaises(RuntimeError):
                    runner._validate_archive_members(destination, root, member_set)
        finally:
            shutil.rmtree(destination, ignore_errors=True)

    def test_timeout_stale_report_and_environment_are_fail_closed(self):
        with patch.object(runner, "RUN_TIMEOUT_SECONDS", 0.01):
            result = runner.run([sys.executable, "-c", "import time; time.sleep(1)"], Path.cwd(), dict(runner.os.environ))
            self.assertEqual(result["returncode"], 124)
        with tempfile.TemporaryDirectory(prefix="as03-stale-") as directory:
            report = Path(directory) / "report.json"
            report.write_text("stale", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "create-new"):
                runner.execute("AS-03", run_id="stale", report_path=report, run_root_path=Path(directory) / "fresh", python=Path("missing-python"), cargo=Path("missing-cargo"), candidate_commit="0" * 40, candidate_tree="0" * 40, candidate_archive_sha256="0" * 64)
        with patch.dict(runner.os.environ, {"RUSTFLAGS": "ambient", "RUSTC_WRAPPER": "ambient", "CARGO_BUILD_RUSTC_WRAPPER": "ambient", "GIT_DIR": "ambient"}, clear=False):
            env = runner._build_env(Path("C:/candidate"), Path("C:/target"), Path("C:/rustc.exe"))
            self.assertEqual(env["CARGO_NET_OFFLINE"], "true")
            self.assertNotIn("RUSTC_WRAPPER", env)
            self.assertNotIn("CARGO_BUILD_RUSTC_WRAPPER", env)
            self.assertNotIn("GIT_DIR", env)

    def test_report_payload_rejects_absolute_paths(self):
        self.assertTrue(runner.has_absolute_payload({"bad": r"C:\outside\report"}))
        self.assertFalse(runner.has_absolute_payload({"good": "docs/report.json"}))

    def test_aggregate_requires_custody_and_create_new_output(self):
        report = {
            "schema": "sipi.agent-spice-as-numeric-bound.v3",
            "workflow": "AS-02",
            "status": "completed_numeric_mismatch_open",
            "parity_claim": False,
            "numeric_parity": False,
            "run_id": "a",
            "fresh_run_nonce": "0" * 64,
            "candidate": {},
            "upstream": {},
            "runner": {},
            "wrapper_policy": {},
            "custody": {},
            "profile": runner.profile_for("AS-03", "x"),
            "fixture": {},
            "fixture_sha256": "x",
            "toolchain": {},
            "metrics": {},
        }
        with tempfile.TemporaryDirectory(prefix="as03-aggregate-", dir=aggregator.ROOT / "docs/baselines") as directory:
            root = Path(directory)
            first = root / "first.json"
            second = root / "second.json"
            output = root / "aggregate.json"
            first.write_text(json.dumps(report), encoding="utf-8")
            report["run_id"] = "b"
            report["fresh_run_nonce"] = "1" * 64
            second.write_text(json.dumps(report), encoding="utf-8")
            result = aggregator.aggregate(first, second, output)
            self.assertIn("custody contract", result["blockers"])
            self.assertIn("governing AS-02 profile contract", result["blockers"])
            with self.assertRaises(FileExistsError):
                aggregator.aggregate(first, second, output)


if __name__ == "__main__":
    unittest.main()
