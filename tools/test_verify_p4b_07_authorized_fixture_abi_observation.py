"""Tests for the P4B-07a authorized-fixture ABI observation verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p4b_07_authorized_fixture_abi_observation as GATE


class ObservationTests(unittest.TestCase):
    def test_current_observation_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["tx_probes"], 4)
        self.assertEqual(result["rx_probes"], 4)

    def test_tx_all_success_and_rx_crash_recorded(self) -> None:
        evidence = GATE.load_yaml(GATE.EVIDENCE)
        entries = {entry["dll_id"]: entry for entry in evidence["entries"]}
        self.assertTrue(all(s == "success" for s in entries["ads-pcie-gen5-tx-dll"]["probe_statuses"].values()))
        self.assertTrue(all(s == "probe_crash" for s in entries["ads-pcie-gen5-rx-dll"]["probe_statuses"].values()))

    def test_dll_hashes_match_registry(self) -> None:
        registry = GATE.load_yaml(GATE.REGISTRY)
        registered = {m["id"]: m for m in registry["materials"]}
        self.assertEqual(registered["ads-pcie-gen5-tx-dll"]["sha256"], GATE.TX_DLL)
        self.assertEqual(registered["ads-pcie-gen5-rx-dll"]["sha256"], GATE.RX_DLL)

    def test_plan_row_present(self) -> None:
        plan_text = GATE.PLAN.read_text(encoding="utf-8")
        self.assertIn("**P4B-07a", plan_text)

    def test_rejects_probe_input_drift(self) -> None:
        charter = GATE.load_yaml(GATE.CHARTER)
        charter["probe_inputs"]["bit_time_s"] = 1e-9
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "charter.yaml"
            tmp_path.write_text(GATE.yaml.safe_dump(charter, sort_keys=False), encoding="utf-8")
            import unittest.mock as mock
            with mock.patch.object(GATE, "CHARTER", tmp_path):
                with self.assertRaises(GATE.ObservationError):
                    GATE.validate(ROOT)


if __name__ == "__main__":
    unittest.main()
