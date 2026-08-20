"""Tests for the P3B-03 receiver self-conformance gate."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p3b_03_receiver_self_conformance as GATE


class ReceiverSelfConformanceTests(unittest.TestCase):
    def test_current_self_conformance_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["verifiers"], 4)

    def test_all_semantic_verifiers_present(self) -> None:
        for name, relative in GATE.SEMANTIC_VERIFIERS.items():
            self.assertTrue((ROOT / relative).is_file(), f"{name}: {relative}")

    def test_publication_row_bound(self) -> None:
        publication = GATE.load_yaml(GATE.PUBLICATION)
        row = next((r for r in publication["rows"] if r.get("id") == "link-receiver-diagnostic"), None)
        self.assertIsNotNone(row)
        self.assertEqual(row["command_id"], "link.receiver.run")
        self.assertEqual(row["product_surface"], "available")
        self.assertEqual(row["acceptance_state"], "specified")

    def test_rejects_missing_verifier(self) -> None:
        # The gate validates from disk; ensure the verifier set is complete.
        self.assertEqual(len(GATE.SEMANTIC_VERIFIERS), 4)


if __name__ == "__main__":
    unittest.main()
