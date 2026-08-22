from __future__ import annotations

import copy
import os
import sys
import tomllib
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCE_VALUE = os.environ.get("SIPI_AGENT_SPICE_SOURCE")
SOURCE = None if SOURCE_VALUE is None else Path(SOURCE_VALUE)
sys.path.insert(0, str(ROOT / "tools"))
import verify_as_upstream_adapters as gate  # noqa: E402


class AsUpstreamAdapterEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = yaml.safe_load(gate.CONTRACT_PATH.read_text(encoding="utf-8"))

    def test_current_contract_is_ready(self) -> None:
        report = gate.verify(copy.deepcopy(self.document))
        self.assertTrue(report["ready"], report["blockers"])
        self.assertEqual(report["command_count"], 6)
        self.assertEqual(report["source_commit"], gate.EXPECTED_COMMIT)
        self.assertFalse(report["source_git_objects_checked"])

    @unittest.skipUnless(
        SOURCE is not None and SOURCE.is_dir(),
        "set SIPI_AGENT_SPICE_SOURCE to check pinned external Git objects",
    )
    def test_explicit_source_checks_exact_git_objects(self) -> None:
        assert SOURCE is not None
        report = gate.verify(copy.deepcopy(self.document), SOURCE)
        self.assertTrue(report["ready"], report["blockers"])
        self.assertTrue(report["source_git_objects_checked"])

    def test_source_commit_drift_is_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        document["source"]["commit"] = "0" * 40
        report = gate.verify(document)
        self.assertFalse(report["ready"])
        self.assertIn("source commit is not the pinned Agent-Spice object", report["blockers"])

    def test_source_tree_drift_is_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        document["source"]["tree"] = "0" * 40
        report = gate.verify(document)
        self.assertFalse(report["ready"])
        self.assertIn("source tree is not the pinned Agent-Spice tree", report["blockers"])

    def test_source_blob_drift_is_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        document["source_file_index"]["cli"]["sha256"] = "0" * 64
        report = gate.verify(document)
        self.assertFalse(report["ready"])
        self.assertIn("source file index identity drift", report["blockers"])

    def test_missing_command_row_is_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        document["commands"] = document["commands"][:-1]
        report = gate.verify(document)
        self.assertFalse(report["ready"])
        self.assertIn("six AS command rows are not an exact set", report["blockers"])

    def test_safety_policy_drift_is_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        document["adapter"]["fallback_policy"] = "silent"
        report = gate.verify(document)
        self.assertFalse(report["ready"])
        self.assertIn("fallback policy drift", report["blockers"])

    def test_output_admission_drift_is_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        document["adapter"]["output_admission"]["required_explicit_outputs"]["AS-01"] = []
        report = gate.verify(document)
        self.assertFalse(report["ready"])
        self.assertIn("output admission required paths drift", report["blockers"])

    def test_dangling_symlink_policy_drift_is_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        document["adapter"]["output_admission"]["output_symlink_target"] = "accepted"
        report = gate.verify(document)
        self.assertFalse(report["ready"])
        self.assertIn("dangling output symlink policy drift", report["blockers"])

    def test_required_artifact_mapping_drift_is_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        document["adapter"]["post_success_required_artifacts"]["AS-01"]["--output"] = (
            "directory"
        )
        report = gate.verify(document)
        self.assertFalse(report["ready"])
        self.assertIn("post-success required artifact mapping drift", report["blockers"])

    def test_process_tree_policy_drift_is_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        document["adapter"]["process_tree_termination"]["windows"] = "direct_child_only"
        report = gate.verify(document)
        self.assertFalse(report["ready"])
        self.assertIn("windows process-tree termination policy drift", report["blockers"])

    def test_missing_audit_identity_is_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        del document["audit"]
        report = gate.verify(document)
        self.assertFalse(report["ready"])
        self.assertIn("audit identity missing", report["blockers"])

    def test_test_support_targets_cannot_escape_feature_gate(self) -> None:
        cargo = tomllib.loads(
            (ROOT / "crates" / "sipi-agent-spice-adapter" / "Cargo.toml").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(gate._test_support_manifest_blockers(cargo), [])

        mutations = []
        missing_feature = copy.deepcopy(cargo)
        del missing_feature["features"]["test-support"]
        mutations.append(missing_feature)
        default_feature = copy.deepcopy(cargo)
        default_feature["features"]["default"] = ["test-support"]
        mutations.append(default_feature)
        ungated_bin = copy.deepcopy(cargo)
        del ungated_bin["bin"][0]["required-features"]
        mutations.append(ungated_bin)
        ungated_test = copy.deepcopy(cargo)
        ungated_test["test"][0]["required-features"] = []
        mutations.append(ungated_test)
        duplicate_fake_path = copy.deepcopy(cargo)
        duplicate_fake_path["bin"].append(
            {
                "name": "ungated-fake-alias",
                "path": "tests/fake_interpreter.rs",
            }
        )
        mutations.append(duplicate_fake_path)

        for mutated in mutations:
            with self.subTest(mutated=mutated):
                self.assertTrue(gate._test_support_manifest_blockers(mutated))


if __name__ == "__main__":
    unittest.main()
