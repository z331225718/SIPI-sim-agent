import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import run_pb_01_legacy_leaf_replay as replay  # noqa: E402


class Pb01LegacyLeafReplayTests(unittest.TestCase):
    def test_safe_relative_rejects_cross_platform_paths(self):
        for value in ["../fixture.yaml", r"C:\Users\host\fixture.yaml", r"\\server\share\fixture.yaml", "/tmp/fixture.yaml"]:
            with self.subTest(value=value):
                with self.assertRaises(RuntimeError):
                    replay._safe_relative(value)

    def test_compare_accepts_scoped_numeric_leaf(self):
        oracle = {name: {"present": True, "length": 2, "max_abs": 1.0, "values": [0.0, 1.0]} for name in replay.ARRAY_NAMES}
        candidate = copy.deepcopy(oracle)
        candidate["chnl_h"]["values"][1] += 1.0e-8
        result = replay._compare(oracle, candidate)
        self.assertEqual(result["status"], "passed")
        self.assertFalse(result["blockers"])

    def test_compare_rejects_length_drift(self):
        oracle = {name: {"present": True, "length": 2, "max_abs": 1.0, "values": [0.0, 1.0]} for name in replay.ARRAY_NAMES}
        candidate = copy.deepcopy(oracle)
        candidate["dfe_out_h"]["length"] = 1
        candidate["dfe_out_h"]["values"] = [0.0]
        result = replay._compare(oracle, candidate)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("dfe_out_h: length drift", result["blockers"])

    def test_runtime_identity_is_path_free(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "uv.exe"
            executable.write_bytes(b"runtime")
            completed = replay.subprocess.CompletedProcess(
                args=[str(executable), "--version"], returncode=0, stdout=b"uv 1\n", stderr=b""
            )
            with mock.patch.object(replay.subprocess, "run", return_value=completed):
                identity, resolved = replay._runtime_identity(str(executable), "uv", ("--version",))
            self.assertEqual(resolved, executable.resolve())
            self.assertTrue(identity["path_redacted"])
            self.assertNotIn(str(executable), json.dumps(identity))

    def test_artifact_summary_is_relative(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "result.pybert_data").write_bytes(b"pickle")
            summary = replay._artifact(root, "result.pybert_data")
            self.assertTrue(summary["present"])
            self.assertEqual(summary["path"], "result.pybert_data")
            self.assertNotIn(str(root), json.dumps(summary))


if __name__ == "__main__":
    unittest.main()
