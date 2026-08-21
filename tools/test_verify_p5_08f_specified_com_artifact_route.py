"""Mutation tests for the specified/non-oracle COM artifact route."""

from __future__ import annotations

import copy
import unittest

from tools import verify_p5_08f_specified_com_artifact_route as GATE


class SpecifiedComArtifactRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = GATE._load(GATE.DOCUMENT)

    def test_current_document_is_valid(self) -> None:
        self.assertTrue(GATE.validate()["valid"])

    def test_rejects_acceptance_or_main_item_promotion(self) -> None:
        for path, value in (
            (("scope", "external_acceptance"), "accepted"),
            (("scope", "release_evidence"), True),
            (("legacy_boundary", "p5_08_main_item_closed"), True),
        ):
            document = copy.deepcopy(self.document)
            document[path[0]][path[1]] = value
            with self.subTest(path=path), self.assertRaises(GATE.RouteError):
                GATE.validate(document)

    def test_rejects_false_p5_05g_binding(self) -> None:
        document = copy.deepcopy(self.document)
        document["scope"]["p5_05g_workbook_ingestion_reused"] = True
        with self.assertRaises(GATE.RouteError):
            GATE.validate(document)

    def test_rejects_budget_or_identity_drift(self) -> None:
        for key, value in (("pulse_max_bytes", 0), ("output_publication", "overwrite")):
            document = copy.deepcopy(self.document)
            document["contract"][key] = value
            with self.subTest(key=key), self.assertRaises(GATE.RouteError):
                GATE.validate(document)

    def test_rejects_source_or_audit_drift(self) -> None:
        for parent, key in (("implementation", "cli_surface"), ("audit", None)):
            document = copy.deepcopy(self.document)
            binding = document[parent] if key is None else document[parent][key]
            binding["sha256"] = "0" * 64
            with self.subTest(parent=parent), self.assertRaises(GATE.RouteError):
                GATE.validate(document)


if __name__ == "__main__":
    unittest.main()
