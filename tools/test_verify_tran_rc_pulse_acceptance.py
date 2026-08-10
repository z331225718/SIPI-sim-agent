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

from verify_tran_rc_pulse_acceptance import _load, verify_document


class TranRcPulseAcceptanceTests(unittest.TestCase):
    def document(self) -> dict:
        return copy.deepcopy(_load(ROOT / "docs" / "baselines" / "tran-rc-pulse-acceptance.v1.yaml"))

    def temporary_source(self, document: dict) -> Path:
        root = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.email", "tests@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.name", "SIPI tests"], check=True)
        path = root / "fixtures" / "rc.cir"
        path.parent.mkdir(parents=True)
        payload = b"project-owned external fixture identity test\n"
        path.write_bytes(payload)
        subprocess.run(["git", "-C", str(root), "add", "fixtures/rc.cir"], check=True)
        subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture"], check=True)
        commit = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
        tree = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD^{tree}"], check=True, capture_output=True, text=True).stdout.strip()
        blob = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD:fixtures/rc.cir"], check=True, capture_output=True, text=True).stdout.strip()
        subprocess.run(["git", "-C", str(root), "remote", "add", "origin", "https://example.invalid/agent-spice.git"], check=True)
        document["source"].update({"canonical_origin": "https://example.invalid/agent-spice.git", "commit": commit, "tree": tree, "path": "fixtures/rc.cir", "git_blob": blob, "content_sha256": hashlib.sha256(payload).hexdigest()})
        return root

    def test_external_object_and_specified_contract_validate(self) -> None:
        document = self.document()
        root = self.temporary_source(document)
        report = verify_document(document, root)
        self.assertTrue(report["valid"], report["blockers"])
        self.assertTrue(report["source_git_object_checked"])
        self.assertTrue(report["acceptance_ready"])

    def test_ready_contract_is_not_a_numerical_result(self) -> None:
        document = self.document()
        root = self.temporary_source(document)
        report = verify_document(document, root, require_ready=True)
        self.assertTrue(report["valid"], report["blockers"])
        invalid = self.document()
        invalid["acceptance"]["result_status"] = "passed"
        root = self.temporary_source(invalid)
        report = verify_document(invalid, root)
        self.assertFalse(report["valid"])
        self.assertTrue(any("acceptance policy" in item for item in report["blockers"]))

    def test_source_identity_scope_and_external_boundary_fail_closed(self) -> None:
        document = self.document()
        root = self.temporary_source(document)
        invalid = copy.deepcopy(document)
        invalid["source"]["content_sha256"] = "0" * 64
        self.assertFalse(verify_document(invalid, root)["valid"])
        invalid = copy.deepcopy(document)
        invalid["scope"]["observables"] = ["voltage_out_volts"]
        self.assertFalse(verify_document(invalid, root)["valid"])
        invalid = copy.deepcopy(document)
        invalid["oracle"]["product_fallback"] = "allowed"
        self.assertFalse(verify_document(invalid, root)["valid"])
        invalid = copy.deepcopy(document)
        invalid["acceptance"]["time_axis"]["expected_values_seconds"][3] = 4.0e-6
        self.assertFalse(verify_document(invalid, root)["valid"])
        invalid = copy.deepcopy(document)
        invalid["acceptance"]["voltage_out"]["relative_tolerance"] = 1.0e-3
        self.assertFalse(verify_document(invalid, root)["valid"])


if __name__ == "__main__":
    unittest.main()
