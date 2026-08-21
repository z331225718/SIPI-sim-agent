from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import sys
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_p3c_exact_impulse_current_replay_evidence",
    ROOT / "tools/verify_p3c_exact_impulse_current_replay_evidence.py",
)
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = GATE
SPEC.loader.exec_module(GATE)


class ExactImpulseCurrentReplayEvidenceTests(unittest.TestCase):
    def document(self) -> dict[str, object]:
        return copy.deepcopy(yaml.safe_load(GATE.DEFAULT.read_text(encoding="utf-8")))

    def assert_invalid(self, document: dict[str, object], reason: str) -> None:
        with self.assertRaisesRegex(GATE.VerificationError, reason):
            GATE.verify(document, ROOT)

    def test_record_is_valid_but_replay_and_release_remain_blocked(self) -> None:
        result = GATE.verify(self.document(), ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["ticket"], "T08")
        self.assertEqual(result["status"], "external_only_two_fresh_current_replay_blocked_missing_ads_reference")
        self.assertFalse(result["external_replay_executed"])
        self.assertFalse(result["ads_reference_available"])
        self.assertFalse(result["release_admitted"])

    def test_input_and_search_mutations_fail_closed(self) -> None:
        document = self.document()
        document["inputs"]["selected_s4p"]["sha256"] = "0" * 64
        self.assert_invalid(document, "input_identity")

        document = self.document()
        document["inputs"]["ads_reference"]["search"]["bytes_reconstructed"] = True
        self.assert_invalid(document, "input_identity")

        document = self.document()
        document["inputs"]["ads_reference"]["search"]["old_report_reused"] = True
        self.assert_invalid(document, "input_identity")

        document = self.document()
        document["inputs"]["ads_reference"]["search"]["exact_length_matches"] = 1
        self.assert_invalid(document, "input_identity")

    def test_replay_and_promotion_mutations_fail_closed(self) -> None:
        document = self.document()
        document["replay"]["runner_invoked"] = True
        self.assert_invalid(document, "replay_blocked_state")

        document = self.document()
        document["replay"]["strict_index_nrmse_bits"] = "3f80000000000000"
        self.assert_invalid(document, "replay_blocked_state")

        document = self.document()
        document["admission"]["external_replay_executed"] = True
        self.assert_invalid(document, "admission_fail_closed")

        document = self.document()
        document["status"] = "prepared_observed_not_accepted"
        self.assert_invalid(document, "record_identity")

        document = self.document()
        document["blockers"] = []
        self.assert_invalid(document, "blockers")

        document = self.document()
        document["rust_runner_probe"]["rejection_reason"] = "accepted"
        self.assert_invalid(document, "rust_runner_probe")

    def test_lineage_and_build_mutations_fail_closed(self) -> None:
        document = self.document()
        document["baseline"]["tree"] = "0" * 40
        self.assert_invalid(document, "baseline_identity")

        document = self.document()
        document["observer"]["sha256"] = "0" * 64
        self.assert_invalid(document, "observer_identity")

        document = self.document()
        document["inputs"]["product_cli"]["cargo_offline"] = False
        self.assert_invalid(document, "input_identity")

        document = self.document()
        document["inputs"]["product_cli"]["target_external"] = False
        self.assert_invalid(document, "input_identity")

    def test_report_cannot_gain_paths_or_payloads(self) -> None:
        document = self.document()
        document["non_claims"][0] = "C:/external/report.json"
        self.assert_invalid(document, "non_claims")

        document = self.document()
        document["waveform"] = []
        self.assert_invalid(document, "top_level_shape")

    def test_unknown_top_level_field_is_rejected(self) -> None:
        document = self.document()
        document["reference_waveform"] = {"sha256": "0" * 64}
        self.assert_invalid(document, "top_level_shape")


if __name__ == "__main__":
    unittest.main()
