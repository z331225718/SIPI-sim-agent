"""Fail-closed aggregate for two PB-01/PB-03 archive source replays."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

try:  # pragma: no cover
    from . import run_pb_01_03_source_corpus as runner
except ImportError:  # pragma: no cover
    import run_pb_01_03_source_corpus as runner


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load(path: Path) -> tuple[dict[str, Any], bytes]:
    data = path.read_bytes()
    value = json.loads(data.decode("utf-8"))
    if type(value) is not dict:
        raise ValueError("report root must be an object")
    return value, data


def validate(report: dict[str, Any]) -> None:
    if report.get("schema") != runner.SCHEMA or report.get("version") != 1 or report.get("status") != "passed":
        raise ValueError("report schema/status drift")
    if not isinstance(report.get("run_id"), str) or not isinstance(report.get("nonce"), str) or len(report["nonce"]) != 64:
        raise ValueError("run identity drift")
    cases = report.get("cases")
    if not isinstance(cases, list) or [item.get("id") for item in cases] != ["pb01_class_pickle", "pb03_baseline", "pb03_analytic_ctle", "pb03_gain_rejected"] or not all(item.get("passed") is True for item in cases):
        raise ValueError("case acceptance drift")
    pb01, baseline, ctle, rejected = cases
    if len(pb01.get("comparison", {}).get("rows", [])) != 23 or pb01["comparison"].get("passed") is not True:
        raise ValueError("PB-01 class evidence drift")
    for case in (baseline, ctle):
        comparison = case.get("comparison", {})
        if comparison.get("passed") is not True or len(comparison.get("arrays", {}).get("members", [])) != 150 or comparison.get("metadata", {}).get("excluded_paths") != list(runner.PB03_EXCLUSIONS):
            raise ValueError("PB-03 full payload evidence drift")
    if rejected.get("no_artifacts") != {"candidate": True, "oracle": True}:
        raise ValueError("PB-03 rejection artifact drift")


def oracle_runtime_identity(value: Any) -> dict[str, Any]:
    """Keep immutable package bytes and discard per-run inode/capture receipts."""
    if not isinstance(value, dict) or not isinstance(value.get("modules"), dict):
        raise ValueError("oracle runtime schema drift")
    modules = {}
    for name in ("numpy", "pybert", "scipy"):
        module = value["modules"].get(name)
        if not isinstance(module, dict) or not isinstance(module.get("file"), dict):
            raise ValueError("oracle module receipt drift")
        fact = module["file"]
        modules[name] = {"version": module.get("version"), "owner": module.get("owner"), "relative_path": module.get("relative_path"), "bytes": fact.get("bytes"), "sha256": fact.get("sha256")}
    return {key: value.get(key) for key in ("clean_archive_or_venv_only", "host_pythonpath_absent", "host_uv_flags_cleared", "host_virtual_env_absent", "uv_cache_explicit_lock_bound", "uv_link_mode_copy", "uv_offline_frozen_no_config")} | {"modules": modules}


def aggregate(first_path: Path, second_path: Path, output: Path) -> dict[str, Any]:
    first, first_bytes = load(first_path); second, second_bytes = load(second_path)
    validate(first); validate(second)
    for key in ("candidate", "upstream", "scope", "toolchain"):
        if first[key] != second[key]:
            raise ValueError(f"cross-run {key} drift")
    if oracle_runtime_identity(first["oracle_runtime"]) != oracle_runtime_identity(second["oracle_runtime"]):
        raise ValueError("cross-run oracle runtime identity drift")
    if first["run_id"] == second["run_id"] or first["nonce"] == second["nonce"] or sha256(first_bytes) == sha256(second_bytes):
        raise ValueError("runs are not independent")
    result = {
        "schema": "sipi.pb-01-03-source-corpus-aggregate.v1",
        "status": "passed",
        "candidate": first["candidate"], "upstream": first["upstream"], "scope": first["scope"], "oracle_runtime": oracle_runtime_identity(first["oracle_runtime"]),
        "reports": [
            {"path": first_path.name, "bytes": len(first_bytes), "sha256": sha256(first_bytes), "run_id": first["run_id"], "nonce": first["nonce"]},
            {"path": second_path.name, "bytes": len(second_bytes), "sha256": sha256(second_bytes), "run_id": second["run_id"], "nonce": second["nonce"]},
        ],
        "accepted": {"pb01_class_pickle": True, "pb03_baseline": True, "pb03_analytic_ctle": True, "pb03_gain_rejected": True},
        "non_claims": ["not whole-PyBERT parity", "not root sipi integration", "not license or release approval"],
    }
    if output.exists() or output.is_symlink():
        raise ValueError("aggregate output already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(json.dumps(result, sort_keys=True, indent=2).encode() + b"\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--first", type=Path, required=True); parser.add_argument("--second", type=Path, required=True); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = aggregate(args.first, args.second, args.output)
    print(json.dumps({"status": result["status"]}, sort_keys=True)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
