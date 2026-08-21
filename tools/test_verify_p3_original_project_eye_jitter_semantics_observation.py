from __future__ import annotations

import copy
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))
import verify_p3_original_project_eye_jitter_semantics_observation as GATE


class OriginalProjectEyeJitterObservationTests(unittest.TestCase):
    def test_hash_bound_document_is_valid_without_external_roots(self) -> None:
        document = GATE._load()
        GATE.validate(document)

    def test_pinned_external_objects_are_verified(self) -> None:
        pybert_root = os.environ.get("SIPI_PYBERT_ROOT")
        agent_com_root = os.environ.get("SIPI_AGENT_COM_ROOT")
        if not pybert_root or not agent_com_root:
            self.skipTest("set SIPI_PYBERT_ROOT and SIPI_AGENT_COM_ROOT for external object verification")
        GATE._verify_external_source("pybert", Path(pybert_root))
        GATE._verify_external_source("agent-com", Path(agent_com_root))

    def test_content_sha256_cannot_pose_as_git_blob(self) -> None:
        document = copy.deepcopy(GATE._load())
        document["sources"][0]["files"][0]["git_blob_sha1"] = "a" * 64
        with self.assertRaisesRegex(GATE.EvidenceError, "source_file_binding_invalid"):
            GATE.validate(document)

    def test_pending_decision_cannot_be_promoted(self) -> None:
        document = copy.deepcopy(GATE._load())
        document["decision_surface"]["p3c_02_eye_folding_bins"] = "selected"
        with self.assertRaisesRegex(GATE.EvidenceError, "decision_surface_invalid"):
            GATE.validate(document)

    def test_mismatch_cannot_be_rewritten_as_pass(self) -> None:
        document = copy.deepcopy(GATE._load())
        document["strict_waveform_reference"]["full_chain_nrmse"] = 0.0
        with self.assertRaisesRegex(GATE.EvidenceError, "strict_waveform_reference_invalid"):
            GATE.validate(document)


if __name__ == "__main__":
    unittest.main()
