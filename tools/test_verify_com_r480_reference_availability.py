from __future__ import annotations

import copy
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verify_com_r480_reference_availability import _load, verify_document


class ComR480ReferenceAvailabilityTests(unittest.TestCase):
    def document(self) -> dict:
        return copy.deepcopy(_load(ROOT / "docs" / "baselines" / "com-r480-reference-availability-preflight.v1.yaml"))

    def temporary_source(self, document: dict) -> Path:
        root = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.email", "tests@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.name", "SIPI tests"], check=True)
        path = root / "schemas" / "r480-capability-envelope-v1.yaml"
        path.parent.mkdir(parents=True)
        payload = b"project-authored external identity fixture\n"
        path.write_bytes(payload)
        subprocess.run(["git", "-C", str(root), "add", "schemas/r480-capability-envelope-v1.yaml"], check=True)
        subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture"], check=True)
        commit = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
        tree = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD^{tree}"], check=True, capture_output=True, text=True).stdout.strip()
        blob = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD:schemas/r480-capability-envelope-v1.yaml"], check=True, capture_output=True, text=True).stdout.strip()
        subprocess.run(["git", "-C", str(root), "remote", "add", "origin", "https://github.com/z331225718/agent-com.git"], check=True)
        document["source"].update({"commit": commit, "tree": tree, "git_blob": blob, "content_sha256": hashlib.sha256(payload).hexdigest()})
        return root

    def test_missing_inputs_are_a_valid_fail_closed_preflight(self) -> None:
        document = self.document()
        root = self.temporary_source(document)
        report = verify_document(document, root)
        self.assertTrue(report["valid"], report["blockers"])
        self.assertEqual(report["reference_generation_status"], "blocked")
        self.assertFalse(report["runtime_invoked"])

    def test_availability_cannot_be_promoted_without_evidence(self) -> None:
        document = self.document()
        root = self.temporary_source(document)
        invalid = copy.deepcopy(document)
        invalid["availability"]["oracle_runner"]["status"] = "available"
        self.assertFalse(verify_document(invalid, root)["valid"])
        invalid = copy.deepcopy(document)
        invalid["preflight"]["status"] = "reference_generation_ready"
        self.assertFalse(verify_document(invalid, root)["valid"])
        invalid = copy.deepcopy(document)
        invalid["expected_reference_bundle"]["product_asset"] = "allowed"
        self.assertFalse(verify_document(invalid, root)["valid"])

    def test_source_and_contract_bindings_fail_closed(self) -> None:
        document = self.document()
        root = self.temporary_source(document)
        invalid = copy.deepcopy(document)
        invalid["source"]["content_sha256"] = "0" * 64
        self.assertFalse(verify_document(invalid, root)["valid"])
        invalid = copy.deepcopy(document)
        invalid["profile"]["acceptance_contract"]["content_sha256"] = "0" * 64
        self.assertFalse(verify_document(invalid, root)["valid"])


if __name__ == "__main__":
    unittest.main()
