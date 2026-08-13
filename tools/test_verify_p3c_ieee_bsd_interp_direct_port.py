"""Mutation tests for the selected IEEE BSD interpolation direct-port boundary."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p3c_ieee_interp", ROOT / "tools" / "verify_p3c_ieee_bsd_interp_direct_port.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


class DirectPortTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load((ROOT / "docs" / "baselines" / "p3c-ieee-bsd-interp-direct-port.v1.yaml").read_text(encoding="utf-8"))

    def test_exact_record_and_local_license_surface_pass(self) -> None:
        self.assertFalse(GATE.verify_document(self.document)["release_admitted"])
        GATE.verify_files()

    def test_policy_source_and_gate_mutations_reject(self) -> None:
        for mutate in (
            lambda value: value["policy"].__setitem__("magnitude_branch", "old"),
            lambda value: value["policy"].__setitem__("debug_bypass", "enabled"),
            lambda value: value["source"].__setitem__("license", "MIT"),
            lambda value: value["source"]["excluded_source_objects"].pop(),
            lambda value: value["gates"].__setitem__("ifft_implemented", True),
            lambda value: value["gates"].__setitem__("release_ledger_promoted", True),
        ):
            altered = copy.deepcopy(self.document)
            mutate(altered)
            with self.assertRaises(GATE.DirectPortError):
                GATE.verify_document(altered)


if __name__ == "__main__":
    unittest.main()
