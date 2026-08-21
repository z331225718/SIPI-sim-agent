# -*- coding: utf-8 -*-
"""Mutation tests for the P5-05g ingestion verifier."""

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

import verify_p5_05g_parameter_ingestion as gate


class ParameterIngestionVerifierTests(unittest.TestCase):
    def test_current_document_is_valid(self) -> None:
        result = gate.validate(ROOT)
        self.assertTrue(result["source_sha256"])
        self.assertEqual(
            result["audit_sha256"],
            gate.hashlib.sha256(gate.AUDIT.read_bytes()).hexdigest(),
        )
        self.assertEqual(result["test_count"], 8)

    def test_source_hash_is_bound(self) -> None:
        charter = gate.load_yaml(gate.CHARTER)
        self.assertEqual(
            charter["implementation"]["sha256"],
            gate.hashlib.sha256(gate.SOURCE.read_bytes()).hexdigest(),
        )

    def test_audit_metadata_is_bound(self) -> None:
        charter = gate.load_yaml(gate.CHARTER)
        self.assertEqual(charter["audit"]["path"], gate.AUDIT_RELATIVE)
        self.assertEqual(
            charter["audit"]["sha256"],
            gate.hashlib.sha256(gate.AUDIT.read_bytes()).hexdigest(),
        )

    def test_non_claims_are_explicit(self) -> None:
        charter = gate.load_yaml(gate.CHARTER)
        for claim in (
            "not_authoritative_com_oracle",
            "not_full_r480_parameter_contract",
            "not_profile_acceptance",
            "not_ieee_certification",
            "not_release_evidence",
        ):
            self.assertIn(claim, charter["non_claims"])

    def test_rejects_source_hash_mutation(self) -> None:
        charter = copy.deepcopy(gate.load_yaml(gate.CHARTER))
        charter["implementation"]["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as directory:
            mutated = Path(directory) / gate.CHARTER.name
            mutated.write_text(gate.yaml.safe_dump(charter, sort_keys=False), encoding="utf-8")
            with mock.patch.object(gate, "CHARTER", mutated):
                with self.assertRaises(gate.ParameterIngestionError):
                    gate.validate(ROOT)

    def test_rejects_audit_metadata_path_mutation(self) -> None:
        charter = copy.deepcopy(gate.load_yaml(gate.CHARTER))
        charter["audit"]["path"] = "docs/baselines/audits/other.md"
        with tempfile.TemporaryDirectory() as directory:
            mutated = Path(directory) / gate.CHARTER.name
            mutated.write_text(gate.yaml.safe_dump(charter, sort_keys=False), encoding="utf-8")
            with mock.patch.object(gate, "CHARTER", mutated):
                with self.assertRaises(gate.ParameterIngestionError):
                    gate.validate(ROOT)

    def test_rejects_audit_metadata_hash_mutation(self) -> None:
        charter = copy.deepcopy(gate.load_yaml(gate.CHARTER))
        charter["audit"]["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as directory:
            mutated = Path(directory) / gate.CHARTER.name
            mutated.write_text(gate.yaml.safe_dump(charter, sort_keys=False), encoding="utf-8")
            with mock.patch.object(gate, "CHARTER", mutated):
                with self.assertRaises(gate.ParameterIngestionError):
                    gate.validate(ROOT)

    def test_rejects_audit_content_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mutated = Path(directory) / gate.AUDIT.name
            mutated.write_bytes(gate.AUDIT.read_bytes() + b"\ncontent mutation\n")
            with mock.patch.object(gate, "AUDIT", mutated):
                with self.assertRaises(gate.ParameterIngestionError):
                    gate.validate(ROOT)

    def test_rejects_missing_non_claim(self) -> None:
        charter = copy.deepcopy(gate.load_yaml(gate.CHARTER))
        charter["non_claims"].remove("not_release_evidence")
        with tempfile.TemporaryDirectory() as directory:
            mutated = Path(directory) / gate.CHARTER.name
            mutated.write_text(gate.yaml.safe_dump(charter, sort_keys=False), encoding="utf-8")
            with mock.patch.object(gate, "CHARTER", mutated):
                with self.assertRaises(gate.ParameterIngestionError):
                    gate.validate(ROOT)


if __name__ == "__main__":
    unittest.main()
