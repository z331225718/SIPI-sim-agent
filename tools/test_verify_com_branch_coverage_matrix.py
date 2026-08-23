from __future__ import annotations

import unittest
from pathlib import Path

import yaml

from verify_com_branch_coverage_matrix import VerificationError, verify


ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "docs" / "baselines" / "audits" / "2026-08-23-com-02-04-branch-coverage-matrix.v1.yaml"


class BranchCoverageMatrixTests(unittest.TestCase):
    def test_matrix_is_portable_complete(self) -> None:
        result = verify(MATRIX)
        self.assertEqual(result["portable_missing"], [])
        self.assertGreaterEqual(result["branch_count"], 10)

    def test_portable_missing_mutation_fails(self) -> None:
        document = yaml.safe_load(MATRIX.read_text(encoding="utf-8"))
        document["portable_missing"] = ["mmse"]
        temporary = MATRIX.with_suffix(".mutation.yaml")
        temporary.write_text(yaml.safe_dump(document), encoding="utf-8")
        try:
            with self.assertRaises(VerificationError):
                verify(temporary)
        finally:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
