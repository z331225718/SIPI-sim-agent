"""Mutation tests for the P5-08h main scoped replacement."""

from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import verify_p5_08h_com_run_main_scoped_closure as GATE


class P508hMainScopedClosureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = GATE._load(GATE.EVIDENCE)

    def test_current_record_invokes_live_manifest_and_is_valid(self) -> None:
        result = GATE.validate()
        self.assertTrue(result["valid"])
        self.assertTrue(result["p5_08_main_item_closed"])
        self.assertEqual(result["route"], "com.run-artifact")
        self.assertEqual(result["legacy_com_run"], "unavailable")

    def test_rejects_main_item_reopen_or_child_disposition(self) -> None:
        document = copy.deepcopy(self.document)
        document["decision"]["p5_08_main_item_closed"] = False
        with self.assertRaisesRegex(GATE.P508hError, "decision_invalid"):
            GATE.validate(document)

    def test_rejects_historical_08g_rewrite_or_binding_drift(self) -> None:
        for field, value in (
            ("status", "p5_08_main_scoped_replacement_open"),
            ("p5_08_main_item_closed", True),
        ):
            document = copy.deepcopy(self.document)
            document["historical"]["prior_scoped_closure"][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(GATE.P508hError, "historical_binding_invalid"):
                GATE.validate(document)
        document = copy.deepcopy(self.document)
        document["historical"]["prior_scoped_closure"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(GATE.P508hError, "historical_binding_invalid"):
            GATE.validate(document)

    def test_rejects_budget_schema_threat_and_nonclaim_drift(self) -> None:
        mutations = (
            ("contract", lambda value: value["request"].update(maximum_bytes=0)),
            ("contract", lambda value: value["result"].update(schema="wrong")),
            ("threat_model", lambda value: value.update(hostile_writer_safe=True)),
            ("non_claims", lambda value: value.append("claims_acceptance")),
        )
        for field, mutation in mutations:
            document = copy.deepcopy(self.document)
            mutation(document[field])
            with self.subTest(field=field), self.assertRaisesRegex(GATE.P508hError, f"{field}_drift"):
                GATE.validate(document)

    def test_rejects_com_run_promotion_in_live_command_manifest(self) -> None:
        commands = GATE._run_command_manifest()
        promoted = copy.deepcopy(commands)
        next(command for command in promoted if command["id"] == "com.run")["availability"] = "available"
        with patch.object(GATE, "_run_command_manifest", return_value=promoted), self.assertRaisesRegex(
            GATE.P508hError, "command_manifest_legacy_com_promoted"
        ):
            GATE.validate(self.document)

    def test_rejects_specified_route_promotion_in_publication(self) -> None:
        document = copy.deepcopy(self.document)
        document["publication"]["acceptance_state"] = "accepted"
        with self.assertRaisesRegex(GATE.P508hError, "publication_binding_invalid"):
            GATE.validate(document)

    def test_rejects_blocker_promotion(self) -> None:
        document = copy.deepcopy(self.document)
        document["remaining_blockers"]["P5-02"] = "closed"
        with self.assertRaisesRegex(GATE.P508hError, "remaining_blockers_drift"):
            GATE.validate(document)

    def test_rejects_audit_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mutated = Path(directory) / GATE.AUDIT.name
            mutated.write_bytes(GATE.AUDIT.read_bytes() + b"\nmutation\n")
            with patch.object(GATE, "AUDIT", mutated), self.assertRaisesRegex(
                GATE.P508hError, "audit_binding_invalid"
            ):
                GATE.validate(self.document)


if __name__ == "__main__":
    unittest.main()
