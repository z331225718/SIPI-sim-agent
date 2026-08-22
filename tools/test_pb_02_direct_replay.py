import copy
import json
import struct
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import aggregate_pb_02_direct_replay as aggregate  # noqa: E402
import run_pb_02_direct_replay as runner  # noqa: E402


class Pb02ReplayToolTests(unittest.TestCase):
    def test_safe_fixture_relative_rejects_absolute_anchor_drive_unc_and_parent(self):
        unsafe = [
            Path("/tmp/fixture.json"),
            Path("../fixture.json"),
            Path("nested/../../fixture.json"),
            "C:\\fixture.json",
            "C:fixture.json",
            "\\\\server\\share\\fixture.json",
            "\\fixture.json",
        ]
        for value in unsafe:
            with self.subTest(value=value):
                with self.assertRaises(RuntimeError):
                    runner._safe_fixture_relative(value)

    def test_archived_fixture_hash_ignores_dirty_worktree_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "candidate"
            relative = runner.FIXTURE_RELATIVE
            archived = root / relative
            archived.parent.mkdir(parents=True)
            archived.write_bytes(b"committed fixture")
            dirty_worktree = Path(temporary) / "worktree" / relative
            dirty_worktree.parent.mkdir(parents=True)
            dirty_worktree.write_bytes(b"dirty fixture")
            _, payload = runner._read_archived_fixture(root, relative)
            self.assertEqual(payload, b"committed fixture")
            self.assertNotEqual(runner._sha256(payload), runner._sha256(dirty_worktree.read_bytes()))

    def test_run_fixture_hash_comes_from_materialized_commit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate_repo = root / "candidate-repo"
            upstream_repo = root / "upstream-repo"
            fixture_relative = runner.FIXTURE_RELATIVE
            worktree_fixture = candidate_repo / fixture_relative
            worktree_fixture.parent.mkdir(parents=True)
            worktree_fixture.write_bytes(b"dirty worktree fixture")
            report_path = root / "report.json"
            args = SimpleNamespace(
                candidate_repo=candidate_repo,
                upstream_repo=upstream_repo,
                candidate_commit="candidate-commit",
                upstream_commit=runner.EXPECTED_UPSTREAM_COMMIT,
                fixture=fixture_relative,
                run_id="fixture-origin-test",
                report=report_path,
                work_root=root / "runs",
                cargo="cargo",
                uv="uv",
                timeout_seconds=1,
                keep_work=True,
            )

            def materialize(repo, _commit, destination):
                destination.mkdir(parents=True)
                if repo == candidate_repo:
                    archived_fixture = destination / fixture_relative
                    archived_fixture.parent.mkdir(parents=True)
                    archived_fixture.write_bytes(b"committed archive fixture")
                return {"commit": "commit", "tree": "tree", "archive_sha256": "archive"}

            replay = {
                "parity": {
                    "candidate_exit_zero": True,
                    "oracle_exit_zero": True,
                    "candidate_array_members_equal_oracle": True,
                    "array_member_names": [],
                }
            }
            with (
                mock.patch.object(runner, "_commit_tree", side_effect=[("candidate", "candidate-tree"), (runner.EXPECTED_UPSTREAM_COMMIT, runner.EXPECTED_UPSTREAM_TREE)]),
                mock.patch.object(runner, "_materialize_git_archive", side_effect=materialize),
                mock.patch.object(runner, "_run_one", return_value=replay),
            ):
                result = runner.run(args)

            committed = b"committed archive fixture"
            self.assertEqual(result["fixture"]["sha256"], runner._sha256(committed))
            self.assertEqual(result["fixture"]["bytes"], len(committed))
            oracle_input = args.work_root / args.run_id / "upstream" / "oracle-input.json"
            self.assertEqual(oracle_input.read_bytes(), committed)

    def test_prebuild_inventory_does_not_change_with_generated_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            crate = root / runner.CRATE_RELATIVE
            source = crate / "src" / "lib.rs"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"source")
            info = {"commit": "commit", "tree": "tree", "archive_sha256": "archive"}
            before = runner._source_facts(root, info, [str(runner.CRATE_RELATIVE)])
            generated = crate / "target" / "release" / "generated.pyd"
            generated.parent.mkdir(parents=True)
            generated.write_bytes(b"generated after snapshot")
            self.assertEqual(
                before["inventory"]["entries"],
                [
                    {
                        "path": "crates/sipi-pybert-direct/src/lib.rs",
                        "sha256": runner._sha256(b"source"),
                        "bytes": 6,
                    }
                ],
            )

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
                header = b"{'descr': '<f8', 'fortran_order': False, 'shape': (1,), }"
                header_length = 128 - 10
                padded_header = header + b" " * (header_length - len(header) - 1) + b"\n"
                npy = b"\x93NUMPY\x01\x00" + struct.pack("<H", header_length) + padded_header + b"\x00" * 8
                archive.writestr("z.npy", npy)
                archive.writestr("a.npy", npy)
            summary = runner._npz_summary(path)
            self.assertEqual(list(summary["member_sha256"]), ["a.npy", "z.npy"])
            self.assertEqual(list(summary["logical_members"]), ["a.npy", "z.npy"])
            self.assertEqual(summary["logical_sha256"], runner._sha256(runner._canonical(summary["logical_members"])))

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
                "candidate": {"artifacts": {"arrays": {"logical_members": {"a.npy": {"f64_sha256": "a"}}, "logical_sha256": "la"}}},
                "oracle": {"artifacts": {"arrays": {"logical_members": {"a.npy": {"f64_sha256": "a"}}}}},
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
