"""Synthetic contract and mutation tests for the PB Stage-2 adapter."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

import aggregate_pb_01_02_candidate_matrix_stage2 as aggregate
import verify_pb_01_02_candidate_matrix_stage2 as verifier


ZERO = "0" * 64


def _fact(path: str, *, sha256: str = ZERO, bytes_count: int = 0, exclusive: bool = False) -> dict:
    identity = [1, 1, bytes_count, 1]
    result = {
        "bytes": bytes_count,
        "nlink": 1,
        "nonlink": True,
        "path": path,
        "post_identity": identity[:],
        "pre_identity": identity[:],
        "regular": True,
        "sha256": sha256,
        "single_handle_read": True,
    }
    if exclusive:
        result.update({"exclusive_create": True, "pre_absent": True, "readback_equal": True})
    return result


def _process(exit_code: int = 0) -> dict:
    return {"exit_code": exit_code, "stderr": _fact("stderr", exclusive=True), "stdout": _fact("stdout", exclusive=True)}


def _toolchain() -> dict:
    result = {"timeout_seconds": 1200}
    for role, (executable, file_sha256, version_sha256) in aggregate.TOOLCHAIN.items():
        fact = _fact(f"{role}.exe", sha256=file_sha256)
        result[role] = {
            "executable": executable,
            "file_custody_equal": True,
            "file_custody_post": copy.deepcopy(fact),
            "file_custody_pre": copy.deepcopy(fact),
            "file_sha256": file_sha256,
            "path_redacted": True,
            "role": role,
            "version_exit": 0,
            "version_sha256": version_sha256,
        }
    return result


def _side() -> dict:
    members = {}
    for member in aggregate.PB02_MEMBERS:
        members[member] = {"count": 1, "dtype": "<f8", "f64_sha256": ZERO, "fortran_order": False, "shape": [1]}
    return {
        "arrays": {"bytes": 0, "logical_members": members, "logical_sha256": ZERO, "sha256": ZERO, "uncompressed_bytes": 0},
        "meta": {"canonical_sha256": ZERO, "fields": {"$object": {"type": "object", "keys": []}}},
    }


def _input(case_id: str) -> dict:
    lane = aggregate.CASE_LANES[case_id]
    extension = "yaml" if lane == "PB-01" else "json"
    bytes_count, sha256 = aggregate.CASE_INPUTS[case_id]
    pre = _fact("input." + extension, sha256=sha256, bytes_count=bytes_count, exclusive=True)
    post = _fact("input." + extension, sha256=sha256, bytes_count=bytes_count)
    return {
        "archive_derived_input": True,
        "base_fixture": copy.deepcopy(aggregate.FIXTURES[lane]),
        "custody": {"case_id": case_id, "equal": True, "post": post, "pre": pre},
        "derived_bytes": bytes_count,
        "derived_sha256": sha256,
        "patch": copy.deepcopy(aggregate.CASE_PATCHES[case_id]),
        "patch_sha256": aggregate.CASE_PATCH_SHA256[case_id],
        "path": f"{case_id}/input.{extension}",
    }


def _artifact(case_id: str, role: str, kind: str, present: bool = True) -> dict:
    if not present:
        return {"case_id": case_id, "kind": kind, "path": f"{role}-{kind}", "present": False, "role": role}
    return {
        "bytes": 0,
        "case_id": case_id,
        "kind": kind,
        "nlink": 1,
        "nonlink": True,
        "path": f"{role}-{kind}",
        "post_identity": [1, 1, 0, 1],
        "pre_absent": True,
        "pre_identity": [1, 1, 0, 1],
        "present": True,
        "regular": True,
        "role": role,
        "sha256": ZERO,
        "single_handle_read": True,
    }


def _pb01_comparison() -> dict:
    rows = [{"length": 1, "max_abs": 0.0, "name": name, "passed": True, "scale": 1.0, "tolerance": 1.1e-6} for name in aggregate.PB01_ITEM_NAMES]
    return {
        "blockers": [],
        "candidate_process": _process(),
        "candidate_schema": {"array_keys": sorted(aggregate.PB01_SCHEMA_NAMES), "item_names": list(aggregate.PB01_SCHEMA_NAMES), "kind": "python_pickle_dict", "schema": "sipi.pybert_data.v1"},
        "class_pickle_covered_by_matrix": False,
        "kind": "pb01_selected_numeric_arrays",
        "oracle_process": _process(),
        "oracle_schema": {"kind": "PyBertData_class_pickle"},
        "rows": rows,
    }


def _case(case_id: str) -> dict:
    blockers = list(aggregate.EXPECTED_BLOCKERS[case_id])
    lane = aggregate.CASE_LANES[case_id]
    if lane == "PB-01":
        comparison = _pb01_comparison()
        artifacts = [_artifact(case_id, "candidate", "legacy_result"), _artifact(case_id, "oracle", "legacy_result")]
    else:
        is_jitter = case_id == "pb02_impulse_jitter_bathtub_analysis"
        is_eq = case_id == "pb02_impulse_tx_rx_equalization"
        comparison = {
            "candidate": None if is_eq or is_jitter else _side(),
            "candidate_process": _process(1 if is_jitter else 0),
            "kind": "pb02_complete_meta_and_logical_npz",
            "oracle": None if is_eq or is_jitter else _side(),
            "oracle_process": _process(1 if is_jitter else 0),
        }
        artifacts = []
        for role in ("candidate", "oracle"):
            for kind in ("meta", "arrays"):
                artifacts.append(_artifact(case_id, role, kind, not is_jitter))
    return {
        "artifacts": artifacts,
        "blockers": blockers,
        "comparison": comparison,
        "id": case_id,
        "input": _input(case_id),
        "lane": lane,
        "status": "passed" if not blockers else "blocked",
    }


def synthetic_report(run_index: int) -> dict:
    cases = [_case(case_id) for case_id in aggregate.CASE_IDS]
    claims = {
        "global_branch_parity": False,
        "pb01_duo_selected_array_parity": True,
        "pb02_nrz_pam4_duo_eq_logical_npz_parity": False,
        "product_capability_admission": False,
        "release_acceptance": False,
        "whole_payload_parity": False,
    }
    custody = {
        "archive_materialization": [
            {"archive_sha256": aggregate.CANDIDATE["archive_sha256"], "fact": _fact("candidate.tar", sha256=aggregate.CANDIDATE["archive_sha256"]), "role": "candidate"},
            {"archive_sha256": aggregate.UPSTREAM["archive_sha256"], "fact": _fact("upstream-pristine.tar", sha256=aggregate.UPSTREAM["archive_sha256"]), "role": "upstream_pristine"},
            {"archive_sha256": aggregate.UPSTREAM["archive_sha256"], "fact": _fact("upstream-oracle.tar", sha256=aggregate.UPSTREAM["archive_sha256"]), "role": "upstream_oracle"},
        ],
        "artifacts": [artifact for case in cases for artifact in case["artifacts"]],
        "inputs": [case["input"]["custody"] for case in cases],
        "materialized_archives_created_new": True,
        "output": {"exclusive_report": True, "fresh_root": True},
        "run_root_created_new": True,
        "run_root_path_redacted": True,
        "work_root_empty_before_run": True,
        "work_root_outside_candidate_repo": True,
        "work_root_outside_upstream_repo": True,
        "work_root_path_redacted": True,
    }
    harness = {
        "immutable_harness_commit": None,
        "legacy_matrix_primitives": {"path": "tools/run_pb_01_02_portable_matrix.py", "sha256": aggregate.HARNESS_SHA256["legacy_matrix_primitives"]},
        "native_custody_primitives": {"path": "tools/run_pb_02_direct_replay.py", "sha256": aggregate.HARNESS_SHA256["native_custody_primitives"]},
        "runner": {"path": "tools/run_pb_01_02_candidate_matrix.py", "sha256": aggregate.HARNESS_SHA256["runner"]},
        "source_mode": "working_tree_content_hash_at_replay",
    }
    modules = {name: {"file": _fact(f"{name}.py"), "owner": "venv", "relative_path": f"site-packages/{name}.py", "version": "0"} for name in ("numpy", "pybert", "scipy")}
    report = {
        "build": {"binary_pre": _fact("sipi-pybert-direct.exe", exclusive=True), "cargo_binary_source": _fact("sipi-pybert-direct.exe"), "env": {key: True for key in ("cargo_cache_lock_bound", "cargo_config_and_flags_cleared", "cargo_home_explicit", "cargo_offline", "cargo_target_external", "path_closed", "rustc_explicit", "rustc_wrappers_cleared")}, "process": _process()},
        "candidate": copy.deepcopy(aggregate.CANDIDATE),
        "cases": cases,
        "challenge": {**aggregate.CHALLENGE, "run_index": run_index},
        "claims": claims,
        "codec_boundary": {"candidate": "python_pickle_dict_sipi.pybert_data.v1", "class_codec_byte_parity": False, "comparison": "selected_numeric_arrays_only", "oracle": "PyBertData_class_pickle"},
        "corpus": copy.deepcopy(aggregate.CORPUS),
        "custody": custody,
        "fixtures": copy.deepcopy(aggregate.FIXTURES),
        "fresh_run_nonce": f"{run_index:064x}",
        "harness": harness,
        "non_claims": list(aggregate.NON_CLAIMS),
        "oracle_runtime": {"clean_archive_or_venv_only": True, "host_pythonpath_absent": True, "host_uv_flags_cleared": True, "host_virtual_env_absent": True, "modules": modules, "oracle_work_archive_sha256": aggregate.UPSTREAM["archive_sha256"], "oracle_work_started_clean": True, "process": _process(), "uv_cache_explicit_lock_bound": True, "uv_link_mode_copy": True, "uv_offline_frozen_no_config": True},
        "run_id": aggregate.RUN_IDS[run_index - 1],
        "schema": aggregate.SCHEMA,
        "source_mode": "git_archive_at_immutable_commit",
        "status": "scoped_matrix_blocked",
        "toolchain": _toolchain(),
        "upstream": copy.deepcopy(aggregate.UPSTREAM),
        "version": 1,
    }
    return report


class Stage2SyntheticTests(unittest.TestCase):
    def setUp(self) -> None:
        self.first = synthetic_report(1)
        self.second = synthetic_report(2)
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.first_path = self.root / "run-01.json"
        self.second_path = self.root / "run-02.json"
        self.first_path.write_text(json.dumps(self.first, sort_keys=True) + "\n", encoding="utf-8")
        self.second_path.write_text(json.dumps(self.second, sort_keys=True) + "\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _load(self, path: Path, run_id: str) -> tuple[dict, str]:
        return aggregate.load_report(path, run_id)

    def _write_mutated_pair(self, label: str, mutate) -> tuple[Path, Path]:
        first = copy.deepcopy(self.first)
        second = copy.deepcopy(self.second)
        mutate(first)
        mutate(second)
        first_path = self.root / f"{label}-01.json"
        second_path = self.root / f"{label}-02.json"
        first_path.write_text(json.dumps(first, sort_keys=True) + "\n", encoding="utf-8")
        second_path.write_text(json.dumps(second, sort_keys=True) + "\n", encoding="utf-8")
        return first_path, second_path

    def _assert_synchronized_report_mutation_rejected(self, label: str, mutate) -> None:
        first_path, second_path = self._write_mutated_pair(label, mutate)
        with self.assertRaises(aggregate.AggregateError):
            self._load(first_path, aggregate.RUN_IDS[0])
        with self.assertRaises(aggregate.AggregateError):
            self._load(second_path, aggregate.RUN_IDS[1])

    def _assert_synchronized_recompute_rejected(self, label: str, mutate) -> None:
        first_path, second_path = self._write_mutated_pair(label, mutate)
        first, first_hash = self._load(first_path, aggregate.RUN_IDS[0])
        second, second_hash = self._load(second_path, aggregate.RUN_IDS[1])
        with self.assertRaises(aggregate.AggregateError):
            aggregate.aggregate_documents(first, first_hash, second, second_hash, first_path, second_path)

    @staticmethod
    def _git(repo: Path, *args: str, env: dict[str, str] | None = None) -> str:
        result = subprocess.run(["git", "-c", "core.autocrlf=false", *args], cwd=repo, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, check=False)
        if result.returncode != 0:
            raise AssertionError(f"git {' '.join(args)} failed: {result.stderr}")
        return result.stdout.strip()

    def test_synthetic_reports_validate_and_aggregate(self) -> None:
        first, first_hash = self._load(self.first_path, aggregate.RUN_IDS[0])
        second, second_hash = self._load(self.second_path, aggregate.RUN_IDS[1])
        document = aggregate.aggregate_documents(first, first_hash, second, second_hash, self.first_path, self.second_path)
        self.assertEqual(document["status"], "blocked")
        self.assertTrue(document["cross_run"]["challenge_equal"])
        self.assertTrue(document["cross_run"]["case_projection_equal"])
        self.assertEqual(document["cases"][0]["status"], "passed")

    def test_aggregate_rejects_same_path_or_digest(self) -> None:
        first, digest = self._load(self.first_path, aggregate.RUN_IDS[0])
        second, _ = self._load(self.second_path, aggregate.RUN_IDS[1])
        with self.assertRaises(aggregate.AggregateError):
            aggregate.aggregate_documents(first, digest, second, digest, self.first_path, self.second_path)
        with self.assertRaises(aggregate.AggregateError):
            aggregate.aggregate_documents(first, digest, second, "1" * 64, self.first_path, self.first_path)

    def test_duplicate_json_key_rejected(self) -> None:
        path = self.root / "duplicate.json"
        path.write_text('{"schema":1,"schema":2}', encoding="utf-8")
        with self.assertRaises(aggregate.AggregateError):
            aggregate._load_json(path)

    def test_mutation_schema_rejected(self) -> None:
        mutated = copy.deepcopy(self.first)
        mutated["schema"] = "other"
        path = self.root / "schema.json"
        path.write_text(json.dumps(mutated), encoding="utf-8")
        with self.assertRaises(aggregate.AggregateError):
            self._load(path, aggregate.RUN_IDS[0])

    def test_mutation_nonce_rejected(self) -> None:
        mutated = copy.deepcopy(self.first)
        mutated["fresh_run_nonce"] = "not-hex"
        path = self.root / "nonce.json"
        path.write_text(json.dumps(mutated), encoding="utf-8")
        with self.assertRaises(aggregate.AggregateError):
            self._load(path, aggregate.RUN_IDS[0])

    def test_mutation_source_identity_rejected(self) -> None:
        mutated = copy.deepcopy(self.first)
        mutated["candidate"]["tree"] = "1" * 40
        path = self.root / "source.json"
        path.write_text(json.dumps(mutated), encoding="utf-8")
        with self.assertRaises(aggregate.AggregateError):
            self._load(path, aggregate.RUN_IDS[0])

    def test_mutation_toolchain_path_rejected(self) -> None:
        mutated = copy.deepcopy(self.first)
        mutated["toolchain"]["cargo"]["executable"] = "C:\\cargo.exe"
        path = self.root / "toolchain.json"
        path.write_text(json.dumps(mutated), encoding="utf-8")
        with self.assertRaises(aggregate.AggregateError):
            self._load(path, aggregate.RUN_IDS[0])

    def test_mutation_case_blocker_rejected(self) -> None:
        mutated = copy.deepcopy(self.first)
        mutated["cases"][1]["blockers"] = []
        path = self.root / "case.json"
        path.write_text(json.dumps(mutated), encoding="utf-8")
        with self.assertRaises(aggregate.AggregateError):
            self._load(path, aggregate.RUN_IDS[0])

    def test_mutation_metadata_type_rejected(self) -> None:
        mutated = copy.deepcopy(self.first)
        mutated["cases"][1]["comparison"]["candidate"]["meta"]["fields"]["$object"]["type"] = "string"
        path = self.root / "metadata.json"
        path.write_text(json.dumps(mutated), encoding="utf-8")
        with self.assertRaises(aggregate.AggregateError):
            self._load(path, aggregate.RUN_IDS[0])

    def test_mutation_npy_crossfield_rejected(self) -> None:
        mutated = copy.deepcopy(self.first)
        mutated["cases"][1]["comparison"]["candidate"]["arrays"]["logical_members"][aggregate.PB02_MEMBERS[0]]["count"] = 2
        path = self.root / "npy.json"
        path.write_text(json.dumps(mutated), encoding="utf-8")
        with self.assertRaises(aggregate.AggregateError):
            self._load(path, aggregate.RUN_IDS[0])

    def test_mutation_artifact_custody_rejected(self) -> None:
        mutated = copy.deepcopy(self.first)
        mutated["cases"][0]["artifacts"][0]["pre_absent"] = False
        path = self.root / "artifact.json"
        path.write_text(json.dumps(mutated), encoding="utf-8")
        with self.assertRaises(aggregate.AggregateError):
            self._load(path, aggregate.RUN_IDS[0])

    def test_synchronized_blocker_mutation_rejected(self) -> None:
        self._assert_synchronized_report_mutation_rejected(
            "sync-blocker",
            lambda report: report["cases"][1]["blockers"].append("unapproved_blocker"),
        )

    def test_synchronized_claim_mutation_rejected(self) -> None:
        self._assert_synchronized_report_mutation_rejected(
            "sync-claim",
            lambda report: report["claims"].__setitem__("release_acceptance", True),
        )

    def test_synchronized_candidate_upstream_mutations_rejected(self) -> None:
        self._assert_synchronized_report_mutation_rejected(
            "sync-candidate",
            lambda report: report["candidate"].__setitem__("tree", "1" * 40),
        )
        self._assert_synchronized_report_mutation_rejected(
            "sync-upstream",
            lambda report: report["upstream"].__setitem__("tree", "2" * 40),
        )

    def test_synchronized_toolchain_and_build_mutations_rejected(self) -> None:
        self._assert_synchronized_report_mutation_rejected(
            "sync-toolchain",
            lambda report: report["toolchain"]["cargo"].__setitem__("file_sha256", "3" * 64),
        )
        self._assert_synchronized_report_mutation_rejected(
            "sync-build",
            lambda report: report["build"]["binary_pre"].__setitem__("bytes", 1),
        )

    def test_synchronized_fixture_and_input_mutations_rejected(self) -> None:
        self._assert_synchronized_report_mutation_rejected(
            "sync-fixture",
            lambda report: report["fixtures"]["PB-02"].__setitem__("sha256", "4" * 64),
        )
        self._assert_synchronized_report_mutation_rejected(
            "sync-input",
            lambda report: report["cases"][1]["input"].__setitem__("derived_bytes", aggregate.CASE_INPUTS[aggregate.CASE_IDS[1]][0] + 1),
        )

    def test_synchronized_artifact_npz_and_metadata_mutations_rejected(self) -> None:
        self._assert_synchronized_report_mutation_rejected(
            "sync-artifact",
            lambda report: report["cases"][1]["artifacts"][1].__setitem__("sha256", "5" * 64),
        )
        self._assert_synchronized_report_mutation_rejected(
            "sync-npz",
            lambda report: report["cases"][1]["comparison"]["candidate"]["arrays"]["logical_members"][aggregate.PB02_MEMBERS[0]].__setitem__("count", 2),
        )
        self._assert_synchronized_report_mutation_rejected(
            "sync-meta",
            lambda report: report["cases"][1]["comparison"]["candidate"]["meta"]["fields"]["$object"].__setitem__("type", "string"),
        )

    def test_synchronized_nonce_rejected_during_recompute(self) -> None:
        self._assert_synchronized_recompute_rejected(
            "sync-nonce",
            lambda report: report.__setitem__("fresh_run_nonce", "a" * 64),
        )

    def test_synchronized_run_and_challenge_mutations_rejected(self) -> None:
        self._assert_synchronized_report_mutation_rejected(
            "sync-run",
            lambda report: report.__setitem__("run_id", "shared-run-id"),
        )
        self._assert_synchronized_report_mutation_rejected(
            "sync-challenge",
            lambda report: report["challenge"].__setitem__("run_count", 3),
        )

    def test_manifest_synthetic_baseline_and_audit(self) -> None:
        first, first_hash = self._load(self.first_path, aggregate.RUN_IDS[0])
        second, second_hash = self._load(self.second_path, aggregate.RUN_IDS[1])
        document = aggregate.aggregate_documents(first, first_hash, second, second_hash, Path("docs/baselines/pb-01-02-candidate-matrix-run-01.v1.json"), Path("docs/baselines/pb-01-02-candidate-matrix-run-02.v1.json"))
        report_facts = [{"path": aggregate.FORMAL_PATHS[index], "sha256": digest, "bytes": len(path.read_bytes())} for index, (path, digest) in enumerate(((self.first_path, first_hash), (self.second_path, second_hash)))]
        aggregate_payload = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
        aggregate_fact = {"path": aggregate.FORMAL_PATHS[2], "sha256": hashlib.sha256(aggregate_payload).hexdigest(), "bytes": len(aggregate_payload)}
        gate_files = [{"path": path, "blob": "1" * 40, "sha256": "2" * 64, "bytes": 1} for path in verifier.GATE_PATHS]
        manifest = {"schema": verifier.FORMAL_SCHEMA, "version": 1, "status": document["status"], "gate": {"commit": "3" * 40, "tree": "4" * 40, "parent": verifier.ORIGINAL_GATE_COMMIT, "files": gate_files}, "prep": aggregate._prep_binding(), "candidate": copy.deepcopy(aggregate.CANDIDATE), "upstream": copy.deepcopy(aggregate.UPSTREAM), "corpus": copy.deepcopy(aggregate.CORPUS), "fixtures": copy.deepcopy(aggregate.FIXTURES), "reports": [{**report_facts[0], "run_id": first["run_id"], "fresh_run_nonce": first["fresh_run_nonce"]}, {**report_facts[1], "run_id": second["run_id"], "fresh_run_nonce": second["fresh_run_nonce"]}], "aggregate": aggregate_fact, "audit": {"path": verifier.AUDIT_PATH, "sha256": ZERO, "bytes": 1}, "cases": document["cases"], "claims": document["claims"], "blockers": document["blockers"], "non_claims": verifier.NON_CLAIMS}
        audit_payload = verifier.expected_audit(manifest)
        manifest["audit"] = {"path": verifier.AUDIT_PATH, "sha256": hashlib.sha256(audit_payload).hexdigest(), "bytes": len(audit_payload)}
        result = verifier._validate_manifest(manifest, {"commit": "3" * 40, "tree": "4" * 40, "files": gate_files}, document, [first, second], report_facts, aggregate_fact, audit_payload)
        self.assertEqual(result["schema"], verifier.FORMAL_SCHEMA)
        mutated_prep = copy.deepcopy(manifest)
        mutated_prep["prep"]["commit"] = "5" * 40
        with self.assertRaises(verifier.VerifyError):
            verifier._validate_manifest(mutated_prep, {"commit": "3" * 40, "tree": "4" * 40, "files": gate_files}, document, [first, second], report_facts, aggregate_fact, audit_payload)
        mutated = copy.deepcopy(manifest)
        mutated["claims"]["global_branch_parity"] = True
        with self.assertRaises(verifier.VerifyError):
            verifier._validate_manifest(mutated, {"commit": "3" * 40, "tree": "4" * 40, "files": gate_files}, document, [first, second], report_facts, aggregate_fact, audit_payload)

    def test_manifest_audit_changes_with_binding(self) -> None:
        manifest = {"reports": [{"sha256": "1" * 64}, {"sha256": "2" * 64}], "aggregate": {"sha256": "3" * 64}, "status": "blocked", "gate": {"commit": "4" * 40}, "prep": {"commit": verifier.PREP_COMMIT}, "blockers": [], "claims": {}, "non_claims": []}
        expected = verifier.expected_audit(manifest)
        self.assertNotEqual(expected, expected.replace(b"blocked", b"passed", 1))

    def test_manifest_duplicate_yaml_rejected(self) -> None:
        payload = "schema: one\nschema: two\n"
        with self.assertRaises(verifier.VerifyError):
            yaml.load(payload, Loader=verifier._StrictLoader)

    def test_real_temp_successor_record_round_trip(self) -> None:
        """Exercise the exact Git custody chain and both real CLIs in a clone."""

        source = Path(__file__).resolve().parents[1]
        clone = self.root / "git-clone"
        subprocess.run(["git", "clone", "--no-local", "--no-checkout", "--quiet", str(source), str(clone)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self._git(clone, "config", "core.autocrlf", "false")
        self._git(clone, "checkout", "--detach", verifier.ORIGINAL_GATE_COMMIT)
        for relative in verifier.GATE_PATHS:
            path = clone / relative
            path.write_bytes(path.read_bytes() + b"\n# temporary Stage-2 successor mutation\n")
        self._git(clone, "add", "--", *verifier.GATE_PATHS)
        env = os.environ.copy()
        env.update({"GIT_AUTHOR_NAME": "Stage2 test", "GIT_AUTHOR_EMAIL": "stage2@example.invalid", "GIT_COMMITTER_NAME": "Stage2 test", "GIT_COMMITTER_EMAIL": "stage2@example.invalid"})
        self._git(clone, "commit", "--quiet", "-m", "test: temporary Stage2 successor", env=env)
        successor = self._git(clone, "rev-parse", "HEAD")
        successor_gate = verifier.verify_successor(clone, successor, upstream_repo=source / ".." / "Py-bert-agent")
        self.assertEqual(successor_gate["parent"], verifier.ORIGINAL_GATE_COMMIT)

        formal_paths = [clone / relative for relative in verifier.FORMAL_PATHS]
        formal_paths[0].parent.mkdir(parents=True, exist_ok=True)
        formal_paths[0].write_text(json.dumps(self.first, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        formal_paths[1].write_text(json.dumps(self.second, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        cli = clone / "tools" / "aggregate_pb_01_02_candidate_matrix_stage2.py"
        aggregate_run = subprocess.run([sys.executable, str(cli), "--first-report", str(formal_paths[0]), "--second-report", str(formal_paths[1]), "--output", str(formal_paths[2])], cwd=clone, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        self.assertEqual(aggregate_run.returncode, 1, aggregate_run.stderr)
        aggregate_document = json.loads(formal_paths[2].read_text(encoding="utf-8"))
        report_facts = []
        for path, report in zip(formal_paths[:2], (self.first, self.second)):
            payload = path.read_bytes()
            report_facts.append({"path": path.relative_to(clone).as_posix(), "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload), "run_id": report["run_id"], "fresh_run_nonce": report["fresh_run_nonce"]})
        aggregate_payload = formal_paths[2].read_bytes()
        manifest = {
            "schema": verifier.FORMAL_SCHEMA,
            "version": 1,
            "status": aggregate_document["status"],
            "gate": {"commit": successor, "tree": successor_gate["tree"], "parent": verifier.ORIGINAL_GATE_COMMIT, "files": successor_gate["files"]},
            "prep": aggregate._prep_binding(),
            "candidate": copy.deepcopy(aggregate.CANDIDATE),
            "upstream": copy.deepcopy(aggregate.UPSTREAM),
            "corpus": copy.deepcopy(aggregate.CORPUS),
            "fixtures": copy.deepcopy(aggregate.FIXTURES),
            "reports": report_facts,
            "aggregate": {"path": verifier.AGGREGATE_PATH, "sha256": hashlib.sha256(aggregate_payload).hexdigest(), "bytes": len(aggregate_payload)},
            "audit": {"path": verifier.AUDIT_PATH, "sha256": ZERO, "bytes": 1},
            "cases": aggregate_document["cases"],
            "claims": aggregate_document["claims"],
            "blockers": aggregate_document["blockers"],
            "non_claims": verifier.NON_CLAIMS,
        }
        audit_payload = verifier.expected_audit(manifest)
        manifest["audit"] = {"path": verifier.AUDIT_PATH, "sha256": hashlib.sha256(audit_payload).hexdigest(), "bytes": len(audit_payload)}
        formal_paths[3].write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
        formal_paths[4].parent.mkdir(parents=True, exist_ok=True)
        formal_paths[4].write_bytes(audit_payload)
        self._git(clone, "add", "--", *verifier.FORMAL_PATHS)
        self._git(clone, "commit", "--quiet", "-m", "test: temporary Stage-2 formal record", env=env)
        record = self._git(clone, "rev-parse", "HEAD")
        verified = verifier.verify_formal_record(clone, source / ".." / "Py-bert-agent", successor, record)
        self.assertTrue(verified["valid"])
        cli_verify = subprocess.run([sys.executable, str(source / "tools" / "verify_pb_01_02_candidate_matrix_stage2.py"), "--repository", str(clone), "--upstream-repository", str(source / ".." / "Py-bert-agent"), "--gate-commit", successor, "--record-commit", record], cwd=source, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        self.assertEqual(cli_verify.returncode, 0, cli_verify.stderr + cli_verify.stdout)
        self.assertTrue(json.loads(cli_verify.stdout)["valid"])


if __name__ == "__main__":
    unittest.main()
