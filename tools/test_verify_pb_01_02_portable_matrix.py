"""Real Git/filesystem and mutation tests for PB matrix stage-1 custody."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import aggregate_pb_01_02_portable_matrix as aggregate
import run_pb_01_02_portable_matrix as runner
import verify_pb_01_02_portable_matrix as verifier


ROOT = Path(__file__).resolve().parents[1]


def git(repo: Path, *args: str) -> str:
    process = subprocess.run(["git", "-C", str(repo), *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    return process.stdout.decode("utf-8", "strict").strip()


class RealPreparationGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.name", "PB Test")
        git(self.repo, "config", "user.email", "pb@example.invalid")
        git(self.repo, "config", "core.autocrlf", "false")
        (self.repo / "README.md").write_text("base\n", encoding="utf-8")
        git(self.repo, "add", "README.md")
        git(self.repo, "commit", "-q", "-m", "base")
        self.base = git(self.repo, "rev-parse", "HEAD")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _prep(self, *, extra: str | None = None, formal: bool = False) -> str:
        for relative in runner.PREP_PATHS:
            target = self.repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            source = ROOT / relative
            target.write_bytes(source.read_bytes())
        if extra:
            target = self.repo / extra
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("extra\n", encoding="utf-8")
        if formal:
            target = self.repo / runner.FORMAL_PATHS[0]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("{}\n", encoding="utf-8")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-q", "-m", "prep")
        return git(self.repo, "rev-parse", "HEAD")

    def test_real_git_first_introduction_gate_passes_in_both_implementations(self) -> None:
        prep = self._prep()
        first = runner.validate_prep_commit(self.repo, prep, self.base)
        second = verifier.verify_preparation(self.repo, prep, self.base)
        self.assertEqual(first["commit"], prep)
        self.assertEqual(second["tree"], first["tree"])
        self.assertEqual(tuple(first["changed_paths"]), runner.PREP_PATHS)
        work = self.repo / "controlled-archive-work"
        work.mkdir()
        materialized, source = runner.materialize_archive(self.repo, prep, work, "candidate", 30)
        archived, archived_fact = runner.secure_read(materialized, runner.PREP_PATHS[0])
        self.assertEqual(archived, (ROOT / runner.PREP_PATHS[0]).read_bytes())
        self.assertEqual(source["tree"], first["tree"])
        self.assertTrue(archived_fact["single_handle_read"])

    def test_extra_changed_path_is_rejected(self) -> None:
        prep = self._prep(extra="extra.txt")
        with self.assertRaises(runner.CustodyError):
            runner.validate_prep_commit(self.repo, prep, self.base)

    def test_formal_evidence_in_prep_is_rejected(self) -> None:
        prep = self._prep(formal=True)
        with self.assertRaises(verifier.VerifyError):
            verifier.verify_preparation(self.repo, prep, self.base)

    def test_not_first_introduction_is_rejected(self) -> None:
        target = self.repo / runner.PREP_PATHS[0]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("old\n", encoding="utf-8")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-q", "-m", "preexisting")
        parent = git(self.repo, "rev-parse", "HEAD")
        for relative in runner.PREP_PATHS:
            destination = self.repo / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((ROOT / relative).read_bytes())
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-q", "-m", "bad prep")
        with self.assertRaises(runner.CustodyError):
            runner.validate_prep_commit(self.repo, "HEAD", parent)

    def test_wrong_direct_parent_is_rejected(self) -> None:
        prep = self._prep()
        with self.assertRaises(runner.CustodyError):
            runner.validate_prep_commit(self.repo, prep, "0" * 40)

    def test_streamed_archive_partial_file_is_removed_on_write_failure(self) -> None:
        prep = self._prep()
        work = self.repo / "archive-failure-work"
        work.mkdir()
        with mock.patch.object(runner.os, "fsync", side_effect=OSError("injected")):
            with self.assertRaises(OSError):
                runner._archive_bytes(self.repo, prep, work, "failure", 30)
        self.assertFalse((work / "failure.tar").exists())

    def test_default_parent_constant_cannot_be_masked_by_fixture_setup(self) -> None:
        prep = self._prep()
        self.assertNotEqual(self.base, runner.PINNED_PARENT)
        with self.assertRaises(runner.CustodyError):
            runner.validate_prep_commit(self.repo, prep)


class FilesystemCustodyTests(unittest.TestCase):
    def test_single_handle_read_and_exclusive_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "input.bin").write_bytes(b"abc")
            payload, fact = runner.secure_read(root, "input.bin", 3)
            self.assertEqual(payload, b"abc")
            self.assertTrue(fact["single_handle_read"])
            written = runner.exclusive_write(root, "output.bin", b"result")
            self.assertTrue(written["exclusive_create"])
            with self.assertRaises(runner.CustodyError):
                runner.exclusive_write(root, "output.bin", b"overwrite")
            with self.assertRaises(runner.CustodyError):
                runner.exclusive_write(root, "../escape", b"bad")

    def test_hardlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "input.bin").write_bytes(b"abc")
            os.link(root / "input.bin", root / "second.bin")
            with self.assertRaises(runner.CustodyError):
                runner.secure_read(root, "input.bin")

    def test_partial_output_is_removed_on_write_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with mock.patch.object(runner.os, "write", side_effect=OSError("injected")):
                with self.assertRaises(OSError):
                    runner.exclusive_write(root, "partial.bin", b"payload")
            self.assertFalse((root / "partial.bin").exists())

    def test_reparse_ancestor_is_rejected_when_supported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            real = base / "real"; real.mkdir(); (real / "input.bin").write_bytes(b"abc")
            link = base / "linked"
            try:
                os.symlink(real, link, target_is_directory=True)
            except OSError:
                self.skipTest("directory symlink creation is unavailable")
            with self.assertRaises(runner.CustodyError):
                runner.secure_read(link, "input.bin")

    def test_symlink_is_rejected_when_supported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "input.bin").write_bytes(b"abc")
            try:
                os.symlink(root / "input.bin", root / "link.bin")
            except OSError:
                self.skipTest("symlink creation is unavailable")
            with self.assertRaises(runner.CustodyError):
                runner.secure_read(root, "link.bin")


class CorpusMutationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = (ROOT / runner.PREP_PATHS[0]).read_bytes()
        cls.document = json.loads(cls.payload)

    def test_current_corpus_is_exact_and_class_pickle_is_not_misreported(self) -> None:
        document = runner.load_corpus(self.payload)
        item = next(entry for entry in document["excluded_branches"] if entry["id"] == "legacy.result.class_pickle")
        self.assertEqual(item["status"], "implemented_not_covered_by_matrix")

    def test_bool_version_is_rejected(self) -> None:
        value = copy.deepcopy(self.document)
        value["version"] = True
        with self.assertRaises(runner.CustodyError):
            runner.load_corpus(json.dumps(value).encode())

    def test_duplicate_or_extra_case_is_rejected(self) -> None:
        value = copy.deepcopy(self.document)
        value["pb01_cases"].append(copy.deepcopy(value["pb01_cases"][0]))
        with self.assertRaises(runner.CustodyError):
            runner.load_corpus(json.dumps(value).encode())
        value = copy.deepcopy(self.document)
        value["pb01_cases"][0]["extra"] = True
        with self.assertRaises(runner.CustodyError):
            runner.load_corpus(json.dumps(value).encode())


def report(run_id: str, nonce: str) -> dict:
    digest = hashlib.sha256(b"x").hexdigest()
    def fact(path: str) -> dict:
        return {"path": path, "sha256": digest, "bytes": 1, "regular": True, "nonlink": True, "nlink": 1, "single_handle_read": True, "pre_identity": [1, 2, 1, 4], "post_identity": [1, 2, 1, 4]}
    prep_files = {path: {"blob": "1" * 40, "sha256": digest, "bytes": 1, "live_pre": fact(path), "live_post": fact(path), "live_equal": True} for path in runner.PREP_PATHS}
    identity = lambda role: {"role": role, "executable": f"{role}.exe", "file_sha256": digest, "version_sha256": digest, "version_exit": 0, "path_redacted": True, "file_custody_pre": fact(f"{role}.exe"), "file_custody_post": fact(f"{role}.exe"), "file_custody_equal": True}
    exclusive = lambda path: {**fact(path), "exclusive_create": True, "pre_absent": True, "readback_equal": True}
    process = {"exit_code": 0, "stdout": exclusive("stdout.txt"), "stderr": exclusive("stderr.txt")}
    cases = []
    for case_id in runner.EXPECTED_CASE_IDS:
        if case_id.startswith("pb01_"):
            rows = [{"name": name, "length": 1, "max_abs": 0.0, "scale": 1.0, "tolerance": 1.1e-6, "passed": True} for name in runner.PB01_ARRAYS]
            comparison = {"kind": "pb01_selected_numeric_arrays", "class_pickle_covered_by_matrix": False, "candidate_schema": {"kind": "python_pickle_dict", "schema": "sipi.pybert_data.v1", "item_names": list(aggregate.PB01_ITEMS), "array_keys": sorted(aggregate.PB01_ITEMS)}, "oracle_schema": {"kind": "PyBertData_class_pickle"}, "rows": rows, "blockers": [], "candidate_process": copy.deepcopy(process), "oracle_process": copy.deepcopy(process)}
        else:
            member = {"dtype": "<f8", "shape": [1], "fortran_order": False, "count": 1, "f64_sha256": digest}
            arrays = {"bytes": 1, "sha256": digest, "uncompressed_bytes": 88, "logical_members": {name: copy.deepcopy(member) for name in runner.PB02_MEMBERS}, "logical_sha256": digest}
            observation = {"meta": {"canonical_sha256": digest, "fields": {}}, "arrays": arrays}
            comparison = {"kind": "pb02_complete_meta_and_logical_npz", "candidate": copy.deepcopy(observation), "oracle": copy.deepcopy(observation), "candidate_process": copy.deepcopy(process), "oracle_process": copy.deepcopy(process)}
        cases.append({"id": case_id, "status": "passed", "blockers": [], "comparison": comparison})
    inputs = [{"lane": lane, "pre": fact(f"{lane}.input"), "post": fact(f"{lane}.input"), "equal": True} for lane in ("PB-01", "PB-02")]
    inputs += [{"case_id": case_id, "pre": exclusive("input.json"), "post": fact("input.json"), "equal": True} for case_id in runner.EXPECTED_CASE_IDS]
    artifacts = []
    for case_id in runner.EXPECTED_CASE_IDS:
        kinds = ("legacy_result",) if case_id.startswith("pb01_") else ("meta", "arrays")
        for role in ("candidate", "oracle"):
            for kind in kinds:
                artifacts.append({**fact(f"{role}-{kind}.bin"), "present": True, "pre_absent": True, "role": role, "kind": kind, "case_id": case_id})
    return {
        "schema": "sipi.pb-01-02-portable-matrix-report.v2", "version": 2, "run_id": run_id, "run_nonce": nonce,
        "preparation": {"commit": "2" * 40, "tree": "3" * 40, "parent": "4" * 40, "changed_paths": list(runner.PREP_PATHS), "files": prep_files},
        "corpus": {"path": runner.PREP_PATHS[0], "blob": "1" * 40, "sha256": digest, "bytes": 1},
        "source": {"candidate": {"commit": "2" * 40, "tree": "3" * 40, "archive_sha256": digest, "inventory_pre_sha256": digest, "inventory_post_sha256": digest, "inventory_equal": True}, "upstream": {"commit": runner.UPSTREAM_COMMIT, "tree": runner.UPSTREAM_TREE, "archive_sha256": digest, "inventory_pre_sha256": digest, "inventory_post_sha256": digest, "inventory_equal": True}},
        "toolchain": {role: identity(role) for role in ("cargo", "rustc", "uv", "link")},
        "build": {"process": copy.deepcopy(process), "cargo_binary_source": fact("target/release/sipi-pybert-direct.exe"), "binary": {"pre": exclusive("sipi-pybert-direct.exe"), "post": fact("sipi-pybert-direct.exe"), "equal": True}, "env": {"rustc_explicit": True, "rustc_wrappers_cleared": True, "cargo_target_external": True, "cargo_offline": True, "path_closed": True, "cargo_home_explicit": True, "cargo_config_and_flags_cleared": True, "cargo_cache_lock_bound": True}},
        "oracle_runtime": {"process": copy.deepcopy(process), "modules": {"pybert": {"owner": "archive", "relative_path": "src/pybert/__init__.py", "version": "1", "file": fact("src/pybert/__init__.py")}, "numpy": {"owner": "venv", "relative_path": "Lib/site-packages/numpy/__init__.py", "version": "1", "file": fact("Lib/site-packages/numpy/__init__.py")}, "scipy": {"owner": "venv", "relative_path": "Lib/site-packages/scipy/__init__.py", "version": "1", "file": fact("Lib/site-packages/scipy/__init__.py")}}, "clean_archive_or_venv_only": True, "host_pythonpath_absent": True, "host_virtual_env_absent": True, "uv_offline_frozen_no_config": True, "uv_link_mode_copy": True, "uv_cache_explicit_lock_bound": True, "host_uv_flags_cleared": True, "oracle_work_archive_sha256": digest, "oracle_work_started_clean": True},
        "custody": {"archive_materialization": [{"role": "candidate", "archive_sha256": digest, "fact": fact("candidate.tar")}, {"role": "upstream_pristine", "archive_sha256": digest, "fact": fact("upstream.tar")}, {"role": "upstream_oracle", "archive_sha256": digest, "fact": fact("oracle.tar")}], "inputs": inputs, "artifacts": artifacts, "output": {"fresh_root": True, "exclusive_report": True}},
        "cases": cases,
        "claims": {key: False for key in aggregate.CLAIM_KEYS},
    }


class AggregateAndVerifierMutationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.first = report("run-1", "a" * 64)
        self.second = report("run-2", "b" * 64)

    def test_mechanical_aggregate_accepts_exact_closed_reports(self) -> None:
        value = aggregate.aggregate_documents(self.first, self.second)
        self.assertEqual(value["status"], "passed_scoped")
        self.assertEqual(len(value["cases"]), len(runner.EXPECTED_CASE_IDS))
        self.assertFalse(value["claims"]["numeric_parity"])

    def test_controlled_real_aggregate_cli_uses_bounded_files_and_exclusive_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence, output = root / "evidence", root / "output"
            evidence.mkdir(); output.mkdir()
            (evidence / "first.json").write_text(json.dumps(self.first), encoding="utf-8")
            (evidence / "second.json").write_text(json.dumps(self.second), encoding="utf-8")
            process = subprocess.run([
                sys.executable, str(ROOT / "tools/aggregate_pb_01_02_portable_matrix.py"),
                "--evidence-root", str(evidence), "--first", "first.json", "--second", "second.json",
                "--output-root", str(output), "--output", "aggregate.json",
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertEqual(process.returncode, 0, process.stderr.decode("utf-8", "replace"))
            aggregate_bytes, fact = runner.secure_read(output, "aggregate.json")
            self.assertEqual(json.loads(aggregate_bytes)["status"], "passed_scoped")
            self.assertTrue(fact["single_handle_read"])

    def test_duplicate_missing_or_bad_case_cannot_be_ignored(self) -> None:
        for mutation in ("duplicate", "missing", "unknown"):
            value = copy.deepcopy(self.first)
            if mutation == "duplicate":
                value["cases"][1]["id"] = value["cases"][0]["id"]
            elif mutation == "missing":
                value["cases"].pop()
            else:
                value["cases"][0]["id"] = "unknown"
            with self.subTest(mutation=mutation), self.assertRaises(aggregate.AggregateError):
                aggregate.aggregate_documents(value, self.second)

    def test_extra_key_bool_version_and_numeric_claim_are_rejected(self) -> None:
        mutations = []
        value = copy.deepcopy(self.first); value["extra"] = 1; mutations.append(value)
        value = copy.deepcopy(self.first); value["version"] = True; mutations.append(value)
        value = copy.deepcopy(self.first); value["claims"]["numeric_parity"] = True; mutations.append(value)
        for value in mutations:
            with self.subTest(value=value), self.assertRaises(aggregate.AggregateError):
                aggregate.aggregate_documents(value, self.second)

    def test_twelve_case_fake_passed_reports_are_rejected(self) -> None:
        mutations = []
        value = copy.deepcopy(self.first); value["cases"][0]["comparison"]["candidate_process"]["exit_code"] = 9; mutations.append(value)
        value = copy.deepcopy(self.first); value["cases"][0]["comparison"]["rows"] = []; mutations.append(value)
        value = copy.deepcopy(self.first); value["cases"][0]["comparison"]["rows"][0]["length"] = True; mutations.append(value)
        value = copy.deepcopy(self.first); value["cases"][0]["comparison"]["rows"][0]["max_abs"] = float("nan"); mutations.append(value)
        value = copy.deepcopy(self.first); value["cases"][6]["comparison"]["oracle"] = copy.deepcopy(value["cases"][6]["comparison"]["oracle"]); value["cases"][6]["comparison"]["oracle"]["meta"]["canonical_sha256"] = "f" * 64; mutations.append(value)
        value = copy.deepcopy(self.first); value["custody"]["inputs"] = []; value["custody"]["artifacts"] = []; mutations.append(value)
        for value in mutations:
            with self.subTest(), self.assertRaises(aggregate.AggregateError):
                aggregate.aggregate_documents(value, self.second)
            with self.subTest(verifier=True), self.assertRaises(verifier.VerifyError):
                verifier._report(value)

    def test_json_parsers_reject_nonfinite_constants(self) -> None:
        with self.assertRaises(runner.CustodyError):
            runner._json_loads('{"x": NaN}')
        with self.assertRaises(aggregate.AggregateError):
            aggregate._json_loads('{"x": Infinity}')
        with self.assertRaises(verifier.VerifyError):
            verifier._json_loads('{"x": -Infinity}')

    def test_same_run_nonce_or_tool_drift_is_rejected(self) -> None:
        value = copy.deepcopy(self.second); value["run_nonce"] = self.first["run_nonce"]
        with self.assertRaises(aggregate.AggregateError):
            aggregate.aggregate_documents(self.first, value)

    def test_aggregate_partial_output_is_removed_on_write_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with mock.patch.object(aggregate.os, "write", side_effect=OSError("injected")):
                with self.assertRaises(OSError):
                    aggregate._exclusive_json(root, "aggregate.json", {"x": 1})
            self.assertFalse((root / "aggregate.json").exists())
        value = copy.deepcopy(self.second); value["toolchain"]["cargo"]["file_sha256"] = "f" * 64
        with self.assertRaises(aggregate.AggregateError):
            aggregate.aggregate_documents(self.first, value)

    def test_manifest_rejects_extra_key_bool_version_and_numeric_claim(self) -> None:
        digest = "a" * 64
        manifest = {
            "schema": "sipi.pb-01-02-portable-matrix-evidence.v2", "version": 2, "status": "scoped_matrix_blocked",
            "preparation": {"commit": "1" * 40, "tree": "2" * 40, "parent": "3" * 40},
            "harness": {"files": [{"path": path, "blob": "4" * 40, "sha256": digest, "bytes": 1} for path in runner.PREP_PATHS]},
            "evidence": {"reports": [{"path": verifier.FORMAL_PATHS[0], "sha256": digest, "bytes": 1}, {"path": verifier.FORMAL_PATHS[1], "sha256": "b" * 64, "bytes": 1}], "aggregate": {"path": verifier.FORMAL_PATHS[2], "sha256": digest, "bytes": 1}},
            "audit_binding": {"path": verifier.FORMAL_PATHS[4], "sha256": digest, "bytes": 1, "binding_sha256": "0" * 64},
            "claims": {key: False for key in verifier.CLAIMS},
        }
        core = {key: manifest[key] for key in ("schema", "version", "status", "preparation", "harness", "evidence", "claims")}
        core["audit_path"] = manifest["audit_binding"]["path"]
        manifest["audit_binding"]["binding_sha256"] = hashlib.sha256(json.dumps(core, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        verifier.validate_manifest_shape(manifest)
        for mutate in (lambda x: x.update(extra=True), lambda x: x.update(version=True), lambda x: x["claims"].update(numeric_parity=True)):
            value = copy.deepcopy(manifest); mutate(value)
            with self.assertRaises(verifier.VerifyError):
                verifier.validate_manifest_shape(value)


if __name__ == "__main__":
    unittest.main()
