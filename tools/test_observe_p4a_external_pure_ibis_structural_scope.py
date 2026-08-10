"""Tests for the observer-only external IBIS structural scanner."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p4a_external_ibis_scan", ROOT / "tools" / "observe_p4a_external_pure_ibis_structural_scope.py")
assert SPEC and SPEC.loader
SCAN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SCAN)


class ExternalIbisStructuralScanTests(unittest.TestCase):
    def _authorized_synthetic(self, text: str) -> bytes:
        payload = text.encode("ascii")
        self.assertLess(len(payload), SCAN.EXPECTED_LENGTH)
        return payload + b" " * (SCAN.EXPECTED_LENGTH - len(payload))

    def test_requires_identity_before_any_scan(self) -> None:
        with self.assertRaises(SCAN.ObservationError):
            SCAN.observe_bytes(b"[IBIS Ver] 7.1\n", observer_source_sha256="0" * 64)

    def test_rejects_missing_required_sections(self) -> None:
        payload = self._authorized_synthetic("[IBIS Ver] 7.1\n[Component] X\n")
        original = SCAN.EXPECTED_SHA256
        SCAN.EXPECTED_SHA256 = hashlib.sha256(payload).hexdigest()
        try:
            with self.assertRaises(SCAN.ObservationError):
                SCAN.observe_bytes(payload, observer_source_sha256="0" * 64)
        finally:
            SCAN.EXPECTED_SHA256 = original

    def test_reports_only_bounded_metadata_for_synthetic_structure(self) -> None:
        payload = self._authorized_synthetic("[IBIS Ver] 7.1\n[Component] X\n[Model] M\nModel_type Input\n")
        original = SCAN.EXPECTED_SHA256
        SCAN.EXPECTED_SHA256 = hashlib.sha256(payload).hexdigest()
        try:
            report = SCAN.observe_bytes(payload, observer_source_sha256="1" * 64)
        finally:
            SCAN.EXPECTED_SHA256 = original
        self.assertEqual(report["result"], "structural_scope_pass_for_owner_selection")
        self.assertNotIn("M", str(report))
        self.assertTrue(report["observer"]["product_parser_not_used"])


if __name__ == "__main__":
    unittest.main()
