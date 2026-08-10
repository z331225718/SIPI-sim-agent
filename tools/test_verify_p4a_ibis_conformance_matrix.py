from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verify_p4a_ibis_conformance_matrix import MatrixError, validate


class P4aIbisConformanceMatrixTests(unittest.TestCase):
    def matrix(self) -> dict:
        return yaml.safe_load((ROOT / "docs" / "baselines" / "p4a-ibis-conformance-matrix.v1.yaml").read_text(encoding="utf-8"))

    def test_current_boundary_is_complete_and_fail_closed(self) -> None:
        result = validate(self.matrix())
        self.assertTrue(result["valid"])
        self.assertEqual(result["external_profile_accepted"], 1)
        self.assertGreater(result["counts"]["unsupported"], 0)

    def test_external_identity_and_promotion_changes_are_rejected(self) -> None:
        invalid = copy.deepcopy(self.matrix())
        invalid["selected_external_profile"]["custody"] = "product_fixture"
        with self.assertRaisesRegex(MatrixError, "external_profile_identity_invalid"):
            validate(invalid)
        invalid = copy.deepcopy(self.matrix())
        invalid["entries"][0]["status"] = "implemented_self_tested"
        with self.assertRaisesRegex(MatrixError, "coverage_status_invalid"):
            validate(invalid)

    def test_unsupported_routes_and_unsafe_evidence_are_rejected(self) -> None:
        invalid = copy.deepcopy(self.matrix())
        unsupported = next(item for item in invalid["entries"] if item["status"] == "unsupported")
        unsupported["entry_points"] = ["run"]
        with self.assertRaisesRegex(MatrixError, "unsupported_entry_exposes_route"):
            validate(invalid)
        invalid = copy.deepcopy(self.matrix())
        invalid["entries"][0]["evidence_refs"] = ["C:/private/report.json"]
        with self.assertRaisesRegex(MatrixError, "evidence_reference_invalid"):
            validate(invalid)


if __name__ == "__main__":
    unittest.main()
