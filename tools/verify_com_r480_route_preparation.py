"""Fail closed on the pre-distribution R4.80 argv and boundary contracts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BOUNDARY = "docs/baselines/com-r480-route-product-boundary.v2.yaml"
CONTRACT = "docs/baselines/com-r480-argv-contract.v1.yaml"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load(root: Path, relative: str) -> dict[str, Any]:
    value = json.loads((root / relative).read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{relative}: object")
    return value


def validate(boundary: dict[str, Any], contract: dict[str, Any]) -> None:
    require(
        set(boundary)
        == {
            "schema", "status", "scope", "candidate", "distribution", "execution_contract",
            "required_candidate_receipts", "excluded_from_archive", "non_claims",
        },
        "boundary keys",
    )
    require(boundary["schema"] == "sipi.com.r480-route-product-boundary.v2", "boundary schema")
    require(boundary["status"] == "preparation_only_not_distributed", "boundary status")
    require(boundary["candidate"] is None, "boundary candidate must remain absent")
    require(
        boundary["scope"]
        == {
            "command": "sipi com run", "argv_schema": "sipi.com.r480.argv.v1",
            "receipt_schema": "sipi.com.r480-cli-receipt.v1", "profile": "r4.80",
            "target": "x86_64-pc-windows-msvc", "whole_repository_release": False,
        },
        "boundary scope",
    )
    require(
        boundary["distribution"] == {"public_route_enabled": False, "archive_created": False, "release": False},
        "boundary distribution",
    )
    execution = boundary["execution_contract"]
    require(isinstance(execution, dict) and set(execution) == {"required_arguments", "repeatable_arguments", "optional_singleton_arguments", "forbidden_arguments", "forbidden_transports", "output_policy"}, "boundary execution keys")
    require(execution["required_arguments"] == ["--config", "--thru", "--output-dir"], "boundary required args")
    require(execution["repeatable_arguments"] == ["--fext", "--next"], "boundary repeatable args")
    require(execution["optional_singleton_arguments"] == ["--calibration-noise"], "boundary optional args")
    require(execution["forbidden_arguments"] == ["--profile", "--reader", "--fix-id", "--override", "--overwrite", "--legacy-csv"], "boundary forbidden args")
    require(execution["forbidden_transports"] == ["stdin", "url", "inline_waveform", "network"], "boundary transports")
    require(execution["output_policy"] == "new_directory_only_and_direct_port_custody_checked", "boundary output")
    require(len(boundary["required_candidate_receipts"]) == 9 and all(isinstance(item, str) and item for item in boundary["required_candidate_receipts"]), "candidate receipts")
    require(boundary["excluded_from_archive"] == ["matlab_runtime", "agent_com_workbooks", "s_parameter_assets", "python_runtime", "agent_com_adapter"], "archive exclusions")
    require(boundary["non_claims"] == ["no_distribution_admission", "no_release_admission", "no_full_matlab_warning_catalog_parity", "no_s_parameter_fit", "one_final_fd_to_td_impulse_only"], "boundary nonclaims")

    require(
        set(contract) == {"schema", "status", "route", "fixed_profile", "arguments", "limits", "path_policy", "receipt", "non_claims"},
        "contract keys",
    )
    require(contract["schema"] == "sipi.com.r480.argv.v1", "contract schema")
    require(contract["status"] == "preparation_only_no_dispatch", "contract status")
    require(contract["route"] == ["com", "run"] and contract["fixed_profile"] == "r4.80", "contract route")
    require(contract["arguments"] == {"required_singleton": ["--config", "--thru", "--output-dir"], "optional_repeatable": ["--fext", "--next"], "optional_singleton": ["--calibration-noise"], "rejected": ["--profile", "--reader", "--fix-id", "--override", "--overwrite", "--legacy-csv"]}, "contract arguments")
    require(contract["limits"] == {"path_utf8_bytes": 4096, "fext_next_combined": 64}, "contract limits")
    require(contract["path_policy"] == {"remote_urls_rejected": True, "output_must_be_new": True, "input_output_overlap_rejected_by_execution_boundary": True, "symlink_and_hardlink_custody_rejected_by_execution_boundary": True}, "contract path policy")
    require(contract["receipt"] == {"schema": "sipi.com.r480-cli-receipt.v1", "required_fields": ["schema", "status", "profile", "case_count", "warning_count", "config_sha256", "impulse_sha256", "artifacts"], "artifact_fields": ["name", "sha256", "byte_length"], "prohibited_fields": ["absolute_path", "raw_error_text", "direct_result_payload"]}, "contract receipt")
    require(contract["non_claims"] == ["not_an_enabled_cli_route", "not_a_distribution_or_release_record", "not_a_general_com_oracle"], "contract nonclaims")


def verify(root: Path) -> dict[str, str]:
    boundary = load(root, BOUNDARY)
    contract = load(root, CONTRACT)
    validate(boundary, contract)
    return {"valid": "true", "status": boundary["status"], "route": "com.run"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.root.resolve()), sort_keys=True))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"valid": "false", "error": str(error)}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
