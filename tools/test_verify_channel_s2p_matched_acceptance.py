from __future__ import annotations

import copy
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from verify_channel_s2p_matched_acceptance import _load, verify_document


class MatchedS2pAcceptanceTests(unittest.TestCase):
    def document(self) -> dict:
        return copy.deepcopy(_load(ROOT / "docs" / "baselines" / "channel-s2p-matched-acceptance.v1.yaml"))

    def source(self, document: dict) -> Path:
        root = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.email", "tests@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.name", "SIPI tests"], check=True)
        path = root / "models" / "channel.s2p"; path.parent.mkdir(parents=True); payload = b"# Hz S RI R 50.0\n"
        path.write_bytes(payload); subprocess.run(["git", "-C", str(root), "add", "models/channel.s2p"], check=True); subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture"], check=True); subprocess.run(["git", "-C", str(root), "remote", "add", "origin", "https://github.com/z331225718/Py-bert-agent.git"], check=True)
        commit = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip(); tree = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD^{tree}"], check=True, capture_output=True, text=True).stdout.strip(); blob = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD:models/channel.s2p"], check=True, capture_output=True, text=True).stdout.strip()
        document["source"].update({"commit": commit, "tree": tree, "path": "models/channel.s2p", "git_blob": blob, "content_sha256": hashlib.sha256(payload).hexdigest()})
        return root

    def test_policy_and_git_object_validate_without_result(self) -> None:
        document = self.document(); root = self.source(document); report = verify_document(document, root)
        self.assertTrue(report["valid"], report["blockers"]); self.assertTrue(report["acceptance_ready"]); self.assertFalse(report["comparison_ready"])

    def test_hidden_transforms_tolerance_and_source_drift_fail_closed(self) -> None:
        document = self.document(); root = self.source(document); document["contract"]["window"] = "hann"; self.assertFalse(verify_document(document, root)["valid"])
        document = self.document(); root = self.source(document); document["acceptance"]["kernel_compare"]["relative_tolerance"] = 1.0e-3; self.assertFalse(verify_document(document, root)["valid"])
        document = self.document(); root = self.source(document); document["source"]["content_sha256"] = "0" * 64; self.assertFalse(verify_document(document, root)["valid"])


if __name__ == "__main__":
    unittest.main()
