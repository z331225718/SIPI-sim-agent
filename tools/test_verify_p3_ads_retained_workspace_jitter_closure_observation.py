from __future__ import annotations

import copy
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))
import verify_p3_ads_retained_workspace_jitter_closure_observation as GATE


class AdsRetainedWorkspaceClosureTests(unittest.TestCase):
    def test_document_only_is_valid(self) -> None:
        GATE.validate(GATE._load())

    def test_external_workspace_is_verified_when_injected(self) -> None:
        workspace_root = os.environ.get("SIPI_ADS_WORKSPACE_ROOT")
        if not workspace_root:
            self.skipTest("set SIPI_ADS_WORKSPACE_ROOT for external workspace verification")
        GATE._verify_workspace(Path(workspace_root))

    def test_disabled_jitter_output_cannot_be_promoted(self) -> None:
        document = copy.deepcopy(GATE._load())
        document["observed_configuration"]["eye_probe"]["save_jitter_rms"] = True
        with self.assertRaisesRegex(GATE.EvidenceError, "observed_configuration_invalid"):
            GATE.validate(document)

    def test_dataset_digest_drift_is_rejected(self) -> None:
        document = copy.deepcopy(GATE._load())
        document["workspace"]["files"][3]["sha256"] = "0" * 64
        with self.assertRaisesRegex(GATE.EvidenceError, "workspace_file_binding_invalid"):
            GATE.validate(document)


if __name__ == "__main__":
    unittest.main()
