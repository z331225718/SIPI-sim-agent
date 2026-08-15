from __future__ import annotations
import copy
import sys
from pathlib import Path
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import verify_p3c_selected_sensitivity_historical_source_drift as gate

class Tests(unittest.TestCase):
    def document(self): return yaml.safe_load(gate.DEFAULT.read_text(encoding="utf-8"))
    def test_current_document_and_runtime_are_historical(self):
        doc = self.document(); self.assertTrue(gate.verify_document(doc)["valid"]); gate.verify_runtime(doc)
    def test_mutations_fail_closed(self):
        for mutate in (
            lambda d: d["historical_records"][0].__setitem__("evidence_sha256", "0" * 64),
            lambda d: d["historical_records"][1].__setitem__("expected_error", "wrong"),
            lambda d: d["gates"].__setitem__("historical_records_current", True),
            lambda d: d["gates"].__setitem__("release_ledger_promoted", True),
        ):
            with self.subTest(mutate=mutate):
                doc = copy.deepcopy(self.document()); mutate(doc)
                with self.assertRaises(gate.VerificationError): gate.verify_document(doc)

if __name__ == "__main__": unittest.main()
