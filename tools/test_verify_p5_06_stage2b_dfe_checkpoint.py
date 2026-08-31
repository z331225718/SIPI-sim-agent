import copy
import unittest
from pathlib import Path


try:
    from .verify_p5_06_stage2b_dfe_checkpoint import validate_document
except ImportError:
    from verify_p5_06_stage2b_dfe_checkpoint import validate_document


class Stage2bDfeManifestTests(unittest.TestCase):
    def setUp(self):
        import json
        self.document = json.loads(Path("docs/baselines/p5-06-stage2b-dfe-checkpoint-acceptance.v1.yaml").read_text(encoding="utf-8"))

    def test_current_manifest_is_strictly_valid(self):
        validate_document(self.document)

    def test_artifact_digest_mutation_is_rejected(self):
        value = copy.deepcopy(self.document)
        value["artifacts"]["rust_01"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "artifact receipts"):
            validate_document(value)

    def test_performance_mutation_is_rejected(self):
        value = copy.deepcopy(self.document)
        value["performance"]["rust_worst_total_wall_ns"] += 1
        with self.assertRaisesRegex(ValueError, "performance"):
            validate_document(value)

    def test_scope_widening_is_rejected(self):
        value = copy.deepcopy(self.document)
        value["claims"]["p5_06_main_closed"] = True
        with self.assertRaisesRegex(ValueError, "claims"):
            validate_document(value)


if __name__ == "__main__":
    unittest.main()
