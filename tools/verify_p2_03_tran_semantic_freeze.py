"""Verify the P2-03 TRAN semantic freeze against the live product contracts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.p2-03.tran-semantic-freeze.v1"
FREEZE = ROOT / "docs" / "baselines" / "p2-03-tran-semantic-freeze.v1.yaml"
TRAN_LIB = ROOT / "crates" / "sipi-tran" / "src" / "lib.rs"
CONTRACTS = ROOT / "crates" / "sipi-contracts" / "src" / "lib.rs"
CLI_MAIN = ROOT / "crates" / "sipi-cli" / "src" / "main.rs"

EXPECTED_SCHEMAS = frozenset({
    "sipi.tran.one-node-rc-pulse-request.v1",
    "sipi.tran.one-node-rc-pwl-request.v1",
    "sipi.tran.rc-pulse-request.v1",
})

EXPECTED_ERROR_VARIANTS = frozenset({
    "Invariant", "Runtime", "InvalidOutputAxisStart", "NonIncreasingOutputAxis",
    "InvalidResistance", "InvalidCapacitance", "InvalidPulseDelay",
    "InvalidPulseDuration", "InvalidPulseWidth", "InvalidPulseCornerOrder",
    "PwlKnotValueCountMismatch", "PwlKnotAxisTooShort", "InvalidPwlKnotAxisStart",
    "NonIncreasingPwlKnotAxis", "PwlCoverageMismatch", "PwlOutsideCoverage",
    "OutputLimitExceeded", "BreakpointLimitExceeded", "BreakpointCountOverflow",
    "NonFiniteComputation",
})

EXPECTED_TOPOLOGIES = frozenset({
    "ideal_pulse_series_r_capacitor_to_explicit_ref",
    "piecewise_linear_voltage_source_series_r_capacitor_to_explicit_ref",
    "tran-rc-pulse-v1",
})


class FreezeError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    if yaml is not None:
        try:
            value = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, yaml.YAMLError) as error:
            raise FreezeError("invalid_freeze_document") from error
    else:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise FreezeError("invalid_freeze_document") from error
    if not isinstance(value, dict):
        raise FreezeError("invalid_freeze_document")
    return value


def git_tracked(relative: str) -> bool:
    completed = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "--error-unmatch", "--", relative],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=60,
    )
    return completed.returncode == 0


def read_text(relative: str) -> str:
    try:
        return (ROOT / relative).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise FreezeError("source_read_failed") from error


def extract_enum_variants(text: str, enum_name: str) -> set[str]:
    match = re.search(rf"pub enum {re.escape(enum_name)}\s*\{{(.*?)\n\}}", text, re.DOTALL)
    if match is None:
        raise FreezeError(f"enum_not_found:{enum_name}")
    body = match.group(1)
    variants: set[str] = set()
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        name = re.match(r"([A-Za-z_][A-Za-z0-9_]*)", stripped)
        if name is not None:
            variants.add(name.group(1))
    return variants


def validate(freeze: dict[str, Any], root: Path = ROOT) -> dict[str, Any]:
    required = {
        "schema", "status", "owner", "scope", "non_claims", "request_schemas",
        "topology", "device_support_matrix", "solver_policy", "error_taxonomy",
        "contract_refs",
    }
    if set(freeze) != required or freeze["schema"] != SCHEMA:
        raise FreezeError("freeze_schema_invalid")
    if freeze["status"] != "provisional":
        raise FreezeError("freeze_status_invalid")
    if freeze["owner"] != "project" or freeze["scope"] != "current_product_surface_only":
        raise FreezeError("freeze_scope_invalid")
    if not isinstance(freeze["non_claims"], list) or not freeze["non_claims"]:
        raise FreezeError("freeze_non_claims_invalid")

    schemas = freeze["request_schemas"]
    if (
        set(schemas) != {"one_node_rc_pulse", "one_node_rc_pwl", "fixed_profile"}
        or set(schemas.values()) != EXPECTED_SCHEMAS
    ):
        raise FreezeError("freeze_request_schemas_invalid")

    topologies = set(freeze["topology"].values())
    if topologies != EXPECTED_TOPOLOGIES:
        raise FreezeError("freeze_topology_invalid")

    matrix = freeze["device_support_matrix"]
    expected_matrix = {
        "ideal_voltage_source_pulse": "supported",
        "ideal_voltage_source_pwl": "supported",
        "resistor_series": "supported",
        "capacitor_to_explicit_reference": "supported",
        "inductor": "unsupported",
        "diode": "unsupported",
        "transistor": "unsupported",
        "transmission_line": "unsupported",
        "arbitrary_netlist": "rejected",
        "implicit_ground": "rejected",
        "model_selection": "rejected",
        "topology_description": "rejected",
    }
    if matrix != expected_matrix:
        raise FreezeError("freeze_device_matrix_invalid")

    policy = freeze["solver_policy"]
    expected_policy_keys = {
        "integrator", "stepping", "adaptive_stepping", "convergence_iteration",
        "output_sampling", "measurement_semantics", "tolerance_policy",
        "interpolation", "resampling", "initial_condition",
        "implicit_ic_calculation", "resource_limits",
    }
    if policy.get("measurement_semantics") != "not_implemented":
        raise FreezeError("freeze_measurement_policy_invalid")
    if policy.get("tolerance_policy") != "blocked_missing_tolerance_owner_decision":
        raise FreezeError("freeze_tolerance_policy_invalid")
    if set(policy) != expected_policy_keys:
        raise FreezeError("freeze_solver_policy_invalid")
    limits = policy["resource_limits"]
    if (
        limits.get("max_output_samples") != 4096
        or limits.get("max_integration_breakpoints") != 16384
        or limits.get("cooperative_checkpoints") is not True
    ):
        raise FreezeError("freeze_resource_limits_invalid")

    taxonomy = set(freeze["error_taxonomy"])
    if taxonomy != EXPECTED_ERROR_VARIANTS:
        raise FreezeError("freeze_error_taxonomy_invalid")

    for contract in freeze["contract_refs"]:
        if not git_tracked(contract) or not (root / contract).is_file():
            raise FreezeError(f"freeze_contract_missing:{contract}")

    # Live binding: error taxonomy must match the sipi-tran TranError enum.
    library_text = read_text("crates/sipi-tran/src/lib.rs")
    live_variants = extract_enum_variants(library_text, "TranError")
    if live_variants != EXPECTED_ERROR_VARIANTS:
        raise FreezeError("freeze_tran_error_drift")

    # Live binding: request schema constants in sipi-contracts.
    contracts_text = read_text("crates/sipi-contracts/src/lib.rs")
    for schema in EXPECTED_SCHEMAS:
        if schema not in contracts_text:
            raise FreezeError(f"freeze_contract_schema_missing:{schema}")

    # Live binding: topology strings in the CLI provenance emission.
    cli_text = read_text("crates/sipi-cli/src/main.rs")
    for topology in EXPECTED_TOPOLOGIES:
        if topology not in cli_text:
            raise FreezeError(f"freeze_topology_binding_missing:{topology}")

    return {"valid": True, "error_variants": len(EXPECTED_ERROR_VARIANTS)}


def main() -> int:
    parser = argparse.ArgumentParser()
    arguments = parser.parse_args()
    try:
        freeze = load_json(FREEZE)
        result = validate(freeze, ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except FreezeError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
