"""Mutation tests for P7 current-candidate static-PE diagnosis evidence."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p7_pe_diagnosis", ROOT / "tools" / "verify_p7_current_candidate_pe_rejection_diagnosis.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


class P7PeDiagnosisEvidenceTests(unittest.TestCase):
    def document(self) -> dict:
        return json.loads((ROOT / "docs" / "baselines" / "p7-current-candidate-static-pe-rejection-diagnosis.v1.yaml").read_text(encoding="utf-8"))

    def test_document_is_valid(self) -> None:
        result = GATE.validate(self.document())
        self.assertTrue(result["valid"])
        self.assertFalse(result["report_bound"])

    def test_observation_and_gate_mutations_are_rejected(self) -> None:
        for path, value, reason in (
            (("observation", "rejection_classification"), "layout_compatible", "observation_invalid"),
            (("observation", "disallowed_import_dlls"), [], "observation_invalid"),
            (("gates", "allowlist_expanded"), True, "gate_state_invalid"),
            (("gates", "composition_invoked"), True, "gate_state_invalid"),
            (("gates", "promotion_status"), "eligible", "gate_state_invalid"),
            (("non_claims",), ["bogus"], "non_claims_invalid"),
        ):
            with self.subTest(path=path):
                document = self.document()
                target = document
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
                with self.assertRaises(GATE.EvidenceError):
                    GATE.validate(document)

    def test_external_report_is_exactly_bound(self) -> None:
        document = self.document()
        report = GATE.expected_report(document)
        raw = json.dumps(report, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        document["external_report"]["sha256"] = GATE.sha256(raw)
        document["external_report"]["byte_length"] = len(raw)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_bytes(raw)
            result = GATE.validate(document, path)
            self.assertTrue(result["report_bound"])
            tampered = copy.deepcopy(report)
            tampered["observation"]["disallowed_import_dlls"] = []
            path.write_text(json.dumps(tampered), encoding="utf-8")
            with self.assertRaisesRegex(GATE.EvidenceError, "external_report_identity_drift"):
                GATE.validate(document, path)


if __name__ == "__main__":
    unittest.main()
