"""Tests for the P3B-05a causal-FIR request rejection surface gate."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p3b_05a_causal_fir_request_rejection as GATE


class RejectionSurfaceTests(unittest.TestCase):
    def test_current_rejection_surface_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["stage_variants"], 2)

    def test_schema_id_fixed(self) -> None:
        text = GATE.read_text(GATE.CONTRACTS)
        self.assertIn("LINK_CAUSAL_FIR_REQUEST_SCHEMA", text)
        self.assertIn("sipi.link.causal-fir-request.v1", text)

    def test_stage_enums_have_only_bypass_variants(self) -> None:
        text = GATE.read_text(GATE.CONTRACTS)
        for pattern in (r"enum WireTxStageV1\s*\{", r"enum WireCtleStageV1\s*\{", r"enum WireFfeStageV1\s*\{"):
            match = re.search(pattern + r"(.*?)\n\}", text, re.DOTALL)
            self.assertIsNotNone(match, pattern)
            variants = GATE.extract_enum_variants(match.group(1))
            self.assertTrue(variants and variants <= GATE.EXPECTED_STAGE_VARIANTS, f"{pattern}: {variants}")

    def test_all_wire_types_deny_unknown_fields(self) -> None:
        text = GATE.read_text(GATE.CONTRACTS)
        for pattern in GATE.WIRE_STRUCT_PATTERNS:
            match = re.search(pattern, text, re.DOTALL)
            self.assertIsNotNone(match, pattern)
            preceding = text[max(0, match.start() - 300):match.start()]
            self.assertTrue(
                "deny_unknown_fields" in preceding or "deny_unknown_fields" in match.group(0),
                f"{pattern} missing deny_unknown_fields",
            )

    def test_no_forbidden_feature_fields_in_request(self) -> None:
        text = GATE.read_text(GATE.CONTRACTS)
        body = re.search(r"struct WireLinkCausalFirRequestV1\s*\{(.*?)\n\}", text, re.DOTALL)
        self.assertIsNotNone(body)
        fields = body.group(1).lower()
        for token in GATE.FORBIDDEN_FEATURE_TOKENS:
            self.assertIsNone(re.search(rf"\b{re.escape(token)}\b", fields), f"forbidden field {token}")

    def test_rejects_stage_variant_addition(self) -> None:
        text = GATE.read_text(GATE.CONTRACTS)
        match = re.search(r"enum WireTxStageV1\s*\{(.*?)\n\}", text, re.DOTALL)
        self.assertIsNotNone(match)
        # A hypothetical new variant would fail the <= EXPECTED check.
        variants = GATE.extract_enum_variants(match.group(1))
        self.assertTrue(variants <= GATE.EXPECTED_STAGE_VARIANTS)

    def test_rejects_seed_field_addition(self) -> None:
        text = GATE.read_text(GATE.CONTRACTS)
        body = re.search(r"struct WireLinkCausalFirRequestV1\s*\{(.*?)\n\}", text, re.DOTALL)
        self.assertIsNotNone(body)
        self.assertNotIn("seed_hex", body.group(1))


if __name__ == "__main__":
    unittest.main()
