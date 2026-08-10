"""Tests for the P3B Link stage capability ledger verifier."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

import yaml


sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_p3b_link_stage_capabilities as verifier  # noqa: E402


class LinkStageCapabilityLedgerTests(unittest.TestCase):
    def load(self) -> dict:
        return yaml.safe_load(verifier.DEFAULT_LEDGER.read_text(encoding="utf-8"))

    def test_current_ledger_is_valid(self) -> None:
        self.assertTrue(verifier.verify(self.load())["valid"])

    def test_missing_reject_owner_input_and_wrong_bypass_are_rejected(self) -> None:
        document = self.load()
        seed = next(entry for entry in document["entries"] if entry["id"] == "deterministic_seed")
        del seed["required_owner_input"]
        self.assertFalse(verifier.verify(document)["valid"])
        document = self.load()
        bypass = next(entry for entry in document["entries"] if entry["id"] == "ctle_bypass")
        bypass["disposition"] = "supported"
        self.assertFalse(verifier.verify(document)["valid"])

    def test_unknown_or_missing_entries_are_rejected(self) -> None:
        document = self.load()
        document["entries"].pop()
        self.assertFalse(verifier.verify(document)["valid"])
        document = self.load()
        document["entries"].append(copy.deepcopy(document["entries"][0]))
        self.assertFalse(verifier.verify(document)["valid"])


if __name__ == "__main__":
    unittest.main()
