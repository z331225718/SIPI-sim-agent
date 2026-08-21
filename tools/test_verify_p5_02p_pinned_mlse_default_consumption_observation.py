"""Mutation tests for the independent P5-02p source observation document."""

from __future__ import annotations

import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import verify_p5_02p_pinned_mlse_default_consumption_observation as gate


def _source_root() -> Path:
    configured = os.environ.get("SIPI_COM_ROOT")
    return Path(configured) if configured else gate.ROOT.parent / "COM"


class PinnedMlseDefaultConsumptionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = gate._load(gate.EVIDENCE)

    def test_current_document_is_valid(self) -> None:
        result = gate.validate()
        self.assertTrue(result["valid"])
        self.assertEqual(result["entry_count"], 5)
        self.assertEqual(result["source_commit"], "5272ffe74702cd585054d975559b06f8afae7b6e")
        self.assertFalse(result["source_git_object_checked"])

    def test_rejects_source_identity_mutation(self) -> None:
        for key in ("commit", "tree", "git_blob_oid_sha1", "normalized_content_sha256"):
            document = copy.deepcopy(self.document)
            document["source"][key] = "0" * len(document["source"][key])
            with self.subTest(key=key):
                with self.assertRaisesRegex(gate.ObservationError, "source_identity_invalid"):
                    gate.validate(document)

    def test_rejects_default_and_consumer_mutations(self) -> None:
        document = copy.deepcopy(self.document)
        document["entries"][0]["source_default_literal"] = "1e-3"
        with self.assertRaisesRegex(gate.ObservationError, "entries_invalid"):
            gate.validate(document)

        document = copy.deepcopy(self.document)
        document["entries"][1]["consumers"][0]["source_line"] = 2200
        with self.assertRaisesRegex(gate.ObservationError, "entries_invalid"):
            gate.validate(document)

    def test_rejects_alias_promotion(self) -> None:
        document = copy.deepcopy(self.document)
        document["entries"][2]["default_kind"] = "fallback_literal"
        document["entries"][2]["source_default_literal"] = 128
        with self.assertRaisesRegex(gate.ObservationError, "entries_invalid"):
            gate.validate(document)

    def test_rejects_reader_and_helper_mutations(self) -> None:
        document = copy.deepcopy(self.document)
        document["reader"]["simplify_cells"] = True
        with self.assertRaisesRegex(gate.ObservationError, "reader_identity_invalid"):
            gate.validate(document)

        document = copy.deepcopy(self.document)
        document["helper_contract"]["duplicate_behavior"] = "first_match"
        with self.assertRaisesRegex(gate.ObservationError, "helper_contract_invalid"):
            gate.validate(document)

    def test_rejects_scope_and_nonclaim_promotion(self) -> None:
        document = copy.deepcopy(self.document)
        document["scope"]["runtime_implementation"] = "implemented"
        with self.assertRaisesRegex(gate.ObservationError, "scope_invalid"):
            gate.validate(document)

        document = copy.deepcopy(self.document)
        document["non_claims"].remove("not_metric_tolerance")
        with self.assertRaisesRegex(gate.ObservationError, "non_claims_invalid"):
            gate.validate(document)

    def test_rejects_audit_binding_mutation(self) -> None:
        document = copy.deepcopy(self.document)
        document["audit"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(gate.ObservationError, "audit_binding_invalid"):
            gate.validate(document)

        with tempfile.TemporaryDirectory() as temporary:
            audit = Path(temporary) / "audit.md"
            audit.write_text(gate.AUDIT.read_text(encoding="utf-8") + "drift\n", encoding="utf-8")
            with mock.patch.object(gate, "AUDIT", audit):
                with self.assertRaisesRegex(gate.ObservationError, "audit_hash_mismatch"):
                    gate.validate(self.document)

    def test_rejects_absolute_paths(self) -> None:
        document = copy.deepcopy(self.document)
        document["source"]["path"] = "C:\\private\\source.m"
        with self.assertRaisesRegex(gate.ObservationError, "source_identity_invalid"):
            gate.validate(document)

        with tempfile.TemporaryDirectory() as temporary:
            audit = Path(temporary) / "audit.md"
            audit.write_text(
                f"{gate.SCHEMA} {gate.SOURCE['commit']} {gate.SOURCE['git_blob_oid_sha1']} "
                "line 10408 not an input provenance statement no MATLAB execution C:\\bad",
                encoding="utf-8",
            )
            with mock.patch.object(gate, "AUDIT", audit):
                with self.assertRaisesRegex(gate.ObservationError, "audit_absolute_path"):
                    gate.validate(self.document)

    def test_optional_source_root_checks_pinned_git_objects(self) -> None:
        source_root = _source_root()
        if not source_root.is_dir():
            self.skipTest("canonical Agent-COM checkout is unavailable")
        result = gate.validate(source_root=source_root)
        self.assertTrue(result["source_git_object_checked"])

    def test_rejects_wrong_source_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(gate.ObservationError, "source_git_command_failed"):
                gate.validate(source_root=Path(temporary))

    def test_rejects_wrong_commit_and_blob(self) -> None:
        source_root = _source_root()
        if not source_root.is_dir():
            self.skipTest("canonical Agent-COM checkout is unavailable")

        document = copy.deepcopy(self.document)
        wrong_commit = "0" * 40
        document["source"]["commit"] = wrong_commit
        with self.assertRaisesRegex(gate.ObservationError, "source_git_command_failed"):
            gate._validate_source_git_object(document, source_root)

        document = copy.deepcopy(self.document)
        wrong_blob = "0" * 40
        document["source"]["git_blob_oid_sha1"] = wrong_blob
        with self.assertRaisesRegex(gate.ObservationError, "source_blob_mismatch"):
            gate._validate_source_git_object(document, source_root)

    def test_rejects_wrong_line_and_reader_blob(self) -> None:
        source_root = _source_root()
        if not source_root.is_dir():
            self.skipTest("canonical Agent-COM checkout is unavailable")

        document = copy.deepcopy(self.document)
        document["entries"][0]["assignment"] = "changed assignment"
        with mock.patch.object(gate, "ENTRIES", document["entries"]):
            with self.assertRaisesRegex(gate.ObservationError, "assignment_line:der_cdr:mismatch"):
                gate.validate(document, source_root=source_root)

        document = copy.deepcopy(self.document)
        wrong_reader = copy.deepcopy(gate.READER)
        wrong_reader["git_blob_oid_sha1"] = "0" * 40
        document["reader"] = wrong_reader
        with mock.patch.object(gate, "READER", wrong_reader):
            with self.assertRaisesRegex(gate.ObservationError, "reader_blob_mismatch"):
                gate.validate(document, source_root=source_root)


if __name__ == "__main__":
    unittest.main()
