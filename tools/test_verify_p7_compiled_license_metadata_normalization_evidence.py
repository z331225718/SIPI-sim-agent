"""Contract tests for the P7 compiled-license metadata normalization evidence."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "p7_normalization_evidence", ROOT / "tools" / "verify_p7_compiled_license_metadata_normalization_evidence.py"
)
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)
DOCUMENT = ROOT / "docs" / "baselines" / "p7-compiled-license-metadata-normalization-evidence.v1.yaml"


class CompiledLicenseMetadataNormalizationEvidenceTests(unittest.TestCase):
    def document(self) -> dict:
        document = yaml.safe_load(DOCUMENT.read_text(encoding="utf-8"))
        assert isinstance(document, dict)
        return document

    def test_document_is_valid_and_non_conclusive(self) -> None:
        document = self.document()
        VERIFY.validate(document)
        self.assertTrue(document["gates"]["compiled_license_metadata_structurally_normalized"])
        self.assertFalse(document["gates"]["dependency_snapshot_ready"])
        self.assertFalse(document["gates"]["release_ready"])

    def test_external_report_is_exactly_bound(self) -> None:
        document = self.document()
        report = {
            "schema": VERIFY.REPORT_SCHEMA,
            "status": "compiled_license_metadata_structurally_normalized_not_concluded",
            "input": document["input"],
            "result": document["result"],
            "gates": VERIFY.EXPECTED_GATES,
            "non_claims": VERIFY.EXPECTED_NON_CLAIMS,
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "report.json"
            path.write_text(json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
            document["external_report"] = {"sha256": VERIFY.sha256(path.read_bytes()), "bytes": path.stat().st_size}
            VERIFY.verify_report(document, path)

            report["result"]["record_count"] = 87
            path.write_text(json.dumps(report), encoding="utf-8")
            with self.assertRaisesRegex(VERIFY.EvidenceError, "external_report_identity_mismatch"):
                VERIFY.verify_report(document, path)

            report["result"]["record_count"] = 86
            report["unexpected"] = True
            path.write_text(json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
            document["external_report"] = {"sha256": VERIFY.sha256(path.read_bytes()), "bytes": path.stat().st_size}
            with self.assertRaisesRegex(VERIFY.EvidenceError, "external_report_binding_invalid"):
                VERIFY.verify_report(document, path)

    def test_promotion_and_semantic_rewrites_fail_closed(self) -> None:
        document = self.document()
        document["gates"]["release_ready"] = True
        with self.assertRaisesRegex(VERIFY.EvidenceError, "gates_invalid"):
            VERIFY.validate(document)

        document = self.document()
        document["result"]["category_counts"]["declared_string_unparsed"] = 74
        with self.assertRaisesRegex(VERIFY.EvidenceError, "result_invalid"):
            VERIFY.validate(document)

        document = copy.deepcopy(self.document())
        document["non_claims"].remove("notice_requirement_not_evaluated")
        with self.assertRaisesRegex(VERIFY.EvidenceError, "gates_invalid"):
            VERIFY.validate(document)


if __name__ == "__main__":
    unittest.main()
