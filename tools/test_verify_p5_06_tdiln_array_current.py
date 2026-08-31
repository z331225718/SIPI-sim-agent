import copy
import json
import unittest
from pathlib import Path

try:
    from .verify_p5_06_tdiln_array_current import validate_document
except ImportError:
    from verify_p5_06_tdiln_array_current import validate_document


class CurrentTdilnArrayCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.document = json.loads(
            Path("docs/baselines/p5-06-tdiln-array-current-acceptance.v1.yaml").read_text(encoding="utf-8")
        )

    def test_manifest_is_strictly_valid(self):
        validate_document(self.document)

    def test_receipt_mutation_is_rejected(self):
        value = copy.deepcopy(self.document)
        value["artifacts"]["aggregate"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "artifact receipts"):
            validate_document(value)

    def test_speed_gate_mutation_is_rejected(self):
        value = copy.deepcopy(self.document)
        value["gates"]["per_workbook_rust_not_slower"] = False
        with self.assertRaisesRegex(ValueError, "gates"):
            validate_document(value)

    def test_performance_mutation_is_rejected(self):
        value = copy.deepcopy(self.document)
        value["performance"]["speedup_floor"] = 1.0
        with self.assertRaisesRegex(ValueError, "performance"):
            validate_document(value)


if __name__ == "__main__":
    unittest.main()
