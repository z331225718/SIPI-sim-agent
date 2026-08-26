"""Focused custody and schema tests for the additive COM v5 aggregate."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from tools import aggregate_com_workbook_accm_replay_v5 as aggregate
from tools import run_com_workbook_accm_replay_v5 as runner


class AggregateCustodyTests(unittest.TestCase):
    @staticmethod
    def _hash(seed: str) -> str:
        return hashlib.sha256(seed.encode("ascii")).hexdigest()

    def _source(self) -> dict[str, object]:
        return {
            "package_source_inventory": {"count": 1, "total_bytes": 1, "sha256": self._hash("source-inventory")},
            "module_file": {
                "relative_path": "src/agent_com/__init__.py",
                "basename": "__init__.py",
                "bytes": 1,
                "sha256": self._hash("agent-com-init"),
                "root_contained": True,
                "path_redacted": True,
            },
        }

    def _runtime_proof(self, source: dict[str, object], *, project_venv: bool = False) -> dict[str, object]:
        external = {
            "relative_path": None,
            "basename": "runtime.pyd",
            "bytes": 1,
            "sha256": self._hash("numpy-runtime"),
            "root_contained": False,
            "path_redacted": True,
            "regular_file": True,
            "reparse_checked": True,
            "identity": aggregate.REGULAR_NONREPARSE_IDENTITY,
        }
        package_receipt = (
            lambda name: {
                **external,
                "relative_path": f".venv/Lib/site-packages/{name}/__init__.py",
                "basename": "__init__.py",
                "sha256": self._hash(f"{name}-project-runtime"),
                "root_contained": True,
                "module": name,
                "version": "1",
            }
            if project_venv
            else {**external, "module": name, "version": "1"}
        )
        return {
            "environment": {
                "cleared": list(aggregate.UPSTREAM_ENV_CLEARED_KEYS),
                "pythonpath_mode": "materialized_archive_src",
                "pythonno_user_site": True,
                "uv_no_config": True,
                "uv_virtual_env": {
                    "present": project_venv,
                    "relative_path": ".venv" if project_venv else None,
                    "basename": ".venv" if project_venv else None,
                    "root_contained": project_venv,
                    "path_redacted": True,
                    "identity": aggregate.UV_PROJECT_VENV_IDENTITY if project_venv else aggregate.UV_VENV_ABSENT_IDENTITY,
                },
            },
            "agent_com": {
                "module": "agent_com",
                "contained_in_materialized_archive": True,
                "module_file": source["module_file"],
                "package_source_inventory": source["package_source_inventory"],
            },
            "numpy": package_receipt("numpy"),
            "scipy": package_receipt("scipy"),
        }

    def _toolchain(self) -> dict[str, object]:
        roles = ("cargo", "rustc", "python", "uv")
        return {
            role: {
                "role": role,
                "basename": f"{role}.exe",
                "file_bytes": 1,
                "file_sha256": self._hash(f"{role}-file"),
                "version_args": ["--version"],
                "version_exit": 0,
                "version_stdout_sha256": self._hash(f"{role}-stdout"),
                "version_stderr_sha256": self._hash(f"{role}-stderr"),
                "path_redacted": True,
            }
            for role in roles
        }

    def _scratch(self, run_id: str, nonce: str) -> tuple[dict[str, object], dict[str, object]]:
        payload = f"sipi-com-workbook-accm-v5\nrun_id={run_id}\nnonce={nonce}\n".encode("ascii")
        marker = {
            "basename": ".sipi-com-workbook-accm-v5-root-marker",
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "path_redacted": True,
        }
        pre = {
            "basename": f"scratch-{nonce}",
            "nonce": nonce,
            "nonce_bound": True,
            "fresh_at_start": True,
            "reparse_ancestors_checked": True,
            "path_redacted": True,
            "marker": marker,
        }
        post = {"basename": pre["basename"], "nonce": nonce, "post_verified": True, "path_redacted": True, "marker": marker}
        return pre, post

    def _metrics(self) -> dict[str, float]:
        return {key: 1.0 for key in aggregate.METRIC_KEYS}

    def _upstream_case(self, index: int) -> dict[str, object]:
        arrays = {
            name: {"shape": [1], "sample_count": 1, "bytes": 8, "sha256": self._hash(f"upstream-{index}-{name}")}
            for name in ("unequalized_impulse", "equalized_pulse", "frequency_hz", "ptdr", "ptdr_gated", "tdr_time_s")
        }
        metrics = self._metrics()
        for key in ("available_signal_v", "interference_noise_v", "threshold_der", "impulse_sample_count"):
            metrics[key] = None
        return {
            "metrics": metrics,
            "winner": {
                "cursor_index": 0,
                "ctle_index": 1,
                "high_pass_index": 1,
                "tx_grid_index": 1,
                "sigma_n_v": 1.0,
                "fom_db": 1.0,
                "selected_tx_taps": None,
                "dfe_taps": [0.1],
                "dfe_published": True,
            },
            "port_order": list(aggregate.PORT_ORDER),
            "arrays": arrays,
        }

    def _candidate_case(self, index: int) -> dict[str, object]:
        arrays = {name: {"sample_count": 1, "sha256": self._hash(f"candidate-{index}-{name}")} for name in ("channel_impulse", "channel_pulse")}
        metrics = self._metrics()
        metrics["impulse_sample_count"] = 1.0
        return {
            "case_index": index,
            "metrics": metrics,
            "winner": {
                "cursor_index": 0,
                "ctle_index": 1,
                "high_pass_index": 1,
                "tx_grid_index": 1,
                "sigma_n_v": 1.0,
                "fom_db": 1.0,
                "selected_tx_taps": [0.1],
                "dfe_taps": None,
                "dfe_published": False,
                "selected_pulse": dict(arrays["channel_pulse"]),
            },
            "arrays": arrays,
            "port_order": None,
            "port_order_observed": False,
            "provenance": {"config_sha256": "a" * 64, "channel_source_sha256": aggregate.FIXTURE_EXPECTED["s4p"]["sha256"], "impulse_sha256": arrays["channel_impulse"]["sha256"]},
        }

    def _upstream(self, source: dict[str, object]) -> dict[str, object]:
        cases = [self._upstream_case(index) for index in range(2)]
        stdout_sha = self._hash("uv-stdout")
        stderr_sha = self._hash("uv-stderr")
        stdout_bytes = len(b"uv-stdout")
        stderr_bytes = len(b"uv-stderr")
        return {
            "exit": 0,
            "stdout_sha256": stdout_sha,
            "stderr_sha256": stderr_sha,
            "stdout_bytes": stdout_bytes,
            "stderr_bytes": stderr_bytes,
            "runtime": "executed_clean_archive_uv",
            "attempts": [{"exit": 0, "stdout_sha256": stdout_sha, "stderr_sha256": stderr_sha, "stdout_bytes": stdout_bytes, "stderr_bytes": stderr_bytes, "method": "uv_offline", "command": runner.UPSTREAM_UV_COMMAND, "blocker": None}],
            "config_sha256": aggregate.FIXTURE_EXPECTED["workbook"]["sha256"],
            "port_order": list(aggregate.PORT_ORDER),
            "runtime_proof": self._runtime_proof(source),
            "artifact": {"basename": "upstream-projection.json", "bytes": stdout_bytes, "sha256": stdout_sha, "path_redacted": True},
            "cases": cases,
            "blocker": None,
        }

    def _candidate(self) -> dict[str, object]:
        cases = [self._candidate_case(index) for index in range(2)]
        artifacts = [
            {"basename": name, "bytes": 1, "sha256": self._hash(f"candidate-artifact-{name}"), "path_redacted": True}
            for name in ("result.json", "report.html", "diagnostics.json")
        ]
        artifacts[0]["sha256"] = self._hash("candidate-artifact-result.json")
        return {
            "exit": 0,
            "stdout_sha256": self._hash("candidate-stdout"),
            "stderr_sha256": self._hash("candidate-stderr"),
            "runtime_timeout_s": 180,
            "command": "sipi-com-direct-run run --config <pinned-workbook> --thru <pinned-s4p> --output-dir <fresh-output> --override AC_CM_RMS=<vector> --overwrite",
            "vector": [0.0, 0.0],
            "runtime_exit": 0,
            "consumer_proof": True,
            "artifact_sha256": artifacts[0]["sha256"],
            "artifacts": artifacts,
            "cases": cases,
            "blocker": None,
        }

    def _comparison(self, upstream_case: dict[str, object], candidate_case: dict[str, object]) -> dict[str, object]:
        metric_delta = {
            key: None if upstream_case["metrics"][key] is None or candidate_case["metrics"][key] is None else abs(float(upstream_case["metrics"][key]) - float(candidate_case["metrics"][key]))
            for key in aggregate.METRIC_KEYS
        }
        return {
            "port_order_match": False,
            "port_order_observed": False,
            "port_order_status": "not_observed",
            "cursor_index_match": True,
            "sigma_n_v_abs_delta": 0.0,
            "fom_db_abs_delta": 0.0,
            "metric_abs_delta": metric_delta,
            "dfe": {"upstream_published": True, "candidate_published": False, "status": "candidate_missing"},
            "array_receipts": {"upstream": upstream_case["arrays"], "candidate": candidate_case["arrays"]},
        }

    def _build(self, binary_seed: str = "binary") -> dict[str, object]:
        binary = {"basename": "sipi-com-direct-run.exe", "bytes": 1, "sha256": self._hash(binary_seed), "path_redacted": True}
        environment = {
            "cleared_keys": list(runner.BUILD_ENV_CLEARED_KEYS),
            "forced_keys": ["CARGO_INCREMENTAL", "CARGO_NET_OFFLINE", "CARGO_TERM_COLOR", "RUSTC", "CARGO_TARGET_DIR"],
            "flags_cleared": True,
            "target_flags_cleared": True,
            "wrappers_cleared": True,
            "config_policy": runner.BUILD_CONFIG_POLICY,
            "cargo_home_policy": runner.BUILD_CARGO_HOME_POLICY,
            "target_basename": "candidate-target",
            "path_redacted": True,
        }
        return {
            "exit": 0,
            "stdout_sha256": self._hash("build-stdout"),
            "stderr_sha256": self._hash("build-stderr"),
            "command": runner.BUILD_COMMAND,
            "timeout_s": 900,
            "env_policy": runner.BUILD_ENV_POLICY,
            "env_receipt": environment,
            "binary_pre": binary,
            "binary_post": dict(binary),
            "binary_stable": True,
        }

    def _report(self, run_id: str, nonce: str, binary_seed: str = "binary") -> dict[str, object]:
        source = self._source()
        upstream = self._upstream(source)
        candidate = self._candidate()
        controls = []
        for index, vector in enumerate(aggregate.CONTROL_VECTORS):
            upstream = self._upstream(source)
            candidate = self._candidate()
            upstream["cases"] = [self._upstream_case(case_index) for case_index in range(2)]
            candidate["vector"] = list(vector)
            comparisons = [self._comparison(left, right) for left, right in zip(upstream["cases"], candidate["cases"])]
            controls.append({"vector": list(vector), "upstream": upstream, "candidate": candidate, "comparison": comparisons})
        scratch, scratch_post = self._scratch(run_id, nonce)
        return {
            "schema": aggregate.REPORT_SCHEMA,
            "run_id": run_id,
            "nonce": nonce,
            "candidate": {"commit": aggregate.CANDIDATE_COMMIT, "tree": aggregate.CANDIDATE_TREE, "archive": {**aggregate.CANDIDATE_ARCHIVE, "command": "git -c core.autocrlf=false archive --format=tar <candidate>"}},
            "upstream": {"commit": aggregate.UPSTREAM_COMMIT, "tree": aggregate.UPSTREAM_TREE, "archive": {**aggregate.UPSTREAM_ARCHIVE, "command": "git -c core.autocrlf=false archive --format=tar <upstream>"}},
            "fixtures": {
                key: {**expected, "source_commit": aggregate.UPSTREAM_COMMIT, "basename": Path(expected["path"]).name, "materialized_bytes": expected["bytes"], "materialized_sha256": expected["sha256"]}
                for key, expected in aggregate.FIXTURE_EXPECTED.items()
            },
            "fixture_post": {
                key: {"source_bytes": expected["bytes"], "source_sha256": expected["sha256"], "materialized_bytes": expected["bytes"], "materialized_sha256": expected["sha256"]}
                for key, expected in aggregate.FIXTURE_EXPECTED.items()
            },
            "upstream_source_pre": source,
            "upstream_source_post": deepcopy(source),
            "archive_post": {"candidate": {**aggregate.CANDIDATE_ARCHIVE, "path_redacted": True}, "upstream": {**aggregate.UPSTREAM_ARCHIVE, "path_redacted": True}},
            "port_order": {"source_key": "Port Order", "source_cell": "COM_Settings!G7", "one_based": list(aggregate.PORT_ORDER)},
            "toolchain": self._toolchain(),
            "toolchain_post": self._toolchain(),
            "toolchain_stable": True,
            "scratch": scratch,
            "scratch_post": scratch_post,
            "build": self._build(binary_seed),
            "controls": controls,
            "status": "scoped_mismatch_observed",
            "matched": False,
            "acceptance": False,
            "blockers": ["candidate_dfe_taps_not_published"],
            "non_claims": list(aggregate.NON_CLAIMS),
        }

    def _write(self, path: Path, value: object) -> None:
        path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _run_one_with_low_level_stubs(self, root: Path, run_id: str, nonce: str, binary_seed: str, *, direct_fallback: bool = False) -> dict[str, object]:
        """Exercise the real runner composition while isolating external tools."""
        template = self._report(run_id, nonce, binary_seed)
        source = deepcopy(template["upstream_source_pre"])
        binary = root / f"binary-{binary_seed}.exe"
        binary.write_bytes(b"x")
        build = self._build(binary_seed)
        build["binary_pre"] = {"basename": binary.name, "bytes": 1, "sha256": self._hash("x"), "path_redacted": True}
        upstream_controls = [deepcopy(template["controls"][0]["upstream"]), deepcopy(template["controls"][1]["upstream"])]
        if direct_fallback:
            for payload in upstream_controls:
                payload["runtime"] = "executed_clean_archive_external_python_env"
                payload["attempts"][0]["method"] = "direct_python_external_env"
                payload["attempts"][0]["command"] = "python -c <probe> with PYTHONPATH=<clean-upstream>/src"

        def fake_tool_identity(role: str, *_args: object) -> dict[str, object]:
            return deepcopy(template["toolchain"][role])

        with ExitStack() as stack:
            stack.enter_context(patch.object(runner, "archive", side_effect=[(aggregate.CANDIDATE_ARCHIVE["bytes"], aggregate.CANDIDATE_ARCHIVE["sha256"]), (aggregate.UPSTREAM_ARCHIVE["bytes"], aggregate.UPSTREAM_ARCHIVE["sha256"])]))
            stack.enter_context(patch.object(runner, "extract", return_value=None))
            stack.enter_context(patch.object(runner, "source_identity_receipt", side_effect=[deepcopy(source), deepcopy(source)]))
            stack.enter_context(patch.object(runner, "fixture_receipts", return_value=deepcopy(template["fixtures"])))
            stack.enter_context(patch.object(runner, "fixture_post_receipts", return_value=deepcopy(template["fixture_post"])))
            stack.enter_context(patch.object(runner, "resolve_executable", side_effect=lambda value: Path(value)))
            stack.enter_context(patch.object(runner, "tool_identity", side_effect=fake_tool_identity))
            stack.enter_context(patch.object(runner, "run_candidate_build", return_value=(build, binary, {})))
            stack.enter_context(patch.object(runner, "run_upstream_probe", side_effect=upstream_controls))
            stack.enter_context(patch.object(runner, "run_candidate_probe", side_effect=[deepcopy(template["controls"][0]["candidate"]), deepcopy(template["controls"][1]["candidate"])]))
            stack.enter_context(patch.object(runner, "fixture_post_receipts", return_value=deepcopy(template["fixture_post"])))
            stack.enter_context(patch.object(runner, "archive_post_receipts", return_value=deepcopy(template["archive_post"])))
            stack.enter_context(patch.object(runner, "scratch_post_receipt", return_value=deepcopy(template["scratch_post"])))
            return runner.run_one(Path("repo"), Path("upstream"), root / f"scratch-{nonce}", Path("cargo"), Path("python"), run_id, nonce, uv=Path("uv"), rustc=Path("rustc"))

    def test_full_report_aggregate_positive_and_output_is_new(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "run1.json"
            second = root / "run2.json"
            output = root / "aggregate.json"
            self._write(first, self._report("a" * 64, "b" * 64))
            self._write(second, self._report("c" * 64, "d" * 64, "binary-two"))
            result = aggregate.aggregate(first, second, output)
            self.assertEqual(result["status"], "scoped_mismatch_observed")
            self.assertEqual(result["scratch_roots"][0]["slot"], "run1")
            self.assertTrue(output.is_file())
            with self.assertRaises(FileExistsError):
                aggregate.aggregate(first, second, output)

    def test_runner_result_contract_feeds_aggregate_without_shape_rewrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "run1.json"
            second = root / "run2.json"
            output = root / "aggregate.json"
            first_report = self._run_one_with_low_level_stubs(root, "a" * 64, "b" * 64, "binary-one")
            second_report = self._run_one_with_low_level_stubs(root, "c" * 64, "d" * 64, "binary-two")
            self._write(first, first_report)
            self._write(second, second_report)
            result = aggregate.aggregate(first, second, output)
            self.assertEqual(result["status"], "scoped_mismatch_observed")

    def test_runner_project_venv_proof_is_accepted_by_aggregate(self) -> None:
        source = self._source()
        proof = self._runtime_proof(source, project_venv=True)
        runner.validate_runtime_proof(proof, source)
        aggregate._upstream_runtime_proof(proof, source)

    def test_runner_project_venv_package_escape_is_rejected_by_aggregate(self) -> None:
        source = self._source()
        proof = self._runtime_proof(source, project_venv=True)
        proof["numpy"]["relative_path"] = "outside/__init__.py"
        with self.assertRaises(ValueError):
            aggregate._upstream_runtime_proof(proof, source)

    def test_project_venv_relative_path_mutations_are_rejected_by_both_validators(self) -> None:
        source = self._source()
        invalid_paths = (".venv", ".venv//x", ".venv/./x", ".venv/x/..", ".venv\\Lib\\x", "/absolute/x")
        for invalid_path in invalid_paths:
            with self.subTest(invalid_path=invalid_path):
                runner_proof = self._runtime_proof(source, project_venv=True)
                runner_proof["numpy"]["relative_path"] = invalid_path
                with self.assertRaises(ValueError):
                    runner.validate_runtime_proof(runner_proof, source)

                aggregate_proof = self._runtime_proof(source, project_venv=True)
                aggregate_proof["numpy"]["relative_path"] = invalid_path
                with self.assertRaises(ValueError):
                    aggregate._upstream_runtime_proof(aggregate_proof, source)

    def test_project_package_identity_mutations_are_rejected_by_both_validators(self) -> None:
        source = self._source()
        for field, forged in (("regular_file", False), ("reparse_checked", False), ("identity", "forged")):
            with self.subTest(field=field):
                runner_proof = self._runtime_proof(source, project_venv=True)
                runner_proof["numpy"][field] = forged
                with self.assertRaises(ValueError):
                    runner.validate_runtime_proof(runner_proof, source)

                aggregate_proof = self._runtime_proof(source, project_venv=True)
                aggregate_proof["numpy"][field] = forged
                with self.assertRaises(ValueError):
                    aggregate._upstream_runtime_proof(aggregate_proof, source)

    def test_runner_direct_python_fallback_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = self._run_one_with_low_level_stubs(Path(directory), "a" * 64, "b" * 64, "binary-one", direct_fallback=True)
            self.assertEqual(report["status"], "blocked")
            self.assertIn("upstream_formal_uv_runtime_not_proven", report["blockers"])

    def test_cross_field_mutations_are_rejected(self) -> None:
        mutations = []

        report = self._report("a" * 64, "b" * 64)
        report["controls"][0]["candidate"]["cases"][0]["metrics"]["FOM"] = 999.0
        mutations.append(report)

        report = self._report("a" * 64, "b" * 64)
        report["controls"][0]["comparison"][0]["fom_db_abs_delta"] = 123.0
        mutations.append(report)

        report = self._report("a" * 64, "b" * 64)
        report["controls"][0]["upstream"]["cases"][0]["winner"]["cursor_index"] = 999
        mutations.append(report)

        report = self._report("a" * 64, "b" * 64)
        report["controls"][0]["upstream"]["artifact"]["sha256"] = "e" * 64
        mutations.append(report)

        report = self._report("a" * 64, "b" * 64)
        report["controls"][0]["upstream"]["attempts"][0]["command"] = "uv run --forged"
        mutations.append(report)

        report = self._report("a" * 64, "b" * 64)
        report["controls"][0]["candidate"]["cases"][0]["metrics"]["COM_dB"] = None
        mutations.append(report)

        report = self._report("a" * 64, "b" * 64)
        report["controls"][0]["upstream"]["cases"][0]["winner"]["cursor_index"] = 999
        report["controls"][0]["candidate"]["cases"][0]["winner"]["cursor_index"] = 999
        mutations.append(report)

        report = self._report("a" * 64, "b" * 64)
        report["controls"][0]["candidate"]["cases"][0]["metrics"]["impulse_sample_count"] = 999.0
        report["controls"][0]["comparison"][0]["metric_abs_delta"]["impulse_sample_count"] = 998.0
        mutations.append(report)

        report = self._report("a" * 64, "b" * 64)
        report["controls"][0]["upstream"]["cases"][0]["metrics"]["impulse_sample_count"] = 999.0
        report["controls"][0]["comparison"][0]["metric_abs_delta"]["impulse_sample_count"] = 998.0
        mutations.append(report)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "forged-cross-field.json"
            for report in mutations:
                self._write(path, report)
                with self.assertRaises(ValueError):
                    aggregate.load_report(path)

    def test_forged_runtime_and_port_claims_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = self._report("a" * 64, "b" * 64)
            report["controls"][0]["upstream"]["runtime"] = "forged_external_runtime"
            path = root / "forged-runtime.json"
            self._write(path, report)
            with self.assertRaises(ValueError):
                aggregate.load_report(path)
            report = self._report("a" * 64, "b" * 64)
            report["controls"][0]["comparison"][0]["port_order_match"] = True
            report["controls"][0]["comparison"][0]["port_order_observed"] = True
            report["controls"][0]["comparison"][0]["port_order_status"] = "observed"
            self._write(path, report)
            with self.assertRaises(ValueError):
                aggregate.load_report(path)

    def test_duplicate_and_oversize_reports_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            duplicate = root / "duplicate.json"
            duplicate.write_text('{"schema":"x","schema":"y"}', encoding="utf-8")
            with self.assertRaises(ValueError):
                aggregate.load_report(duplicate)
            oversized = root / "oversized.json"
            oversized.write_bytes(b"{" + b" " * aggregate.MAX_REPORT_BYTES + b"}")
            with self.assertRaises(ValueError):
                aggregate.load_report(oversized)

    def test_source_post_and_binary_pre_post_drift_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "drift.json"
            report = self._report("a" * 64, "b" * 64)
            report["upstream_source_post"]["module_file"]["sha256"] = self._hash("changed")
            self._write(path, report)
            with self.assertRaises(ValueError):
                aggregate.load_report(path)
            report = self._report("a" * 64, "b" * 64)
            report["build"]["binary_post"]["sha256"] = self._hash("changed-binary")
            self._write(path, report)
            with self.assertRaises(ValueError):
                aggregate.load_report(path)


if __name__ == "__main__":
    unittest.main()
