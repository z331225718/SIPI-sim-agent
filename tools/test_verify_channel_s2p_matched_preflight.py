"""Focused tests for the observer-only matched S2P preflight."""

from __future__ import annotations

import copy
import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

from verify_channel_s2p_matched_preflight import _load, verify_document


class MatchedS2pPreflightTests(unittest.TestCase):
    def document(self) -> dict:
        return copy.deepcopy(_load(ROOT / "docs" / "baselines" / "channel-s2p-matched-observation.v1.yaml"))

    def source(self, document: dict) -> Path:
        root = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.email", "tests@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.name", "SIPI tests"], check=True)
        path = root / "models" / "channel.s2p"
        path.parent.mkdir(parents=True)
        rows = ["! project-authored structural test", "# Hz S RI R 50.0"]
        for index in range(201):
            frequency = index * 100_000_000
            rows.append(f"{frequency} 0 0 1 0 1 0 0 0")
        payload = ("\n".join(rows) + "\n").encode("utf-8")
        path.write_bytes(payload)
        subprocess.run(["git", "-C", str(root), "add", "models/channel.s2p"], check=True)
        subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture"], check=True)
        subprocess.run(["git", "-C", str(root), "remote", "add", "origin", "https://example.invalid/pybert.git"], check=True)
        commit = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
        tree = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD^{tree}"], check=True, capture_output=True, text=True).stdout.strip()
        blob = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD:models/channel.s2p"], check=True, capture_output=True, text=True).stdout.strip()
        document["source"].update({"canonical_origin": "https://example.invalid/pybert.git", "commit": commit, "tree": tree, "path": "models/channel.s2p", "git_blob": blob, "content_sha256": hashlib.sha256(payload).hexdigest()})
        return root

    def test_git_object_structure_is_verified_without_comparison_claim(self) -> None:
        document = self.document()
        root = self.source(document)
        report = verify_document(document, root)
        self.assertTrue(report["valid"], report["blockers"])
        self.assertEqual(report["structural_preflight"], "passed")
        self.assertFalse(report["comparison_ready"])
        self.assertEqual(report["numerical_acceptance_status"], "blocked_missing_stimulus_policy")

    def test_source_structure_and_legacy_evidence_drift_fail_closed(self) -> None:
        document = self.document()
        root = self.source(document)
        document["structural_expectation"]["reference_impedance_ohm"] = 75.0
        self.assertFalse(verify_document(document, root)["valid"])
        document = self.document()
        root = self.source(document)
        document["source"]["content_sha256"] = "0" * 64
        self.assertFalse(verify_document(document, root)["valid"])
        document = self.document()
        root = self.source(document)
        document["legacy_handoff_evidence"]["tool_git_blob"] = "0" * 40
        self.assertFalse(verify_document(document, root)["valid"])


if __name__ == "__main__":
    unittest.main()
