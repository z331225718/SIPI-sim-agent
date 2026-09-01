"""Mutation tests for the AS-03/AS-04 owner-exclusion successor gate."""

from __future__ import annotations

import copy
import unittest

import yaml

from tools import verify_as03_as04_owner_exclusion as gate


EXPECTED_VERIFIER_SHA = "df41a6f2a1d8694dc69b2202daa62fc4f2360a2e623e0c485073fe40a40511b8"


class OwnerExclusionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ledger_predecessor = gate._load(gate.LEDGER_PREDECESSOR)
        cls.inventory_predecessor = gate._load(gate.INVENTORY_PREDECESSOR)
        cls.owner = gate._load(gate.RECORD)
        cls.ledger = gate._load(gate.LEDGER)
        cls.inventory = gate._load(gate.INVENTORY)

    def reject_ledger(self, mutate) -> None:
        document = copy.deepcopy(self.ledger)
        mutate(document)
        with self.assertRaises(gate.ExclusionError):
            gate._validate_ledger(document, self.ledger_predecessor, self.owner)

    def reject_inventory(self, mutate) -> None:
        document = copy.deepcopy(self.inventory)
        mutate(document)
        with self.assertRaises(gate.ExclusionError):
            gate._validate_inventory(document, self.inventory_predecessor)

    def test_baseline_and_self_anchor(self) -> None:
        self.assertEqual(gate._normalised_sha(gate.VERIFIER), EXPECTED_VERIFIER_SHA)
        result = gate.validate()
        self.assertTrue(result["valid"])
        self.assertEqual(result["excluded_rows"], ["AS-03", "AS-04"])

    def test_owner_decision_cannot_promote_or_reach(self) -> None:
        mutated = copy.deepcopy(self.owner)
        mutated["decision"]["disposition"] = "retained_external_runtime"
        with self.assertRaises(gate.ExclusionError):
            gate._validate_owner_record(mutated)
        mutated = copy.deepcopy(self.owner)
        mutated["decision"]["historical_quarantine_not_product_reachable"] = False
        with self.assertRaises(gate.ExclusionError):
            gate._validate_owner_record(mutated)

    def test_candidate_binding_is_locked_in_all_successors(self) -> None:
        for key, value in (
            ("commit", "0" * 40),
            ("tree", "0" * 40),
            ("archive_sha256", "0" * 64),
        ):
            mutated = copy.deepcopy(self.owner)
            mutated["candidate"][key] = value
            with self.assertRaises(gate.ExclusionError):
                gate._validate_owner_record(mutated)
            self.reject_inventory(lambda document, key=key, value=value: document["candidate"].__setitem__(key, value))
            self.reject_ledger(lambda document, key=key, value=value: document["candidate"].__setitem__(key, value))
        mutated = copy.deepcopy(self.inventory)
        mutated["candidate"]["archive_bytes"] += 1
        with self.assertRaises(gate.ExclusionError):
            gate._validate_inventory(mutated, self.inventory_predecessor)

    def test_ledger_excludes_exactly_two_rows(self) -> None:
        for row_id in ("AS-03", "AS-04"):
            self.reject_ledger(lambda document, row_id=row_id: next(row for row in document["rows"] if row["id"] == row_id)["current_observation"].__setitem__("status", "open"))
            self.reject_ledger(lambda document, row_id=row_id: next(row for row in document["rows"] if row["id"] == row_id)["current_observation"].__setitem__("parity_claim", "accepted"))
        self.reject_ledger(lambda document: next(row for row in document["rows"] if row["id"] == "AS-05").__setitem__("release_state", "excluded_no_release"))
        self.reject_ledger(lambda document: document["summary"].__setitem__("excluded_fail_closed", 2))

    def test_inventory_excludes_exactly_two_rows(self) -> None:
        for row_id in ("AS-03", "AS-04"):
            self.reject_inventory(lambda document, row_id=row_id: next(row for row in document["entries"] if row["id"] == row_id).__setitem__("completion", "open"))
            self.reject_inventory(lambda document, row_id=row_id: next(row for row in document["entries"] if row["id"] == row_id).__setitem__("reachable_inventory", "pinned_reachable_inventory_bound"))
        self.reject_inventory(lambda document: next(row for row in document["entries"] if row["id"] == "AS-05").__setitem__("completion", "excluded_by_owner"))
        self.reject_inventory(lambda document: document["summary"].__setitem__("open", 15))

    def test_successor_and_historical_bindings_are_locked(self) -> None:
        self.reject_ledger(lambda document: document["successor"].__setitem__("predecessor_sha256", "0" * 64))
        self.reject_inventory(lambda document: document["successor"].__setitem__("predecessor_sha256", "0" * 64))
        self.reject_ledger(lambda document: document["owner_exclusion"]["record"].__setitem__("sha256", "0" * 64))
        self.reject_ledger(lambda document: document["rows"][2]["evidence"].__setitem__("sha256", "0" * 64))

    def test_untouched_rows_and_policies_are_locked(self) -> None:
        for row_id in ("AS-01", "AS-02", "AS-05", "AS-06"):
            self.reject_ledger(lambda document, row_id=row_id: next(row for row in document["rows"] if row["id"] == row_id).__setitem__("integration_disposition", "retained_external_runtime"))
        self.reject_ledger(lambda document: document["policy"].__setitem__("s_parameter_fit", "allowed"))
        self.reject_ledger(lambda document: document["policy"].__setitem__("channel_policy", "multi_pass_sparam_fit"))
        self.reject_inventory(lambda document: document["feature_policy"].__setitem__("new_domain_features_allowed", True))

    def test_duplicate_and_nonfinite_yaml_are_rejected(self) -> None:
        with self.assertRaises(gate.ExclusionError):
            yaml.load("a: 1\na: 2\n", Loader=gate.StrictLoader)
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(gate.ExclusionError):
                gate._finite({"value": value})

    def test_audit_markers_are_required(self) -> None:
        audit = gate.AUDIT.read_text(encoding="utf-8")
        gate._validate_audit_text(audit)
        with self.assertRaises(gate.ExclusionError):
            gate._validate_audit_text(audit.replace("parity, acceptance, product capability, or release readiness", "parity only"))


if __name__ == "__main__":
    unittest.main()
