"""Mutation tests for the P4B parameter selection baseline."""

from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p4b_02_parameter_selection as GATE


class ParameterSelectionTests(unittest.TestCase):
    def _validate_mutated(self, mutate) -> GATE.SelectionError:
        charter = copy.deepcopy(GATE.load_yaml(GATE.CHARTER))
        mutate(charter)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / GATE.CHARTER.name
            path.write_text(yaml.safe_dump(charter, sort_keys=False), encoding="utf-8")
            with mock.patch.object(GATE, "CHARTER", path):
                with self.assertRaises(GATE.SelectionError) as context:
                    GATE.validate(ROOT)
        return context.exception

    def test_current_baseline_is_valid_and_keep_is_empty(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["module_count"], 193)
        self.assertEqual(result["selection_counts"]["keep_for_product"], 0)
        self.assertEqual(result["selection_counts"]["quarantine_pending_requirement"], 34)
        self.assertEqual(result["selection_counts"]["delete_candidate"], 159)
        self.assertEqual(result["evidence_count"], 191)
        self.assertEqual(result["evidence_authority"], "product_owned_self_crosscheck_unbound")

    def test_keep_without_ami_requirement_is_rejected(self) -> None:
        error = self._validate_mutated(
            lambda charter: charter["groups"][0].update({"classification": "keep_for_product"})
        )
        self.assertIn("keep_without_requirement", str(error))

    def test_keep_without_live_consumer_is_rejected(self) -> None:
        def mutate(charter: dict[str, object]) -> None:
            group = charter["groups"][0]
            group["classification"] = "keep_for_product"
            group["ami_contract_requirement"]["status"] = "required"

        error = self._validate_mutated(mutate)
        self.assertIn("keep_without_consumer", str(error))

    def test_keep_cannot_be_authorized_by_unbound_crosscheck(self) -> None:
        def mutate(charter: dict[str, object]) -> None:
            group = charter["groups"][0]
            group["classification"] = "keep_for_product"
            group["ami_contract_requirement"]["status"] = "required"
            group["production_consumer"] = {
                "status": "live_default_route",
                "paths": ["crates/sipi-ami-host/src/lib.rs"],
                "symbols": ["AmiTextBindingV1"],
            }
            group["complexity_budget"]["status"] = "allocated"

        error = self._validate_mutated(mutate)
        self.assertIn("keep_without_independent_oracle_gate", str(error))

    def test_inventory_mutation_is_rejected(self) -> None:
        error = self._validate_mutated(
            lambda charter: charter["groups"][2]["selectors"]["prefixes"].clear()
        )
        self.assertIn("selector_matches_nothing", str(error))

    def test_unknown_module_selector_is_rejected(self) -> None:
        error = self._validate_mutated(
            lambda charter: charter["groups"][0]["selectors"]["exact"].append("parameter_not_real_v1")
        )
        self.assertIn("selector_unknown_exact", str(error))

    def test_mutated_evidence_status_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = []
            for index in range(GATE.EXPECTED_EVIDENCE_COUNT):
                path = Path(directory) / f"p4b-02b{index + 3}-crosscheck-evidence.v1.yaml"
                status = "matched_hash_bound" if index == 0 else GATE.EXPECTED_EVIDENCE_STATUS
                path.write_text(
                    yaml.safe_dump(
                        {
                            "schema": f"sipi.p4b-02b{index + 3}.crosscheck-evidence.v1",
                            "status": status,
                        },
                        sort_keys=False,
                    ),
                    encoding="utf-8",
                )
                paths.append(path)
            with self.assertRaisesRegex(GATE.SelectionError, "evidence_status"):
                GATE._validate_evidence_documents(paths)


if __name__ == "__main__":
    unittest.main()
