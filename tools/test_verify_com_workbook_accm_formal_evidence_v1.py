"""Mutation coverage for the COM formal observation evidence gate."""

from __future__ import annotations

import copy
import pathlib
import unittest

import yaml

try:
    from .verify_com_workbook_accm_formal_evidence_v1 import validate_manifest_data, verify_formal_evidence
except ImportError:
    from verify_com_workbook_accm_formal_evidence_v1 import validate_manifest_data, verify_formal_evidence


ROOT = pathlib.Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "baselines" / "com-workbook-accm-replay-v4.manifest.yaml"


class FormalEvidenceMutationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))

    def test_valid_bundle(self) -> None:
        verify_formal_evidence(MANIFEST, ROOT)

    def assert_rejected(self, mutate) -> None:
        value = copy.deepcopy(self.data)
        mutate(value)
        with self.assertRaises(ValueError):
            validate_manifest_data(value, MANIFEST, ROOT)

    def test_status_promotion_rejected(self): self.assert_rejected(lambda v: v.__setitem__("status", "release"))
    def test_top_level_extra_rejected(self): self.assert_rejected(lambda v: v.__setitem__("unexpected", True))
    def test_acceptance_promotion_rejected(self): self.assert_rejected(lambda v: v.__setitem__("acceptance", True))
    def test_release_ready_extra_rejected(self): self.assert_rejected(lambda v: v.__setitem__("release_ready", True))
    def test_prep_head_rejected(self): self.assert_rejected(lambda v: v["prep"]["archive"].__setitem__("command", "git archive HEAD"))
    def test_candidate_archive_rejected(self): self.assert_rejected(lambda v: v["candidate"].__setitem__("archive_sha256", "0" * 64))
    def test_upstream_fixture_rejected(self): self.assert_rejected(lambda v: v["upstream"]["s4p"].__setitem__("sha256", "0" * 64))
    def test_tool_hash_drift_rejected(self): self.assert_rejected(lambda v: v["tools"]["runner"].__setitem__("sha256", "0" * 64))
    def test_formal_gate_hash_drift_rejected(self): self.assert_rejected(lambda v: v["formal_gate"]["verifier"].__setitem__("sha256", "0" * 64))
    def test_audit_path_drift_rejected(self): self.assert_rejected(lambda v: v.__setitem__("audit", "../audit.yaml"))
    def test_audit_hash_drift_rejected(self): self.assert_rejected(lambda v: v.__setitem__("audit_sha256", "0" * 64))
    def test_report_hash_drift_rejected(self): self.assert_rejected(lambda v: v["runs"][0]["report"].__setitem__("sha256", "0" * 64))
    def test_report_short_hash_rejected(self): self.assert_rejected(lambda v: v["runs"][0]["report"].__setitem__("sha256", "0" * 63))
    def test_duplicate_run_id_rejected(self): self.assert_rejected(lambda v: v["runs"][1]["report"].__setitem__("run_id", v["runs"][0]["report"]["run_id"]))
    def test_duplicate_nonce_rejected(self): self.assert_rejected(lambda v: v["runs"][1]["report"].__setitem__("nonce", v["runs"][0]["report"]["nonce"]))
    def test_inventory_drift_rejected(self): self.assert_rejected(lambda v: v["fixed_inputs"]["cargo_inventory"].__setitem__("count", 7726))
    def test_cargo_path_leak_rejected(self): self.assert_rejected(lambda v: v["fixed_inputs"].__setitem__("cargo_home", "C:/Users/private/.cargo"))
    def test_pe_anchor_drift_rejected(self): self.assert_rejected(lambda v: v["fixed_inputs"]["typed_pe"].__setitem__("canonical_sha256", "0" * 64))
    def test_sidecar_binary_drift_rejected(self): self.assert_rejected(lambda v: v["runs"][0].__setitem__("binary_sha256", "0" * 64))
    def test_aggregate_hash_drift_rejected(self): self.assert_rejected(lambda v: v["aggregate"].__setitem__("sha256", "0" * 64))
    def test_metric_artifact_omission_rejected(self): self.assert_rejected(lambda v: v.__setitem__("artifacts", v["artifacts"][:3]))
    def test_artifact_substitution_rejected(self): self.assert_rejected(lambda v: v["artifacts"][0].__setitem__("path", v["artifacts"][1]["path"]))
    def test_numeric_graph_sidecar_drift_rejected(self): self.assert_rejected(lambda v: v["runs"][0].__setitem__("pdb_sha256", "0" * 64))
    def test_nonclaim_deletion_rejected(self): self.assert_rejected(lambda v: v["non_claims"].pop())
    def test_formal_gate_path_escape_rejected(self): self.assert_rejected(lambda v: v["formal_gate"]["tests"].__setitem__("path", "../tests.py"))


if __name__ == "__main__":
    unittest.main()
