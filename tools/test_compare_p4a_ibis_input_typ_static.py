"""Unit tests for the P4A external-only DC-clamp comparator helpers."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p4a_compare", ROOT / "tools" / "compare_p4a_ibis_input_typ_static.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def source() -> bytes:
    return b"""[IBIS Ver] 7.1
[Model] selected_input
Model_type Input
C_comp 2pF NA NA
[GND_clamp]
-1V -2A 10A 20A
0V 0A 10A 20A
1V 2A 10A 20A
[POWER_clamp]
-1V 3A 10A 20A
1V -1A 10A 20A
[Model] other
Model_type Output
"""


class CompareHelpersTest(unittest.TestCase):
    def test_extracts_unique_input_typical_tables_without_consuming_extra_columns(self) -> None:
        selector_hash = hashlib.sha256(b"selected_input").hexdigest()
        selector, version, gnd, power = MODULE.extract_raw_profile(source(), selector_hash)
        self.assertEqual(selector, "selected_input")
        self.assertEqual(version, "7.1")
        self.assertEqual(gnd, ((-1.0, -2.0), (0.0, 0.0), (1.0, 2.0)))
        self.assertEqual(power, ((-1.0, 3.0), (1.0, -1.0)))
        self.assertEqual(MODULE.raw_observation(gnd, power, [0.5])[0]["total_current_a"], 1.0)

    def test_rejects_missing_required_power_clamp(self) -> None:
        selector_hash = hashlib.sha256(b"selected_input").hexdigest()
        broken = source().replace(b"[POWER_clamp]\n-1V 3A 10A 20A\n1V -1A 10A 20A\n", b"")
        with self.assertRaisesRegex(MODULE.CompareError, "external_clamp_section_invalid"):
            MODULE.extract_raw_profile(broken, selector_hash)

    def test_table_fingerprint_is_order_sensitive_and_domain_separated(self) -> None:
        first = (((-1.0, -2.0), (1.0, 2.0)), ((-1.0, 3.0), (1.0, -1.0)))
        second = (((1.0, 2.0), (-1.0, -2.0)), ((-1.0, 3.0), (1.0, -1.0)))
        self.assertNotEqual(MODULE.table_fingerprint(first), MODULE.table_fingerprint(second))


if __name__ == "__main__":
    unittest.main()
