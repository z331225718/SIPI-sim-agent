from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import sys
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p3c_static_bench", ROOT / "tools" / "verify_p3c_selected_four_port_static_bench.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = GATE
SPEC.loader.exec_module(GATE)


class StaticBenchVerifierTests(unittest.TestCase):
    def document(self) -> dict:
        return yaml.safe_load((ROOT / "docs" / "baselines" / "p3c-selected-four-port-static-bench.v1.yaml").read_text(encoding="utf-8"))

    def test_current_document_is_valid(self) -> None:
        self.assertTrue(GATE.verify(self.document())["valid"])

    def test_rejects_port_map_reduction_and_runtime_promotion(self) -> None:
        document = self.document()
        document["external_selection"]["port_map"][1] = "tx_minus"
        with self.assertRaisesRegex(GATE.VerificationError, "source_binding"):
            GATE.verify(document)
        document = self.document()
        document["fixed_bench"]["reduction"] = "S21"
        with self.assertRaisesRegex(GATE.VerificationError, "topology"):
            GATE.verify(document)
        document = self.document()
        document["admission"]["candidate_waveform_generated"] = True
        with self.assertRaisesRegex(GATE.VerificationError, "admission"):
            GATE.verify(document)

    def test_rejects_missing_time_domain_blocker(self) -> None:
        document = copy.deepcopy(self.document())
        document["blockers"].remove("time_domain_network_policy_missing")
        with self.assertRaisesRegex(GATE.VerificationError, "time_domain"):
            GATE.verify(document)


if __name__ == "__main__":
    unittest.main()
