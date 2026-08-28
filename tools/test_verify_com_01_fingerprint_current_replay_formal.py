"""Mutation tests for the COM-01 Stage2 formal-gate contract."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest
import hashlib
import json
import os
import shutil
import stat
import subprocess
import tempfile
from unittest import mock

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from verify_com_01_fingerprint_current_replay_formal import (  # noqa: E402
    AUDIT_NORMALIZED,
    AUDIT_PATH,
    FORMAL_GATE_PATHS,
    FORMAL_GATE_PARENT,
    FORMAL_RECORD_PATHS,
    FORMAL_SCHEMA,
    FORMAL_STATUS,
    PREP_COMMIT,
    _canonical,
    _parse_audit,
    validate_audit_receipt,
    validate_formal_gate,
    validate_formal_bundle,
    validate_formal_record,
)
import verify_com_01_fingerprint_current_replay_formal as formal_module  # noqa: E402
from verify_com_01_fingerprint_current_replay import VerificationError  # noqa: E402


def gate_fixture() -> dict[str, object]:
    return {
        "commit": "a" * 40,
        "parent": FORMAL_GATE_PARENT,
        "tree": "b" * 40,
        "changed_paths": list(FORMAL_GATE_PATHS),
        "first_introduction": True,
        "formal_artifacts_absent": True,
        "files": [
            {"path": path, "git_blob_sha1": "c" * 40, "bytes": 1, "content_sha256": "d" * 64}
            for path in FORMAL_GATE_PATHS
        ],
    }


class FormalGateTests(unittest.TestCase):
    def test_gate_contract_is_exact(self) -> None:
        validate_formal_gate(gate_fixture())

    def test_gate_path_mutation_rejected(self) -> None:
        value = gate_fixture()
        value["changed_paths"] = [FORMAL_GATE_PATHS[0], "tools/other.py"]
        with self.assertRaises(VerificationError):
            validate_formal_gate(value)

    def test_gate_file_digest_shape_is_not_a_binding(self) -> None:
        value = gate_fixture()
        value["files"][1]["content_sha256"] = "e" * 64
        with self.assertRaises(VerificationError):
            validate_formal_gate(value, repo_root=Path(__file__).resolve().parents[1])

    def test_test_source_is_a_gate_member(self) -> None:
        relative = Path(__file__).resolve().relative_to(Path(__file__).resolve().parents[1]).as_posix()
        self.assertEqual(relative, FORMAL_GATE_PATHS[1])

    def test_temporary_git_ancestor_failure_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="com01-gate-no-ancestor-") as directory:
            with self.assertRaises(VerificationError):
                validate_formal_gate(gate_fixture(), repo_root=Path(directory))


def _temporary_gate(*drift_paths: str) -> tuple[Path, dict[str, object], str]:
    root = Path(tempfile.mkdtemp(prefix="com01-gate-drift-"))
    git = shutil.which("git.exe") or shutil.which("git")
    subprocess.run([git, "init", "--quiet", str(root)], check=True)
    subprocess.run([git, "-C", str(root), "config", "user.name", "formal gate test"], check=True)
    subprocess.run([git, "-C", str(root), "config", "user.email", "formal-gate@example.invalid"], check=True)
    for relative in (*formal_module.HARNESS_FILES, formal_module.CRATE_RELATIVE.as_posix() + "/Cargo.toml"):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"base\n")
    subprocess.run([git, "-C", str(root), "add", "."], check=True)
    subprocess.run([git, "-C", str(root), "commit", "--quiet", "-m", "base"], check=True)
    parent = subprocess.check_output([git, "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    for relative in FORMAL_GATE_PATHS:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((Path(__file__).resolve().parent / Path(relative).name).read_bytes())
    for relative in drift_paths:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"drift\n")
    subprocess.run([git, "-C", str(root), "add", "."], check=True)
    subprocess.run([git, "-C", str(root), "commit", "--quiet", "-m", "gate"], check=True)
    commit = subprocess.check_output([git, "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    tree = subprocess.check_output([git, "-C", str(root), "rev-parse", "HEAD^{tree}"], text=True).strip()
    files = []
    for relative in FORMAL_GATE_PATHS:
        payload = (root / relative).read_bytes()
        blob = subprocess.check_output([git, "-C", str(root), "rev-parse", f"HEAD:{relative}"], text=True).strip()
        files.append({"path": relative, "git_blob_sha1": blob, "bytes": len(payload), "content_sha256": hashlib.sha256(payload).hexdigest()})
    return root, {"commit": commit, "parent": parent, "tree": tree, "changed_paths": list(FORMAL_GATE_PATHS), "first_introduction": True, "formal_artifacts_absent": True, "files": files}, parent


def _remove_tree(path: Path) -> None:
    def remove_readonly(function, target, _error):
        os.chmod(target, stat.S_IWRITE)
        function(target)

    shutil.rmtree(path, onerror=remove_readonly)


def _temporary_record() -> tuple[Path, dict[str, object], str]:
    root = Path(tempfile.mkdtemp(prefix="com01-record-"))
    git = shutil.which("git.exe") or shutil.which("git")
    subprocess.run([git, "init", "--quiet", str(root)], check=True)
    subprocess.run([git, "-C", str(root), "config", "user.name", "formal record test"], check=True)
    subprocess.run([git, "-C", str(root), "config", "user.email", "formal-record@example.invalid"], check=True)
    (root / "README").write_bytes(b"gate\n")
    subprocess.run([git, "-C", str(root), "add", "README"], check=True)
    subprocess.run([git, "-C", str(root), "commit", "--quiet", "-m", "gate"], check=True)
    gate = subprocess.check_output([git, "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    for relative in FORMAL_RECORD_PATHS:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"record\n")
    subprocess.run([git, "-C", str(root), "add", "."], check=True)
    subprocess.run([git, "-C", str(root), "commit", "--quiet", "-m", "record"], check=True)
    commit = subprocess.check_output([git, "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    tree = subprocess.check_output([git, "-C", str(root), "rev-parse", "HEAD^{tree}"], text=True).strip()
    files = []
    for relative in FORMAL_RECORD_PATHS:
        payload = (root / relative).read_bytes()
        blob = subprocess.check_output([git, "-C", str(root), "rev-parse", f"HEAD:{relative}"], text=True).strip()
        files.append({"path": relative, "git_blob_sha1": blob, "bytes": len(payload), "content_sha256": hashlib.sha256(payload).hexdigest()})
    return root, {"commit": commit, "parent": gate, "tree": tree, "changed_paths": list(FORMAL_RECORD_PATHS), "first_introduction": True, "files": files, "worktree_clean": True}, gate


def _future_manifest_repo() -> tuple[Path, Path]:
    git = shutil.which("git.exe") or shutil.which("git")
    root = Path(tempfile.mkdtemp(prefix="com01-future-manifest-"))
    subprocess.run([git, "-c", "core.autocrlf=false", "clone", "--no-hardlinks", "--quiet", str(Path(__file__).resolve().parents[1]), str(root)], check=True)
    subprocess.run([git, "-C", str(root), "config", "core.autocrlf", "false"], check=True)
    subprocess.run([git, "-C", str(root), "config", "user.name", "future manifest test"], check=True)
    subprocess.run([git, "-C", str(root), "config", "user.email", "future-manifest@example.invalid"], check=True)
    gate = subprocess.check_output([git, "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    gate_parent = subprocess.check_output([git, "-C", str(root), "rev-parse", f"{gate}^"], text=True).strip()
    gate_tree = subprocess.check_output([git, "-C", str(root), "rev-parse", f"{gate}^{{tree}}"], text=True).strip()
    gate_files = []
    for relative in FORMAL_GATE_PATHS:
        payload = subprocess.check_output([git, "-C", str(root), "show", f"{gate}:{relative}"])
        gate_files.append({"path": relative, "git_blob_sha1": subprocess.check_output([git, "-C", str(root), "rev-parse", f"{gate}:{relative}"], text=True).strip(), "bytes": len(payload), "content_sha256": hashlib.sha256(payload).hexdigest()})
    scope = {"work_item": "COM-01", "leaf": "config-validate", "acceptance": False, "binary_claim": "raw_sha256_per_replay_only", "parity_claim": "scoped_exact_fingerprint_only"}
    report_items = []
    for index, run_id in enumerate(("1" * 64, "2" * 64), 1):
        report = {"run_id": run_id, "fresh_run_nonce": str(index) * 64, "candidate": {"build": {"binary_post": {"sha256": "a" * 64}}}}
        path = root / FORMAL_RECORD_PATHS[index - 1]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
        report_items.append({"path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "run_id": run_id, "fresh_run_nonce": str(index) * 64, "candidate_binary_sha256": "a" * 64})
    aggregate_path = root / FORMAL_RECORD_PATHS[2]
    aggregate_path.write_text("{}", encoding="utf-8")
    audit_path = root / AUDIT_PATH
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(AUDIT_NORMALIZED, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    manifest = {"schema": FORMAL_SCHEMA, "status": FORMAL_STATUS, "scope": scope, "formal_gate": {"commit": gate, "parent": gate_parent, "tree": gate_tree, "changed_paths": list(FORMAL_GATE_PATHS), "first_introduction": True, "formal_artifacts_absent": True, "files": gate_files}, "prep": {"commit": formal_module.PREP_COMMIT, "tree": formal_module.PREP_TREE, "parent": formal_module.PREP_PARENT_COMMIT, "candidate_commit": formal_module.CANDIDATE_COMMIT, "candidate_tree": formal_module.CANDIDATE_TREE, "production_path_unchanged": True}, "reports": report_items, "aggregate": {"path": aggregate_path.name, "sha256": hashlib.sha256(aggregate_path.read_bytes()).hexdigest()}, "audit": {"path": AUDIT_PATH, "sha256": hashlib.sha256(audit_path.read_bytes()).hexdigest(), "canonical_sha256": hashlib.sha256(_canonical(AUDIT_NORMALIZED)).hexdigest(), "normalized": AUDIT_NORMALIZED}, "artifact_policy": "hash_counts_and_exactness_only_no_configuration_payloads", "non_claims": list(AUDIT_NORMALIZED["non_claims"])}
    manifest_path = root / FORMAL_RECORD_PATHS[3]
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    subprocess.run([git, "-C", str(root), "add", "--", *FORMAL_RECORD_PATHS], check=True)
    subprocess.run([git, "-C", str(root), "commit", "--quiet", "-m", "formal record"], check=True)
    return root, manifest_path


def audit_receipt() -> dict[str, object]:
    return {"path": AUDIT_PATH, "sha256": "a" * 64, "canonical_sha256": hashlib.sha256(_canonical(AUDIT_NORMALIZED)).hexdigest(), "normalized": AUDIT_NORMALIZED}


class FutureManifestAuditTests(unittest.TestCase):
    def test_audit_swap_rejected(self) -> None:
        value = audit_receipt()
        value["path"] = "docs/baselines/audits/swapped.md"
        with self.assertRaises(VerificationError):
            validate_audit_receipt(value)

    def test_audit_marker_drift_rejected(self) -> None:
        value = audit_receipt()
        value["normalized"] = dict(AUDIT_NORMALIZED, exact=False)
        with self.assertRaises(VerificationError):
            validate_audit_receipt(value)

    def test_audit_promotion_with_synchronized_sha_rejected(self) -> None:
        value = dict(AUDIT_NORMALIZED)
        value["claims"] = ["raw_sha256_per_replay_only", "release_readiness"]
        raw = (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode("ascii")
        with tempfile.TemporaryDirectory(prefix="com01-audit-promotion-") as directory:
            path = Path(directory) / "audit.md"
            path.write_bytes(raw)
            with self.assertRaises(VerificationError):
                _parse_audit(path, AUDIT_NORMALIZED, hashlib.sha256(_canonical(value)).hexdigest())

    def test_audit_manifest_reciprocal_drift_rejected(self) -> None:
        value = audit_receipt()
        value["normalized"] = dict(AUDIT_NORMALIZED, claims=["scoped_exact_fingerprint_only", "raw_sha256_per_replay_only"])
        with self.assertRaises(VerificationError):
            validate_audit_receipt(value)

    def test_temporary_git_crate_drift_rejected(self) -> None:
        relative = formal_module.CRATE_RELATIVE.as_posix() + "/Cargo.toml"
        root, gate, parent = _temporary_gate(relative)
        try:
            with mock.patch.object(formal_module, "PREP_COMMIT", parent), mock.patch.object(formal_module, "FORMAL_GATE_PARENT", parent):
                with self.assertRaises(VerificationError):
                    validate_formal_gate(gate, repo_root=root)
        finally:
            _remove_tree(root)

    def test_temporary_git_stage1_harness_drift_rejected(self) -> None:
        root, gate, parent = _temporary_gate(formal_module.HARNESS_FILES[0])
        try:
            with mock.patch.object(formal_module, "PREP_COMMIT", parent), mock.patch.object(formal_module, "FORMAL_GATE_PARENT", parent):
                with self.assertRaises(VerificationError):
                    validate_formal_gate(gate, repo_root=root)
        finally:
            _remove_tree(root)

    def test_temporary_record_valid_real_git_binding(self) -> None:
        root, _, gate = _temporary_record()
        try:
            validate_formal_record(root, gate_commit=gate)
        finally:
            _remove_tree(root)

    def test_record_head_equal_gate_rejected(self) -> None:
        root, _, gate = _temporary_record()
        try:
            with self.assertRaises(VerificationError):
                validate_formal_record(root, gate_commit=subprocess.check_output([shutil.which("git.exe") or shutil.which("git"), "-C", str(root), "rev-parse", "HEAD"], text=True).strip())
        finally:
            _remove_tree(root)

    def test_record_non_descendant_rejected(self) -> None:
        root, _, gate = _temporary_record()
        try:
            gate = "0" * 40
            with self.assertRaises(VerificationError):
                validate_formal_record(root, gate_commit=gate)
        finally:
            _remove_tree(root)

    def test_record_extra_path_rejected(self) -> None:
        root, _, gate = _temporary_record()
        try:
            extra = root / "extra.json"
            extra.write_bytes(b"extra\n")
            subprocess.run([shutil.which("git.exe") or shutil.which("git"), "-C", str(root), "add", "extra.json"], check=True)
            subprocess.run([shutil.which("git.exe") or shutil.which("git"), "-C", str(root), "commit", "--quiet", "-m", "extra"], check=True)
            with self.assertRaises(VerificationError):
                validate_formal_record(root, gate_commit=gate)
        finally:
            _remove_tree(root)

    def test_record_untracked_or_dirty_rejected(self) -> None:
        root, _, gate = _temporary_record()
        try:
            (root / FORMAL_RECORD_PATHS[0]).unlink()
            with self.assertRaises(VerificationError):
                validate_formal_record(root, gate_commit=gate)
        finally:
            _remove_tree(root)

    def test_record_nonformal_untracked_rejected(self) -> None:
        root, _, gate = _temporary_record()
        try:
            (root / "not-formal.txt").write_bytes(b"untracked\n")
            with self.assertRaises(VerificationError):
                validate_formal_record(root, gate_commit=gate)
        finally:
            _remove_tree(root)

    def test_record_nonformal_tracked_dirty_rejected(self) -> None:
        root, _, gate = _temporary_record()
        try:
            (root / "README").write_bytes(b"dirty\n")
            with self.assertRaises(VerificationError):
                validate_formal_record(root, gate_commit=gate)
        finally:
            _remove_tree(root)

    def test_record_raw_live_metadata_drift_rejected(self) -> None:
        root, _, gate = _temporary_record()
        try:
            (root / FORMAL_RECORD_PATHS[0]).write_bytes(b"drift\n")
            with self.assertRaises(VerificationError):
                validate_formal_record(root, gate_commit=gate)
        finally:
            _remove_tree(root)

    def test_future_manifest_envelope_and_record_custody(self) -> None:
        """Exercise only formal envelope plus record custody, not full Stage1."""
        root, manifest = _future_manifest_repo()
        try:
            with mock.patch.object(formal_module, "verify_bundle", return_value={"fresh_replays": 2}):
                result = validate_formal_bundle(manifest, repo_root=root, upstream_root=Path(r"C:\Users\z3312\code\COM"))
            self.assertEqual(result["fresh_replays"], 2)
        finally:
            _remove_tree(root)


if __name__ == "__main__":
    unittest.main()
