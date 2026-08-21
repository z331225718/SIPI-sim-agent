"""Mutation tests for the P5-08g specified COM child closure."""

from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import verify_p5_08g_com_run_specified_scoped_closure as GATE


class P508gScopedClosureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = GATE._load(GATE.CHARTER)

    def test_current_record_and_live_route_are_valid(self) -> None:
        result = GATE.validate()
        self.assertTrue(result["valid"])
        self.assertTrue(result["p5_08_scoped_close"])
        self.assertFalse(result["p5_08_main_item_closed"])

    def test_rejects_generalized_p5_08_promotion(self) -> None:
        for field, value in (
            ("p5_08_main_item_closed", True),
            ("child_closure_required", False),
        ):
            document = copy.deepcopy(self.document)
            document["closure"][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(GATE.P508gError, "closure_decision_invalid"):
                GATE.validate(document)

    def test_rejects_threat_model_expansion(self) -> None:
        document = copy.deepcopy(self.document)
        document["threat_model"]["hostile_writer_safe"] = True
        with self.assertRaisesRegex(GATE.P508gError, "threat_model_invalid"):
            GATE.validate(document)

    def test_rejects_external_oracle_and_acceptance_promotion(self) -> None:
        for field in ("agent_com_parity", "authoritative_oracle", "external_acceptance", "release_evidence"):
            document = copy.deepcopy(self.document)
            document["scope"][field] = True
            with self.subTest(field=field), self.assertRaisesRegex(GATE.P508gError, "scope_flags_invalid"):
                GATE.validate(document)

    def test_rejects_partition_or_budget_drift(self) -> None:
        for path, value in (
            (("contract", "caller_owned_parameter_partition", "values_outside_consumed"), "accepted"),
            (("contract", "pulse", "maximum_payload_bytes"), 0),
            (("contract", "request", "maximum_containers"), 0),
            (("contract", "request", "budget_stage"), "after_deserialize"),
            (("contract", "result", "publication"), "overwrite"),
        ):
            document = copy.deepcopy(self.document)
            document[path[0]][path[1]][path[2]] = value
            with self.subTest(path=path), self.assertRaisesRegex(GATE.P508gError, "contract_scope_invalid"):
                GATE.validate(document)

    def test_rejects_history_schema_source_or_test_drift(self) -> None:
        mutations = (
            ("bindings", 0, "sha256", "0" * 64, "history_bindings_drift"),
            ("implementation", "contract_schema", "sha256", "0" * 64, "implementation_binding_invalid:contract_schema"),
            ("tests", "rust_surface", "sha256", "0" * 64, "test_binding_invalid"),
        )
        for parent, key, field, value, reason in mutations:
            document = copy.deepcopy(self.document)
            if parent == "bindings":
                document[parent][key][field] = value
            else:
                document[parent][key][field] = value
            with self.subTest(parent=parent, key=key), self.assertRaisesRegex(GATE.P508gError, reason):
                GATE.validate(document)

    def test_rejects_audit_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mutated = Path(directory) / GATE.AUDIT.name
            mutated.write_bytes(GATE.AUDIT.read_bytes() + b"\nmutation\n")
            with patch.object(GATE, "AUDIT", mutated), self.assertRaisesRegex(
                GATE.P508gError, "audit_binding_invalid"
            ):
                GATE.validate()


if __name__ == "__main__":
    unittest.main()
