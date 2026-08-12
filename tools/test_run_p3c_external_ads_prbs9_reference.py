"""Unit checks for the ADS runner's non-runtime fail-closed boundary."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p3c_ads_runner", ROOT / "tools/run_p3c_external_ads_prbs9_reference.py")
assert SPEC and SPEC.loader
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class ExternalAdsRunnerTests(unittest.TestCase):
    def test_frozen_prbs9_period_is_used_as_explicit_bits(self) -> None:
        period = RUNNER.prbs9_period()
        self.assertEqual(len(period), 511)
        self.assertEqual(RUNNER.sha256_file_bytes(period.encode("ascii")), RUNNER.PERIOD_SHA256)
        netlist = RUNNER.build_netlist(period * RUNNER.PERIODS)
        RUNNER.assert_netlist_isolated(netlist)
        self.assertIn("PRBSsrc:TXP txp 0 0 0 Mode=2", netlist)
        self.assertIn("PRBSsrc:TXM txm 0 0 0 Mode=2", netlist)
        self.assertIn("SnP:CHANNEL txp rxp txm rxm", netlist)

    def test_run_id_is_allowlisted_and_payload_only_excludes_endpoint(self) -> None:
        self.assertTrue(RUNNER.valid_run_id("fresh_run-1"))
        for invalid in ("run/name", "run\\name", "run'name", "run;name", "run name", ".."):
            self.assertFalse(RUNNER.valid_run_id(invalid))
        values = [(index * RUNNER.SAMPLE_INTERVAL_SECONDS, 1.0, -1.0) for index in range(RUNNER.TOTAL_SAMPLES + 1)]
        payload = RUNNER.canonical_waveform_payload(values)
        self.assertEqual(len(payload), RUNNER.TOTAL_SAMPLES * 24)


if __name__ == "__main__":
    unittest.main()
