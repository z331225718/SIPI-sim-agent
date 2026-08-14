from __future__ import annotations

import copy
import unittest

import verify_p3c_selected_highloss_prbs9_waveform_only_v3 as gate


class WaveformOnlyVerifierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = gate.load(gate.CONTRACT)

    def test_current_contract_passes(self) -> None:
        self.assertTrue(gate.verify_document(self.document)["selected_profile_only"])

    def test_eye_or_tie_reenablement_fails_closed(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["eye"]["status"] = "evaluated"
        with self.assertRaisesRegex(gate.WaveformOnlyError, "contract_v3_drift"):
            gate.verify_document(mutated)

    def test_waveform_alignment_relaxation_fails_closed(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["waveform_compare"]["alignment"] = "allowed"
        with self.assertRaisesRegex(gate.WaveformOnlyError, "contract_v3_drift"):
            gate.verify_document(mutated)


if __name__ == "__main__":
    unittest.main()
