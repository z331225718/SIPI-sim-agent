"""Mutation tests for the additive original-project P3C channel observation."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_p3c_original_project_channel_semantics_observation",
    ROOT / "tools" / "verify_p3c_original_project_channel_semantics_observation.py",
)
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


class P3COriginalProjectChannelSemanticsObservationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load(
            (
                ROOT
                / "docs"
                / "baselines"
                / "p3c-original-project-channel-semantics-observation.v1.yaml"
            ).read_text(encoding="utf-8")
        )

    def test_current_record_is_valid_and_archive_bound(self) -> None:
        result = GATE.verify()
        self.assertTrue(result["valid"])
        self.assertTrue(result["source_phase_bound"])
        self.assertFalse(result["current_waveform_accepted"])

    def test_ads_identity_and_phase_mutations_fail_closed(self) -> None:
        mutations = (
            (
                "ads_dataset",
                lambda value: value["external_ads"]["dataset"].__setitem__(
                    "sha256", "0" * 64
                ),
            ),
            (
                "ads_dsdump",
                lambda value: value["external_ads"]["dsdump_observation"].__setitem__(
                    "first_observed_phase_one_transition_index", 64
                ),
            ),
            (
                "ads_controller_log",
                lambda value: value["external_ads"]["workspace_controller_log"].__setitem__(
                    "number_time_points_per_ui", 16
                ),
            ),
        )
        for reason, mutation in mutations:
            with self.subTest(reason=reason):
                value = copy.deepcopy(self.document)
                mutation(value)
                with self.assertRaisesRegex(GATE.VerificationError, reason):
                    GATE.verify_document(value)

    def test_pybert_identity_and_semantics_mutations_fail_closed(self) -> None:
        mutations = (
            (
                "pybert_inventory",
                lambda value: value["external_pybert"]["source_inventory"].__setitem__(
                    "src/pybert/pybert.py", "0" * 64
                ),
            ),
            (
                "pybert_semantics",
                lambda value: value["external_pybert"]["semantics"].__setitem__(
                    "inverse_transform", "linear_resample"
                ),
            ),
        )
        for reason, mutation in mutations:
            with self.subTest(reason=reason):
                value = copy.deepcopy(self.document)
                mutation(value)
                with self.assertRaisesRegex(GATE.VerificationError, reason):
                    GATE.verify_document(value)

    def test_conclusion_and_policy_mutations_fail_closed(self) -> None:
        mutations = (
            (
                "conclusion",
                lambda value: value["comparison"]["conclusion"].__setitem__(
                    "migration_authorized", True
                ),
            ),
            (
                "policy",
                lambda value: value["policy"].__setitem__("alignment", "allowed"),
            ),
        )
        for reason, mutation in mutations:
            with self.subTest(reason=reason):
                value = copy.deepcopy(self.document)
                mutation(value)
                with self.assertRaisesRegex(GATE.VerificationError, reason):
                    GATE.verify_document(value)


if __name__ == "__main__":
    unittest.main()
