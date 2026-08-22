from __future__ import annotations

import copy
import tomllib
import unittest

from tools import verify_pb_upstream_workflows as gate


class PyBertUpstreamWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.inventory = gate._load(gate.INVENTORY)
        self.contract = gate._load(gate.CONTRACT)

    def validate(self, inventory=None, contract=None):
        return gate.validate_documents(
            inventory=self.inventory if inventory is None else inventory,
            contract=self.contract if contract is None else contract,
        )

    def test_current_slice_is_valid_and_unpromoted(self) -> None:
        result = self.validate()
        self.assertTrue(result["valid"])
        self.assertEqual(result["workflows"], 5)
        self.assertEqual(result["parity"], "not_evaluated")

    def test_missing_workflow_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.inventory)
        mutated["workflows"].pop()
        with self.assertRaisesRegex(gate.WorkflowVerificationError, "workflow_id_set_invalid"):
            self.validate(inventory=mutated)

    def test_reachable_branch_must_include_result(self) -> None:
        mutated = copy.deepcopy(self.inventory)
        mutated["workflows"][0]["reachable_numeric_surface"].pop("result")
        with self.assertRaisesRegex(gate.WorkflowVerificationError, "reachable_branch_missing:PB-01:result"):
            self.validate(inventory=mutated)

    def test_source_binding_cannot_drift(self) -> None:
        mutated = copy.deepcopy(self.inventory)
        mutated["source"]["commit"] = "0" * 40
        with self.assertRaisesRegex(gate.WorkflowVerificationError, "source_binding_invalid"):
            self.validate(inventory=mutated)

    def test_silent_fallback_cannot_be_allowed(self) -> None:
        mutated = copy.deepcopy(self.inventory)
        mutated["adapter"]["fallback_policy"] = "silent"
        with self.assertRaisesRegex(gate.WorkflowVerificationError, "adapter_boundary_invalid"):
            self.validate(inventory=mutated)

    def test_bounds_cannot_be_relaxed(self) -> None:
        mutated = copy.deepcopy(self.contract)
        mutated["request_bounds"]["max_stdout_bytes"] = 0
        with self.assertRaisesRegex(gate.WorkflowVerificationError, "contract_bounds_invalid"):
            self.validate(contract=mutated)

    def test_auto_selection_requirement_cannot_disappear(self) -> None:
        mutated = copy.deepcopy(self.contract)
        mutated["backend_rules"]["sim_auto_requires_diagnostics_engine_selection_on_success"] = False
        with self.assertRaisesRegex(gate.WorkflowVerificationError, "contract_backend_rules_invalid"):
            self.validate(contract=mutated)

    def test_working_directory_contract_cannot_be_relaxed(self) -> None:
        mutated = copy.deepcopy(self.contract)
        mutated["working_directory"]["symlink_or_junction_rejected"] = False
        with self.assertRaisesRegex(
            gate.WorkflowVerificationError, "contract_working_directory_invalid"
        ):
            self.validate(contract=mutated)

    def test_required_output_and_job_object_contract_cannot_disappear(self) -> None:
        mutated = copy.deepcopy(self.contract)
        mutated["artifact_rules"]["output_target_must_exist_after_success"] = False
        with self.assertRaisesRegex(
            gate.WorkflowVerificationError, "contract_artifact_rules_invalid"
        ):
            self.validate(contract=mutated)

        mutated = copy.deepcopy(self.contract)
        mutated["artifact_rules"]["output_target_must_be_absent_before_spawn"] = False
        with self.assertRaisesRegex(
            gate.WorkflowVerificationError, "contract_artifact_rules_invalid"
        ):
            self.validate(contract=mutated)

        mutated = copy.deepcopy(self.contract)
        mutated["process_termination"]["windows_job_setup_failure"] = "fallback"
        with self.assertRaisesRegex(
            gate.WorkflowVerificationError, "contract_process_termination_invalid"
        ):
            self.validate(contract=mutated)

    def test_minimum_regular_artifacts_cannot_be_relaxed(self) -> None:
        mutated = copy.deepcopy(self.contract)
        mutated["artifact_rules"]["minimum_regular_artifacts"]["PB-05"] = [
            "meta.json"
        ]
        with self.assertRaisesRegex(
            gate.WorkflowVerificationError, "contract_artifact_rules_invalid"
        ):
            self.validate(contract=mutated)

    def test_process_wrap_license_and_target_boundary_are_bound(self) -> None:
        mutated = copy.deepcopy(self.contract)
        mutated["windows_dependencies"]["process_wrap"]["license"] = "unknown"
        with self.assertRaisesRegex(
            gate.WorkflowVerificationError, "contract_windows_dependency_invalid"
        ):
            self.validate(contract=mutated)

    def test_license_boundary_cannot_claim_source_copy_or_runtime_ownership(self) -> None:
        mutated = copy.deepcopy(self.contract)
        mutated["license_boundary"]["source_copied_into_adapter"] = True
        with self.assertRaisesRegex(gate.WorkflowVerificationError, "license_boundary_invalid"):
            self.validate(contract=mutated)

    def test_caller_launcher_cannot_be_reported_as_attested_runtime(self) -> None:
        mutated = copy.deepcopy(self.contract)
        mutated["runtime_identity"]["runtime_source_authenticated"] = True
        with self.assertRaisesRegex(
            gate.WorkflowVerificationError, "runtime_identity_claim_invalid"
        ):
            self.validate(contract=mutated)

    def test_audit_hash_is_bound_to_contract(self) -> None:
        mutated = copy.deepcopy(self.contract)
        mutated["license_boundary"]["source_audit_sha256"] = "0" * 64
        with self.assertRaisesRegex(gate.WorkflowVerificationError, "license_boundary_invalid"):
            self.validate(contract=mutated)

    def test_windows_tree_termination_uses_fail_closed_job_object(self) -> None:
        adapter_text = gate.ADAPTER.read_text(encoding="utf-8")
        self.assertIn("CommandWrap", adapter_text)
        self.assertIn("JobObject", adapter_text)
        self.assertIn("FailClosedJobSetup", adapter_text)
        self.assertIn("KillSuspendedOnDrop", adapter_text)
        self.assertIn("KillJobOnDrop", adapter_text)
        self.assertIn("PreserveParentCompletionPoll", adapter_text)
        self.assertIn(".start_kill()", adapter_text)
        self.assertNotIn("taskkill.exe", adapter_text)

    def test_windows_job_wrapper_order_cannot_drift(self) -> None:
        adapter_text = gate.ADAPTER.read_text(encoding="utf-8")
        mutated = adapter_text.replace(
            ".wrap(JobObject)\n        .wrap(KillJobOnDropSetup)",
            ".wrap(KillJobOnDropSetup)\n        .wrap(JobObject)",
        )
        self.assertNotEqual(mutated, adapter_text)
        with self.assertRaisesRegex(
            gate.WorkflowVerificationError, "windows_job_wrapper_order_invalid"
        ):
            gate.validate_adapter_process_source(mutated)

    def test_test_support_targets_cannot_escape_feature_gate(self) -> None:
        cargo = tomllib.loads(gate.CARGO_MANIFEST.read_text(encoding="utf-8"))
        gate.validate_test_support_manifest(cargo)

        missing_feature = copy.deepcopy(cargo)
        del missing_feature["features"]["test-support"]
        with self.assertRaisesRegex(
            gate.WorkflowVerificationError, "test_support_feature_invalid"
        ):
            gate.validate_test_support_manifest(missing_feature)

        default_feature = copy.deepcopy(cargo)
        default_feature["features"]["default"] = ["test-support"]
        with self.assertRaisesRegex(
            gate.WorkflowVerificationError, "test_support_enabled_by_default"
        ):
            gate.validate_test_support_manifest(default_feature)

        ungated_bin = copy.deepcopy(cargo)
        del ungated_bin["bin"][0]["required-features"]
        with self.assertRaisesRegex(
            gate.WorkflowVerificationError, "test_support_target_gate_invalid:bin"
        ):
            gate.validate_test_support_manifest(ungated_bin)

        ungated_test = copy.deepcopy(cargo)
        ungated_test["test"][0]["required-features"] = []
        with self.assertRaisesRegex(
            gate.WorkflowVerificationError, "test_support_target_gate_invalid:test"
        ):
            gate.validate_test_support_manifest(ungated_test)

        duplicate_fake_path = copy.deepcopy(cargo)
        duplicate_fake_path["bin"].append(
            {
                "name": "ungated_fake_alias",
                "path": "src/bin/pb_fake_pybert.rs",
            }
        )
        with self.assertRaisesRegex(
            gate.WorkflowVerificationError, "test_support_target_identity_invalid:bin"
        ):
            gate.validate_test_support_manifest(duplicate_fake_path)

    def test_minimum_artifact_check_must_remain_on_inventory_return_path(self) -> None:
        adapter_text = gate.ADAPTER.read_text(encoding="utf-8")
        mutated = adapter_text.replace(
            "validate_required_regular_artifacts(&records, workflow)?;",
            "// validation removed",
        )
        self.assertNotEqual(mutated, adapter_text)
        with self.assertRaisesRegex(
            gate.WorkflowVerificationError,
            "minimum_artifact_validation_not_bound_to_inventory",
        ):
            gate.validate_adapter_process_source(mutated)


if __name__ == "__main__":
    unittest.main()
