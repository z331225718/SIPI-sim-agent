"""Stage-1 and full-graph tests for the combined COM formal gate."""

from __future__ import annotations

import copy
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import uuid

import yaml

try:
    import tools.verify_com_01_03_current_formal as verifier
except ModuleNotFoundError as error:
    if error.name != "tools":
        raise
    import verify_com_01_03_current_formal as verifier


class ComCurrentFormalGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parent = Path(tempfile.mkdtemp(prefix="com-current-formal-test-"))
        self.addCleanup(shutil.rmtree, self.parent, ignore_errors=True)

    @staticmethod
    def git(root: Path, *arguments: str, check: bool = True) -> str:
        completed = subprocess.run(
            ["git", "-c", "core.autocrlf=false", *arguments],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if check and completed.returncode != 0:
            raise AssertionError(completed.stderr)
        return completed.stdout.strip()

    def clone_prep(self) -> Path:
        root = self.parent / f"checkout-{uuid.uuid4().hex}"
        completed = subprocess.run(
            ["git", "-c", "core.autocrlf=false", "clone", "--no-hardlinks", "--quiet", str(verifier.ROOT), str(root)],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.git(root, "checkout", "--detach", verifier.PREP_COMMIT)
        self.git(root, "config", "user.name", "COM formal test")
        self.git(root, "config", "user.email", "com-formal@example.invalid")
        return root

    def install_gate(self, root: Path) -> tuple[str, dict]:
        for relative in verifier.GATE_FILES.values():
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(verifier.ROOT / relative, destination)
        self.git(root, "add", *verifier.GATE_FILES.values())
        self.git(root, "commit", "--quiet", "-m", "formal gate")
        commit = self.git(root, "rev-parse", "HEAD")
        files = {}
        for role, relative in verifier.GATE_FILES.items():
            payload = (root / relative).read_bytes()
            files[role] = {
                "path": relative,
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "git_blob_sha1": self.git(root, "rev-parse", f"HEAD:{relative}"),
            }
        gate = {
            "schema": verifier.GATE_SCHEMA,
            "commit": commit,
            "tree": self.git(root, "rev-parse", "HEAD^{tree}"),
            "files": files,
        }
        return commit, gate

    def install_record(self) -> tuple[Path, str, str, dict[str, bytes]]:
        root = self.clone_prep()
        gate_commit, gate = self.install_gate(root)
        originals = {}
        for relative in verifier.required_bundle_paths():
            source = verifier.ROOT / relative
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        for row in verifier.ROWS.values():
            path = root / row["manifest"]
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
            document["formal_verification_gate"] = copy.deepcopy(gate)
            path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8", newline="\n")
        self.git(root, "add", *verifier.required_bundle_paths())
        self.git(root, "commit", "--quiet", "-m", "formal record")
        record = self.git(root, "rev-parse", "HEAD")
        for relative in verifier.required_bundle_paths():
            originals[relative] = (root / relative).read_bytes()
        for relative in verifier.GATE_FILES.values():
            originals[relative] = (root / relative).read_bytes()
        return root, gate_commit, record, originals

    def commit_mutation(self, root: Path, record: str, paths: list[str], mutate) -> None:
        self.git(root, "checkout", "--detach", record)
        mutate()
        self.git(root, "add", *paths)
        self.git(root, "commit", "--quiet", "-m", "attack")

    @staticmethod
    def load(path: Path) -> dict:
        return yaml.safe_load(path.read_text(encoding="utf-8"))

    @staticmethod
    def write(path: Path, value: dict) -> None:
        path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8", newline="\n")

    def mutate_manifests(self, root: Path, mutate) -> list[str]:
        paths = [row["manifest"] for row in verifier.ROWS.values()]
        for relative in paths:
            path = root / relative
            value = self.load(path)
            mutate(value)
            self.write(path, value)
        return paths

    def test_stage1_gate_without_artifacts_is_explicitly_skipped(self):
        root = self.clone_prep()
        gate_commit, _ = self.install_gate(root)
        result = verifier.verify(repo_root=root)
        self.assertEqual(result["status"], "skipped_formal_artifacts_absent")
        self.assertIs(result["formal"], False)
        self.assertEqual(result["gate_commit"], gate_commit)
        self.assertEqual(set(result["missing"]), set(verifier.required_bundle_paths()))

    def test_partial_bundle_is_blocked(self):
        root = self.clone_prep()
        self.install_gate(root)
        relative = verifier.required_bundle_paths()[0]
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(verifier.ROOT / relative, destination)
        with self.assertRaisesRegex(verifier.VerificationError, "partial formal bundle"):
            verifier.verify(repo_root=root)

    def test_temporary_record_baseline_is_valid(self):
        root, gate_commit, _, _ = self.install_record()
        result = verifier.verify(repo_root=root)
        self.assertEqual(result["status"], "valid")
        self.assertIs(result["formal"], True)
        self.assertEqual(result["rows"], {"COM-01": 2, "COM-03": 2})
        self.assertEqual(result["gate_commit"], gate_commit)

    def test_manifest_graph_attacks_are_blocked(self):
        attacks = [
            ("extra root", lambda value: value.update(extra=True)),
            ("prep commit", lambda value: value["harness"].update(commit="0" * 40)),
            ("prep tree", lambda value: value["harness"].update(tree="0" * 40)),
            ("prep blob", lambda value: value["harness"].update(runner_blob="0" * 40)),
            ("extra harness", lambda value: value["harness"].update(extra=True)),
            ("physical shrink", lambda value: value["physical"].pop()),
        ]
        for label, attack in attacks:
            with self.subTest(label=label):
                root, _, record, _ = self.install_record()
                paths = self.mutate_manifests(root, attack)
                self.git(root, "add", *paths)
                self.git(root, "commit", "--quiet", "-m", "manifest attack")
                with self.assertRaises(verifier.VerificationError):
                    verifier.verify(repo_root=root)

    def test_coordinated_report_and_audit_attacks_are_blocked(self):
        for key in ("reports", "audit"):
            with self.subTest(key=key):
                root, _, _, _ = self.install_record()
                manifest_relative = verifier.ROWS["COM-01"]["manifest"]
                manifest_path = root / manifest_relative
                document = self.load(manifest_path)
                if key == "reports":
                    relative = document["reports"][0]["path"]
                    payload = (root / relative).read_bytes() + b"\n"
                    (root / relative).write_bytes(payload)
                    document["reports"][0]["sha256"] = hashlib.sha256(payload).hexdigest()
                else:
                    relative = document["audit"]["path"]
                    payload = (root / relative).read_bytes() + b"\n"
                    (root / relative).write_bytes(payload)
                    document["audit"]["sha256"] = hashlib.sha256(payload).hexdigest()
                self.write(manifest_path, document)
                self.git(root, "add", manifest_relative, relative)
                self.git(root, "commit", "--quiet", "-m", "coordinated artifact attack")
                with self.assertRaises(verifier.VerificationError):
                    verifier.verify(repo_root=root)

    def test_gate_identity_attacks_are_blocked(self):
        attacks = [
            ("head", lambda gate, record: gate.update(commit=record)),
            ("ancestor", lambda gate, record: gate.update(commit=verifier.PREP_COMMIT)),
            ("tree", lambda gate, record: gate.update(tree="0" * 40)),
            ("blob", lambda gate, record: gate["files"]["verifier"].update(git_blob_sha1="0" * 40)),
            ("path", lambda gate, record: gate["files"]["verifier"].update(path="tools/other.py")),
            ("type", lambda gate, record: gate["files"]["verifier"].update(bytes=True)),
            ("extra", lambda gate, record: gate.update(extra=True)),
        ]
        for label, attack in attacks:
            with self.subTest(label=label):
                root, _, record, _ = self.install_record()
                paths = [row["manifest"] for row in verifier.ROWS.values()]
                for relative in paths:
                    path = root / relative
                    document = self.load(path)
                    attack(document["formal_verification_gate"], record)
                    self.write(path, document)
                self.git(root, "add", *paths)
                self.git(root, "commit", "--quiet", "-m", "gate identity attack")
                with self.assertRaises(verifier.VerificationError):
                    verifier.verify(repo_root=root)

    def test_gate_source_link_and_content_attacks_are_blocked(self):
        root, _, record, originals = self.install_record()
        relative = verifier.GATE_FILES["verifier"]
        path = root / relative
        path.write_bytes(originals[relative] + b"# drift\n")
        self.git(root, "add", relative)
        self.git(root, "commit", "--quiet", "-m", "gate source drift")
        with self.assertRaises(verifier.VerificationError):
            verifier.verify(repo_root=root)

        self.git(root, "checkout", "--detach", record)
        backing = path.with_name("formal-backing.py")
        backing.write_bytes(path.read_bytes())
        path.unlink()
        os.link(backing, path)
        with self.assertRaisesRegex(verifier.VerificationError, "single-link regular file"):
            verifier.verify(repo_root=root)

    def test_duplicate_yaml_key_is_blocked(self):
        root, _, _, _ = self.install_record()
        relative = verifier.ROWS["COM-01"]["manifest"]
        path = root / relative
        path.write_text(path.read_text(encoding="utf-8") + "\nstatus: forged\n", encoding="utf-8", newline="\n")
        self.git(root, "add", relative)
        self.git(root, "commit", "--quiet", "-m", "duplicate yaml")
        with self.assertRaisesRegex(verifier.VerificationError, "duplicate YAML key"):
            verifier.verify(repo_root=root)


if __name__ == "__main__":
    unittest.main()
