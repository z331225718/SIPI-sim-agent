import copy
import hashlib
import json
import os
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


VALID_TOOLCHAIN = {
    "cargo": {
        "role": "cargo",
        "executable": "cargo.exe",
        "path_redacted": True,
        "file_sha256": "a" * 64,
        "version_exit_code": 0,
        "version_output_sha256": "b" * 64,
    },
    "rustc": {
        "role": "rustc",
        "executable": "rustc.exe",
        "path_redacted": True,
        "file_sha256": "c" * 64,
        "version_exit_code": 0,
        "version_output_sha256": "d" * 64,
    },
    "uv": {
        "role": "uv",
        "executable": "uv.exe",
        "path_redacted": True,
        "file_sha256": "e" * 64,
        "version_exit_code": 0,
        "version_output_sha256": "f" * 64,
    },
    "timeout_seconds": 1,
}


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
                cargo=r"C:\Users\runner\.cargo\bin\cargo.exe",
                uv=r"C:\Users\runner\uv\uv.exe",
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
                mock.patch.object(
                    runner,
                    "_runtime_toolchain_identity",
                    return_value=(
                        {
                            "cargo": {"role": "cargo", "executable": "cargo.exe", "path_redacted": True},
                            "rustc": {"role": "rustc", "executable": "rustc.exe", "path_redacted": True},
                            "uv": {"role": "uv", "executable": "uv.exe", "path_redacted": True},
                            "timeout_seconds": 1,
                        },
                        {"cargo": Path(args.cargo), "rustc": Path("rustc.exe"), "uv": Path(args.uv)},
                    ),
                ),
                mock.patch.object(runner, "_commit_tree", side_effect=[("candidate", "candidate-tree"), (runner.EXPECTED_UPSTREAM_COMMIT, runner.EXPECTED_UPSTREAM_TREE)]),
                mock.patch.object(runner, "_materialize_git_archive", side_effect=materialize),
                mock.patch.object(runner, "_run_one", return_value=replay),
            ):
                result = runner.run(args)

            committed = b"committed archive fixture"
            self.assertEqual(result["fixture"]["sha256"], runner._sha256(committed))
            self.assertEqual(result["fixture"]["bytes"], len(committed))
            self.assertEqual(result["toolchain"]["cargo"]["role"], "cargo")
            self.assertEqual(result["toolchain"]["cargo"]["executable"], "cargo.exe")
            self.assertTrue(result["toolchain"]["cargo"]["path_redacted"])
            self.assertEqual(result["toolchain"]["uv"]["role"], "uv")
            self.assertEqual(result["toolchain"]["uv"]["executable"], "uv.exe")
            self.assertTrue(result["toolchain"]["uv"]["path_redacted"])
            self.assertRegex(result["fresh_run_nonce"], r"^[0-9a-f]{64}$")
            report_text = report_path.read_text(encoding="utf-8")
            self.assertNotIn("C:\\Users\\", report_text)
            self.assertNotIn("/Users/", report_text)
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

    def test_runtime_identity_hashes_file_and_version_without_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "cargo.exe"
            executable.write_bytes(b"fake cargo")
            completed = runner.subprocess.CompletedProcess(
                args=[str(executable), "-Vv"], returncode=0, stdout=b"cargo 1.0\n", stderr=b""
            )
            with mock.patch.object(runner.subprocess, "run", return_value=completed):
                identity = runner._runtime_tool_identity(str(executable), "cargo", ("-Vv",))
            self.assertEqual(identity["executable"], "cargo.exe")
            self.assertEqual(identity["file_sha256"], hashlib.sha256(b"fake cargo").hexdigest())
            self.assertEqual(identity["version_output_sha256"], runner._sha256(b"cargo 1.0\n\x00"))
            self.assertNotIn(str(executable), json.dumps(identity))

    def test_default_tool_resolution_fails_closed(self):
        with mock.patch.object(runner.shutil, "which", return_value=None):
            with self.assertRaises(RuntimeError):
                runner._resolve_executable("cargo", "cargo")

    def test_path_command_resolves_to_actual_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "cargo.exe"
            executable.write_bytes(b"fake cargo")
            with mock.patch.object(runner.shutil, "which", return_value=str(executable)):
                self.assertEqual(runner._resolve_executable("cargo", "cargo"), executable.resolve())

    def test_nonzero_version_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "cargo.exe"
            executable.write_bytes(b"fake cargo")
            completed = runner.subprocess.CompletedProcess(
                args=[str(executable), "-Vv"], returncode=1, stdout=b"", stderr=b"error"
            )
            with mock.patch.object(runner.subprocess, "run", return_value=completed):
                with self.assertRaises(RuntimeError):
                    runner._runtime_tool_identity(str(executable), "cargo", ("-Vv",))

    def test_missing_file_digest_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "cargo.exe"
            executable.write_bytes(b"fake cargo")
            with mock.patch.object(runner, "_file_digest", return_value=None):
                with self.assertRaises(RuntimeError):
                    runner._runtime_tool_identity(str(executable), "cargo", ("-Vv",))

    def test_missing_version_digest_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "cargo.exe"
            executable.write_bytes(b"fake cargo")
            completed = runner.subprocess.CompletedProcess(
                args=[str(executable), "-Vv"], returncode=0, stdout=b"cargo 1.0\n", stderr=b""
            )
            with (
                mock.patch.object(runner, "_file_digest", return_value="a" * 64),
                mock.patch.object(runner, "_sha256", return_value=None),
                mock.patch.object(runner.subprocess, "run", return_value=completed),
            ):
                with self.assertRaises(RuntimeError):
                    runner._runtime_tool_identity(str(executable), "cargo", ("-Vv",))

    def test_build_and_oracle_use_same_resolved_rustc_without_wrappers(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rustc = root / "rustc.exe"
            calls = []

            def fake_run(command, *, cwd, env, timeout):
                calls.append((command, cwd, env, timeout))
                return runner.subprocess.CompletedProcess(command, 1 if len(calls) == 1 else 0, b"", b"")

            with (
                mock.patch.dict(os.environ, {"RUSTC_WRAPPER": "wrapper", "RUSTC_WORKSPACE_WRAPPER": "workspace", "CARGO_BUILD_RUSTC_WRAPPER": "cargo-wrapper", "CARGO_BUILD_RUSTC_WORKSPACE_WRAPPER": "cargo-workspace", "RUSTFLAGS": "-C target-cpu=native", "CARGO_ENCODED_RUSTFLAGS": "bad" , "PATH": "" + os.pathsep + str(root / "existing") + os.pathsep}, clear=False),
                mock.patch.object(runner, "_run", side_effect=fake_run),
            ):
                runner._run_one(
                    run_root=root / "run",
                    candidate_root=root / "candidate",
                    upstream_root=root / "upstream",
                    fixture=root / "fixture.json",
                    cargo=root / "cargo.exe",
                    rustc=rustc,
                    uv=root / "uv.exe",
                    timeout=1,
                )

                self.assertEqual(len(calls), 2)
            for _command, _cwd, env, _timeout in calls:
                self.assertEqual(env["RUSTC"], str(rustc.resolve()))
                self.assertEqual(env["CARGO"], str((root / "cargo.exe").resolve()))
                self.assertEqual(env["CARGO_BUILD_RUSTC"], str(rustc.resolve()))
                self.assertEqual(env["CARGO_NET_OFFLINE"], "true")
                self.assertNotIn("RUSTC_WRAPPER", env)
                self.assertNotIn("RUSTC_WORKSPACE_WRAPPER", env)
                self.assertNotIn("CARGO_BUILD_RUSTC_WRAPPER", env)
                self.assertNotIn("CARGO_BUILD_RUSTC_WORKSPACE_WRAPPER", env)
                self.assertNotIn("RUSTFLAGS", env)
                self.assertNotIn("CARGO_ENCODED_RUSTFLAGS", env)
                self.assertNotIn("", env["PATH"].split(os.pathsep))

    def test_successful_build_runtime_and_oracle_share_exact_rust_env_and_offline_uv(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rustc = root / "rustc.exe"
            cargo = root / "cargo.exe"
            uv = root / "uv.exe"
            binary = root / "pseudo-sipi-pybert-direct.exe"
            binary.write_bytes(b"pseudo-binary")
            calls = []

            def fake_run(command, *, cwd, env, timeout):
                calls.append((command, cwd, env, timeout))
                return runner.subprocess.CompletedProcess(command, 0, b"", b"")

            with mock.patch.object(runner, "_binary_path", return_value=binary), mock.patch.object(runner, "_run", side_effect=fake_run):
                runner._run_one(
                    run_root=root / "run",
                    candidate_root=root / "candidate",
                    upstream_root=root / "upstream",
                    fixture=root / "fixture.json",
                    cargo=cargo,
                    rustc=rustc,
                    uv=uv,
                    timeout=1,
                )

            self.assertEqual(len(calls), 3)
            expected_cargo = str(cargo.resolve())
            expected_rustc = str(rustc.resolve())
            for _command, _cwd, env, _timeout in calls:
                self.assertEqual(env["CARGO"], expected_cargo)
                self.assertEqual(env["RUSTC"], expected_rustc)
                self.assertEqual(env["CARGO_BUILD_RUSTC"], expected_rustc)
                for name in ("RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER", "CARGO_BUILD_RUSTC_WRAPPER", "CARGO_BUILD_RUSTC_WORKSPACE_WRAPPER", "RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS"):
                    self.assertNotIn(name, env)
                self.assertNotIn(os.pathsep + os.pathsep, env["PATH"])
            self.assertIn("--offline", calls[2][0])
            self.assertIn("--offline", calls[0][0])

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
            "fresh_run_nonce": "1" * 64,
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

    def test_aggregate_rejects_same_resolved_path(self):
        base = {
            "schema": "sipi.pb-02-direct-replay.v1",
            "status": "passed",
            "source_mode": "git_archive_at_immutable_commit",
            "run_id": "one",
            "fresh_run_nonce": "1" * 64,
            "candidate": {"commit": "c", "tree": "t", "inventory": {"sha256": "i"}},
            "upstream": {"commit": "u", "tree": "ut", "inventory": {"sha256": "ui"}},
            "fixture": {"sha256": "f"},
            "replay": {"parity": {"candidate_array_members_equal_oracle": True}},
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "one.json"
            output = Path(temporary) / "aggregate.json"
            path.write_text(json.dumps(base), encoding="utf-8")
            result = aggregate.aggregate(path, path, output)
            self.assertEqual(result["status"], "blocked")
            self.assertIn("report paths must be distinct", result["blockers"])

    def test_aggregate_rejects_same_nonce_and_report_digest(self):
        base = {
            "schema": "sipi.pb-02-direct-replay.v1",
            "status": "passed",
            "source_mode": "git_archive_at_immutable_commit",
            "run_id": "one",
            "fresh_run_nonce": "1" * 64,
            "candidate": {"commit": "c", "tree": "t", "inventory": {"sha256": "i"}},
            "upstream": {"commit": "u", "tree": "ut", "inventory": {"sha256": "ui"}},
            "fixture": {"sha256": "f"},
            "replay": {"parity": {"candidate_array_members_equal_oracle": True}},
        }
        second = copy.deepcopy(base)
        with tempfile.TemporaryDirectory() as temporary:
            first_path = Path(temporary) / "one.json"
            second_path = Path(temporary) / "two.json"
            output = Path(temporary) / "aggregate.json"
            first_path.write_text(json.dumps(base), encoding="utf-8")
            second_path.write_text(json.dumps(second), encoding="utf-8")
            result = aggregate.aggregate(first_path, second_path, output)
            self.assertEqual(result["status"], "blocked")
            self.assertIn("fresh run nonces must be distinct", result["blockers"])
            self.assertIn("complete report digests must be distinct", result["blockers"])

    def test_aggregate_report_ids_never_leak_absolute_paths(self):
        base = {
            "schema": "sipi.pb-02-direct-replay.v1",
            "status": "passed",
            "source_mode": "git_archive_at_immutable_commit",
            "run_id": "one",
            "fresh_run_nonce": "1" * 64,
            "candidate": {"commit": "c", "tree": "t", "inventory": {"sha256": "i"}},
            "upstream": {"commit": "u", "tree": "ut", "inventory": {"sha256": "ui"}},
            "fixture": {"sha256": "f"},
            "toolchain": copy.deepcopy(VALID_TOOLCHAIN),
            "replay": {"parity": {"candidate_array_members_equal_oracle": True}},
        }
        second = copy.deepcopy(base)
        second["run_id"] = "two"
        second["fresh_run_nonce"] = "2" * 64
        with tempfile.TemporaryDirectory() as temporary:
            first_path = Path(temporary) / "one.json"
            second_path = Path(temporary) / "two.json"
            output = Path(temporary) / "aggregate.json"
            first_path.write_text(json.dumps(base), encoding="utf-8")
            second_path.write_text(json.dumps(second), encoding="utf-8")
            result = aggregate.aggregate(first_path, second_path, output)
            self.assertTrue(all(not Path(item["path"]).is_absolute() for item in result["reports"]))
            self.assertEqual([item["path"] for item in result["reports"]], ["one.json", "two.json"])
            self.assertEqual(result["toolchain"], VALID_TOOLCHAIN)

    def test_aggregate_rejects_toolchain_identity_drift(self):
        base = {
            "schema": "sipi.pb-02-direct-replay.v1",
            "status": "passed",
            "source_mode": "git_archive_at_immutable_commit",
            "run_id": "one",
            "fresh_run_nonce": "1" * 64,
            "candidate": {"commit": "c", "tree": "t", "inventory": {"sha256": "i"}},
            "upstream": {"commit": "u", "tree": "ut", "inventory": {"sha256": "ui"}},
            "fixture": {"sha256": "f"},
            "toolchain": copy.deepcopy(VALID_TOOLCHAIN),
            "replay": {"parity": {"candidate_array_members_equal_oracle": True}},
        }
        second = copy.deepcopy(base)
        second["run_id"] = "two"
        second["fresh_run_nonce"] = "2" * 64
        second["toolchain"]["cargo"]["file_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first_path = root / "one.json"
            second_path = root / "two.json"
            output = root / "aggregate.json"
            first_path.write_text(json.dumps(base), encoding="utf-8")
            second_path.write_text(json.dumps(second), encoding="utf-8")
            result = aggregate.aggregate(first_path, second_path, output)
            self.assertIn("toolchain identity drift between replays", result["blockers"])

    def test_aggregate_rejects_null_or_nonzero_toolchain_identity(self):
        base = {
            "schema": "sipi.pb-02-direct-replay.v1",
            "status": "passed",
            "source_mode": "git_archive_at_immutable_commit",
            "run_id": "one",
            "fresh_run_nonce": "1" * 64,
            "candidate": {"commit": "c", "tree": "t", "inventory": {"sha256": "i"}},
            "upstream": {"commit": "u", "tree": "ut", "inventory": {"sha256": "ui"}},
            "fixture": {"sha256": "f"},
            "toolchain": copy.deepcopy(VALID_TOOLCHAIN),
            "replay": {"parity": {"candidate_array_members_equal_oracle": True}},
        }
        for mutation, expected in (
            (lambda value: value["cargo"].__setitem__("file_sha256", None), "first cargo file_sha256 is missing or malformed"),
            (lambda value: value["uv"].__setitem__("version_exit_code", 1), "first uv version command did not pass"),
            (lambda value: value["rustc"].__setitem__("extra", {"path": "C:\\Users\\leak"}), "first rustc identity keys are not exact"),
        ):
            with self.subTest(expected=expected):
                mutated = copy.deepcopy(base)
                mutation(mutated["toolchain"])
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    first_path = root / "one.json"
                    second_path = root / "two.json"
                    output = root / "aggregate.json"
                    first_path.write_text(json.dumps(mutated), encoding="utf-8")
                    second = copy.deepcopy(base)
                    second["run_id"] = "two"
                    second["fresh_run_nonce"] = "2" * 64
                    second_path.write_text(json.dumps(second), encoding="utf-8")
                    result = aggregate.aggregate(first_path, second_path, output)
                    self.assertIn(expected, result["blockers"])


if __name__ == "__main__":
    unittest.main()
