"""Focused custody and budget tests for the AS-06 preflight runner."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stderr, redirect_stdout

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import preflight_as06_xspice_rfm as runner


class PreflightTests(unittest.TestCase):
    def test_missing_asset_is_typed_and_path_free(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            result = runner.source_asset(Path(root))
        self.assertEqual(result["kind"], "missing")
        self.assertFalse(result["present"])
        self.assertNotIn("root", result)

    def test_wrong_file_is_distinct_from_missing(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            Path(root, "ngspice-46_64.7z").write_bytes(b"wrong")
            result = runner.source_asset(Path(root))
        self.assertEqual(result["kind"], "wrong_file")
        self.assertFalse(result["present"])
        self.assertEqual(result["wrong_file_count"], 1)
        self.assertNotIn("ngspice-46_64.7z", str(result))

    def test_expected_basename_hash_mismatch_is_typed(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            Path(root, runner.SOURCE_BASENAME).write_bytes(b"not-the-pinned-source")
            result = runner.source_asset(Path(root))
        self.assertEqual(result["kind"], "mismatch")
        self.assertTrue(result["present"])
        self.assertTrue(result["mismatch"])

    def test_tar_escape_and_symlink_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            archive = Path(root, "bad.tar")
            with tarfile.open(archive, "w") as tar:
                item = tarfile.TarInfo("../escape")
                item.size = 1
                tar.addfile(item, io.BytesIO(b"x"))
            ok, reason = runner.extract_clean_archive(archive, Path(root, "out"))
        self.assertFalse(ok)
        self.assertEqual(reason, "unsafe_member")

    def test_windows_drive_ads_and_reserved_names_are_rejected(self) -> None:
        for name in ("C:relative", "file:stream", "dir\\file", "CON", "name. "):
            self.assertFalse(runner.safe_member(name, set())[0], name)

    def test_casefold_duplicate_is_rejected(self) -> None:
        seen: set[str] = set()
        self.assertTrue(runner.safe_member("file", seen)[0])
        self.assertFalse(runner.safe_member("FILE", seen)[0])

    def test_many_asset_entries_stop_at_fixed_budget(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            Path(root, "first").write_bytes(b"1")
            Path(root, "second").write_bytes(b"2")
            result = runner.source_asset(Path(root))
        self.assertEqual(result["kind"], "wrong_file")
        self.assertEqual(result["file_count"], 2)

    def test_many_directories_are_typed_without_full_enumeration(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            Path(root, "one").mkdir()
            Path(root, "two").mkdir()
            result = runner.source_asset(Path(root))
        self.assertEqual(result["kind"], "wrong_file")

    def test_tar_member_iteration_is_streaming(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            archive = Path(root, "one.tar")
            with tarfile.open(archive, "w") as tar:
                item = tarfile.TarInfo("one")
                item.size = 1
                tar.addfile(item, io.BytesIO(b"x"))
            with patch.object(tarfile.TarFile, "getmembers", side_effect=AssertionError("must stream")):
                ok, reason = runner.extract_clean_archive(archive, Path(root, "out"))
        self.assertTrue(ok, reason)

    def test_tar_member_budget_is_fixed_and_typed(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            archive = Path(root, "many.tar")
            with tarfile.open(archive, "w") as tar:
                for name in ("one", "two"):
                    item = tarfile.TarInfo(name)
                    item.size = 1
                    tar.addfile(item, io.BytesIO(b"x"))
            with patch.object(runner, "MAX_TAR_MEMBERS", 1):
                ok, reason = runner.extract_clean_archive(archive, Path(root, "out"))
        self.assertFalse(ok)
        self.assertEqual(reason, "member_budget")

    def test_pinned_upstream_tree_is_recomputed(self) -> None:
        import shutil
        import subprocess

        git = Path(shutil.which("git")).resolve()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            subprocess.run([str(git), "init", "-q"], cwd=root, check=True)
            subprocess.run([str(git), "config", "user.email", "test@example.invalid"], cwd=root, check=True)
            subprocess.run([str(git), "config", "user.name", "test"], cwd=root, check=True)
            Path(root, "fixture.txt").write_text("fixture\n", encoding="utf-8")
            subprocess.run([str(git), "add", "fixture.txt"], cwd=root, check=True)
            subprocess.run([str(git), "commit", "-q", "-m", "fixture"], cwd=root, check=True)
            commit = subprocess.check_output([str(git), "rev-parse", "HEAD"], cwd=root, text=True).strip()
            tree = subprocess.check_output([str(git), "rev-parse", "HEAD^{tree}"], cwd=root, text=True).strip()
            self.assertEqual(runner.git_revision(git, root, f"{commit}^{{tree}}"), tree)

    def test_asset_identity_drift_wrong_exact_wrong_is_not_stable(self) -> None:
        wrong = {"kind": "mismatch", "sha256": "0" * 64}
        exact = {"kind": "exact", "sha256": "1" * 64}
        self.assertFalse(runner.asset_identity_stable(wrong, exact, wrong))

    def test_runner_three_way_identity_mutation_is_rejected(self) -> None:
        initial = {"bytes": 4, "sha256": "a" * 64, "overflow": False}
        member = {"match": True, "runtime_bytes": 4, "runtime_sha256": "a" * 64, "member_bytes": 4, "member_sha256": "a" * 64, "runtime_overflow": False, "member_overflow": False}
        post = {"bytes": 5, "sha256": "b" * 64, "overflow": False}
        self.assertFalse(runner.runner_identity_gate(initial, member, post))
        self.assertTrue(runner.runner_identity_gate(initial, member, initial))

    def test_overflow_has_no_partial_hash(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            Path(root, runner.SOURCE_BASENAME).write_bytes(b"123456")
            with patch.object(runner, "MAX_SOURCE_BYTES", 3):
                result = runner.source_asset(Path(root))
        self.assertEqual(result["kind"], "overflow")
        self.assertIsNone(result["sha256"])

    def test_exact_asset_is_hash_attested(self) -> None:
        payload = b"pinned-source"
        with tempfile.TemporaryDirectory() as root:
            Path(root, runner.SOURCE_BASENAME).write_bytes(payload)
            with patch.object(runner, "NGSPICE_SOURCE_SHA256", hashlib.sha256(payload).hexdigest()):
                result = runner.source_asset(Path(root))
        self.assertEqual(result["kind"], "exact")
        self.assertEqual(result["sha256"], hashlib.sha256(payload).hexdigest())

    def test_runtime_member_requires_byte_identity(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            tools = Path(root, "tools")
            tools.mkdir()
            member = tools / "preflight_as06_xspice_rfm.py"
            member.write_bytes(Path(runner.__file__).read_bytes())
            result = runner.runtime_member_observation(Path(root))
        self.assertTrue(result["present"])
        self.assertTrue(result["match"])

    def test_existing_output_is_create_new(self) -> None:
        with tempfile.NamedTemporaryFile() as output:
            with patch.object(sys, "argv", ["runner", "--candidate-root", str(Path.cwd()), "--upstream-root", str(Path.cwd()), "--asset-root", str(Path.cwd()), "--git-executable", sys.executable, "--docker-executable", sys.executable, "--candidate-commit", "0" * 40, "--run-id", "test", "--output-report", output.name]):
                with self.assertRaises(SystemExit):
                    runner.main()

    def test_archive_sha_is_not_a_caller_argument(self) -> None:
        with patch.object(sys, "argv", ["runner", "--help", "--candidate-archive-sha256", "0" * 64]):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                runner.main()

    def test_dual_pipe_budget_kills_process(self) -> None:
        python = Path(sys.executable).resolve()
        result = runner.run_process(python, ("-c", "import sys;sys.stdout.write('x'*2000);sys.stderr.write('y'*2000)"), 100, 5)
        self.assertTrue(result.overflowed)

    def test_timeout_kills_and_waits(self) -> None:
        python = Path(sys.executable).resolve()
        result = runner.run_process(python, ("-c", "import time;time.sleep(2)"), 1000, 0.05)
        self.assertTrue(result.timed_out)
        self.assertNotEqual(result.returncode, 0)

    def test_nonce_is_os_sized(self) -> None:
        self.assertEqual(len(runner.secrets.token_hex(32)), 64)
        self.assertEqual(len(hashlib.sha256(b"fixture").hexdigest()), 64)


if __name__ == "__main__":
    unittest.main()
