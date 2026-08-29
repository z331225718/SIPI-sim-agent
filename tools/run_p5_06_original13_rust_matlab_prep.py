"""Prepare the pinned original-13 Rust-vs-MATLAB acceptance corpus.

This tool does not execute either implementation and cannot create acceptance.
It inventories immutable Git objects and emits only repository-relative identities.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path
from typing import Any

UPSTREAM_COMMIT = "5272ffe74702cd585054d975559b06f8afae7b6e"
UPSTREAM_TREE = "7094ab6e84989b218730c52432c70da10261f8ea"
HISTORICAL_IMPLEMENTATION = "3257c2be2d575da870ab603fb5c44ed547fec314"
BENCHMARK_PATH = "benchmarks/original-13/benchmark.json"
BENCHMARK_SHA256 = "2dcf8e68feedcf979ba780a10cfbc454926c6c6dfefe673f7c37847761933d8f"
ROLES = ("THRU", "FEXT", "NEXT")
METRICS = ("COM_dB", "CTLE_DC_gain_dB", "ERL", "FOM", "ICN_mV", "IL_dB_channel_only_at_Fnq", "Peak_ISI_XTK_and_Noise_interference_at_BER_mV", "VEC_dB", "VEO_mV", "fitted_IL_dB_at_Fnq", "g_DC_HP", "itick")
ABS_TOLERANCE = 1e-9
MATLAB_REPEAT_ABS_TOLERANCE = 1e-12
STATUS = "pending_fresh_rust_vs_matlab_original_config_matrix"
HEX64 = re.compile(r"^[0-9a-f]{64}$")

class PrepError(RuntimeError): pass

def git(repo: Path, *args: str, cap: int = 64 * 1024 * 1024) -> bytes:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, timeout=30, check=False)
    if result.returncode or len(result.stdout) > cap or len(result.stderr) > 1024 * 1024: raise PrepError("bounded Git custody failed")
    return result.stdout

def blob(repo: Path, path: str) -> bytes:
    if path.startswith(("/", "\\")) or "\\" in path or ".." in path.split("/"): raise PrepError("unsafe asset path")
    return git(repo, "show", f"{UPSTREAM_COMMIT}:{path}")

def sha(data: bytes) -> str: return hashlib.sha256(data).hexdigest()

def scalar_equal(left: Any, right: Any, nan_allowed: bool = False) -> bool:
    if type(left) not in (int, float) or type(right) not in (int, float) or isinstance(left, bool) or isinstance(right, bool): return False
    left = float(left); right = float(right)
    if math.isnan(left) or math.isnan(right): return nan_allowed and math.isnan(left) and math.isnan(right)
    if math.isinf(left) or math.isinf(right): return math.isinf(left) and math.isinf(right) and (left > 0) == (right > 0)
    return abs(left - right) <= ABS_TOLERANCE

def array_contract(left: dict, right: dict, tolerance: float | None) -> str:
    keys = {"shape", "dtype", "order", "axis", "values"}
    if set(left) != keys or set(right) != keys: raise PrepError("array schema drift")
    if any(left[key] != right[key] for key in ("shape", "dtype", "order", "axis")): raise PrepError("array axis/shape/dtype/order drift")
    if tolerance is None: return "diagnostic_unset_tolerance"
    if type(tolerance) is not float or not math.isfinite(tolerance) or tolerance < 0: raise PrepError("array tolerance drift")
    if len(left["values"]) != len(right["values"]): raise PrepError("array element count drift")
    return "passed" if all(scalar_equal(a, b) if tolerance == ABS_TOLERANCE else abs(float(a)-float(b)) <= tolerance for a, b in zip(left["values"], right["values"])) else "failed"

def inspect(repo: Path) -> dict:
    if git(repo, "show", "-s", "--format=%T", UPSTREAM_COMMIT).decode().strip() != UPSTREAM_TREE: raise PrepError("upstream tree drift")
    raw = blob(repo, BENCHMARK_PATH)
    if sha(raw) != BENCHMARK_SHA256: raise PrepError("benchmark blob drift")
    benchmark = json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(PrepError("non-finite JSON")))
    if benchmark.get("implementation_commit") != HISTORICAL_IMPLEMENTATION or len(benchmark.get("matrix_cases", [])) != 13: raise PrepError("historical corpus drift")
    assets: dict[tuple[str, str], dict] = {}
    slots = 0; case_count = 0
    for case in benchmark["matrix_cases"]:
        config = case["config"]; config_raw = blob(repo, config)
        assets[("workbook", config)] = {"kind": "workbook", "path": config, "bytes": len(config_raw), "sha256": sha(config_raw), "historical_declared_sha256": case["config_sha256"], "historical_identity_matches_current": sha(config_raw) == case["config_sha256"]}
        if tuple(item["role"] for item in case["channels"]) != ROLES: raise PrepError("channel role/order drift")
        for item in case["channels"]:
            path = "fixtures/synthetic/" + item["name"]; raw_asset = blob(repo, path)
            assets[(item["role"], path)] = {"kind": "channel", "role": item["role"], "path": path, "bytes": len(raw_asset), "sha256": sha(raw_asset), "historical_declared_sha256": item["sha256"], "historical_identity_matches_current": sha(raw_asset) == item["sha256"]}
        comparisons = case["comparisons"]; slots += len(comparisons)
        indices = {item["case_index"] for item in comparisons}; case_count += max(indices) + 1 if indices else 0
        if any(item["metric"] not in METRICS for item in comparisons): raise PrepError("metric surface drift")
    if (case_count, slots) != (28, 303): raise PrepError("case/slot count drift")
    return {"schema": "sipi.p5-06.original13-prep-inventory.v1", "status": STATUS, "upstream": {"commit": UPSTREAM_COMMIT, "tree": UPSTREAM_TREE}, "historical_benchmark": {"path": BENCHMARK_PATH, "bytes": len(raw), "sha256": sha(raw), "implementation_commit": HISTORICAL_IMPLEMENTATION, "authority": "corpus_schema_precedent_only", "historical_python_pass_is_not_rust_acceptance": True}, "matrix": {"workbook_count": 13, "channel_roles": list(ROLES), "case_count": 28, "scalar_slot_count": 303, "metric_order": list(METRICS), "assets": sorted(assets.values(), key=lambda item: (item["kind"], item.get("role", ""), item["path"]))}, "acceptance": {"stage1": "fresh_matlab_twice_and_rust_twice_final_public_surface", "finite_absolute_tolerance": ABS_TOLERANCE, "matlab_repeat_absolute_tolerance": MATLAB_REPEAT_ABS_TOLERANCE, "infinity": "same_sign_same_position_only", "nan": "fail_unless_case_field_allowlisted_after_two_fresh_matlab_replays", "array_alignment": "forbidden", "stage2": "diagnostic_unset_array_tolerances", "instrumented_uninstrumented_final_surface_equivalence_required": True, "s_parameter_fit": "forbidden", "channel_policy": "one_final_fd_to_td_impulse"}, "custody": {"independent_matlab_runs": 2, "independent_rust_runs": 2, "fresh_nonce_and_run_id": True, "distinct_roots": True, "repo_relative_assets_only": True}, "claims": {"fresh_replay_executed": False, "rust_matlab_parity": False, "acceptance": False, "release": False}}

def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--upstream-repo", type=Path, required=True); parser.add_argument("--output", type=Path, required=True); args = parser.parse_args()
    payload = inspect(args.upstream_repo)
    with args.output.open("x", encoding="utf-8", newline="\n") as handle: json.dump(payload, handle, indent=2, sort_keys=True); handle.write("\n")
    return 0
if __name__ == "__main__": raise SystemExit(main())
