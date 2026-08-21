"""Mutation tests for the rejected-at-evaluation P7 current-chain record."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p7_current_rejected", ROOT / "tools" / "verify_p7_current_candidate_chain_rejected_evaluation.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


class CurrentCandidateRejectedEvaluationTests(unittest.TestCase):
    def document(self) -> dict:
        return json.loads((ROOT / "docs" / "baselines" / "p7-current-candidate-chain-rejected-evaluation.v1.yaml").read_text(encoding="utf-8"))

    def test_document_is_valid(self) -> None:
        GATE.validate(self.document())

    def test_rejection_and_promotion_state_are_fail_closed(self) -> None:
        document = self.document()
        document["stage_observations"]["evaluation"]["report_present"] = True
        with self.assertRaisesRegex(GATE.ChainError, "evaluation_stage_invalid"):
            GATE.validate(document)
        document = self.document()
        document["promotion_status"] = "ready"
        with self.assertRaisesRegex(GATE.ChainError, "promotion_state_invalid"):
            GATE.validate(document)

    def test_candidate_identity_and_custody_are_bound(self) -> None:
        document = self.document()
        document["candidate_cargo_lock_sha256"] = "0" * 64
        with self.assertRaisesRegex(GATE.ChainError, "candidate_lock_mismatch"):
            GATE.validate(document)
        document = self.document()
        document["performance_policy_custody"]["status"] = "available"
        with self.assertRaisesRegex(GATE.ChainError, "performance_policy_custody_invalid"):
            GATE.validate(document)

    def test_external_rejection_output_digest_and_stage_binding(self) -> None:
        document = self.document()
        rejection = {"reason": "evidence_json_invalid", "schema": "sipi.p7-fixed-tran-candidate-performance-evaluation.v1", "status": "rejected"}
        raw = (json.dumps(rejection, sort_keys=True) + "\n").encode()
        document["evidence"]["evaluation_rejection_output"] = {"sha256": GATE.sha256_bytes(raw), "bytes": len(raw)}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evaluation-rejection.json"
            path.write_bytes(raw)
            GATE._external_json(path, document["evidence"]["evaluation_rejection_output"], "evaluation_rejection_output")
            tampered = copy.deepcopy(rejection)
            tampered["reason"] = "within_policy"
            path.write_bytes((json.dumps(tampered, sort_keys=True) + "\n").encode())
            with self.assertRaisesRegex(GATE.ChainError, "evaluation_rejection_output_identity_mismatch"):
                GATE._external_json(path, document["evidence"]["evaluation_rejection_output"], "evaluation_rejection_output")


if __name__ == "__main__":
    unittest.main()
