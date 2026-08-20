"""Tests for the P2-02 solver-singleton verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p2_02_solver_singleton as GATE


class SolverSingletonTests(unittest.TestCase):
    def test_current_solver_invariant_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["solver_symbols"], len(GATE.SOLVER_SYMBOLS))

    def test_every_solver_symbol_defined_once_in_library(self) -> None:
        library_text = GATE.read_text(GATE.SOLVER_LIB)
        for symbol in GATE.SOLVER_SYMBOLS:
            count = sum(1 for line in library_text.splitlines()
                       if line.strip().startswith(("pub fn " + symbol + "(", "fn " + symbol + "(")))
            self.assertEqual(count, 1, f"{symbol} must be defined exactly once in the library")

    def test_no_solver_symbol_defined_in_consumer_crates(self) -> None:
        for crate in GATE.CONSUMER_CRATES:
            for source in sorted((ROOT / crate).rglob("*.rs")):
                text = source.read_text(encoding="utf-8")
                for symbol in GATE.SOLVER_SYMBOLS:
                    self.assertIsNone(
                        GATE.definition_line(symbol, text),
                        f"{source.relative_to(ROOT)} must not define {symbol}",
                    )

    def test_multi_line_import_block_is_detected(self) -> None:
        text = "use sipi_tran::{\n    simulate_rc_pulse,\n    RcPulseTransientV1,\n};\n"
        imported = GATE.sipi_tran_imported_symbols(text)
        self.assertIn("simulate_rc_pulse", imported)
        self.assertIn("RcPulseTransientV1", imported)

    def test_single_line_import_is_detected(self) -> None:
        text = "use sipi_tran::simulate_rc_pulse;\n"
        self.assertIn("simulate_rc_pulse", GATE.sipi_tran_imported_symbols(text))

    def test_harness_stays_feature_gated(self) -> None:
        cargo_text = GATE.read_text(GATE.HARNESS_CARGO)
        self.assertIn(f"required-features = [\"{GATE.HARNESS_FEATURE}\"]", cargo_text)
        harness_text = GATE.read_text(GATE.HARNESS_BIN)
        self.assertIn("comparator-only", harness_text.lower())

    def test_rejects_consumer_definition(self) -> None:
        # A hypothetical consumer file with a copied definition must be caught.
        text = "pub fn simulate_rc_pulse(request: u8) -> u8 { request }\n"
        self.assertIsNotNone(GATE.definition_line("simulate_rc_pulse", text))


if __name__ == "__main__":
    unittest.main()
