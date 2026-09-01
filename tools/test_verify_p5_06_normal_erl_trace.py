from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

try:
    from .verify_p5_06_normal_erl_trace import validate_document
except ImportError:
    from verify_p5_06_normal_erl_trace import validate_document


class NormalErlTraceAcceptanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = json.loads(Path("docs/baselines/p5-06-normal-erl-trace-acceptance.v1.yaml").read_text(encoding="utf-8"))

    def test_current_manifest_is_strictly_valid(self) -> None:
        validate_document(self.document)

    def test_artifact_receipt_mutation_is_rejected(self) -> None:
        value = copy.deepcopy(self.document)
        value["artifacts"]["aggregate"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "artifact receipts"):
            validate_document(value)

    def test_scope_widening_is_rejected(self) -> None:
        value = copy.deepcopy(self.document)
        value["claims"]["p5_06_main_closed"] = True
        with self.assertRaisesRegex(ValueError, "claims"):
            validate_document(value)

    def test_performance_regression_is_rejected(self) -> None:
        value = copy.deepcopy(self.document)
        value["performance"]["minimum_speedup_floor"] = 1.0
        with self.assertRaisesRegex(ValueError, "performance"):
            validate_document(value)


if __name__ == "__main__":
    unittest.main()
