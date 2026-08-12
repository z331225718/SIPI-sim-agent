"""Mutation tests for the Agent-COM S-parameter authorization preflight."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p3c_agent_com_source_preflight", ROOT / "tools" / "verify_p3c_agent_com_sparam_source_authorization_preflight.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


class AgentComSparameterSourceAuthorizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load((ROOT / "docs" / "baselines" / "p3c-agent-com-sparam-source-authorization-preflight.v1.yaml").read_text(encoding="utf-8"))

    def test_static_review_is_exact_and_direct_port_remains_blocked(self) -> None:
        report = GATE.verify_document(self.document)
        self.assertEqual(report["candidate_count"], 3)
        self.assertFalse(report["direct_port_admitted"])

    def test_rejects_promotion_or_removed_r480_blocker(self) -> None:
        promoted = copy.deepcopy(self.document)
        promoted["authority"]["direct_port_admitted"] = True
        with self.assertRaises(GATE.PreflightError):
            GATE.verify_document(promoted)
        relaxed = copy.deepcopy(self.document)
        relaxed["blockers"].remove("p5_authoritative_r480_reference_missing")
        with self.assertRaises(GATE.PreflightError):
            GATE.verify_document(relaxed)

    def test_rejects_identity_lineage_and_policy_mutation(self) -> None:
        for mutate in (
            lambda value: value["candidates"][0].__setitem__("content_sha256", "0" * 64),
            lambda value: value["candidates"][1].__setitem__("declared_lineage_markers", []),
            lambda value: value["review_requirements"]["product_policy"].remove("dc_policy"),
            lambda value: value["review_requirements"]["excluded_material"].remove("matlab_src"),
        ):
            altered = copy.deepcopy(self.document)
            mutate(altered)
            with self.assertRaises(GATE.PreflightError):
                GATE.verify_document(altered)


if __name__ == "__main__":
    unittest.main()
