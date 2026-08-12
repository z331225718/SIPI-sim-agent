"""Mutation tests for the selective IEEE 802-COM BSD lineage observation."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p3c_ieee_bsd_lineage", ROOT / "tools" / "verify_p3c_agent_com_sparam_ieee_bsd_lineage_observation.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


class IeeeBsdLineageObservationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load((ROOT / "docs" / "baselines" / "p3c-agent-com-sparam-ieee-bsd-lineage-observation.v1.yaml").read_text(encoding="utf-8"))

    def test_exact_record_has_two_selective_source_inputs(self) -> None:
        report = GATE.verify_document(self.document)
        self.assertEqual(report["admitted_source_input_count"], 2)
        self.assertEqual(report["blocked_source_input_count"], 1)
        self.assertFalse(report["direct_port_implementation_started"])

    def test_rejects_mit_only_global_promotion_and_named_author_relaxation(self) -> None:
        for mutate in (
            lambda value: value["authority"].__setitem__("direct_port_implementation_started", True),
            lambda value: value["paths"][0].__setitem__("source_input_status", "admitted_mit_only"),
            lambda value: value["paths"][2].__setitem__("source_input_status", "admitted_bsd3_notice_and_product_policy_pending"),
            lambda value: value["blockers"].remove("causality_named_author_chain_confirmation_missing"),
        ):
            altered = copy.deepcopy(self.document)
            mutate(altered)
            with self.assertRaises(GATE.LineageError):
                GATE.verify_document(altered)

    def test_rejects_license_identity_notice_and_release_mutations(self) -> None:
        for mutate in (
            lambda value: value["ieee_802_com_source"]["root_license"].__setitem__("observed_spdx", "MIT"),
            lambda value: value["paths"][0]["ieee_802_com"]["required_markers"].pop(0),
            lambda value: value["paths"].pop(),
            lambda value: value["authority"].__setitem__("release_admitted", True),
        ):
            altered = copy.deepcopy(self.document)
            mutate(altered)
            with self.assertRaises(GATE.LineageError):
                GATE.verify_document(altered)


if __name__ == "__main__":
    unittest.main()
