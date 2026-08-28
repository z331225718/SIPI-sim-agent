from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aggregate_as_03_power_wave_solve_replay as aggregate_module
import run_as_03_power_wave_solve_replay as replay
import verify_as_03_power_wave_solve_replay as verifier


H40 = "1" * 40
H64 = "2" * 64


def git_receipt(path: str, seed: str = "2") -> dict:
    return {"path": path, "git_blob": seed * 40, "bytes": 100, "sha256": seed * 64}


def live_receipt(path: str, seed: str = "2") -> dict:
    return {"path": path, "bytes": 100, "sha256": seed * 64, "nlink": 1, "path_redacted": True}


def archive() -> dict:
    return {"bytes": 1024, "sha256": H64, "links_rejected": True, "overlay": False}


def tool(role: str) -> dict:
    source = {"bytes": 100, "nlink": 2 if role in {"git", "cargo", "rustc"} else 1, "file_sha256": H64, "path_redacted": True}
    return {"role": role, "basename": f"{role}.exe", "source": source, "copy": {**source, "nlink": 1}, "version_args": ["--version"], "version_exit": 0, "version_sha256": H64, "path_redacted": True}


def module(name: str) -> dict:
    role = "scikit_rf_archive" if name == "skrf" else "python_environment"
    return {"basename": f"{name}.py", "bytes": 100, "sha256": H64, "version": "1.0" if name in {"numpy", "scipy", "skrf"} else None, "path_redacted": True, "relative_path": f"site/{name}.py", "root_role": role, "root_contained": True}


def executed_source(name: str) -> dict:
    return {"basename": f"{name}.py", "bytes": 100, "sha256": H64, "version": None, "path_redacted": True, "relative_path": f"skrf/{name}.py", "root_role": "scikit_rf_archive", "root_contained": True}


def matrix(bits: tuple[str, str, str, str]) -> list[dict]:
    return [{"re_bits": value, "im_bits": "0000000000000000"} for value in bits]


def report(run_id: str, nonce_seed: str) -> dict:
    prep_git = [git_receipt(path) for path in replay.PREP_PATHS]
    prep_live = [live_receipt(path) for path in replay.PREP_PATHS]
    candidate_git = [git_receipt(path) for path in replay.PRODUCTION_PATHS]
    candidate_live = [live_receipt(path) for path in replay.PRODUCTION_PATHS]
    tools = {role: tool(role) for role in ("git", "cargo", "rustc", "python", "linker")}
    modules = {name: module(name) for name in ("numpy", "numpy_linalg", "scipy", "skrf")}
    upstream_matrix = matrix(("3fb616f560a06f4a", "bfb58d5e7e3717c5", "bfb58d5e7e3717c5", "3fb616f560a06f4a"))
    candidate_matrix = matrix(("3fb616f560a06f4a", "bfb58d5e7e3717c4", "bfb58d5e7e3717c4", "3fb616f560a06f49"))
    prior_matrix = matrix(("3fb616f560a06f4d", "bfb58d5e7e3717c8", "bfb58d5e7e3717c8", "3fb616f560a06f4e"))
    candidate_real = [cell["re_bits"] for cell in candidate_matrix]
    upstream_real = [cell["re_bits"] for cell in upstream_matrix]
    current = {**replay._difference_real(candidate_real, upstream_real), "committed_asserted_real_bits": candidate_real, "upstream_real_bits": upstream_real, "upstream_complex_matrix": upstream_matrix, "independent_complex_diagnostic": candidate_matrix}
    archive_paths = (replay.SOURCE_PATH, "Cargo.lock", "rust-toolchain.toml")
    archive_live = [live_receipt(path) for path in archive_paths]
    binary = {"path": "sipi_agent_spice_direct-test.exe", "bytes": 100, "sha256": H64, "nlink": 1, "path_redacted": True}
    executed_sources = {name: executed_source(name) for name in ("network", "mathFunctions", "constants")}
    summaries = {name: {"exit_code": 0, "stdout_bytes": 0, "stdout_sha256": replay._sha256(b""), "stderr_bytes": 0, "stderr_sha256": replay._sha256(b""), "stream_limit_bytes": replay.MAX_PROCESS_BYTES} for name in ("cargo_metadata", "candidate_build", "candidate_test", "scikit_rf_leaf_probe", "independent_probe_build", "independent_probe")}
    independent_stdout = replay._independent_stdout(candidate_matrix)
    summaries["independent_probe"].update({"stdout_bytes": len(independent_stdout), "stdout_sha256": replay._sha256(independent_stdout)})
    upstream_stdout = replay._upstream_stdout(upstream_matrix, executed_sources, modules)
    summaries["scikit_rf_leaf_probe"].update({"stdout_bytes": len(upstream_stdout), "stdout_sha256": replay._sha256(upstream_stdout)})
    dependency_inventory = {"packages": 10, "files": 100, "bytes": 1000, "sha256": H64, "path_redacted": True}
    compiled_inputs = [live_receipt("libfaer-test.rlib"), live_receipt("libnum_complex-test.rlib")]
    return {
        "schema": replay.REPORT_SCHEMA,
        "status": "blocked_numeric_semantics",
        "work_item": "AS-03",
        "run_id": run_id,
        "nonce": nonce_seed * 64,
        "prep": {"commit": H40, "tree": "3" * 40, "parent": replay.EXPECTED_PREP_PARENT_COMMIT, "changed_paths": sorted(replay.PREP_PATHS), "first_introduction": True, "formal_artifacts_absent": True, "sources": prep_git, "live_pre": prep_live, "live_post": copy.deepcopy(prep_live), "stable": True},
        "candidate": {"commit": replay.PRODUCTION_COMMIT, "tree": replay.PRODUCTION_TREE, "archive": archive(), "sources": candidate_git, "live_pre": candidate_live, "live_post": copy.deepcopy(candidate_live), "archive_pre": archive_live, "archive_post": copy.deepcopy(archive_live), "archive_stable": True, "binary_pre": binary, "binary_post": copy.deepcopy(binary), "binary_stable": True, "dependency_inventory_pre": dependency_inventory, "dependency_inventory_post": copy.deepcopy(dependency_inventory), "dependency_inventory_stable": True, "compiled_inputs_pre": compiled_inputs, "compiled_inputs_post": copy.deepcopy(compiled_inputs), "compiled_inputs_stable": True, "stable": True},
        "baseline": {**git_receipt(replay.BASELINE_PATH), "schema": "sipi.as-03-numeric-physical-checkpoint.v1", "status": "blocked_numeric_semantics", "candidate_commit": replay.BASELINE_CANDIDATE_COMMIT, "candidate_tree": replay.BASELINE_CANDIDATE_TREE, "candidate_matrix": prior_matrix, "upstream_matrix": upstream_matrix, "prior_difference": replay._difference(prior_matrix, upstream_matrix)},
        "upstream": {"commit": replay.UPSTREAM_COMMIT, "tree": replay.UPSTREAM_TREE, "archive": archive(), "sources": [git_receipt(path) for path in replay.UPSTREAM_PATHS]},
        "scikit_rf": {"commit": replay.SKRF_COMMIT, "tree": replay.SKRF_TREE, "archive": archive(), "sources": [git_receipt(path) for path in replay.SKRF_PATHS], "executed_sources_pre": executed_sources, "executed_sources_post": copy.deepcopy(executed_sources), "executed_sources_stable": True},
        "toolchain": {"pre": tools, "post": copy.deepcopy(tools), "stable": True, "modules_pre": modules, "modules_post": copy.deepcopy(modules), "modules_stable": True, "timeout_seconds": 900, "environment": {"cargo_home_explicit": True, "cargo_home_path_redacted": True, "cargo_net_offline": True, "cargo_locked": True, "cargo_incremental": False, "cargo_profile": "test", "target_root_fresh": True, "rustc_explicit": True, "linker_explicit": True, "rust_host": "x86_64-pc-windows-msvc", "wrappers_cleared": True, "paths_redacted": True}},
        "fixture": {"kind": "fixed_touchstone_line_s2p_v1", "bytes": len(replay.FIXTURE), "sha256": replay.FIXTURE_SHA256, "created": {"basename": "fixture.s2p", "bytes": len(replay.FIXTURE), "sha256": replay.FIXTURE_SHA256, "nlink": 1, "path_redacted": True}},
        "execution": {**summaries, "candidate_test_name": replay.TEST_NAME, "private_probe_injection": False, "independent_probe_not_production_runtime": True, "agent_spice_yparam_path_executed": False},
        "numeric_change": {"prior": {"differing_components": 4, "max_ulp": 4}, "current": current, "differing_components_change": "4_to_3", "max_ulp_change": "4_to_1", "first_cell_exact": True, "numeric_parity": False, "blocked_numeric_semantics": True},
        "blockers": ["blocked_numeric_semantics"],
        "claims": {"clean_production_archive_execution": True, "committed_test_execution": True, "committed_real_checkpoint": True, "pinned_scikit_rf_leaf_execution": True, "agent_spice_source_replay": False, "complete_complex_checkpoint": False, "private_probe_injection": False, "numeric_parity": False, "s_parameter_fit": False},
        "non_claims": ["candidate_complete_complex_checkpoint", "independent_probe_is_production_runtime", "agent_spice_yparam_path_execution", "numeric_parity", "acceptance_tolerance", "general_nudge_eig_equivalence", "s_parameter_fit", "AS-05_Xyce_XDM", "release_acceptance"],
    }


def payload(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2).encode("ascii") + b"\n"


def aggregate(first: dict, second: dict, first_payload: bytes, second_payload: bytes) -> dict:
    return {
        "schema": aggregate_module.SCHEMA,
        "status": "blocked_numeric_semantics",
        "work_item": "AS-03",
        "report_count": 2,
        "reports": [
            {"basename": name, "path_redacted": True, "bytes": len(data), "sha256": replay._sha256(data), "nlink": 1, "run_id": item["run_id"], "nonce": item["nonce"]}
            for name, data, item in (("run-01.json", first_payload, first), ("run-02.json", second_payload, second))
        ],
        "shared": {"prep_commit": first["prep"]["commit"], "prep_tree": first["prep"]["tree"], "prep_parent": first["prep"]["parent"], "candidate_commit": first["candidate"]["commit"], "candidate_tree": first["candidate"]["tree"], "baseline_path": first["baseline"]["path"], "baseline_candidate_commit": first["baseline"]["candidate_commit"], "baseline_candidate_tree": first["baseline"]["candidate_tree"], "upstream_commit": first["upstream"]["commit"], "upstream_tree": first["upstream"]["tree"], "scikit_rf_commit": first["scikit_rf"]["commit"], "scikit_rf_tree": first["scikit_rf"]["tree"], "toolchain": first["toolchain"], "fixture_sha256": first["fixture"]["sha256"], "baseline_sha256": first["baseline"]["sha256"]},
        "numeric_change": {key: first["numeric_change"][key] for key in ("prior", "current", "differing_components_change", "max_ulp_change", "numeric_parity", "blocked_numeric_semantics")},
        "blockers": ["blocked_numeric_semantics"],
        "claims": {"two_fresh_replays": True, "clean_production_archive_execution": True, "committed_real_checkpoint": True, "pinned_scikit_rf_leaf_execution": True, "agent_spice_source_replay": False, "complete_complex_checkpoint": False, "private_probe_injection": False, "numeric_parity": False, "s_parameter_fit": False},
        "non_claims": first["non_claims"],
    }


class ReplayValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.first = report("run-01", "a")
        self.second = report("run-02", "b")
        self.first_payload = payload(self.first)
        self.second_payload = payload(self.second)
        self.aggregate = aggregate(self.first, self.second, self.first_payload, self.second_payload)

    def verify(self) -> dict:
        return verifier.verify_values(self.first, self.second, self.aggregate, self.first_payload, self.second_payload, "run-01.json", "run-02.json")

    def test_valid_documents_remain_blocked_not_parity(self) -> None:
        self.assertEqual(self.verify()["status"], "valid")
        self.assertFalse(self.aggregate["claims"]["numeric_parity"])

    def test_report_extra_key_is_rejected(self) -> None:
        self.first["extra"] = True
        with self.assertRaises(ValueError): replay.validate_report(self.first)

    def test_prep_parent_drift_is_rejected(self) -> None:
        self.first["prep"]["parent"] = "0" * 40
        with self.assertRaises(ValueError): replay.validate_report(self.first)

    def test_prep_live_drift_is_rejected(self) -> None:
        self.first["prep"]["live_post"][0]["sha256"] = "0" * 64
        with self.assertRaises(ValueError): replay.validate_report(self.first)

    def test_source_path_drift_is_rejected(self) -> None:
        self.first["candidate"]["sources"][0]["path"] = "wrong.rs"
        with self.assertRaises(ValueError): replay.validate_report(self.first)

    def test_archive_overlay_is_rejected(self) -> None:
        self.first["candidate"]["archive"]["overlay"] = True
        with self.assertRaises(ValueError): replay.validate_report(self.first)

    def test_baseline_four_by_four_fact_drift_is_rejected(self) -> None:
        self.first["baseline"]["prior_difference"]["max_ulp"] = 3
        with self.assertRaises(ValueError): replay.validate_report(self.first)

    def test_scikit_source_identity_drift_is_rejected(self) -> None:
        self.first["scikit_rf"]["tree"] = "0" * 40
        with self.assertRaises(ValueError): replay.validate_report(self.first)

    def test_toolchain_pre_post_drift_is_rejected(self) -> None:
        self.first["toolchain"]["post"]["rustc"]["copy"]["file_sha256"] = "0" * 64
        with self.assertRaises(ValueError): replay.validate_report(self.first)

    def test_bool_is_rejected_for_nlink_and_version_exit(self) -> None:
        for key, value in (("nlink", True), ("version_exit", False)):
            mutated = copy.deepcopy(self.first)
            if key == "nlink":
                mutated["toolchain"]["pre"]["cargo"]["source"][key] = value
            else:
                mutated["toolchain"]["pre"]["cargo"][key] = value
            mutated["toolchain"]["post"] = copy.deepcopy(mutated["toolchain"]["pre"])
            with self.subTest(key=key), self.assertRaises(ValueError):
                replay.validate_report(mutated)

    def test_module_path_disclosure_key_is_rejected(self) -> None:
        self.first["toolchain"]["modules_pre"]["numpy"]["path"] = "C:/secret"
        self.first["toolchain"]["modules_post"] = copy.deepcopy(self.first["toolchain"]["modules_pre"])
        with self.assertRaises(ValueError): replay.validate_report(self.first)

    def test_fixture_hash_drift_is_rejected(self) -> None:
        self.first["fixture"]["sha256"] = "0" * 64
        with self.assertRaises(ValueError): replay.validate_report(self.first)

    def test_private_probe_claim_is_rejected(self) -> None:
        self.first["execution"]["private_probe_injection"] = True
        with self.assertRaises(ValueError): replay.validate_report(self.first)

    def test_numeric_three_by_one_fact_drift_is_rejected(self) -> None:
        self.first["numeric_change"]["current"]["max_ulp"] = 2
        with self.assertRaises(ValueError): replay.validate_report(self.first)

    def test_bool_is_rejected_for_ulp(self) -> None:
        self.first["numeric_change"]["current"]["differences"][0]["ulp"] = True
        with self.assertRaises(ValueError): replay.validate_report(self.first)

    def test_parity_claim_is_rejected(self) -> None:
        self.first["claims"]["numeric_parity"] = True
        with self.assertRaises(ValueError): replay.validate_report(self.first)

    def test_aggregate_report_hash_drift_is_rejected(self) -> None:
        self.aggregate["reports"][0]["sha256"] = "0" * 64
        with self.assertRaises(ValueError): self.verify()

    def test_aggregate_nonce_reuse_is_rejected(self) -> None:
        self.aggregate["reports"][1]["nonce"] = self.aggregate["reports"][0]["nonce"]
        with self.assertRaises(ValueError): aggregate_module.validate_aggregate(self.aggregate)

    def test_aggregate_bool_report_count_is_rejected(self) -> None:
        self.aggregate["report_count"] = True
        with self.assertRaises(ValueError): aggregate_module.validate_aggregate(self.aggregate)

    def test_aggregate_path_disclosure_is_rejected(self) -> None:
        self.aggregate["reports"][0]["basename"] = "C:/secret/run.json"
        with self.assertRaises(ValueError): aggregate_module.validate_aggregate(self.aggregate)

    def test_safe_relative_rejects_windows_and_posix_escape(self) -> None:
        for value in ("../x", "C:\\x", "C:/x", "/x", "\\\\server\\share\\x"):
            with self.subTest(value=value), self.assertRaises(RuntimeError): replay._safe_relative(value)

    def test_candidate_checkpoint_parser_is_exact(self) -> None:
        source = b'''fn power_wave_solve_has_stable_fixed_line_checkpoint() {\n        assert_eq!(y[0].re.to_bits(), 0x3fb6_16f5_60a0_6f4a);\n        assert_eq!(y[1].re.to_bits(), 0xbfb5_8d5e_7e37_17c4);\n        assert_eq!(y[2].re.to_bits(), 0xbfb5_8d5e_7e37_17c4);\n        assert_eq!(y[3].re.to_bits(), 0x3fb6_16f5_60a0_6f49);\n    }'''
        self.assertEqual(replay._candidate_real_assertions(source)[0], "3fb616f560a06f4a")

    def test_default_git_and_rustup_tool_smoke_allows_source_hardlinks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            staged: dict[str, Path] = {}
            sources: dict[str, Path] = {}
            for role, raw, args in (("git", "git", ("--version",)), ("cargo", replay.DEFAULT_CARGO, ("-Vv",)), ("rustc", replay.DEFAULT_RUSTC, ("-vV",))):
                with self.subTest(role=role):
                    sources[role] = replay._resolve_tool(raw, role)
                    staged[role] = replay._stage_tool(sources[role], role, root)
                    identity = replay._tool_snapshot(sources[role], staged[role], role, args)
                    self.assertGreaterEqual(identity["source"]["nlink"], 1)
                    self.assertEqual(identity["copy"]["nlink"], 1)
                    self.assertEqual(identity["version_exit"], 0)
            linker, _ = replay._linker_for(staged["rustc"])
            linker_copy = replay._stage_tool(linker, "linker", root)
            self.assertEqual(replay._tool_snapshot(linker, linker_copy, "linker", replay.LINKER_VERSION_ARGS)["version_exit"], 0)

    def test_fresh_child_allows_parent_directory_timestamp_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            child = replay._fresh_child(root, "runner")
            self.assertEqual(child.parent, root.resolve())
            self.assertTrue(child.is_dir())

    def test_real_git_prep_gate_requires_single_first_introduction_commit(self) -> None:
        git = replay._resolve_tool("git", "git")
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            base = [str(git), "-c", "user.name=AS03 Test", "-c", "user.email=as03@example.invalid", "-C", str(repo)]
            subprocess.run([str(git), "init", "--quiet", str(repo)], check=True)
            subprocess.run([*base, "commit", "--allow-empty", "--quiet", "-m", "production"], check=True)
            production = subprocess.run([*base, "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
            for path in replay.PREP_PATHS:
                target = repo / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(path, encoding="ascii")
            subprocess.run([*base, "add", "--", *replay.PREP_PATHS], check=True)
            subprocess.run([*base, "commit", "--quiet", "-m", "prep"], check=True)
            prep = subprocess.run([*base, "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
            with mock.patch.object(replay, "EXPECTED_PREP_PARENT_COMMIT", production):
                receipt = replay._prep_gate(git, repo, prep)
            self.assertEqual(receipt["changed_paths"], sorted(replay.PREP_PATHS))
            self.assertTrue(receipt["first_introduction"])
            self.assertTrue(receipt["formal_artifacts_absent"])

    def test_exclusive_output_rejects_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_bytes(b"existing")
            with self.assertRaises(RuntimeError): replay._create_file(path, b"new", 16)

    def test_aggregate_cli_smoke_uses_exclusive_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second, output = root / "run-01.json", root / "run-02.json", root / "aggregate.json"
            replay._create_file(first, self.first_payload, replay.MAX_REPORT_BYTES)
            replay._create_file(second, self.second_payload, replay.MAX_REPORT_BYTES)
            command = [sys.executable, str(Path(aggregate_module.__file__).resolve()), "--first", str(first), "--second", str(second), "--report-root", str(root), "--output", str(output), "--output-root", str(root)]
            completed = subprocess.run(command, check=False, capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            aggregate_module.validate_aggregate(json.loads(replay._read_regular(output, replay.MAX_REPORT_BYTES)))

    def test_tool_source_hardlink_is_admitted_then_exclusive_copy_is_single_link(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first, second = Path(directory) / "a", Path(directory) / "b"
            first.write_bytes(b"data")
            os.link(first, second)
            payload = replay._read_regular(first, 16, require_nlink_one=False)
            copied = Path(directory) / "copy"
            receipt = replay._create_file(copied, payload, 16)
            self.assertEqual(receipt["nlink"], 1)


if __name__ == "__main__":
    unittest.main()
