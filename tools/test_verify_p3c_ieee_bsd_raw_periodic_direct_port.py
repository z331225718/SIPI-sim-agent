"""Mutation tests for the selected IEEE BSD raw-periodic direct-port boundary."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "p3c_raw_periodic_direct_port",
    ROOT / "tools" / "verify_p3c_ieee_bsd_raw_periodic_direct_port.py",
)
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


class RawPeriodicDirectPortTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load(
            (ROOT / "docs" / "baselines" / "p3c-ieee-bsd-raw-periodic-direct-port.v1.yaml").read_text(encoding="utf-8")
        )

    def test_exact_record_and_license_surface_pass(self) -> None:
        self.assertEqual(
            GATE.verify_document(self.document),
            {"valid": True, "raw_periodic_implemented": True, "release_admitted": False},
        )
        GATE.verify_files()

    def test_policy_source_and_gate_mutations_reject(self) -> None:
        for mutate in (
            lambda value: value["policy"]["inverse"].__setitem__("normalization", "none"),
            lambda value: value["policy"]["time_axis"].__setitem__("fftshift", "enabled"),
            lambda value: value["policy"].__setitem__("truncation", "threshold"),
            lambda value: value["source"].__setitem__("license", "MIT"),
            lambda value: value["source"]["excluded_source_objects"].clear(),
            lambda value: value["gates"].__setitem__("causal_impulse_admitted", True),
            lambda value: value["gates"].__setitem__("release_ledger_promoted", True),
            lambda value: value["blockers"].remove("external_selected_raw_periodic_response_observation_missing"),
        ):
            altered = copy.deepcopy(self.document)
            mutate(altered)
            with self.assertRaises(GATE.DirectPortError):
                GATE.verify_document(altered)


if __name__ == "__main__":
    unittest.main()
