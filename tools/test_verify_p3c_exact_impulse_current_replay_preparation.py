from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import sys
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


GATE = load("verify_p3c_exact_impulse_current_replay_preparation", "tools/verify_p3c_exact_impulse_current_replay_preparation.py")
OBSERVER = load("observe_p3c_exact_impulse_current_replay_preparation", "tools/observe_p3c_exact_impulse_current_replay_preparation.py")


class ExactImpulseCurrentReplayPreparationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load((ROOT / "docs/baselines/p3c-exact-impulse-current-replay-preparation.v1.yaml").read_text(encoding="utf-8"))

    def run_fact(self, suffix: str) -> dict[str, object]:
        return {
            "source_manifest_sha256": "1" * 64,
            "reference_manifest_sha256": "2" * 64,
            "candidate_manifest_sha256": "3" * 64,
            "record_count": 2002,
            "candidate_prefix_sha256": "4" * 64,
            "reference_rx_payload_sha256": "5" * 64,
            "candidate_payload_sha256": "6" * 64,
            "reference_waveform_digest": "7" * 64,
            "candidate_waveform_digest": "8" * 64,
            "waveform_nrmse_bits": "3f9dd1842739ab12",
            "waveform_nrmse_limit_bits": "3f847ae147ae147b",
            "within_waveform_nrmse_limit": False,
            "within_selected_waveform_only_profile": False,
        }

    def child_report(self) -> dict[str, object]:
        first = self.run_fact("first")
        second = self.run_fact("second")
        second["source_manifest_sha256"] = "9" * 64
        second["reference_manifest_sha256"] = "a" * 64
        second["candidate_manifest_sha256"] = "b" * 64
        return {
            "schema": OBSERVER.CHILD_SCHEMA,
            "status": "observed_not_accepted",
            "source_byte_length": OBSERVER.S4P_BYTES,
            "source_sha256": OBSERVER.S4P_SHA256,
            "ads_canonical_triple_payload_sha256": OBSERVER.ADS_SHA256,
            "contract_sha256": OBSERVER.CONTRACT_SHA256,
            "source_reference_identity_checks": "before_stage_after_equal",
            "fresh_runs": [first, second],
            "cleanup_status": "complete",
        }

    def test_contract_and_child_report_baseline(self) -> None:
        self.assertEqual(GATE.verify(self.document)["current_replay_preparation"], True)
        self.assertTrue(OBSERVER.assert_child_report(self.child_report()))

    def test_contract_mutations_are_fail_closed(self) -> None:
        mutations = (
            lambda value: value.__setitem__("status", "external_replay_observed"),
            lambda value: value["clean_archive"].__setitem__("worktree_execution", "allowed"),
            lambda value: value["impulse_chain"]["current_candidate"].__setitem__("ui_boundary_phase_0", "current_symbol"),
            lambda value: value["impulse_chain"]["strict_index_compare"].__setitem__("gain_fit", "allowed"),
            lambda value: value["product_source_inventory"].__setitem__("Cargo.lock", "0" * 64),
            lambda value: value["admission"].__setitem__("external_replay_executed", True),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                value = copy.deepcopy(self.document)
                mutation(value)
                with self.assertRaises(GATE.VerificationError):
                    GATE.verify(value)

    def test_child_report_mutations_are_stage_qualified(self) -> None:
        mutations = (
            lambda value: value.__setitem__("status", "accepted"),
            lambda value: value["fresh_runs"][1].__setitem__("source_manifest_sha256", value["fresh_runs"][0]["source_manifest_sha256"]),
            lambda value: value["fresh_runs"][1].__setitem__("candidate_payload_sha256", "f" * 64),
            lambda value: value["fresh_runs"][0].__setitem__("within_selected_waveform_only_profile", True),
            lambda value: value.__setitem__("source_sha256", "0" * 64),
            lambda value: value.__setitem__("path", "C:/external/report.json"),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                value = self.child_report()
                mutation(value)
                with self.assertRaises(OBSERVER.FreshReplayError):
                    OBSERVER.assert_child_report(value)

    def test_archive_and_external_boundaries(self) -> None:
        self.assertEqual(OBSERVER.clean_archive_tree(OBSERVER.BASELINE_COMMIT), OBSERVER.BASELINE_TREE)
        with self.assertRaisesRegex(OBSERVER.FreshReplayError, "commit_invalid"):
            OBSERVER.clean_archive_tree("not-a-commit")
        with self.assertRaisesRegex(OBSERVER.FreshReplayError, "must_be_external"):
            OBSERVER.require_external(ROOT / "docs", kind="input")


if __name__ == "__main__":
    unittest.main()
