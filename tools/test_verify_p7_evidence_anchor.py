"""Contract tests for the non-release P7 evidence anchor."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("anchor", ROOT / "tools" / "verify_p7_evidence_anchor.py")
assert SPEC and SPEC.loader
ANCHOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ANCHOR)
V2_SPEC = importlib.util.spec_from_file_location("anchor_v2", ROOT / "tools" / "verify_p7_evidence_anchor_v2.py")
assert V2_SPEC and V2_SPEC.loader
ANCHOR_V2 = importlib.util.module_from_spec(V2_SPEC)
V2_SPEC.loader.exec_module(ANCHOR_V2)


class EvidenceAnchorTests(unittest.TestCase):
    def document(self) -> dict:
        return json.loads((ROOT / "docs" / "baselines" / "p7-evidence-anchor.v1.yaml").read_text(encoding="utf-8"))

    def test_current_anchor_is_valid(self) -> None:
        ANCHOR.validate(self.document())

    def test_release_state_and_blockers_fail_closed(self) -> None:
        document = self.document()
        document["release_candidate"] = True
        with self.assertRaisesRegex(ANCHOR.AnchorError, "promotion_state_invalid"):
            ANCHOR.validate(document)
        document = self.document()
        document["global_blockers"] = ["license_notice_pending"]
        with self.assertRaisesRegex(ANCHOR.AnchorError, "global_blockers_invalid"):
            ANCHOR.validate(document)

    def test_record_candidate_mix_and_unsafe_reference_fail_closed(self) -> None:
        document = self.document()
        document["record_commit"] = document["candidate_source_commit"]
        with self.assertRaisesRegex(ANCHOR.AnchorError, "record_candidate_not_distinct"):
            ANCHOR.validate(document)
        document = self.document()
        document["audit_ref"] = "C:/external/audit.md"
        with self.assertRaisesRegex(ANCHOR.AnchorError, "audit_reference_invalid"):
            ANCHOR.validate(document)

    def test_external_evaluation_digest_and_chain_are_bound(self) -> None:
        document = self.document()
        report = {
            "schema": ANCHOR.EVALUATION_SCHEMA,
            "status": "within_policy",
            "promotion_status": "blocked",
            "policy_sha256": document["evidence"]["policy_sha256"],
            "observation_sha256": document["evidence"]["candidate_observation_sha256"],
            "candidate_chain": {
                "commit": document["candidate_source_commit"], "tree": document["candidate_tree"],
                "cargo_lock_sha256": document["candidate_cargo_lock_sha256"],
                "toolchain_sha256": document["candidate_toolchain_sha256"],
                "executable_sha256": document["candidate_executable_sha256"],
                "twin_report_sha256": document["evidence"]["twin_report_sha256"],
                "composition_report_sha256": document["evidence"]["composition_report_sha256"],
                "archive_report_sha256": document["evidence"]["archive_report_sha256"],
                "install_report_sha256": document["evidence"]["install_report_sha256"],
            },
            "observed_medians": {}, "thresholds": {}, "threshold_verdict": "pass", "limitations": ["provisional"],
        }
        raw = json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
        document["evidence"]["candidate_evaluation_sha256"] = ANCHOR.sha256_bytes(raw)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "evaluation.json"
            path.write_bytes(raw)
            ANCHOR.verify_external_evaluation(document, path)
            tampered = copy.deepcopy(report)
            tampered["candidate_chain"]["tree"] = "0" * 40
            path.write_text(json.dumps(tampered), encoding="utf-8")
            with self.assertRaisesRegex(ANCHOR.AnchorError, "evaluation_digest_mismatch"):
                ANCHOR.verify_external_evaluation(document, path)

    def test_v2_current_candidate_anchor_keeps_candidate_and_release_separate(self) -> None:
        document = json.loads((ROOT / "docs" / "baselines" / "p7-evidence-anchor.v2.yaml").read_text(encoding="utf-8"))
        ANCHOR_V2.validate(document)
        document["chain_state"]["release_candidate"] = True
        with self.assertRaisesRegex(ANCHOR_V2.ObservationError, "chain_state_invalid"):
            ANCHOR_V2.validate(document)

    def test_v2_candidate_and_external_reference_mutations_fail_closed(self) -> None:
        document = json.loads((ROOT / "docs" / "baselines" / "p7-evidence-anchor.v2.yaml").read_text(encoding="utf-8"))
        document["candidate_tree"] = "0" * 40
        with self.assertRaisesRegex(ANCHOR_V2.ObservationError, "candidate_git_identity_invalid"):
            ANCHOR_V2.validate(document)
        document = json.loads((ROOT / "docs" / "baselines" / "p7-evidence-anchor.v2.yaml").read_text(encoding="utf-8"))
        document["evidence"]["twin_report"]["bytes"] = 0
        with self.assertRaisesRegex(ANCHOR_V2.ObservationError, "report_reference_invalid"):
            ANCHOR_V2.validate(document)
        document = json.loads((ROOT / "docs" / "baselines" / "p7-evidence-anchor.v2.yaml").read_text(encoding="utf-8"))
        document["recording"]["candidate_tree_excludes_this_record"] = False
        with self.assertRaisesRegex(ANCHOR_V2.ObservationError, "candidate_record_separation_invalid"):
            ANCHOR_V2.validate(document)


if __name__ == "__main__":
    unittest.main()
