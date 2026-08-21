from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import verify_p3c_exact_impulse_current_replay_identity_reconciliation_v3 as GATE  # noqa: E402


class ReplayIdentityReconciliationTests(unittest.TestCase):
    def document(self) -> dict:
        value = yaml.safe_load(GATE.DOCUMENT.read_text(encoding="utf-8"))
        self.assertIsInstance(value, dict)
        return value

    def test_current_reconciliation_is_valid_and_blocked(self) -> None:
        result = GATE.validate(self.document())
        self.assertEqual(result["exact_matches"], 0)
        self.assertFalse(result["release_ready"])

    def test_recorded_digest_cannot_be_promoted(self) -> None:
        value = copy.deepcopy(self.document())
        first = next(iter(value["source_identity_observations"].values()))
        first["canonical_git_blob_sha256"] = first["recorded_checkout_sha256"]
        with self.assertRaises(GATE.ReconciliationError):
            GATE.validate(value)

    def test_release_cannot_be_promoted(self) -> None:
        value = copy.deepcopy(self.document())
        value["gates"]["release_ready"] = True
        with self.assertRaisesRegex(GATE.ReconciliationError, "gates_invalid"):
            GATE.validate(value)


if __name__ == "__main__":
    unittest.main()
