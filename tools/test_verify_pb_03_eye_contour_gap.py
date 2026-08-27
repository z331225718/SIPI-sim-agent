"""Real-clone and mutation tests for the PB-03 eye/contour gate."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import yaml


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_pb_03_eye_contour_gap as gate


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _git(repo: Path, *arguments: str, raw: bool = False) -> bytes | str:
    result = subprocess.run(
        ["git", "-c", "core.autocrlf=false", "-C", str(repo), *arguments],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return result.stdout if raw else result.stdout.decode("ascii").strip()


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", "--all")
    _git(repo, "commit", "--quiet", "-m", message)
    commit = _git(repo, "rev-parse", "HEAD")
    if not isinstance(commit, str):
        raise AssertionError("commit identity type drift")
    return commit


def _configure_identity(repo: Path) -> None:
    _git(repo, "config", "user.name", "PB03 gate test")
    _git(repo, "config", "user.email", "pb03-gate@example.invalid")


def _clone(source: Path, destination: Path) -> Path:
    subprocess.run(
        ["git", "-c", "core.autocrlf=false", "clone", "--quiet", "--no-local", str(source), str(destination)],
        check=True,
    )
    _configure_identity(destination)
    return destination


def _clone_candidate(destination: Path) -> Path:
    repo = _clone(ROOT, destination)
    _git(repo, "switch", "--quiet", "--detach", gate.CANDIDATE_COMMIT)
    return repo


def _write_yaml(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8", newline="\n")


def _load_manifest(repo: Path) -> dict[str, Any]:
    value = yaml.safe_load((repo / gate.MANIFEST_PATH).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError("manifest root type drift")
    return value


def _install_gate(repo: Path) -> dict[str, Any]:
    for path in (gate.VERIFIER_PATH, gate.MUTATION_TEST_PATH):
        target = repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / path, target)
    gate_commit = _commit(repo, "pb03 eye contour gate")
    gate_tree = _git(repo, "rev-parse", "HEAD^{tree}")
    if not isinstance(gate_tree, str):
        raise AssertionError("gate tree type drift")
    files: dict[str, Any] = {}
    for label, path in (("verifier", gate.VERIFIER_PATH), ("mutation_test", gate.MUTATION_TEST_PATH)):
        payload = _git(repo, "show", f"{gate_commit}:{path}", raw=True)
        if not isinstance(payload, bytes):
            raise AssertionError("gate payload type drift")
        blob = _git(repo, "rev-parse", f"{gate_commit}:{path}")
        if not isinstance(blob, str):
            raise AssertionError("gate blob type drift")
        files[label] = {
            "path": path,
            "blob": blob,
            "bytes": len(payload),
            "sha256": _sha256(payload),
        }
    return {
        "candidate_ancestor": gate.CANDIDATE_COMMIT,
        "commit": gate_commit,
        "tree": gate_tree,
        "files": files,
    }


def _install_record(repo: Path, gate_block: dict[str, Any]) -> str:
    audit_text = gate.bound_audit(gate_block)
    audit_path = repo / gate.AUDIT_PATH
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(audit_text, encoding="utf-8", newline="\n")
    manifest = gate.future_manifest(gate_block, _sha256(audit_text.encode("utf-8")))
    _write_yaml(repo / gate.MANIFEST_PATH, manifest)
    return _commit(repo, "pb03 eye contour formal record")


def _run_verifier(repo: Path) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, str(repo / gate.VERIFIER_PATH)],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    stream = result.stdout if result.stdout.strip() else result.stderr
    try:
        payload = json.loads(stream.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as error:
        raise AssertionError(
            f"verifier produced no JSON: rc={result.returncode}, stdout={result.stdout}, stderr={result.stderr}"
        ) from error
    payload["returncode"] = result.returncode
    return payload


class EyeContourTwoStageGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.baseline_repo = _clone_candidate(Path(cls.temporary.name) / "baseline")
        cls.gate_block = _install_gate(cls.baseline_repo)
        cls.clean_gate_result = _run_verifier(cls.baseline_repo)
        cls.record_commit = _install_record(cls.baseline_repo, cls.gate_block)
        cls.baseline_result = _run_verifier(cls.baseline_repo)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    @contextmanager
    def mutation_repo(self, name: str) -> Iterator[Path]:
        with tempfile.TemporaryDirectory() as temporary:
            repo = _clone(self.baseline_repo, Path(temporary) / name)
            yield repo

    def assert_invalid(self, result: dict[str, Any], reason: str) -> None:
        self.assertFalse(result.get("valid"), result)
        self.assertNotEqual(result["returncode"], 0, result)
        self.assertIn(reason, result.get("reason", ""), result)

    def test_gate_only_checkout_explicitly_skips_formal_artifacts(self) -> None:
        self.assertTrue(self.clean_gate_result["valid"], self.clean_gate_result)
        self.assertEqual(self.clean_gate_result["returncode"], 0)
        self.assertEqual(self.clean_gate_result["status"], "skipped_formal_artifacts_absent")
        self.assertEqual(self.clean_gate_result["gate_commit"], self.gate_block["commit"])

    def test_real_clone_formal_record_baseline_is_valid(self) -> None:
        self.assertTrue(self.baseline_result["valid"], self.baseline_result)
        self.assertEqual(self.baseline_result["returncode"], 0)
        self.assertEqual(self.baseline_result["candidate_field_count"], 142)
        self.assertEqual(self.baseline_result["ordered_contour_ber_levels"], [1.0e-5, 1.0e-4, 1.0e-3])
        self.assertEqual(self.baseline_result["blocked_eye_matrices"], 10)
        self.assertEqual(self.baseline_result["blocked_response_hashes"], 7)
        self.assertFalse(self.baseline_result["whole_payload_parity"])

    def test_bool_as_int_and_count_as_float_fail_closed(self) -> None:
        with self.mutation_repo("bool-int") as repo:
            document = _load_manifest(repo)
            document["scope"]["whole_payload_parity"] = 0
            _write_yaml(repo / gate.MANIFEST_PATH, document)
            _commit(repo, "mutate bool to int")
            self.assert_invalid(_run_verifier(repo), "type drift")

        with self.mutation_repo("count-float") as repo:
            document = _load_manifest(repo)
            document["payload"]["candidate_field_count"] = 142.0
            _write_yaml(repo / gate.MANIFEST_PATH, document)
            _commit(repo, "mutate count to float")
            self.assert_invalid(_run_verifier(repo), "type drift")

    def test_recursive_extra_key_fails_closed(self) -> None:
        with self.mutation_repo("extra-key") as repo:
            document = _load_manifest(repo)
            document["payload"]["third_contour"]["extra"] = False
            _write_yaml(repo / gate.MANIFEST_PATH, document)
            _commit(repo, "add recursive extra key")
            self.assert_invalid(_run_verifier(repo), "keys drift")

    def test_candidate_source_drift_fails_closed(self) -> None:
        with self.mutation_repo("candidate-drift") as repo:
            document = _load_manifest(repo)
            document["source"]["candidate"]["tree"] = "0" * 40
            _write_yaml(repo / gate.MANIFEST_PATH, document)
            _commit(repo, "drift candidate tree")
            self.assert_invalid(_run_verifier(repo), "value drift")

    def test_gate_identity_and_current_tool_drift_fail_closed(self) -> None:
        with self.mutation_repo("gate-identity") as repo:
            document = _load_manifest(repo)
            document["git_gate"]["tree"] = "0" * 40
            _write_yaml(repo / gate.MANIFEST_PATH, document)
            _commit(repo, "drift gate identity")
            self.assert_invalid(_run_verifier(repo), "git gate tree drift")

        with self.mutation_repo("tool-drift") as repo:
            test_path = repo / gate.MUTATION_TEST_PATH
            test_path.write_text(test_path.read_text(encoding="utf-8") + "\n# record drift\n", encoding="utf-8", newline="\n")
            _commit(repo, "drift current gate tool")
            self.assert_invalid(_run_verifier(repo), "differs from git gate")

    def test_audit_coordination_fails_even_when_hash_is_rebound(self) -> None:
        with self.mutation_repo("audit-coordination") as repo:
            audit_path = repo / gate.AUDIT_PATH
            audit_text = audit_path.read_text(encoding="utf-8").replace(
                "This record binds the reviewed Rust production candidate",
                "This record weakly binds the reviewed Rust production candidate",
            )
            audit_path.write_text(audit_text, encoding="utf-8", newline="\n")
            document = _load_manifest(repo)
            document["bindings"]["audit"]["sha256"] = _sha256(audit_text.encode("utf-8"))
            _write_yaml(repo / gate.MANIFEST_PATH, document)
            _commit(repo, "coordinate mutated audit hash")
            self.assert_invalid(_run_verifier(repo), "audit coordinated content drift")

    def test_hardlinked_audit_fails_path_gate(self) -> None:
        with self.mutation_repo("hardlink") as repo:
            audit_path = repo / gate.AUDIT_PATH
            hardlink_path = audit_path.with_name("pb-03-eye-contour-hardlink.md")
            os.link(audit_path, hardlink_path)
            self.assert_invalid(_run_verifier(repo), "nlink gate")


if __name__ == "__main__":
    unittest.main()
