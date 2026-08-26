"""Mutation tests for the COM v5 formal replay evidence gate."""

from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import yaml

try:
    import tools.verify_com_workbook_accm_replay_v5 as verifier
except ModuleNotFoundError as error:
    if error.name != "tools":
        raise
    import verify_com_workbook_accm_replay_v5 as verifier


DEFAULT_MANIFEST = verifier.DEFAULT_MANIFEST
VerificationError = verifier.VerificationError
validate = verifier.validate
validate_verification_gate = verifier.validate_verification_gate


class ComWorkbookAccmV5FormalVerifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if DEFAULT_MANIFEST.is_file():
            cls.document = yaml.safe_load(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
        else:
            # Commit 1 intentionally contains only the trust-root verifier and
            # its tests.  The formal evidence bundle arrives in Commit 2.
            cls.document = None

    def verify_mutation(self, mutate) -> None:
        if self.formal_bundle_deferred:
            self.skipTest("formal evidence bundle is deferred until Commit 2")
        document = copy.deepcopy(self.document)
        root, path = self.copy_bundle()
        mutate(document)
        self.write_manifest(path, document)
        with self.assertRaises(VerificationError):
            validate(path, repo_root=root)

    def copy_bundle(self) -> tuple[Path, Path]:
        if self.formal_bundle_deferred:
            self.skipTest("formal evidence bundle is deferred until Commit 2")
        parent = Path(tempfile.mkdtemp(prefix="com-v5-evidence-clone-"))
        root = parent / "checkout"
        self.addCleanup(shutil.rmtree, parent, ignore_errors=True)
        completed = subprocess.run(
            ["git", "-c", "core.autocrlf=false", "clone", "--no-hardlinks", "--quiet", str(verifier.ROOT), str(root)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

        manifest = DEFAULT_MANIFEST
        document = yaml.safe_load(manifest.read_text(encoding="utf-8"))
        formal_paths = [
            manifest.relative_to(verifier.ROOT).as_posix(),
            document["audit"]["path"],
            document["aggregate"]["path"],
            *(binding["path"] for binding in document["runs"]),
        ]
        for relative in formal_paths:
            source = verifier.ROOT / relative
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

        # Commit 1 contains the gate files, but this fallback keeps the test
        # useful while the two formal verifier files are still untracked.
        for relative in verifier.VERIFICATION_GATE_FILES.values():
            target = root / relative
            if not target.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(verifier.ROOT / relative, target)

        # The source checkout is Commit 1 while formal evidence belongs to
        # Commit 2.  Record the copied five-file bundle in this disposable
        # checkout so HEAD is a real descendant of the gate before validating.
        self.git(root, "config", "user.name", "COM v5 test")
        self.git(root, "config", "user.email", "com-v5-test@example.invalid")
        self.git(root, "add", *formal_paths)
        self.git(root, "commit", "--quiet", "--allow-empty", "-m", "temporary formal evidence record")

        path = root / verifier.MANIFEST_RELATIVE
        baseline = validate(path, repo_root=root)
        self.assertEqual(baseline["formal_replays"], 2)
        return root, path

    @property
    def formal_bundle_deferred(self) -> bool:
        if self.document is None:
            return True
        gate = self.document.get("verification_gate")
        return not isinstance(gate, dict) or gate.get("commit") == "0" * 40

    def copy_bundle_without_git(self) -> tuple[Path, Path]:
        if self.formal_bundle_deferred:
            self.skipTest("formal evidence bundle is deferred until Commit 2")
        root = Path(tempfile.mkdtemp(prefix="com-v5-evidence-no-git-"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        manifest = DEFAULT_MANIFEST
        document = yaml.safe_load(manifest.read_text(encoding="utf-8"))
        paths = [
            manifest.relative_to(verifier.ROOT).as_posix(),
            document["audit"]["path"],
            document["aggregate"]["path"],
            *(binding["path"] for binding in document["runs"]),
            *verifier.VERIFICATION_GATE_FILES.values(),
        ]
        for relative in paths:
            source = verifier.ROOT / relative
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        return root, root / verifier.MANIFEST_RELATIVE

    @staticmethod
    def write_manifest(path: Path, document: dict) -> None:
        path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8", newline="\n")

    @staticmethod
    def digest(path: Path) -> tuple[int, str]:
        payload = path.read_bytes()
        return len(payload), hashlib.sha256(payload).hexdigest()

    @staticmethod
    def git(root: Path, *arguments: str, check: bool = True) -> str:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        if check and completed.returncode != 0:
            raise AssertionError(completed.stderr)
        return completed.stdout.strip()

    def synthetic_gate_repo(self) -> tuple[Path, dict]:
        root = Path(tempfile.mkdtemp(prefix="com-v5-gate-repo-"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        (root / "tools").mkdir()
        payloads = {
            "verifier": b"synthetic verifier source\n",
            "mutation_tests": b"synthetic mutation test source\n",
        }
        paths = verifier.VERIFICATION_GATE_FILES
        for role, relative in paths.items():
            (root / relative).write_bytes(payloads[role])
        self.git(root, "init", "--quiet")
        self.git(root, "config", "user.name", "COM v5 test")
        self.git(root, "config", "user.email", "com-v5-test@example.invalid")
        self.git(root, "add", "tools")
        self.git(root, "commit", "--quiet", "-m", "gate")
        gate_commit = self.git(root, "rev-parse", "HEAD")
        gate_tree = self.git(root, "rev-parse", "HEAD^{tree}")
        files = {}
        for role, relative in paths.items():
            payload = payloads[role]
            files[role] = {
                "path": relative,
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "git_blob_sha1": self.git(root, "rev-parse", f"HEAD:{relative}"),
            }
        # A second commit makes the gate a strict ancestor of the record HEAD.
        (root / "record.txt").write_text("record\n", encoding="utf-8")
        self.git(root, "add", "record.txt")
        self.git(root, "commit", "--quiet", "-m", "record")
        document = {"verification_gate": {"commit": gate_commit, "tree": gate_tree, "files": files}}
        return root, document

    def test_baseline_is_valid(self):
        if self.document is None:
            self.skipTest("formal evidence bundle is deferred until Commit 2")
        gate = self.document.get("verification_gate")
        if not isinstance(gate, dict) or gate.get("commit") == "0" * 40:
            self.skipTest("formal baseline is intentionally deferred until Commit 2 installs the Commit 1 gate")
        if self.git(verifier.ROOT, "rev-parse", "HEAD") == gate.get("commit"):
            self.skipTest("formal manifest is present but Commit 2 has not yet advanced HEAD")
        result = validate()
        self.assertEqual(result["formal_replays"], 2)
        self.assertEqual(result["status"], "scoped_mismatch_observed")
        self.assertEqual(result["port_order"], "not_observed")

    def test_status_promotion_fails(self):
        self.verify_mutation(lambda value: value.update(status="passed"))

    def test_scope_acceptance_promotion_fails(self):
        self.verify_mutation(lambda value: value["scope"].update(acceptance=True))

    def test_scope_acceptance_integer_zero_fails(self):
        self.verify_mutation(lambda value: value["scope"].update(acceptance=0))

    def test_claim_numeric_parity_fails(self):
        self.verify_mutation(lambda value: value["claims"].update(numeric_parity=True))

    def test_claim_numeric_parity_integer_zero_fails(self):
        self.verify_mutation(lambda value: value["claims"].update(numeric_parity=0))

    def test_non_claim_removal_fails(self):
        self.verify_mutation(lambda value: value["non_claims"].pop())

    def test_harness_commit_drift_fails(self):
        self.verify_mutation(lambda value: value["harness"].update(source_commit="0" * 40))

    def test_harness_blob_drift_fails(self):
        self.verify_mutation(lambda value: value["harness"]["files"][0].update(git_blob_sha1="0" * 40))

    def test_harness_file_digest_drift_fails(self):
        self.verify_mutation(lambda value: value["harness"]["files"][1].update(sha256="0" * 64))

    def test_candidate_commit_drift_fails(self):
        self.verify_mutation(lambda value: value["candidate"].update(commit="0" * 40))

    def test_candidate_archive_drift_fails(self):
        self.verify_mutation(lambda value: value["candidate"]["archive"].update(sha256="0" * 64))

    def test_upstream_tree_drift_fails(self):
        self.verify_mutation(lambda value: value["upstream"].update(tree="0" * 40))

    def test_fixture_digest_drift_fails(self):
        self.verify_mutation(lambda value: value["fixtures"]["s4p"].update(sha256="0" * 64))

    def test_toolchain_digest_drift_fails(self):
        self.verify_mutation(lambda value: value["toolchain"].update(sha256="0" * 64))

    def test_toolchain_role_drift_fails(self):
        self.verify_mutation(lambda value: value["toolchain"].update(roles=["cargo"]))

    def test_first_report_path_drift_fails(self):
        self.verify_mutation(lambda value: value["runs"][0].update(path="docs/baselines/other.json"))

    def test_first_report_digest_drift_fails(self):
        self.verify_mutation(lambda value: value["runs"][0].update(sha256="0" * 64))

    def test_first_report_byte_drift_fails(self):
        self.verify_mutation(lambda value: value["runs"][0].update(bytes=1))

    def test_run_id_drift_fails(self):
        self.verify_mutation(lambda value: value["runs"][0].update(run_id="0" * 64))

    def test_duplicate_nonce_fails(self):
        self.verify_mutation(lambda value: value["runs"][1].update(nonce=value["runs"][0]["nonce"]))

    def test_binary_receipt_drift_fails(self):
        self.verify_mutation(lambda value: value["runs"][1]["binary_post"].update(sha256="0" * 64))

    def test_aggregate_digest_drift_fails(self):
        self.verify_mutation(lambda value: value["aggregate"].update(sha256="0" * 64))

    def test_aggregate_blocker_removal_fails(self):
        self.verify_mutation(lambda value: value["aggregate"].update(blockers=[]))

    def test_observation_numeric_digest_drift_fails(self):
        self.verify_mutation(lambda value: value["observations"][0].update(comparison_sha256="0" * 64))

    def test_observation_numeric_value_drift_fails(self):
        self.verify_mutation(lambda value: value["observations"][0]["comparison"][0].update(port_order_status="observed"))

    def test_observation_index_bool_fails(self):
        self.verify_mutation(lambda value: value["observations"][0].update(index=False))

    def test_observation_dfe_integer_zero_fails(self):
        self.verify_mutation(lambda value: value["observations"][0]["comparison"][0]["dfe"].update(candidate_published=0))

    def test_observation_array_receipt_drift_fails(self):
        self.verify_mutation(lambda value: value["observations"][0]["candidate_cases"][0]["channel_impulse"].update(sample_count=1))

    def test_observation_artifact_drift_fails(self):
        self.verify_mutation(lambda value: value["observations"][1]["artifacts"]["run2"].update(artifact_sha256="0" * 64))

    def test_audit_digest_drift_fails(self):
        self.verify_mutation(lambda value: value["audit"].update(sha256="0" * 64))

    def test_audit_path_drift_fails(self):
        self.verify_mutation(lambda value: value["audit"].update(path="docs/baselines/audits/other.md"))

    def test_verifier_inventory_drift_fails(self):
        self.verify_mutation(lambda value: value["verification_gate"]["files"]["verifier"].update(sha256="0" * 64))

    def test_mutation_test_inventory_drift_fails(self):
        self.verify_mutation(lambda value: value["verification_gate"]["files"]["mutation_tests"].update(bytes=1))

    def test_copied_root_is_self_contained(self):
        root, manifest = self.copy_bundle_without_git()
        with self.assertRaises(VerificationError):
            validate(manifest, repo_root=root)

    def test_physical_report_append_fails(self):
        root, manifest = self.copy_bundle()
        document = yaml.safe_load(manifest.read_text(encoding="utf-8"))
        report = root / document["runs"][0]["path"]
        report.write_bytes(report.read_bytes() + b"\n")
        with self.assertRaises(VerificationError):
            validate(manifest, repo_root=root)

    def test_physical_report_append_and_receipt_sync_cannot_bypass_anchor(self):
        root, manifest = self.copy_bundle()
        document = yaml.safe_load(manifest.read_text(encoding="utf-8"))
        report = root / document["runs"][0]["path"]
        report.write_bytes(report.read_bytes() + b"\n")
        bytes_count, digest = self.digest(report)
        document["runs"][0].update(bytes=bytes_count, sha256=digest)
        document["anchors"]["reports"][0].update(bytes=bytes_count, sha256=digest)
        self.write_manifest(manifest, document)
        with self.assertRaises(VerificationError):
            validate(manifest, repo_root=root)

    def test_physical_aggregate_append_and_receipt_sync_cannot_bypass_anchor(self):
        root, manifest = self.copy_bundle()
        document = yaml.safe_load(manifest.read_text(encoding="utf-8"))
        aggregate = root / document["aggregate"]["path"]
        aggregate.write_bytes(aggregate.read_bytes() + b"\n")
        bytes_count, digest = self.digest(aggregate)
        document["aggregate"].update(bytes=bytes_count, sha256=digest)
        document["anchors"]["aggregate"].update(bytes=bytes_count, sha256=digest)
        self.write_manifest(manifest, document)
        with self.assertRaises(VerificationError):
            validate(manifest, repo_root=root)

    def test_physical_audit_append_and_receipt_sync_cannot_bypass_anchor(self):
        root, manifest = self.copy_bundle()
        document = yaml.safe_load(manifest.read_text(encoding="utf-8"))
        audit = root / document["audit"]["path"]
        audit.write_bytes(audit.read_bytes() + b"\n")
        bytes_count, digest = self.digest(audit)
        document["audit"].update(bytes=bytes_count, sha256=digest)
        document["anchors"]["audit"].update(bytes=bytes_count, sha256=digest)
        self.write_manifest(manifest, document)
        with self.assertRaises(VerificationError):
            validate(manifest, repo_root=root)

    def test_full_report_aggregate_audit_coordination_attack_fails(self):
        root, manifest = self.copy_bundle()
        document = yaml.safe_load(manifest.read_text(encoding="utf-8"))

        report = root / document["runs"][0]["path"]
        report.write_bytes(report.read_bytes() + b"\n")
        report_bytes, report_sha = self.digest(report)
        document["runs"][0].update(bytes=report_bytes, sha256=report_sha)
        document["anchors"]["reports"][0].update(bytes=report_bytes, sha256=report_sha)

        aggregate = root / document["aggregate"]["path"]
        aggregate.write_bytes(aggregate.read_bytes() + b"\n")
        aggregate_bytes, aggregate_sha = self.digest(aggregate)
        document["aggregate"].update(bytes=aggregate_bytes, sha256=aggregate_sha)
        document["anchors"]["aggregate"].update(bytes=aggregate_bytes, sha256=aggregate_sha)

        audit = root / document["audit"]["path"]
        audit.write_bytes(audit.read_bytes() + b"\n")
        audit_bytes, audit_sha = self.digest(audit)
        document["audit"].update(bytes=audit_bytes, sha256=audit_sha)
        document["anchors"]["audit"].update(bytes=audit_bytes, sha256=audit_sha)

        self.write_manifest(manifest, document)
        with self.assertRaises(VerificationError):
            validate(manifest, repo_root=root)

    def test_audit_integer_zero_bool_fails(self):
        if self.document is None:
            self.skipTest("formal evidence bundle is deferred until Commit 2")
        root, manifest = self.copy_bundle()
        document = yaml.safe_load(manifest.read_text(encoding="utf-8"))
        audit = root / document["audit"]["path"]
        contents = audit.read_text(encoding="utf-8")
        self.assertIn("  matched: false", contents)
        contents = contents.replace("  matched: false", "  matched: 0", 1)
        audit.write_text(contents, encoding="utf-8", newline="\n")
        audit_bytes, audit_sha = self.digest(audit)
        document["audit"].update(bytes=audit_bytes, sha256=audit_sha)
        document["anchors"]["audit"].update(bytes=audit_bytes, sha256=audit_sha)
        self.write_manifest(manifest, document)

        original_binding = verifier.AUDIT_BINDING
        verifier.AUDIT_BINDING = {**original_binding, "bytes": audit_bytes, "sha256": audit_sha}
        try:
            with self.assertRaises(VerificationError):
                validate(manifest, repo_root=root)
        finally:
            verifier.AUDIT_BINDING = original_binding

    def test_synthetic_gate_is_valid(self):
        root, document = self.synthetic_gate_repo()
        self.assertIsNone(validate_verification_gate(document, root))

    def test_gate_head_is_not_strict_ancestor(self):
        root, document = self.synthetic_gate_repo()
        gate = document["verification_gate"]
        gate["commit"] = self.git(root, "rev-parse", "HEAD")
        gate["tree"] = self.git(root, "rev-parse", "HEAD^{tree}")
        with self.assertRaises(VerificationError):
            validate_verification_gate(document, root)

    def test_gate_non_ancestor_fails(self):
        root, document = self.synthetic_gate_repo()
        gate = document["verification_gate"]
        gate["commit"] = self.git(root, "commit-tree", gate["tree"], "-m", "unrelated")
        with self.assertRaises(VerificationError):
            validate_verification_gate(document, root)

    def test_gate_missing_commit_fails(self):
        root, document = self.synthetic_gate_repo()
        document["verification_gate"].update(commit="f" * 40, tree="f" * 40)
        with self.assertRaises(VerificationError):
            validate_verification_gate(document, root)

    def test_gate_tree_drift_fails(self):
        root, document = self.synthetic_gate_repo()
        document["verification_gate"]["tree"] = "0" * 40
        with self.assertRaises(VerificationError):
            validate_verification_gate(document, root)

    def test_gate_only_test_file_change_fails(self):
        root, document = self.synthetic_gate_repo()
        document["verification_gate"]["files"]["mutation_tests"]["sha256"] = "0" * 64
        with self.assertRaises(VerificationError):
            validate_verification_gate(document, root)

    def test_gate_verifier_blob_change_fails(self):
        root, document = self.synthetic_gate_repo()
        document["verification_gate"]["files"]["verifier"]["git_blob_sha1"] = "0" * 40
        with self.assertRaises(VerificationError):
            validate_verification_gate(document, root)

    def test_gate_file_set_change_fails(self):
        root, document = self.synthetic_gate_repo()
        document["verification_gate"]["files"].pop("verifier")
        with self.assertRaises(VerificationError):
            validate_verification_gate(document, root)

    def test_gate_path_swap_and_escape_fail(self):
        for path in ("tools/test_verify_com_workbook_accm_replay_v5.py", "../tools/verify_com_workbook_accm_replay_v5.py", "C:/outside.py"):
            root, document = self.synthetic_gate_repo()
            document["verification_gate"]["files"]["verifier"]["path"] = path
            with self.assertRaises(VerificationError):
                validate_verification_gate(document, root)

    def test_gate_symlink_is_rejected(self):
        root, document = self.synthetic_gate_repo()
        verifier_path = root / verifier.VERIFICATION_GATE_FILES["verifier"]
        outside = root / "outside-source.py"
        outside.write_bytes(verifier_path.read_bytes())
        verifier_path.unlink()
        try:
            verifier_path.symlink_to(outside)
        except OSError as error:
            self.skipTest(f"symlink creation unavailable: {error}")
        with self.assertRaises(VerificationError):
            validate_verification_gate(document, root)

    def test_gate_current_source_drift_fails(self):
        root, document = self.synthetic_gate_repo()
        verifier_path = root / verifier.VERIFICATION_GATE_FILES["verifier"]
        verifier_path.write_bytes(b"tampered\n")
        with self.assertRaises(VerificationError):
            validate_verification_gate(document, root)

    def test_gate_without_git_fails_closed(self):
        root, document = self.synthetic_gate_repo()
        copied = Path(tempfile.mkdtemp(prefix="com-v5-gate-no-git-"))
        self.addCleanup(shutil.rmtree, copied, ignore_errors=True)
        shutil.copytree(root / "tools", copied / "tools")
        with self.assertRaises(VerificationError):
            validate_verification_gate(document, copied)


if __name__ == "__main__":
    unittest.main()
