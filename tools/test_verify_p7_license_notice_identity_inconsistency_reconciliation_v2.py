from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import verify_p7_license_notice_identity_inconsistency_reconciliation_v2 as GATE  # noqa: E402


class IdentityReconciliationTests(unittest.TestCase):
    def document(self) -> dict:
        value = yaml.safe_load(GATE.DOCUMENT.read_text(encoding="utf-8"))
        self.assertIsInstance(value, dict)
        return value

    def test_current_record_is_valid_and_blocked(self) -> None:
        self.assertEqual(GATE.validate(self.document())["release_ready"], False)

    def test_exact_match_promotion_is_rejected(self) -> None:
        value = copy.deepcopy(self.document())
        value["identity_observations"][0]["exact_match"] = True
        with self.assertRaisesRegex(GATE.IdentityReconciliationError, "historical_exact_identity_claim_invalid"):
            GATE.validate(value)

    def test_release_promotion_is_rejected(self) -> None:
        value = copy.deepcopy(self.document())
        value["gates"]["release_ready"] = True
        with self.assertRaisesRegex(GATE.IdentityReconciliationError, "gates_invalid"):
            GATE.validate(value)


if __name__ == "__main__":
    unittest.main()
