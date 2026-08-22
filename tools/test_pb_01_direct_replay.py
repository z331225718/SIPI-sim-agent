import copy
import io
import json
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import aggregate_pb_01_direct_replay as aggregate  # noqa: E402
import run_pb_01_direct_replay as runner  # noqa: E402


class Pb01ReplayPreparationTests(unittest.TestCase):
    def test_safe_relative_rejects_cross_platform_absolute_and_parent_paths(self):
        for value in [
            Path("../config.yaml"),
            Path("/tmp/config.yaml"),
            r"C:\Users\host\config.yaml",
            r"\\server\share\config.yaml",
            r"\config.yaml",
        ]:
            with self.subTest(value=value):
                with self.assertRaises(RuntimeError):
                    runner._safe_relative(value)

    def test_artifact_summary_is_relative_and_opaque(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = root / "result.pybert_data"
            result.write_bytes(b"opaque pickle bytes")
            summary = runner._artifact_summary(root, "result.pybert_data")
            self.assertTrue(summary["present"])
            self.assertEqual(summary["path"], "result.pybert_data")
            self.assertNotIn(str(root), json.dumps(summary))

    def test_runtime_identity_redacts_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "uv.exe"
            executable.write_bytes(b"fake executable")
            completed = runner.subprocess.CompletedProcess(
                args=[str(executable), "--version"], returncode=0, stdout=b"uv 1\n", stderr=b""
            )
            with mock.patch.object(runner.subprocess, "run", return_value=completed):
                identity, resolved = runner._runtime_identity(str(executable), "uv", ("--version",))
            self.assertEqual(resolved, executable.resolve())
            self.assertEqual(identity["executable"], "uv.exe")
            self.assertTrue(identity["path_redacted"])
            self.assertNotIn(str(executable), json.dumps(identity))

    def test_archive_links_are_rejected_before_materialization(self):
        payload = io.BytesIO()
        with tarfile.open(fileobj=payload, mode="w") as archive:
            link = tarfile.TarInfo("escape")
            link.type = tarfile.SYMTYPE
            link.linkname = "C:/outside"
            archive.addfile(link)
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(RuntimeError):
                runner._extract_archive(payload.getvalue(), Path(temporary) / "archive")

    def test_aggregate_never_promotes_open_observations(self):
        base = {
            "schema": "sipi.pb-01-direct-replay.v1",
            "status": "prepared_open",
            "source_mode": "git_archive_at_immutable_commit",
            "run_id": "one",
            "fresh_run_nonce": "1" * 64,
            "stage_1_source_preparation": {
                "candidate": {"commit": "c"},
                "upstream": {"commit": "u"},
                "config": {"sha256": "f"},
            },
            "runtime": {"uv": {"role": "uv"}, "candidate": None},
        }
        second = copy.deepcopy(base)
        second["run_id"] = "two"
        second["fresh_run_nonce"] = "2" * 64
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first_path = root / "one.json"
            second_path = root / "two.json"
            output = root / "aggregate.json"
            first_path.write_text(json.dumps(base), encoding="utf-8")
            second_path.write_text(json.dumps(second), encoding="utf-8")
            result = aggregate.aggregate(first_path, second_path, output)
            self.assertEqual(result["status"], "blocked")
            self.assertTrue(any("numeric comparator" in item for item in result["blockers"]))
            self.assertEqual([item["path"] for item in result["reports"]], ["one.json", "two.json"])


if __name__ == "__main__":
    unittest.main()
