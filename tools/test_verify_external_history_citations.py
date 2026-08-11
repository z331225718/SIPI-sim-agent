"""Tests for the P7 hash-only external-history citation verifier."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import tempfile
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

    def test_rejects_unsafe_origin_and_release_doc_paths(self) -> None:
        for origin in (
            "https://",
            "https://user@github.com/z331225718/agent-spice.git",
            "https://github.com/z331225718/agent-spice.git?ref=main",
            "https://github.com/z331225718/agent-spice.git#main",
            "https://github.com/z331225718%2Fagent-spice.git",
            "https://git.example/owner/repo.git",
        ):
            with self.subTest(origin=origin):
                document = self.registry()
                document["entries"][0]["canonical_origin"] = origin
                with self.assertRaises(GATE.CitationError):
                    GATE.validate(document, ROOT)
        for path in ("/tmp/a.md", "//host/a.md", "C:/private.md", r"\\server\share\a.md", "docs/baselines/../a.md"):
            self.assertFalse(GATE.safe_doc(path))

    def test_rejects_unix_absolute_path_in_release_doc(self) -> None:
        document = self.registry()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "docs" / "baselines" / "audit.md"
            path.parent.mkdir(parents=True)
            markers = "\n".join(
                f"history-ref:{entry['id']}@{entry['object_hash']}" for entry in document["entries"]
            )
            path.write_text(f"{markers}\nunsafe: (/tmp/private)\n", encoding="utf-8")
            document["release_docs"] = ["docs/baselines/audit.md"]
            for entry in document["entries"]:
                entry["evidence_ref"] = "docs/baselines/audit.md"
            with self.assertRaises(GATE.CitationError):
                GATE.validate(document, root)


if __name__ == "__main__":
    unittest.main()
