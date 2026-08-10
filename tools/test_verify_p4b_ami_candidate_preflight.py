"""Contract tests for the P4B AMI candidate quarantine preflight."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p4b_preflight", ROOT / "tools" / "verify_p4b_ami_candidate_preflight.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


class AmiCandidatePreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = GATE.materialize_manifest(ROOT)

    def test_current_git_objects_are_quarantine_only(self) -> None:
        report = GATE.verify_manifest(ROOT, self.manifest)
        self.assertEqual(report["status"], "quarantine_preflight_passed")
        self.assertFalse(report["promotion_eligible"])

    def test_missing_target_entry_is_rejected(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["entries"].pop()
        with self.assertRaises(GATE.PreflightError):
            GATE.verify_manifest(ROOT, manifest)

    def test_wrong_blob_and_fake_promotion_are_rejected(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["entries"][0]["target"]["git_blob"] = "0" * 40
        with self.assertRaises(GATE.PreflightError):
            GATE.verify_manifest(ROOT, manifest)
        manifest = copy.deepcopy(self.manifest)
        manifest["promotion_eligible"] = True
        with self.assertRaises(GATE.PreflightError):
            GATE.verify_manifest(ROOT, manifest)

    def test_vendor_path_and_unknown_dependency_are_rejected(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["entries"][0]["target"]["path"] = "native/vendor/example.dll"
        with self.assertRaises(GATE.PreflightError):
            GATE.verify_manifest(ROOT, manifest)
        manifest = copy.deepcopy(self.manifest)
        manifest["dependency_closures"][0]["locked_packages"].append({"name": "unknown", "version": "0", "source": None, "checksum": None})
        with self.assertRaises(GATE.PreflightError):
            GATE.verify_manifest(ROOT, manifest)

    def test_release_layout_style_source_map_promotion_is_rejected(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["entries"][0]["source_map"]["boundary_class"] = "product_candidate"
        with self.assertRaises(GATE.PreflightError):
            GATE.verify_manifest(ROOT, manifest)


if __name__ == "__main__":
    unittest.main()
