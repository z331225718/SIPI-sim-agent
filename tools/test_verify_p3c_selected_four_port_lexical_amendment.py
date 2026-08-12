from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p3c_lexical_amendment", ROOT / "tools" / "verify_p3c_selected_four_port_lexical_amendment.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


class SelectedFourPortLexicalAmendmentTests(unittest.TestCase):
    def document(self) -> dict:
        return yaml.safe_load((ROOT / "docs" / "baselines" / "p3c-selected-four-port-lexical-amendment.v1.yaml").read_text(encoding="utf-8"))

    def test_current_document_is_valid(self) -> None:
        self.assertTrue(GATE.verify(self.document())["valid"])

    def test_rejects_allowlist_or_history_rewrite(self) -> None:
        document = self.document()
        document["amendment"]["v2_option_lines_exact"].append("# Hz S RI R 50.00")
        with self.assertRaisesRegex(GATE.VerificationError, "scope_invalid"):
            GATE.verify(document)
        document = self.document()
        document["historical_v1_rejected_observation"]["status"] = "observed"
        with self.assertRaisesRegex(GATE.VerificationError, "history_invalid"):
            GATE.verify(document)

    def test_rejects_external_or_runtime_promotion(self) -> None:
        document = copy.deepcopy(self.document())
        document["admission"]["selected_external_s4p_static_admitted"] = True
        with self.assertRaisesRegex(GATE.VerificationError, "promotion_invalid"):
            GATE.verify(document)


if __name__ == "__main__":
    unittest.main()
