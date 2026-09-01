import copy
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import verify_as05_direct_port as verifier  # noqa: E402


class VerifyAs05DirectPortTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = yaml.safe_load(verifier.EVIDENCE.read_text(encoding="utf-8"))

    def test_pinned_admission_is_valid(self):
        result = verifier.verify(copy.deepcopy(self.document))
        self.assertTrue(result["valid"], result)
        self.assertEqual(result["crate_integration"], "root_workspace_member")

    def test_root_workspace_membership_is_explicit_and_exact(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            crate = root / "crates" / "sipi-agent-spice-direct"
            crate.mkdir(parents=True)
            (root / "Cargo.toml").write_text(
                '[workspace]\nmembers = ["crates/sipi-agent-spice-direct"]\n',
                encoding="utf-8",
            )
            self.assertTrue(verifier._is_root_workspace_member(crate, root))
            (root / "Cargo.toml").write_text('[workspace]\nmembers = []\n', encoding="utf-8")
            self.assertFalse(verifier._is_root_workspace_member(crate, root))

    def test_source_commit_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["source"]["commit"] = "0" * 40
        result = verifier.verify(document)
        self.assertIn("source commit drift", result["blockers"])

    def test_partial_status_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["status"] = "admission_complete_rust_solver_open"
        result = verifier.verify(document)
        self.assertIn("partial admission status drift", result["blockers"])

    def test_differential_corpus_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["differential_corpus"]["cases"][0]["expectation"] = "drift"
        result = verifier.verify(document)
        self.assertIn("differential corpus inventory drift", result["blockers"])

    def test_upstream_commit_evidence_binding_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["direct_port"]["upstream_commit_constant"] = "0" * 40
        result = verifier.verify(document)
        self.assertIn("direct-port upstream commit evidence binding drift", result["blockers"])

    def test_rust_upstream_commit_constant_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        with tempfile.TemporaryDirectory() as temporary:
            temporary_crate = Path(temporary) / "sipi-agent-spice-direct"
            (temporary_crate / "src").mkdir(parents=True)
            shutil.copy2(verifier.CRATE / "Cargo.toml", temporary_crate / "Cargo.toml")
            shutil.copy2(
                verifier.CRATE / "NOTICE-AGENT-SPICE-MIT.md",
                temporary_crate / "NOTICE-AGENT-SPICE-MIT.md",
            )
            source_path = temporary_crate / "src" / "lib.rs"
            source_path.write_text(
                (verifier.CRATE / "src" / "lib.rs")
                .read_text(encoding="utf-8")
                .replace(
                    verifier.EXPECTED_COMMIT, "0" * 40, 1
                ),
                encoding="utf-8",
            )
            with mock.patch.object(verifier, "CRATE", temporary_crate):
                result = verifier.verify(document)
        self.assertIn("direct-port Rust upstream commit constant drift", result["blockers"])

    def test_backend_branch_deletion_is_rejected(self):
        document = copy.deepcopy(self.document)
        del document["branch_graph"]["backends"]["xyce_xdm"]
        result = verifier.verify(document)
        self.assertIn("backend branch set drift", result["blockers"])

    def test_license_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["source_paths"][0]["license"] = "GPL-3.0"
        result = verifier.verify(document)
        self.assertTrue(any("path license drift" in item for item in result["blockers"]))

    def test_numeric_tolerance_claim_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["oracle_replay"]["replay_tolerance"]["numeric_waveforms"] = 1e-6
        result = verifier.verify(document)
        self.assertIn("replay tolerance policy drift", result["blockers"])

    def test_audit_hash_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["audit"]["sha256"] = "0" * 64
        result = verifier.verify(document)
        self.assertIn("audit binding drift", result["blockers"])


if __name__ == "__main__":
    unittest.main()
