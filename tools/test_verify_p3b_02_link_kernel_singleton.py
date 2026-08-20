"""Tests for the P3B-02 link kernel-singleton and bypass-only gate."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p3b_02_link_kernel_singleton as GATE


class LinkKernelTests(unittest.TestCase):
    def test_current_invariant_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["kernel_symbols"], 3)

    def test_convolution_symbols_defined_once_in_library(self) -> None:
        text = GATE.read_text(GATE.LINK_LIB)
        for symbol in GATE.CONVOLUTION_SYMBOLS:
            count = sum(1 for line in text.splitlines()
                       if line.strip().startswith(("pub fn " + symbol + "(", "fn " + symbol + "(")))
            self.assertEqual(count, 1, f"{symbol} must be defined exactly once in the library")

    def test_bypass_assertion_present(self) -> None:
        text = GATE.read_text(GATE.LINK_LIB)
        self.assertIn("RxStagesV1::bypass().ctle(), CtleStageV1::Bypass", text)

    def test_equalizer_regex_detects_non_bypass_stage(self) -> None:
        import re
        pattern = r"ctle[a-z0-9_]*::(?!bypass)[a-z0-9_]+"
        self.assertTrue(re.search(pattern, "ctlestagev1::threetap"))
        self.assertTrue(re.search(pattern, "ctle_stage_v1::threetap"))
        self.assertFalse(re.search(pattern, "ctlestagev1::bypass"))
        self.assertTrue(re.search(r"ffe[a-z0-9_]*::(?!bypass)[a-z0-9_]+", "ffestagev1::fivetap"))

    def test_no_consumer_defines_kernel(self) -> None:
        for relative in GATE.CONSUMER_PATHS:
            if not GATE.git_tracked(relative):
                continue
            text = GATE.read_text(relative)
            for symbol in GATE.CONVOLUTION_SYMBOLS:
                self.assertIsNone(GATE.definition_line(symbol, text), f"{relative} must not define {symbol}")

    def test_consumer_references_use_library_import(self) -> None:
        for relative in GATE.CONSUMER_PATHS:
            if not GATE.git_tracked(relative):
                continue
            text = GATE.read_text(relative)
            imported = GATE.sipi_link_imported_symbols(text)
            for symbol in GATE.CONVOLUTION_SYMBOLS:
                refs = [line for line in text.splitlines()
                        if symbol in line and "use sipi_link" not in line and not line.strip().startswith("//")]
                if refs:
                    self.assertIn(symbol, imported, f"{relative} uses {symbol} without sipi_link import")


if __name__ == "__main__":
    unittest.main()
