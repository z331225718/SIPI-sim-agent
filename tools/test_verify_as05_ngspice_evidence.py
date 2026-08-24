"""Mutation tests for additive AS-05 bounded evidence bindings."""

from __future__ import annotations

import json
import hashlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import verify_as05_ngspice_evidence as verifier


MANIFEST_PATH = ROOT / "docs/baselines/as-05-ngspice-scoped-observation-v2.manifest.json"


class VerifyAs05EvidenceTests(unittest.TestCase):
    def document(self) -> dict:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    def check(self, document: dict, valid: bool = False) -> None:
        result = verifier.verify_manifest(document, MANIFEST_PATH)
        self.assertEqual(result["valid"], valid, result)

    def test_exact_manifest(self) -> None:
        self.check(self.document(), True)

    def test_candidate_drift_rejected(self) -> None:
        document = self.document()
        document["candidate"]["commit"] = "0" * 40
        self.check(document)

    def test_upstream_anchor_drift_rejected(self) -> None:
        document = self.document()
        document["upstream"]["tree"] = "0" * 40
        self.check(document)

    def test_runner_anchor_drift_rejected(self) -> None:
        document = self.document()
        document["runner"]["sha256"] = "0" * 64
        self.check(document)

    def test_report_sha_drift_rejected(self) -> None:
        document = self.document()
        document["reports"][0]["sha256"] = "0" * 64
        self.check(document)

    def test_report_link_run_id_mismatch_rejected(self) -> None:
        document = self.document()
        document["reports"][0]["run_id"] = "as05-ngspice-v2-coordinated"
        self.check(document)

    def test_report_path_escape_rejected(self) -> None:
        document = self.document()
        document["reports"][0]["path"] = "../outside.json"
        self.check(document)

    def test_run_id_mutation_rejected(self) -> None:
        document = self.document()
        document["reports"][0]["run_id"] = document["reports"][1]["run_id"]
        self.check(document)

    def test_nonce_mutation_rejected(self) -> None:
        document = self.document()
        document["reports"][0]["fresh_run_nonce"] = document["reports"][1]["fresh_run_nonce"]
        self.check(document)

    def test_scope_promotion_rejected(self) -> None:
        document = self.document()
        document["scope"]["release"] = True
        self.check(document)

    def test_extra_manifest_key_rejected(self) -> None:
        document = self.document()
        document["release_allowed"] = True
        self.check(document)

    def test_wrong_type_candidate_blocked(self) -> None:
        document = self.document()
        document["candidate"] = []
        self.check(document)

    def test_wrong_type_report_link_blocked(self) -> None:
        document = self.document()
        document["reports"] = [None, "report"]
        self.check(document)

    def test_wrong_type_report_artifacts_blocked(self) -> None:
        document = self.document()
        report = ROOT / document["reports"][0]["path"].replace("\\", "/")
        original = report.read_bytes()
        try:
            value = json.loads(original.decode("utf-8"))
            value["cases"][0]["artifacts"] = None
            mutated = (json.dumps(value, sort_keys=True, indent=2) + "\n").encode("utf-8")
            report.write_bytes(mutated)
            document["reports"][0]["sha256"] = hashlib.sha256(mutated).hexdigest()
            self.check(document)
        finally:
            report.write_bytes(original)

    def test_malformed_aggregate_blocked(self) -> None:
        document = self.document()
        aggregate = ROOT / document["aggregate"]["path"].replace("\\", "/")
        original = aggregate.read_bytes()
        try:
            aggregate.write_bytes(b"[]\n")
            self.check(document)
        finally:
            aggregate.write_bytes(original)

    def test_audit_link_drift_rejected(self) -> None:
        document = self.document()
        document["audit"]["sha256"] = "0" * 64
        self.check(document)

    def test_aggregate_status_drift_rejected(self) -> None:
        document = self.document()
        aggregate = ROOT / document["aggregate"]["path"].replace("\\", "/")
        original = aggregate.read_bytes()
        try:
            value = json.loads(original.decode("utf-8"))
            value["status"] = "released"
            aggregate.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
            self.check(document)
        finally:
            aggregate.write_bytes(original)

    def test_audit_non_claim_drift_rejected(self) -> None:
        document = self.document()
        audit = ROOT / document["audit"]["path"].replace("\\", "/")
        original = audit.read_bytes()
        try:
            value = json.loads(original.decode("utf-8"))
            value["non_claims"] = []
            audit.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
            self.check(document)
        finally:
            audit.write_bytes(original)


if __name__ == "__main__":
    unittest.main()
