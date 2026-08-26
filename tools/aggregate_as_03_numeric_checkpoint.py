"""Aggregate two independent AS-03 physical checkpoint reports."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX16 = re.compile(r"^[0-9a-f]{16}$")
REPORT_KEYS = {"schema", "status", "parity_claim", "numeric_parity", "integrity_gate", "run_id", "fresh_run_nonce", "trust", "scope", "runner", "fixture", "candidate", "upstream", "toolchain", "execution", "checkpoint", "blockers", "non_claims", "custody"}
AGGREGATE_KEYS = {"schema", "status", "integrity_gate", "parity_claim", "numeric_parity", "report_runs", "reports", "trust", "fixture", "candidate", "upstream", "toolchain", "checkpoint", "blockers", "non_claims"}
STABLE_REPORT_KEYS = ("trust", "scope", "runner", "fixture", "candidate", "upstream", "toolchain", "checkpoint", "blockers", "non_claims", "custody")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def exact_equal(left: Any, right: Any) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return set(left) == set(right) and all(exact_equal(left[key], right[key]) for key in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(exact_equal(a, b) for a, b in zip(left, right, strict=True))
    return bool(left == right)


def _exact_dict(value: Any, keys: set[str]) -> bool:
    return type(value) is dict and set(value) == keys


def _hex(value: Any, pattern: re.Pattern[str]) -> bool:
    return type(value) is str and pattern.fullmatch(value) is not None


def _receipt(value: Any) -> bool:
    keys = {"fixture_sha256", "fixture_bytes", "frequency_points", "frequency_hz", "ports", "reference_impedance_bits", "sample_matrix"}
    if not _exact_dict(value, keys) or not _hex(value["fixture_sha256"], HEX64) or not _hex(value["reference_impedance_bits"], HEX16): return False
    if any(type(value[key]) is not int for key in ("fixture_bytes", "frequency_points", "frequency_hz", "ports")) or type(value["sample_matrix"]) is not list or len(value["sample_matrix"]) != value["ports"] ** 2: return False
    return all(_exact_dict(cell, {"re_bits", "im_bits"}) and _hex(cell["re_bits"], HEX16) and _hex(cell["im_bits"], HEX16) for cell in value["sample_matrix"])


def _checkpoint_side(value: Any) -> bool:
    keys = {"schema", "frequency_hz", "sample_index", "ports", "condition", "matrix", "parser_receipt", "physical_f64_le_sha256", "normalized_sha256", "parser_receipt_sha256"}
    if not _exact_dict(value, keys) or value["schema"] != "sipi.as-03-s-to-y-checkpoint.v1" or any(type(value[key]) is not int for key in ("frequency_hz", "sample_index", "ports")) or type(value["condition"]) is not str or not _receipt(value["parser_receipt"]): return False
    if not _hex(value["physical_f64_le_sha256"], HEX64) or not _hex(value["normalized_sha256"], HEX64) or not _hex(value["parser_receipt_sha256"], HEX64) or type(value["matrix"]) is not list or len(value["matrix"]) != value["ports"] ** 2: return False
    return all(_exact_dict(cell, {"re", "im", "re_bits", "im_bits"}) and all(type(cell[key]) is str for key in ("re", "im")) and _hex(cell["re_bits"], HEX16) and _hex(cell["im_bits"], HEX16) for cell in value["matrix"])


def _difference(value: Any) -> bool:
    keys = {"row", "column", "component", "candidate", "upstream", "delta", "delta_bits"}
    return _exact_dict(value, keys) and type(value["row"]) is int and type(value["column"]) is int and value["component"] in {"re", "im"} and all(type(value[key]) is str for key in ("candidate", "upstream", "delta")) and _hex(value["delta_bits"], HEX16)


def _source(value: Any) -> bool:
    if not _exact_dict(value, {"commit", "tree", "archive", "sources"}) or not _hex(value["commit"], HEX40) or not _hex(value["tree"], HEX40): return False
    if not _exact_dict(value["archive"], {"bytes", "sha256"}) or type(value["archive"]["bytes"]) is not int or not _hex(value["archive"]["sha256"], HEX64) or type(value["sources"]) is not list: return False
    return all(_exact_dict(item, {"path", "git_blob", "bytes", "sha256"}) and type(item["path"]) is str and _hex(item["git_blob"], HEX40) and type(item["bytes"]) is int and _hex(item["sha256"], HEX64) for item in value["sources"])


def _snapshot(value: Any, role: str) -> bool:
    keys = {"role", "executable", "path_redacted", "file_sha256", "version_sha256", "version_exit"}
    return _exact_dict(value, keys) and value["role"] == role and type(value["executable"]) is str and value["path_redacted"] is True and _hex(value["file_sha256"], HEX64) and _hex(value["version_sha256"], HEX64) and type(value["version_exit"]) is int and value["version_exit"] == 0


def _tool(value: Any, role: str) -> bool:
    return _exact_dict(value, {"role", "pre", "post", "pre_post_equal"}) and value["role"] == role and value["pre_post_equal"] is True and _snapshot(value["pre"], role) and _snapshot(value["post"], role) and exact_equal(value["pre"], value["post"])


def _module_fact(value: Any) -> bool:
    return _exact_dict(value, {"version", "basename", "sha256"}) and type(value["version"]) is str and type(value["basename"]) is str and _hex(value["sha256"], HEX64)


def _execution(value: Any) -> bool:
    keys = {"exit_code", "stdout_sha256", "stdout_bytes", "stdout_limit_bytes", "stdout_within_limit", "stderr_sha256", "stderr_bytes", "stderr_limit_bytes", "stderr_within_limit"}
    return _exact_dict(value, keys) and type(value["exit_code"]) is int and value["exit_code"] == 0 and all(type(value[key]) is int for key in ("stdout_bytes", "stdout_limit_bytes", "stderr_bytes", "stderr_limit_bytes")) and value["stdout_within_limit"] is True and value["stderr_within_limit"] is True and value["stdout_bytes"] <= value["stdout_limit_bytes"] and value["stderr_bytes"] <= value["stderr_limit_bytes"] and _hex(value["stdout_sha256"], HEX64) and _hex(value["stderr_sha256"], HEX64)


def validate_report(report: Any) -> list[str]:
    blockers: list[str] = []
    if not _exact_dict(report, REPORT_KEYS): return ["report exact top-level keys"]
    if report["schema"] != "sipi.as-03-numeric-physical-checkpoint.v1" or report["status"] != "blocked_numeric_semantics" or report["integrity_gate"] != "passed" or report["parity_claim"] is not False or report["numeric_parity"] is not False: blockers.append("report gate")
    if type(report["run_id"]) is not str or not _hex(report["fresh_run_nonce"], HEX64): blockers.append("report run identity")
    if not exact_equal(report["trust"], {"scope": "integrity_only", "external_trust_root": False, "reciprocal_execution_anchor": True}): blockers.append("report trust")
    if not exact_equal(report["scope"], {"workflow": "fit-yparam", "y_parameter_fit": True, "si_s_parameter_fit": False, "as05_xyce_xdm": False}): blockers.append("report scope")
    if not _exact_dict(report["runner"], {"path", "sha256"}) or type(report["runner"]["path"]) is not str or not _hex(report["runner"]["sha256"], HEX64): blockers.append("report runner")
    fixture = report["fixture"]
    if not _exact_dict(fixture, {"kind", "sha256", "bytes", "frequency_points", "parsed_receipt"}) or fixture["kind"] != "fixed_touchstone_line_s2p_v1" or not _hex(fixture["sha256"], HEX64) or type(fixture["bytes"]) is not int or type(fixture["frequency_points"]) is not int or not _receipt(fixture["parsed_receipt"]): blockers.append("report fixture")
    candidate = report["candidate"]
    candidate_core = {key: candidate.get(key) for key in ("commit", "tree", "archive", "sources")} if _exact_dict(candidate, {"commit", "tree", "archive", "sources", "instrumentation"}) else None
    if not _source(candidate_core) or not _exact_dict(candidate.get("instrumentation") if type(candidate) is dict else None, {"kind", "suffix_sha256", "instrumented_source_sha256", "production_source_unchanged"}) or candidate["instrumentation"]["production_source_unchanged"] is not True or candidate["instrumentation"]["kind"] != "append_private_module_test_only" or not _hex(candidate["instrumentation"]["suffix_sha256"], HEX64) or not _hex(candidate["instrumentation"]["instrumented_source_sha256"], HEX64): blockers.append("report candidate")
    if not _source(report["upstream"]): blockers.append("report upstream")
    toolchain = report["toolchain"]
    if not _exact_dict(toolchain, {"git", "cargo", "rustc", "python", "modules", "timeout_seconds", "stdout_limit_bytes", "stderr_limit_bytes"}) or any(not _tool(toolchain[role], role) for role in ("git", "cargo", "rustc", "python")) or any(type(toolchain[key]) is not int for key in ("timeout_seconds", "stdout_limit_bytes", "stderr_limit_bytes")): blockers.append("report toolchain")
    modules = toolchain.get("modules", {}) if type(toolchain) is dict else {}
    if not _exact_dict(modules, {"pre", "post", "pre_post_equal"}) or modules.get("pre_post_equal") is not True or not exact_equal(modules.get("pre"), modules.get("post")) or any(not _module_fact(modules.get("pre", {}).get(name)) for name in ("numpy", "skrf")): blockers.append("report modules")
    if not _exact_dict(report["execution"], {"candidate_probe", "upstream_probe"}) or any(not _execution(report["execution"].get(name)) for name in ("candidate_probe", "upstream_probe")): blockers.append("report execution")
    checkpoint = report["checkpoint"]
    if not _exact_dict(checkpoint, {"candidate", "upstream", "comparison", "reciprocal_anchor_sha256"}) or not _checkpoint_side(checkpoint.get("candidate")) or not _checkpoint_side(checkpoint.get("upstream")) or not _hex(checkpoint.get("reciprocal_anchor_sha256"), HEX64): blockers.append("report checkpoint")
    comparison = checkpoint.get("comparison", {}) if type(checkpoint) is dict else {}
    if not _exact_dict(comparison, {"first_lexicographic_difference", "max_abs_difference", "differing_components"}) or not _difference(comparison.get("first_lexicographic_difference")) or not _difference(comparison.get("max_abs_difference")) or type(comparison.get("differing_components")) is not int: blockers.append("report comparison")
    if type(report["blockers"]) is not list or type(report["non_claims"]) is not list or any(type(item) is not str for item in [*report["blockers"], *report["non_claims"]]): blockers.append("report claims lists")
    custody = report["custody"]
    if not _exact_dict(custody, {"git_object_sources", "immutable_archives", "archive_links_rejected", "single_link_files", "work_root_external", "paths_redacted"}) or any(custody[key] is not True for key in custody): blockers.append("report custody")
    return blockers


def build_aggregate(first: dict[str, Any], second: dict[str, Any], first_ref: dict[str, Any], second_ref: dict[str, Any]) -> dict[str, Any]:
    errors = [*validate_report(first), *validate_report(second)]
    if errors: raise RuntimeError("; ".join(errors))
    if first["run_id"] == second["run_id"] or first["fresh_run_nonce"] == second["fresh_run_nonce"] or first_ref["path"] == second_ref["path"] or first_ref["sha256"] == second_ref["sha256"]: raise RuntimeError("fresh replay identities must differ")
    for key in STABLE_REPORT_KEYS:
        if not exact_equal(first[key], second[key]): raise RuntimeError(f"fresh replay drift: {key}")
    reports = [
        {"path": first_ref["path"], "sha256": first_ref["sha256"], "run_id": first["run_id"], "fresh_run_nonce": first["fresh_run_nonce"]},
        {"path": second_ref["path"], "sha256": second_ref["sha256"], "run_id": second["run_id"], "fresh_run_nonce": second["fresh_run_nonce"]},
    ]
    return {"schema": "sipi.as-03-numeric-physical-checkpoint-aggregate.v1", "status": "blocked_numeric_semantics", "integrity_gate": "passed", "parity_claim": False, "numeric_parity": False, "report_runs": 2, "reports": reports, "trust": first["trust"], "fixture": first["fixture"], "candidate": {key: first["candidate"][key] for key in ("commit", "tree", "archive", "sources")}, "upstream": first["upstream"], "toolchain": first["toolchain"], "checkpoint": first["checkpoint"], "blockers": first["blockers"], "non_claims": first["non_claims"]}


def _has_reparse(path: Path) -> bool:
    current = path.absolute()
    while True:
        try: info = current.lstat()
        except FileNotFoundError: info = None
        if info is not None and (stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)): return True
        if current.parent == current: return False
        current = current.parent


def _safe_path(raw: str, *, must_exist: bool) -> Path:
    if not isinstance(raw, str) or not raw or "\0" in raw: raise RuntimeError("evidence path malformed")
    host, posix, windows = Path(raw), PurePosixPath(raw), PureWindowsPath(raw)
    parts = [part for part in re.split(r"[\\/]", raw) if part not in ("", ".")]
    if host.is_absolute() or host.anchor or posix.is_absolute() or posix.anchor or windows.is_absolute() or windows.anchor or windows.drive or ".." in parts or tuple(parts[:2]) != ("docs", "baselines"): raise RuntimeError("evidence path must be repository-relative under docs/baselines")
    path = ROOT / Path(*parts)
    if _has_reparse(path if must_exist else path.parent): raise RuntimeError("evidence path has reparse custody")
    if must_exist:
        resolved = path.resolve(strict=True); info = resolved.stat()
        if ROOT.resolve(strict=True) not in resolved.parents or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1: raise RuntimeError("evidence file custody failed")
    elif path.exists(): raise RuntimeError("aggregate output must be create-new")
    return path


def aggregate(first_raw: str, second_raw: str, output_raw: str) -> dict[str, Any]:
    first_path, second_path = _safe_path(first_raw, must_exist=True), _safe_path(second_raw, must_exist=True)
    first_ref, second_ref = {"path": Path(first_raw).as_posix(), "sha256": _sha(first_path)}, {"path": Path(second_raw).as_posix(), "sha256": _sha(second_path)}
    first, second = json.loads(first_path.read_text(encoding="utf-8")), json.loads(second_path.read_text(encoding="utf-8"))
    result = build_aggregate(first, second, first_ref, second_ref)
    if not _exact_dict(result, AGGREGATE_KEYS): raise RuntimeError("aggregate exact graph failed")
    output_path = _safe_path(output_raw, must_exist=False)
    with output_path.open("x", encoding="utf-8", newline="\n") as handle: handle.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    info = output_path.stat()
    if _has_reparse(output_path) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1: raise RuntimeError("aggregate output custody changed")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first", required=True); parser.add_argument("--second", required=True); parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try: result = aggregate(args.first, args.second, args.output)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"valid": False, "error": str(error)})); return 2
    print(json.dumps({"status": result["status"], "report_runs": result["report_runs"]}, sort_keys=True)); return 0


if __name__ == "__main__": raise SystemExit(main())
