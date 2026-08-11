"""Tests for the P7-05a provisional capability publication verifier."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p7_publication", ROOT / "tools" / "verify_release_capability_publication.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


def manifest_for(publication: dict) -> list[dict]:
    return [{"id": row["command_id"], "availability": row["product_surface"]} for row in publication["rows"]]


class PublicationTests(unittest.TestCase):
    def publication(self) -> dict:
        return json.loads((ROOT / "docs" / "baselines" / "release-capability-publication.v1.yaml").read_text(encoding="utf-8"))

    def test_current_publication_is_valid_and_deterministic(self) -> None:
        publication = self.publication()
        GATE.validate(publication, manifest_for(publication), ROOT)
        self.assertEqual(GATE.render(publication), GATE.render(publication))

    def test_rejects_command_drift_and_missing_coverage(self) -> None:
        publication = self.publication()
        manifest = manifest_for(publication)
        manifest[0]["availability"] = "unavailable"
        with self.assertRaises(GATE.PublicationError):
            GATE.validate(publication, manifest, ROOT)
        publication = self.publication()
        publication["rows"].pop()
        with self.assertRaises(GATE.PublicationError):
            GATE.validate(publication, manifest_for(self.publication()), ROOT)

    def test_rejects_promotion_and_unsafe_evidence(self) -> None:
        publication = self.publication()
        publication["promotion_status"] = "approved"
        with self.assertRaises(GATE.PublicationError):
            GATE.validate(publication, manifest_for(self.publication()), ROOT)
        publication = self.publication()
        publication["report_index"][0]["path"] = "C:/private/report.md"
        with self.assertRaises(GATE.PublicationError):
            GATE.validate(publication, manifest_for(publication), ROOT)


if __name__ == "__main__":
    unittest.main()
