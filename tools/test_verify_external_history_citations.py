"""Tests for the P7 hash-only external-history citation verifier."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p7_history", ROOT / "tools" / "verify_external_history_citations.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


class CitationTests(unittest.TestCase):
    def registry(self) -> dict:
        return json.loads((ROOT / "docs" / "baselines" / "external-history-citations.v1.yaml").read_text(encoding="utf-8"))

    def test_current_registry_is_valid(self) -> None:
        GATE.validate(self.registry(), ROOT)

    def test_rejects_mutable_or_product_promotion(self) -> None:
        document = self.registry()
        document["entries"][0]["object_hash"] = "main"
        with self.assertRaises(GATE.CitationError):
            GATE.validate(document, ROOT)
        document = self.registry()
        document["entries"][0]["product_material_status"] = "product_candidate"
        with self.assertRaises(GATE.CitationError):
            GATE.validate(document, ROOT)

    def test_rejects_unregistered_marker_and_unsafe_ref(self) -> None:
        document = self.registry()
        document["entries"][0]["evidence_ref"] = "C:/private.md"
        with self.assertRaises(GATE.CitationError):
            GATE.validate(document, ROOT)
        document = self.registry()
        document["entries"].pop()
        with self.assertRaises(GATE.CitationError):
            GATE.validate(document, ROOT)


if __name__ == "__main__":
    unittest.main()
