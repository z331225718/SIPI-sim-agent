"""Tests for the owner-input request verifier."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_owner_input_request as GATE


class OwnerInputTests(unittest.TestCase):
    def test_request_matches_ledger_input_classes(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["entries"], 10)
        self.assertEqual(result["owner_decision"], 5)
        self.assertEqual(result["external_asset"], 5)

    def test_every_entry_has_decision_point_and_gate(self) -> None:
        request = GATE.load_yaml(GATE.DEFAULT)
        for entry in request["entries"]:
            self.assertTrue(entry["decision_point"], entry["id"])
            self.assertTrue((ROOT / entry["gate"]).is_file(), f"{entry['id']}: {entry['gate']}")

    def test_p4b08_requests_only_remaining_external_runtime_facts(self) -> None:
        request = GATE.load_yaml(GATE.DEFAULT)
        entry = next(item for item in request["entries"] if item["id"] == "P4B-08")
        self.assertEqual(entry["kind"], "external_asset")
        self.assertIn("topology/port mapping is already observed", entry["decision_point"])
        self.assertIn("dynamic dependency closure", entry["decision_point"])
        self.assertEqual(
            entry["gate"],
            "tools/verify_p4b_08c_ads_netlist_topology_semantic_response.py",
        )

    def test_rejects_extra_entry(self) -> None:
        request = copy.deepcopy(GATE.load_yaml(GATE.DEFAULT))
        request["entries"].append({"id": "P2-06", "kind": "owner_decision", "decision_point": "x", "gate": "tools/verify_p2_06_stage_compare_coverage.py"})
        # 直接构造：写临时文件验证 set drift
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "request.yaml"
            tmp_path.write_text(GATE.yaml.safe_dump(request, sort_keys=False), encoding="utf-8")
            with mock.patch.object(GATE, "DEFAULT", tmp_path):
                with self.assertRaises(GATE.OwnerInputError):
                    GATE.validate(ROOT)


if __name__ == "__main__":
    unittest.main()
