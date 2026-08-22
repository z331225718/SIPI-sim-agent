from __future__ import annotations

import copy
import json
import subprocess
import sys
import tomllib
import unittest

from tools import verify_upstream_cli_integration as gate


class UpstreamCliIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.evidence = gate._load()

    def test_current_evidence_is_valid(self) -> None:
        result = gate.validate(self.evidence)
        self.assertTrue(result["valid"])
        self.assertEqual(result["routes"], 15)

    def test_command_line_output_is_json(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-B", str(gate.__file__)],
            cwd=gate.ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(json.loads(completed.stdout)["valid"])

    def test_route_cannot_claim_product_capability(self) -> None:
        mutated = copy.deepcopy(self.evidence)
        mutated["scope"]["product_capability"] = "accepted"
        with self.assertRaisesRegex(gate.IntegrationError, "scope_claim_invalid"):
            gate.validate(mutated)

    def test_missing_route_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.evidence)
        mutated["routes"].pop()
        with self.assertRaisesRegex(gate.IntegrationError, "route_count_invalid"):
            gate.validate(mutated)

    def test_new_semantics_are_rejected(self) -> None:
        mutated = copy.deepcopy(self.evidence)
        mutated["feature_freeze"]["numerical_semantics_added"] = True
        with self.assertRaisesRegex(gate.IntegrationError, "numerical_semantics_added"):
            gate.validate(mutated)

    def test_audit_hash_drift_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.evidence)
        mutated["audit"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(gate.IntegrationError, "audit_hash_drift"):
            gate.validate(mutated)

    def test_audit_path_drift_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.evidence)
        mutated["audit"]["path"] = "docs/baselines/audits/other.md"
        with self.assertRaisesRegex(gate.IntegrationError, "audit_path_invalid"):
            gate.validate(mutated)

    def test_source_hash_drift_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.evidence)
        mutated["source_files"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(gate.IntegrationError, "source_hash_drift"):
            gate.validate(mutated)

    def test_source_path_drift_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.evidence)
        mutated["source_files"][0]["path"] = "crates/sipi-cli/src/other.rs"
        with self.assertRaisesRegex(gate.IntegrationError, "source_file_path_invalid"):
            gate.validate(mutated)

    def test_command_id_drift_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.evidence)
        mutated["routes"][0]["command_id"] = "upstream.agent-spice.run-rfm"
        with self.assertRaisesRegex(gate.IntegrationError, "command_id_drift"):
            gate.validate(mutated)

    def test_route_drift_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.evidence)
        mutated["routes"][0]["route"] = ["upstream", "agent-spice", "run-rfm"]
        with self.assertRaisesRegex(gate.IntegrationError, "route_drift"):
            gate.validate(mutated)

    def cargo_manifest(self):
        return tomllib.loads(gate.CLI_CARGO.read_text(encoding="utf-8"))

    def test_test_support_feature_must_remain_empty(self) -> None:
        cargo = self.cargo_manifest()
        cargo["features"]["test-support"] = ["sipi-pybert-adapter/test-support"]
        with self.assertRaisesRegex(gate.IntegrationError, "test_support_feature_not_empty"):
            gate._verify_test_fixture_isolation(cargo)

    def test_fake_bin_requires_exact_test_support_feature(self) -> None:
        cargo = self.cargo_manifest()
        fake = next(item for item in cargo["bin"] if item["name"] == "sipi-upstream-fake")
        fake["required-features"] = []
        with self.assertRaisesRegex(gate.IntegrationError, "fixture_bin_feature_isolation_invalid"):
            gate._verify_test_fixture_isolation(cargo)

    def test_upstream_integration_test_requires_exact_test_support_feature(self) -> None:
        cargo = self.cargo_manifest()
        test = next(item for item in cargo["test"] if item["name"] == "upstream_migration")
        test["required-features"] = ["test-support", "extra"]
        with self.assertRaisesRegex(gate.IntegrationError, "fixture_test_feature_isolation_invalid"):
            gate._verify_test_fixture_isolation(cargo)

    def test_com_mismatch_must_remain_a_typed_result(self) -> None:
        module = gate.CLI_MODULE.read_text(encoding="utf-8").replace(
            '"matched": result.report.matched',
            '"matched": true',
        )
        tests = gate.CLI_TEST.read_text(encoding="utf-8")
        with self.assertRaisesRegex(gate.IntegrationError, "com_typed_mismatch_semantics_missing"):
            gate._verify_com_compare_semantics(module, tests)

    def test_com_protocol_and_other_exits_must_remain_transport_failures(self) -> None:
        module = gate.CLI_MODULE.read_text(encoding="utf-8")
        tests = gate.CLI_TEST.read_text(encoding="utf-8").replace(
            '("exit4", "external_adapter_nonzero_exit")',
            '("exit4", "typed_result")',
        )
        with self.assertRaisesRegex(gate.IntegrationError, "com_typed_mismatch_test_missing"):
            gate._verify_com_compare_semantics(module, tests)


if __name__ == "__main__":
    unittest.main()
