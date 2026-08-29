"""Verify the additive original-13 Rust-vs-MATLAB acceptance preparation."""

from __future__ import annotations

import argparse
import math
import re
from pathlib import Path
from typing import Any

import yaml

try:
    from .run_p5_06_original13_rust_matlab_prep import ABS_TOLERANCE, MATLAB_REPEAT_ABS_TOLERANCE, METRICS, ROLES, STATUS, PrepError, array_contract, inspect, scalar_equal
except ImportError:
    from run_p5_06_original13_rust_matlab_prep import ABS_TOLERANCE, MATLAB_REPEAT_ABS_TOLERANCE, METRICS, ROLES, STATUS, PrepError, array_contract, inspect, scalar_equal

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs/baselines/p5-06-original13-rust-matlab-acceptance-prep.v1.yaml"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
CHECKPOINTS = ["normalized_workbook_case_package_port_order", "network_package", "final_impulse", "TXLE_CTLE_DFE_winner", "noise_checkpoints", "final_metrics"]

class VerificationError(RuntimeError): pass
class StrictLoader(yaml.SafeLoader): pass
def strict_mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result: raise VerificationError("duplicate key")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result
StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, strict_mapping)

def finite(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value): raise VerificationError("nonfinite contract")
    if isinstance(value, dict):
        for key, child in value.items():
            if type(key) is not str: raise VerificationError("non-string key")
            finite(child)
    elif isinstance(value, list):
        for child in value: finite(child)

def exact(actual: Any, expected: Any, label: str) -> None:
    if type(actual) is not type(expected): raise VerificationError(label + ":type")
    if isinstance(expected, dict):
        if set(actual) != set(expected): raise VerificationError(label + ":keys")
        for key in expected: exact(actual[key], expected[key], label + ":" + key)
    elif isinstance(expected, list):
        if len(actual) != len(expected): raise VerificationError(label + ":length")
        for index, item in enumerate(expected): exact(actual[index], item, label + f":{index}")
    elif actual != expected: raise VerificationError(label + ":value")

def no_absolute_paths(value: Any) -> None:
    if isinstance(value, str) and (value.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:[\\/]", value)): raise VerificationError("absolute path leak")
    if isinstance(value, dict):
        for child in value.values(): no_absolute_paths(child)
    elif isinstance(value, list):
        for child in value: no_absolute_paths(child)

def validate(document: dict, upstream_repo: Path) -> dict:
    finite(document); no_absolute_paths(document)
    expected_inventory = inspect(upstream_repo)
    if set(document) != {"schema", "status", "supersession", "corpus_inventory", "stage1_contract", "stage2_checkpoint_contract", "custody", "non_claims"}: raise VerificationError("top schema")
    if document["schema"] != "sipi.p5-06.original13-rust-matlab-acceptance-prep.v1" or document["status"] != STATUS: raise VerificationError("status")
    exact(document["corpus_inventory"], expected_inventory, "inventory")
    if document["supersession"] != {"kind": "additive_reclassification", "historical_items_immutable": ["P5-06k", "P5-06q", "P5-06r", "P3C-03", "P5-06 scoped result-surface"], "historical_td_iln_three_scalar_contract": "not_current_acceptance_authority", "does_not_close_p5_06": True}: raise VerificationError("supersession")
    stage1 = document["stage1_contract"]
    if stage1["metric_order"] != list(METRICS) or stage1["finite_absolute_tolerance"] != ABS_TOLERANCE or stage1["matlab_repeat_absolute_tolerance"] != MATLAB_REPEAT_ABS_TOLERANCE or stage1["acceptance_ready"] is not False or stage1["runs"] != {"matlab": 2, "rust": 2, "distinct_root_run_id_nonce_and_report_sha": True}: raise VerificationError("stage1")
    stage2 = document["stage2_checkpoint_contract"]
    if stage2["checkpoint_names"] != CHECKPOINTS or stage2["array_tolerances"] != "unset" or stage2["alignment_resample_crop"] != "forbidden" or stage2["status"] != "diagnostic_hash_bound_not_acceptance": raise VerificationError("stage2")
    if "no_td_iln_requirement" not in document["non_claims"] or "no_historical_python_pass_as_rust_acceptance" not in document["non_claims"]: raise VerificationError("nonclaims")
    return {"valid": True, "status": STATUS, "workbooks": 13, "cases": 28, "scalar_slots": 303}

def validate_future_diagnostic(bundle: dict) -> None:
    finite(bundle); no_absolute_paths(bundle)
    if set(bundle) != {"schema", "status", "runs", "assets", "case_order", "checkpoints", "instrumentation", "historical_python_pass_is_rust_acceptance", "acceptance"}: raise VerificationError("future schema")
    if bundle["schema"] != "sipi.p5-06.original13-future-diagnostic.v1" or bundle["status"] != STATUS or bundle["acceptance"] is not False or bundle["historical_python_pass_is_rust_acceptance"] is not False: raise VerificationError("future claims")
    if [item["implementation"] for item in bundle["runs"]] != ["matlab", "matlab", "rust", "rust"]: raise VerificationError("run role/order")
    for key in ("root_id", "run_id", "nonce", "report_sha256"):
        values = [item[key] for item in bundle["runs"]]
        if len(set(values)) != 4 or any(type(value) is not str or (key in ("nonce", "report_sha256") and not HEX64.fullmatch(value)) for value in values): raise VerificationError("fresh identity")
    if [item["role"] for item in bundle["assets"] if item["kind"] == "channel"] != list(ROLES): raise VerificationError("asset role/order")
    if bundle["case_order"] != list(range(28)): raise VerificationError("case order")
    if any(not HEX64.fullmatch(item["sha256"]) or type(item["bytes"]) is not int or item["bytes"] <= 0 for item in bundle["assets"]): raise VerificationError("asset identity")
    if [item["name"] for item in bundle["checkpoints"]] != CHECKPOINTS: raise VerificationError("checkpoint order")
    if bundle["instrumentation"] != {"instrumented_uninstrumented_final_surface_equivalent": False, "acceptance_blocked_until_equivalent": True}: raise VerificationError("instrumentation claim")

def load(path: Path = CONTRACT) -> dict:
    document = yaml.load(path.read_text(encoding="utf-8"), Loader=StrictLoader); finite(document); return document
def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--upstream-repo", type=Path, required=True); args = parser.parse_args(); print(validate(load(), args.upstream_repo)); return 0
if __name__ == "__main__": raise SystemExit(main())
