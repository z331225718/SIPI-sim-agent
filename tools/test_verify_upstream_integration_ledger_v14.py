"""Mutation tests for additive upstream integration ledger v14."""

import copy
import hashlib
import os
import tempfile
import unittest
from pathlib import Path

import yaml

from tools import verify_upstream_integration_ledger_v14 as gate

EXPECTED_VERIFIER_SHA = "0b9bfe0ca73d7e24a340e77bff5bbc250d8a262859c7dd6cd97d9bfff7a81c7f"

class LedgerV14Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.document = gate.load()
    def reject(self, mutate):
        document = copy.deepcopy(self.document); mutate(document)
        with self.assertRaises(gate.LedgerError): gate.validate(document)
    def row(self, document, row_id): return next(item for item in document["rows"] if item["id"] == row_id)
    def test_baseline(self):
        self.assertEqual(EXPECTED_VERIFIER_SHA, gate.VERIFIER_SHA)
        self.assertEqual(gate.validate(copy.deepcopy(self.document)), {"valid": True, "rows": 15, "release_ready": 0})
    def test_candidate_predecessor_and_shape(self):
        self.reject(lambda d: d["candidate"].__setitem__("commit", "0" * 40))
        self.reject(lambda d: d["successor"].__setitem__("predecessor_sha256", "0" * 64))
        self.reject(lambda d: d.__setitem__("unexpected", True))
        self.reject(lambda d: d["rows"].append(copy.deepcopy(d["rows"][0])))
    def test_formal_record_custody(self):
        for key in ("as06", "com02_04", "pb01_02"):
            self.reject(lambda d, key=key: d["formal_records"][key]["manifest"].__setitem__("sha256", "0" * 64))
            self.reject(lambda d, key=key: d["formal_records"][key]["gate"].__setitem__("commit", "0" * 40))
            self.reject(lambda d, key=key: d["formal_records"][key]["record"].__setitem__("tree", "0" * 40))
    def test_as06_cannot_promote(self):
        for key in ("solver_correctness", "acceptance", "release_ready", "s_parameter_fit", "as05_xyce_xdm"):
            self.reject(lambda d, key=key: self.row(d, "AS-06")["current_observation"].__setitem__(key, True))
    def test_com_cannot_promote_or_invent_wire(self):
        for row_id in ("COM-02", "COM-04"):
            for key in ("upstream_numeric_parity", "port_order_result_wire", "acceptance", "release_ready"):
                self.reject(lambda d, row_id=row_id, key=key: self.row(d, row_id)["current_observation"].__setitem__(key, True))
            self.reject(lambda d, row_id=row_id: self.row(d, row_id)["current_observation"].__setitem__("dfe_winner_taps_published", False))
    def test_pb_scopes_are_locked(self):
        self.reject(lambda d: self.row(d, "PB-01")["current_observation"].__setitem__("whole_payload_parity", True))
        self.reject(lambda d: self.row(d, "PB-01")["current_observation"].__setitem__("scope", "complete"))
        self.reject(lambda d: self.row(d, "PB-02")["current_observation"].__setitem__("blocker_count", 12))
        self.reject(lambda d: self.row(d, "PB-02")["current_observation"].__setitem__("complete_typed_output_parity", True))
    def test_global_policy_and_summary(self):
        self.reject(lambda d: d["policy"].__setitem__("s_parameter_fit", "allowed"))
        self.reject(lambda d: d["policy"].__setitem__("channel_policy", "multiple_conversions"))
        self.reject(lambda d: d["summary"].__setitem__("release_ready", 1))
        self.reject(lambda d: self.row(d, "AS-05")["current_observation"].__setitem__("xyce_xdm_extension", "implemented"))
    def test_harness_plan_audit_bindings(self):
        self.reject(lambda d: d["plan"].__setitem__("sha256", "0" * 64))
        self.reject(lambda d: d["audit"].__setitem__("sha256", "0" * 64))
        self.reject(lambda d: d["harness"]["mutation_tests"].__setitem__("sha256", "0" * 64))
    def test_duplicate_and_nonfinite_yaml_rejected(self):
        with self.assertRaises(gate.LedgerError): yaml.load("a: 1\na: 2\n", Loader=gate.StrictLoader)
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(gate.LedgerError): gate.finite({"value": value})
    def test_component_link_and_hardlink_admission(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); regular = root / "regular"; regular.write_text("x", encoding="utf-8")
            self.assertTrue(gate.safe("regular", root))
            hard = root / "hard"
            try:
                os.link(regular, hard); self.assertFalse(gate.safe("regular", root)); self.assertFalse(gate.safe("hard", root))
            except OSError: pass
            nested = root / "nested"; nested.mkdir(); (nested / "value").write_text("x", encoding="utf-8")
            link = root / "link"
            try:
                link.symlink_to(nested, target_is_directory=True); self.assertFalse(gate.safe("link/value", root))
            except OSError: pass
    def test_coordinated_physical_harness_and_audit_drift_rejected(self):
        mutated = copy.deepcopy(self.document)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for section in ("verifier", "mutation_tests"):
                binding = mutated["harness"][section]; target = root / binding["path"]; target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((gate.ROOT / binding["path"]).read_bytes() + b"\n# coordinated append\n"); binding["sha256"] = gate.sha(target, root)
            audit = root / mutated["audit"]["path"]; audit.parent.mkdir(parents=True, exist_ok=True); audit.write_bytes((gate.ROOT / mutated["audit"]["path"]).read_bytes() + b"\ncoordinated audit append\n")
            mutated["audit"]["sha256"] = hashlib.sha256(audit.read_bytes()).hexdigest()
            with self.assertRaises(gate.LedgerError): gate.validate(mutated, root)

if __name__ == "__main__": unittest.main()
