"""Non-runtime boundary checks for the ADS source-only runner."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("source_only_runner", ROOT / "tools/run_p3c_external_ads_prbs9_source_only.py")
assert SPEC and SPEC.loader
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class SourceOnlyRunnerTests(unittest.TestCase):
    def test_explicit_prbs_and_matched_load_topology_are_frozen(self) -> None:
        period = RUNNER.prbs9_period()
        self.assertEqual(len(period), 511)
        netlist = RUNNER.build_netlist(period * RUNNER.PERIODS)
        RUNNER.assert_netlist_isolated(netlist)
        self.assertIn("R:TX_PLUS_MATCH txp 0 R=50 Ohm", netlist)
        self.assertIn("R:TX_MINUS_MATCH txm 0 R=50 Ohm", netlist)
        self.assertNotIn("SnP:", netlist)
        self.assertNotIn("rxp", netlist.lower())

    def test_canonical_payload_discards_only_the_inclusive_endpoint(self) -> None:
        values = [(index * RUNNER.SAMPLE_INTERVAL_SECONDS, 0.5, 0.0) for index in range(RUNNER.ADS_INCLUSIVE_SAMPLES)]
        payload = RUNNER.canonical_source_payload(values)
        self.assertEqual(len(payload), RUNNER.TOTAL_SAMPLES * 24)


if __name__ == "__main__":
    unittest.main()
