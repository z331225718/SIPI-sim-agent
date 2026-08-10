"""Tests for P4A IBIS 7.1 observation-scope preflight."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p4a_ibis71_scope", ROOT / "tools" / "verify_p4a_ibis71_behavior_scope_preflight.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)
MANIFEST = ROOT / "docs" / "baselines" / "p4a-ibis71-behavior-scope-preflight.v1.yaml"


class Ibis71ScopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))

    def test_candidate_scope_stays_blocked_without_runtime(self) -> None:
        report = GATE.validate_manifest(self.document)
        self.assertEqual(report["black_box_status"], "not_run_blocked_asset_identity")
        self.assertFalse(report["required"])

    def test_rejects_candidate_promotion_and_runtime_inference(self) -> None:
        altered = copy.deepcopy(self.document)
        altered["candidate_fact"]["required"] = True
        with self.assertRaises(GATE.ScopeError):
            GATE.validate_manifest(altered)
        altered = copy.deepcopy(self.document)
        altered["semantic_boundary"]["algorithmic_attachment_implies_runtime"] = "allowed"
        with self.assertRaises(GATE.ScopeError):
            GATE.validate_manifest(altered)

    def test_rejects_raw_asset_material_or_run_status_upgrade(self) -> None:
        altered = copy.deepcopy(self.document)
        altered["non_claims"].append("[IBIS Ver] 7.1")
        with self.assertRaises(GATE.ScopeError):
            GATE.validate_manifest(altered)
        altered = copy.deepcopy(self.document)
        altered["observation_scope"][-1]["status"] = "run_passed"
        with self.assertRaises(GATE.ScopeError):
            GATE.validate_manifest(altered)


if __name__ == "__main__":
    unittest.main()
