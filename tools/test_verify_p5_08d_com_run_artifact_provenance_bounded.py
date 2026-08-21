# -*- coding: utf-8 -*-
"""Mutation tests for the P5-08d bounded artifact evidence gate."""

from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p5_08d_com_run_artifact_provenance_bounded as GATE


class BoundedArtifactEvidenceTests(unittest.TestCase):
    def test_current_document_is_valid(self) -> None:
        self.assertEqual(GATE.validate(ROOT)["schema"], GATE.SCHEMA)

    def test_binds_exact_source_and_manifest_hashes(self) -> None:
        evidence = GATE.load_yaml(GATE.EVIDENCE)
        self.assertEqual(
            evidence["implementation"]["source_content_sha256"],
            GATE.EXPECTED_SOURCE_SHA256,
        )
        self.assertEqual(evidence["fixture"], GATE.EXPECTED_FIXTURE)

    def test_rejects_schema_mutation(self) -> None:
        self._reject_mutation(lambda document: document.__setitem__("schema", "sipi.wrong"), "schema_drift")

    def test_rejects_status_overclaim(self) -> None:
        self._reject_mutation(
            lambda document: document.__setitem__("status", "authoritative_verified"),
            "status_overclaim_or_drift",
        )

    def test_rejects_source_hash_mutation(self) -> None:
        def mutate(document: dict) -> None:
            document["implementation"]["source_content_sha256"] = "0" * 64

        self._reject_mutation(mutate, "source_hash_document_drift")

    def test_rejects_budget_mutation(self) -> None:
        def mutate(document: dict) -> None:
            document["bounded_read_policy"]["maximum_report_bytes"] = 1

        self._reject_mutation(mutate, "bounded_policy_drift")

    def test_rejects_nonclaim_mutation(self) -> None:
        def mutate(document: dict) -> None:
            document["non_claims"].pop()

        self._reject_mutation(mutate, "non_claim_drift")

    def test_rejects_absolute_path_mutation(self) -> None:
        def mutate(document: dict) -> None:
            document["observed"]["fixture_path"] = "C:\\outside\\fixture"

        self._reject_mutation(mutate, "absolute_path_in_evidence_or_audit")

    def test_rejects_absolute_path_in_audit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            audit = Path(temporary) / "audit.md"
            audit.write_text("fixture: C:\\outside\\fixture\n", encoding="utf-8")
            with mock.patch.object(GATE, "AUDIT", audit):
                with self.assertRaisesRegex(
                    GATE.EvidenceError, "absolute_path_in_evidence_or_audit"
                ):
                    GATE.validate(ROOT)

    def _reject_mutation(self, mutate, reason: str) -> None:
        document = copy.deepcopy(GATE.load_yaml(GATE.EVIDENCE))
        mutate(document)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "evidence.yaml"
            path.write_text(GATE.yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
            with mock.patch.object(GATE, "EVIDENCE", path):
                with self.assertRaisesRegex(GATE.EvidenceError, reason):
                    GATE.validate(ROOT)


if __name__ == "__main__":
    unittest.main()
