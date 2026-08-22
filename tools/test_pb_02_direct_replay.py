import copy
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import aggregate_pb_02_direct_replay as aggregate  # noqa: E402
import run_pb_02_direct_replay as runner  # noqa: E402


class Pb02ReplayToolTests(unittest.TestCase):
    def test_meta_normalization_removes_machine_local_input_path(self):
        value = {
            "input_file": "C:\\temporary\\candidate\\input.json",
            "nested": {"input_file": "C:\\temporary\\upstream\\input.json"},
        }
        normalized = runner._normalize_meta(value)
        self.assertEqual(normalized["input_file"], "<input-file>")
        self.assertEqual(normalized["nested"]["input_file"], "<input-file>")

    def test_npz_summary_hashes_members_not_container(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "arrays.npz"
            with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("z.npy", b"z-array")
                archive.writestr("a.npy", b"a-array")
            summary = runner._npz_summary(path)
            self.assertEqual(list(summary["member_sha256"]), ["a.npy", "z.npy"])
            self.assertEqual(summary["logical_sha256"], runner._sha256(runner._canonical(summary["member_sha256"])))

    def test_aggregate_rejects_identity_drift(self):
        base = {
            "schema": "sipi.pb-02-direct-replay.v1",
            "status": "passed",
            "source_mode": "git_archive_at_immutable_commit",
            "run_id": "one",
            "candidate": {"commit": "c", "tree": "t", "inventory": {"sha256": "i"}},
            "upstream": {"commit": "u", "tree": "ut", "inventory": {"sha256": "ui"}},
            "fixture": {"sha256": "f"},
            "replay": {
                "parity": {"candidate_array_members_equal_oracle": True},
                "candidate": {"artifacts": {"arrays": {"member_sha256": {"a.npy": "a"}, "logical_sha256": "la"}}},
                "oracle": {"artifacts": {"arrays": {"member_sha256": {"a.npy": "a"}}}},
            },
        }
        second = copy.deepcopy(base)
        second["run_id"] = "two"
        second["candidate"]["tree"] = "drift"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first_path = root / "one.json"
            second_path = root / "two.json"
            output = root / "aggregate.json"
            first_path.write_text(json.dumps(base), encoding="utf-8")
            second_path.write_text(json.dumps(second), encoding="utf-8")
            result = aggregate.aggregate(first_path, second_path, output)
            self.assertEqual(result["status"], "blocked")
            self.assertIn("candidate identity drift between replays", result["blockers"])


if __name__ == "__main__":
    unittest.main()
