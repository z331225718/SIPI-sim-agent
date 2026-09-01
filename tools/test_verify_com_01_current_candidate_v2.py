"""Prep-stage schema, custody, and coordinated mutation tests for COM-01."""

from __future__ import annotations

import copy
import os
import subprocess
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from aggregate_com_01_current_candidate_v2 import VerificationError as AggregateError, aggregate
from run_com_01_current_candidate_v2 import (
    ENVIRONMENT_SCOPE,
    CANDIDATE_COMMIT,
    CANDIDATE_TREE,
    COM01_ERROR_OBSERVATIONS,
    COM01_BINARY_BASENAME,
    COM01_MATERIALIZED_OBSERVATION,
    COM01_ROUTING_CONTRACT,
    COM01_SCENARIO_CONTRACT,
    COM01_STRUCTURED_OBSERVATIONS,
    COM01_TEXT_OBSERVATION,
    SHARED_HELPER_SCHEMA,
    UPSTREAM_COMMIT,
    UPSTREAM_TREE,
    _atomic_json_create,
    _archive,
    _bounded_file,
    _copy_cargo_binary,
    _execution_copy_receipt,
    _popen_bounded,
    _extract_archive,
    _git_inventory,
    _load_semantic_runner,
    _path_free,
    _safe_file,
    _validate_com01_report,
)

def prepared_report() -> dict:
    def tool(role: str, basename: str) -> dict:
        version_args = ["-flavor", "link", "help"] if role == "linker" else ["--version"]
        return {"role": role, "basename": basename, "file_bytes": 1, "file_sha256": "1" * 64, "version_args": version_args, "version_exit": 0, "version_stdout_sha256": "2" * 64, "version_stderr_sha256": "3" * 64, "path_redacted": True}
    tools = {"cargo": tool("cargo", "cargo.exe"), "rustc": tool("rustc", "rustc.exe"), "python": tool("python", "python.exe"), "uv": tool("uv", "uv.exe"), "linker": tool("linker", "rust-lld.exe"), "cargo_cache": {"scope": "resolved_locked_dependency_sources", "path_redacted": True, "package_count": 1, "file_count": 1, "total_bytes": 1, "sha256": "9" * 64}}
    source = {"module_file": {"relative_path": "src/agent_com/__init__.py", "basename": "__init__.py", "bytes": 1, "sha256": "4" * 64, "root_contained": True, "path_redacted": True}, "package_source_inventory": {"file_count": 1, "total_bytes": 1, "sha256": "5" * 64}}
    runtime = {"runtime": "executed_clean_archive_uv_frozen_offline", "command": "uv run --frozen --offline", "exit": 0, "stdout_bytes": 1, "stdout_sha256": "6" * 64, "stderr_bytes": 0, "stderr_sha256": "7" * 64, "source": copy.deepcopy(source), "environment": {"cleared": ["PYTHONPATH"], "direct_python_fallback": False, "project_venv": "materialized_inside_archive", "pythonno_user_site": True, "uv_no_config": True, "global_uv_cache": "required_path_redacted_environment_local", "uv_frozen": True, "uv_offline": True}, "modules": {name: {"relative_path": "src/agent_com/__init__.py" if name == "agent_com" else f".venv/{name}/__init__.py", "basename": "__init__.py", "bytes": 1, "sha256": "8" * 64} for name in ("agent_com", "numpy", "openpyxl", "scipy", "yaml")}}
    common_materialized = {"consumption_summary": {"status_counts": {"implemented": {"options": 63, "parameters": 133, "total": 196}, "obsolete": {"options": 5, "parameters": 10, "total": 15}, "report_only": {"options": 21, "parameters": 5, "total": 26}, "unimplemented": {"options": 1, "parameters": 0, "total": 1}, "unverified": {"options": 0, "parameters": 0, "total": 0}}, "total": 238}, "materialized": {"option_count": 90, "option_keys_sha256": "db2dcb5e7d9b32ee6d2c55e905fe22d28a744581c8c3a88757754b61cfbd0137", "parameter_count": 148, "parameter_keys_sha256": "0d5ac58e2807c5cda038371fcb4f3b689359a393fe0053c6f9773927227ad870"}, "schema_version": 1, "top_level_keys": ["config", "config_consumption", "execution", "materialized", "materialized_fingerprint", "schema_version", "warnings"], "warnings": []}
    scenarios = []
    empty_sha = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    for scenario_id, (comparison, category, kind) in COM01_SCENARIO_CONTRACT.items():
        if kind == "structured":
            profile, packages, warnings, projection = COM01_STRUCTURED_OBSERVATIONS[scenario_id]
            oracle = candidate = {"options": 90, "package_blocks": packages, "parameters": 148, "profile": profile, "projection_sha256": projection, "top_level_keys": ["config", "options", "package_blocks", "parameters", "profile", "warnings"], "warnings": list(warnings)}
            exit_code, output, fingerprint = 0, "json", None
        elif kind == "text":
            oracle = {"stdout_bytes": COM01_TEXT_OBSERVATION[0][0], "stdout_sha256": COM01_TEXT_OBSERVATION[0][1]}; candidate = {"stdout_bytes": COM01_TEXT_OBSERVATION[1][0], "stdout_sha256": COM01_TEXT_OBSERVATION[1][1]}
            exit_code, output, fingerprint = 0, "text", None
        elif kind == "materialized":
            oracle = {**common_materialized, "projection_sha256": COM01_MATERIALIZED_OBSERVATION[0][0], "materialized_fingerprint": COM01_MATERIALIZED_OBSERVATION[0][1]}; candidate = {**common_materialized, "projection_sha256": COM01_MATERIALIZED_OBSERVATION[1][0], "materialized_fingerprint": COM01_MATERIALIZED_OBSERVATION[1][1]}
            exit_code, output, fingerprint = 0, "materialized_json", True
        else:
            exit_code, category, oracle_error, candidate_error = COM01_ERROR_OBSERVATIONS[scenario_id]
            oracle = {"error_category": category, "stderr_bytes": oracle_error[0], "stderr_sha256": oracle_error[1], "stdout_bytes": 0, "stdout_sha256": empty_sha}; candidate = {"error_category": category, "stderr_bytes": candidate_error[0], "stderr_sha256": candidate_error[1], "stdout_bytes": 0, "stdout_sha256": empty_sha}
            output, fingerprint = "json", None
        fixture_role, output = COM01_ROUTING_CONTRACT[scenario_id]
        scenarios.append({"id": scenario_id, "fixture_role": fixture_role, "output": output, "oracle_exit": exit_code, "candidate_exit": exit_code, "oracle_error_category": category, "candidate_error_category": category, "oracle_summary": oracle, "candidate_summary": candidate, "value_match": True, "fingerprint_match": fingerprint, "difference_keys": [], "comparison": comparison})
    files = ["tools/run_com_01_current_candidate_v2.py", "tools/aggregate_com_01_current_candidate_v2.py", "tools/verify_com_01_current_candidate_v2.py", "tools/test_verify_com_01_current_candidate_v2.py", "tools/run_com_01_direct_oracle_v2.py"]
    harness_source = {"commit": "c" * 40, "tree": "d" * 40, "files": [{"path": path, "bytes": 1, "sha256": "e" * 64} for path in files], "shared_helper_schema": SHARED_HELPER_SCHEMA}
    binary = {"basename": COM01_BINARY_BASENAME, "bytes": 1, "sha256": "a" * 64, "nlink": 1, "path_redacted": True}
    cargo_source = {"basename": COM01_BINARY_BASENAME, "bytes": 1, "sha256": "a" * 64, "nlink": 2, "path_redacted": True}
    build = {"command": "cargo build", "cargo_source_pre": cargo_source, "cargo_source_post": copy.deepcopy(cargo_source), "cargo_source_stable": True, "binary_pre": binary, "binary_post": copy.deepcopy(binary), "binary_stable": True, "copy_matches_source": True, "raw_binary_scope": ENVIRONMENT_SCOPE, "stdout_sha256": "b" * 64, "stderr_sha256": "c" * 64, "log_policy": "stable_event_categories", "environment": {"cleared": ["RUSTFLAGS"], "incremental": "0", "offline": True, "rustc_forced": True, "wrappers_cleared": True, "source_path_remapped": True, "target_is_independent": True, "cargo_home_policy": "host_cargo_home_retained_for_offline_dependency_cache", "native_linker_overrides_cleared": True, "linker_forced": True, "cargo_cache_bound_pre_post": True}}
    return {"schema": "sipi.com-01.current-candidate-replay.v2", "status": "scoped_current_candidate_parity_observed", "work_item": "COM-01", "leaf": "config-validate", "run_id": "d" * 64, "nonce": "e" * 64, "candidate": {"commit": CANDIDATE_COMMIT, "tree": CANDIDATE_TREE, "archive": {"bytes": 1, "sha256": "f" * 64, "command": "git archive", "path_redacted": True}, "source_mode": "git_archive_at_immutable_commit", "inventory": {"file_count": 1, "total_bytes": 1, "sha256": "0" * 64}, "cargo_lock_sha256": "1" * 64, "source_date_epoch": "1", "build": build}, "upstream": {"commit": UPSTREAM_COMMIT, "tree": UPSTREAM_TREE, "archive": {"bytes": 1, "sha256": "2" * 64, "command": "git archive", "path_redacted": True}, "source_mode": "git_archive_at_immutable_commit", "inventory": {"file_count": 1, "total_bytes": 1, "sha256": "3" * 64}, "source": source, "runtime": runtime, "uv_lock": {"bytes": 1, "sha256": "4" * 64}}, "toolchain": {"pre": tools, "post": copy.deepcopy(tools), "stable": True}, "harness": {"runner": files[0], "semantic_runner": "tools/run_com_01_direct_oracle_v2.py", "corpus": "docs/baselines/com-01-direct-port-corpus.v1.json", "scenario_count": 14, "scenario_set_sha256": "5" * 64, "archive_only_inputs": True, "report_policy": "bounded", "timeout_seconds": 30, "source": harness_source, "shared_helper_schema": SHARED_HELPER_SCHEMA}, "fixtures": [{"role": "primary_xlsx", "basename": "fixture.xlsx", "extension": ".xlsx", "bytes": 1, "sha256": "6" * 64, "path_redacted": True}], "outcomes": {"error_code_match": 7, "passed": 7}, "values_aligned": True, "difference_scenario_ids": [], "scenarios": scenarios, "blockers": [], "matched": True, "acceptance": False, "non_claims": ["no_complete_com_parity"]}


class Com01PrepTests(unittest.TestCase):
    def test_reference_graph_is_exact(self):
        _validate_com01_report(prepared_report())

    def test_root_nested_and_exact_type_mutations_fail(self):
        mutations = [
            lambda value: value.update(extra=True),
            lambda value: value["candidate"]["archive"].update(extra=True),
            lambda value: value["toolchain"]["pre"]["cargo"].update(file_bytes=True),
            lambda value: value["scenarios"][0].update(comparison="error_code_match"),
            lambda value: value["scenarios"][7].update(candidate_error_category="profile_error"),
            lambda value: value["scenarios"][0]["candidate_summary"].update(extra=True),
            lambda value: value["harness"]["source"]["files"][0].update(sha256="z" * 64),
            lambda value: value["candidate"]["build"].update(binary_stable=False),
            lambda value: (value["scenarios"][0].update(oracle_exit=3), value["scenarios"][0].update(candidate_exit=3)),
            lambda value: (value["scenarios"][0]["oracle_summary"].update(projection_sha256="0" * 64), value["scenarios"][0]["candidate_summary"].update(projection_sha256="0" * 64)),
            lambda value: value["scenarios"][0].update(value_match=False),
        ]
        for mutate in mutations:
            value = prepared_report()
            mutate(value)
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                _validate_com01_report(value)

    def test_receipt_mutations_hit_target_invariants(self):
        mutations = [
            (lambda build: (build["binary_pre"].update(nlink=True), build["binary_post"].update(nlink=True)), "candidate binary identity drift"),
            (lambda build: (build["cargo_source_pre"].update(nlink=True), build["cargo_source_post"].update(nlink=True)), "candidate Cargo source identity drift"),
            (lambda build: tuple(build[key].update(bytes=-1) for key in ("binary_pre", "binary_post", "cargo_source_pre", "cargo_source_post")), "candidate binary identity drift"),
            (lambda build: (build["cargo_source_pre"].update(basename="forged.exe"), build["cargo_source_post"].update(basename="forged.exe")), "candidate Cargo source identity drift"),
            (lambda build: tuple(build[key].update(basename="forged.exe") for key in ("binary_pre", "binary_post", "cargo_source_pre", "cargo_source_post")), "candidate binary identity drift"),
            (lambda build: tuple(build[key].update(sha256="z" * 64) for key in ("binary_pre", "binary_post", "cargo_source_pre", "cargo_source_post")), "candidate binary identity drift"),
        ]
        for mutate, error in mutations:
            value = prepared_report()
            mutate(value["candidate"]["build"])
            with self.subTest(error=error), self.assertRaisesRegex(ValueError, error):
                _validate_com01_report(value)

    def test_semantic_runner_first_candidate_scenario_uses_archive_cwd(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate_root = root / "candidate"
            upstream_root = root / "upstream"
            candidate_root.mkdir()
            upstream_root.mkdir()
            runner = candidate_root / "semantic_runner.py"
            runner.write_text(
                "def _artifact_summary(*args): return {}\n"
                "def _redact(value, fixture): return value\n"
                "def compare_scenario(scenario, fixture, upstream_root, candidate_binary):\n"
                "    code, stdout, stderr = _run([str(candidate_binary), '-c', 'import os; print(os.getcwd())'])\n"
                "    return {'id': scenario['id'], 'code': code, 'cwd': stdout.strip(), 'stderr': stderr}\n",
                encoding="ascii",
            )
            corpus = candidate_root / "corpus.json"
            corpus.write_text("{}", encoding="ascii")
            module = _load_semantic_runner(
                runner,
                corpus,
                upstream_root,
                candidate_root,
                {},
                30,
            )
            observed = module.compare_scenario(
                {"id": "first"},
                candidate_root / "fixture.xlsx",
                upstream_root,
                Path(sys.executable),
            )
            self.assertEqual(observed["code"], 0)
            self.assertEqual(Path(observed["cwd"]), candidate_root)

    def test_complete_report_rejects_windows_posix_and_unc_host_paths(self):
        _path_free(prepared_report())
        for leaked in (
            r"C:\Users\runner\candidate.exe",
            "/home/runner/candidate",
            r"\\server\share\candidate.exe",
        ):
            value = prepared_report()
            value["non_claims"][0] = leaked
            with self.subTest(leaked=leaked), self.assertRaisesRegex(
                ValueError, "absolute path leaked"
            ):
                _path_free(value)

    def test_msvc_linker_help_argument_is_path_free(self):
        value = prepared_report()
        self.assertEqual(
            value["toolchain"]["pre"]["linker"]["version_args"],
            ["-flavor", "link", "help"],
        )
        _path_free(value)
        value["toolchain"]["pre"]["linker"]["version_args"][-1] = "/?"
        with self.assertRaisesRegex(ValueError, "absolute path leaked"):
            _path_free(value)

    def test_safe_file_rejects_hardlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "a.json"
            original.write_text("{}", encoding="ascii")
            linked = root / "b.json"
            os.link(original, linked)
            with self.assertRaises(RuntimeError):
                _safe_file(root, Path("a.json"))
            with self.assertRaises(RuntimeError):
                _bounded_file(linked)

    def test_cargo_hardlink_is_copied_to_single_link_execution_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "target"
            release = target / "release"
            release.mkdir(parents=True)
            backing = release / "backing.exe"
            backing.write_bytes(b"candidate-binary")
            source = release / "candidate.exe"
            os.link(backing, source)
            copied, source_receipt, copy_receipt = _copy_cargo_binary(source, target, target / "execution")
            self.assertGreaterEqual(source_receipt["nlink"], 2)
            self.assertEqual(copy_receipt["nlink"], 1)
            self.assertEqual(copied.read_bytes(), source.read_bytes())

    def test_execution_copy_rejects_new_hardlink_and_content_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "target"
            release = target / "release"
            release.mkdir(parents=True)
            source = release / "candidate.exe"
            source.write_bytes(b"candidate-binary")
            copied, source_receipt, _ = _copy_cargo_binary(source, target, target / "execution")
            linked = copied.with_name("linked.exe")
            os.link(copied, linked)
            with self.assertRaises(RuntimeError):
                _execution_copy_receipt(copied, source_receipt)
            linked.unlink()
            copied.write_bytes(b"tampered-binary!")
            with self.assertRaises(RuntimeError):
                _execution_copy_receipt(copied, source_receipt)

    def test_cargo_copy_rejects_source_outside_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target"
            target.mkdir()
            outside = root / "outside.exe"
            outside.write_bytes(b"outside")
            with self.assertRaises(RuntimeError):
                _copy_cargo_binary(outside, target, target / "execution")

    def test_cargo_copy_rejects_reparse_backed_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target"
            release = target / "release"
            release.mkdir(parents=True)
            source = release / "candidate.exe"
            source.write_bytes(b"candidate")
            alias = target / "alias"
            if os.name == "nt":
                completed = _popen_bounded(["cmd.exe", "/d", "/c", "mklink", "/J", alias.name, release.name], cwd=target, env=None, timeout=30, max_stdout=1024 * 1024, max_stderr=1024 * 1024)
                if completed.returncode != 0:
                    self.skipTest("platform cannot create a directory junction")
            else:
                try:
                    os.symlink(release, alias, target_is_directory=True)
                except OSError:
                    self.skipTest("platform cannot create a directory symlink")
            try:
                with self.assertRaises(RuntimeError):
                    _copy_cargo_binary(alias / source.name, target, target / "execution")
            finally:
                os.rmdir(alias)

    def test_atomic_publish_is_create_new(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "report.json"
            _atomic_json_create(output, {"ok": True}, output_root=root)
            with self.assertRaises(FileExistsError):
                _atomic_json_create(output, {"ok": False}, output_root=root)
            outside = root.parent / f"outside-{root.name}"
            outside.mkdir()
            try:
                with self.assertRaises(RuntimeError):
                    _atomic_json_create(outside / "escape.json", {}, output_root=root)
            finally:
                outside.rmdir()
            with self.assertRaises(RuntimeError):
                _atomic_json_create(root / "missing" / "report.json", {}, output_root=root)

    def test_atomic_publish_rejects_parent_and_higher_junctions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            real = root / "real"
            nested = real / "nested"
            nested.mkdir(parents=True)
            junction = root / "junction"
            if os.name == "nt":
                completed = _popen_bounded(
                    ["cmd.exe", "/d", "/c", "mklink", "/J", junction.name, real.name],
                    cwd=root,
                    env=None,
                    timeout=30,
                    max_stdout=1024 * 1024,
                    max_stderr=1024 * 1024,
                )
                if completed.returncode != 0:
                    self.skipTest("platform cannot create a directory junction")
            else:
                try:
                    os.symlink(real, junction, target_is_directory=True)
                except OSError:
                    self.skipTest("platform cannot create a directory symlink")
            try:
                with self.assertRaises(RuntimeError):
                    _atomic_json_create(junction / "parent.json", {}, output_root=root)
                with self.assertRaises(RuntimeError):
                    _atomic_json_create(junction / "nested" / "higher.json", {}, output_root=junction / "nested")
            finally:
                os.rmdir(junction)

    def test_subprocess_overflow_kills_and_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(RuntimeError):
            _popen_bounded(
                [sys.executable, "-c", "import sys,time;sys.stdout.buffer.write(b'x'*65536);sys.stdout.flush();time.sleep(30)"],
                cwd=Path(directory),
                env=None,
                timeout=5,
                max_stdout=1024,
                max_stderr=1024,
            )

    def test_subprocess_timeout_kills_and_waits(self):
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(subprocess.TimeoutExpired):
            _popen_bounded(
                [sys.executable, "-c", "import time;time.sleep(30)"],
                cwd=Path(directory),
                env=None,
                timeout=1,
                max_stdout=1024,
                max_stderr=1024,
            )

    def test_git_archive_inventory_is_mechanically_recomputed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "repo"
            repository.mkdir()
            (repository / "src").mkdir()
            (repository / "src" / "leaf.txt").write_text("pinned\n", encoding="ascii")
            for command in (["git", "init"], ["git", "config", "user.email", "test@example.invalid"], ["git", "config", "user.name", "Test"], ["git", "add", "src/leaf.txt"], ["git", "commit", "-m", "fixture"]):
                completed = _popen_bounded(command, cwd=repository, env=None, timeout=30, max_stdout=1024 * 1024, max_stderr=1024 * 1024)
                self.assertEqual(completed.returncode, 0)
            expected = _git_inventory(repository, "HEAD", (Path("src"),))
            archive = _archive(repository, "HEAD")
            extracted = root / "extracted"
            _extract_archive(archive, extracted)
            self.assertEqual(expected["file_count"], 1)
            self.assertEqual((extracted / "src" / "leaf.txt").read_text(encoding="ascii"), "pinned\n")

    def test_aggregate_full_graph_and_freshness(self):
        first = prepared_report()
        second = copy.deepcopy(first)
        second["run_id"] = "1" * 64
        second["nonce"] = "2" * 64
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            one, two, output = root / "one.json", root / "two.json", root / "aggregate.json"
            _atomic_json_create(one, first, output_root=root)
            _atomic_json_create(two, second, output_root=root)
            result = aggregate(one, two, output)
            self.assertEqual(result["fresh_replays"], 2)
            self.assertEqual(result["binary_raw_drift_scope"], ENVIRONMENT_SCOPE)
            bad = copy.deepcopy(second)
            bad["upstream"]["inventory"]["sha256"] = "0" * 64
            bad_path = root / "bad.json"
            _atomic_json_create(bad_path, bad, output_root=root)
            with self.assertRaises(AggregateError):
                aggregate(one, bad_path, root / "blocked.json")


if __name__ == "__main__":
    unittest.main()
