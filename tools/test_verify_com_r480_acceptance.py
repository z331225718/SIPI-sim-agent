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

from verify_com_r480_acceptance import _load, verify_document


class ComR480AcceptanceTests(unittest.TestCase):
    def document(self) -> dict:
        return copy.deepcopy(_load(ROOT / "docs" / "baselines" / "com-r480-acceptance.v1.yaml"))

    def temporary_source(self, document: dict) -> Path:
        root = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.email", "tests@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.name", "SIPI tests"], check=True)
        path = root / "schemas" / "r480-capability-envelope-v1.yaml"
        path.parent.mkdir(parents=True)
        payload = b"project-authored external observer identity test\n"
        path.write_bytes(payload)
        subprocess.run(["git", "-C", str(root), "add", "schemas/r480-capability-envelope-v1.yaml"], check=True)
        subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture"], check=True)
        commit = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
        tree = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD^{tree}"], check=True, capture_output=True, text=True).stdout.strip()
        blob = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD:schemas/r480-capability-envelope-v1.yaml"], check=True, capture_output=True, text=True).stdout.strip()
        subprocess.run(["git", "-C", str(root), "remote", "add", "origin", "https://github.com/z331225718/agent-com.git"], check=True)
        document["external_oracle"]["source"].update({"commit": commit, "tree": tree, "git_blob": blob, "content_sha256": hashlib.sha256(payload).hexdigest()})
        return root

    def test_required_but_missing_reference_contract_validates(self) -> None:
        document = self.document()
        root = self.temporary_source(document)
        report = verify_document(document, root)
        self.assertTrue(report["valid"], report["blockers"])
        self.assertTrue(report["required"])
        self.assertFalse(report["comparison_ready"])
        self.assertEqual(report["authoritative_reference_status"], "missing")

    def test_reference_or_product_boundary_cannot_be_relaxed(self) -> None:
        document = self.document()
        root = self.temporary_source(document)
        invalid = copy.deepcopy(document)
        invalid["authoritative_reference"]["status"] = "available"
        self.assertFalse(verify_document(invalid, root)["valid"])
        invalid = copy.deepcopy(document)
        invalid["external_materials"]["matlab_source"] = "product_input"
        self.assertFalse(verify_document(invalid, root)["valid"])
        invalid = copy.deepcopy(document)
        invalid["comparison"]["product_self_comparison"] = "allowed"
        self.assertFalse(verify_document(invalid, root)["valid"])

    def test_source_identity_and_product_scope_fail_closed(self) -> None:
        document = self.document()
        root = self.temporary_source(document)
        invalid = copy.deepcopy(document)
        invalid["external_oracle"]["source"]["content_sha256"] = "0" * 64
        self.assertFalse(verify_document(invalid, root)["valid"])
        invalid = copy.deepcopy(document)
        invalid["product_contract"]["metric_bundle"].append({"id": "legacy_api", "unit": "none", "comparison_level": "scalar"})
        self.assertFalse(verify_document(invalid, root)["valid"])


if __name__ == "__main__":
    unittest.main()
