from __future__ import annotations

import copy
import unittest

from tools.verify_com_r480_route_preparation import validate


def documents() -> tuple[dict, dict]:
    boundary = {
        "schema": "sipi.com.r480-route-product-boundary.v2", "status": "preparation_only_not_distributed",
        "scope": {"command": "sipi com run", "argv_schema": "sipi.com.r480.argv.v1", "receipt_schema": "sipi.com.r480-cli-receipt.v1", "profile": "r4.80", "target": "x86_64-pc-windows-msvc", "whole_repository_release": False},
        "candidate": None, "distribution": {"public_route_enabled": False, "archive_created": False, "release": False},
        "execution_contract": {"required_arguments": ["--config", "--thru", "--output-dir"], "repeatable_arguments": ["--fext", "--next"], "optional_singleton_arguments": ["--calibration-noise"], "forbidden_arguments": ["--profile", "--reader", "--fix-id", "--override", "--overwrite", "--legacy-csv"], "forbidden_transports": ["stdin", "url", "inline_waveform", "network"], "output_policy": "new_directory_only_and_direct_port_custody_checked"},
        "required_candidate_receipts": [str(index) for index in range(9)],
        "excluded_from_archive": ["matlab_runtime", "agent_com_workbooks", "s_parameter_assets", "python_runtime", "agent_com_adapter"],
        "non_claims": ["no_distribution_admission", "no_release_admission", "no_full_matlab_warning_catalog_parity", "no_s_parameter_fit", "one_final_fd_to_td_impulse_only"],
    }
    contract = {
        "schema": "sipi.com.r480.argv.v1", "status": "preparation_only_no_dispatch", "route": ["com", "run"], "fixed_profile": "r4.80",
        "arguments": {"required_singleton": ["--config", "--thru", "--output-dir"], "optional_repeatable": ["--fext", "--next"], "optional_singleton": ["--calibration-noise"], "rejected": ["--profile", "--reader", "--fix-id", "--override", "--overwrite", "--legacy-csv"]},
        "limits": {"path_utf8_bytes": 4096, "fext_next_combined": 64},
        "path_policy": {"remote_urls_rejected": True, "output_must_be_new": True, "input_output_overlap_rejected_by_execution_boundary": True, "symlink_and_hardlink_custody_rejected_by_execution_boundary": True},
        "receipt": {"schema": "sipi.com.r480-cli-receipt.v1", "required_fields": ["schema", "status", "profile", "case_count", "warning_count", "config_sha256", "impulse_sha256", "artifacts"], "artifact_fields": ["name", "sha256", "byte_length"], "prohibited_fields": ["absolute_path", "raw_error_text", "direct_result_payload"]},
        "non_claims": ["not_an_enabled_cli_route", "not_a_distribution_or_release_record", "not_a_general_com_oracle"],
    }
    return boundary, contract


class RoutePreparationTests(unittest.TestCase):
    def test_valid_preparation_documents(self) -> None:
        validate(*documents())

    def test_enabling_route_is_rejected(self) -> None:
        boundary, contract = documents()
        boundary["distribution"]["public_route_enabled"] = True
        with self.assertRaisesRegex(ValueError, "distribution"):
            validate(boundary, contract)

    def test_candidate_binding_is_rejected_before_candidate_stage(self) -> None:
        boundary, contract = documents()
        boundary["candidate"] = {"commit": "a" * 40}
        with self.assertRaisesRegex(ValueError, "candidate"):
            validate(boundary, contract)

    def test_contract_surface_drift_is_rejected(self) -> None:
        boundary, contract = documents()
        contract = copy.deepcopy(contract)
        contract["arguments"]["rejected"].remove("--override")
        with self.assertRaisesRegex(ValueError, "contract arguments"):
            validate(boundary, contract)

    def test_untyped_receipt_is_rejected(self) -> None:
        boundary, contract = documents()
        contract = copy.deepcopy(contract)
        contract["receipt"]["prohibited_fields"].append("anything")
        with self.assertRaisesRegex(ValueError, "contract receipt"):
            validate(boundary, contract)


if __name__ == "__main__":
    unittest.main()
