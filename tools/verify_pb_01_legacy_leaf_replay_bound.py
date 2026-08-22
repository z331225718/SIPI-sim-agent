"""Verify the immutable PB-01 scoped legacy-leaf replay evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "docs/baselines/pb-01-legacy-leaf-replay-bound.v1.yaml"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
ABSOLUTE_PATH = re.compile(r"(?:[A-Za-z]:[\\/]|/Users/|/home/|\\\\[^\\]+\\[^\\]+)")
ARRAY_NAMES = (
    "chnl_h", "tx_out_h", "ctle_out_h", "dfe_out_h", "chnl_s", "tx_out_s",
    "ctle_out_s", "dfe_out_s", "chnl_p", "tx_out_p", "ctle_out_p", "dfe_out_p",
)
CANONICAL_ITEM_NAMES = (
    "chnl_h", "tx_out_h", "ctle_out_h", "dfe_out_h", "chnl_s", "tx_s",
    "ctle_s", "dfe_s", "tx_out_s", "ctle_out_s", "dfe_out_s", "chnl_p",
    "tx_out_p", "ctle_out_p", "dfe_out_p", "chnl_H", "tx_H", "ctle_H",
    "dfe_H", "tx_out_H", "ctle_out_H", "dfe_out_H", "tx_out",
)
COMPARISON_POLICY = {"absolute_tolerance": 1.0e-7, "relative_scale": 1.0e-6, "formula": "absolute_tolerance + relative_scale * scale"}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _path(root: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute() or ".." in Path(value).parts:
        raise ValueError("evidence path is not repository-relative")
    resolved = (root / value).resolve()
    if root.resolve() not in resolved.parents:
        raise ValueError("evidence path escapes repository")
    return resolved


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("bound JSON is not an object")
    return value


def _toolchain(value: Any) -> bool:
    if not isinstance(value, dict) or set(value) != {"cargo", "rustc", "uv", "timeout_seconds"}:
        return False
    if type(value["timeout_seconds"]) is not int or value["timeout_seconds"] <= 0:
        return False
    expected = {"role", "executable", "path_redacted", "file_sha256", "version_exit_code", "version_output_sha256"}
    for role in ("cargo", "rustc", "uv"):
        item = value.get(role)
        if not isinstance(item, dict) or set(item) != expected or item.get("role") != role:
            return False
        if item.get("path_redacted") is not True or item.get("version_exit_code") != 0:
            return False
        if not isinstance(item.get("executable"), str) or any(x in item["executable"] for x in ("/", "\\", ":")):
            return False
        if any(not isinstance(item.get(key), str) or HEX64.fullmatch(item[key]) is None for key in ("file_sha256", "version_output_sha256")):
            return False
    return True


def verify(manifest_path: Path = DEFAULT_MANIFEST, root: Path = ROOT) -> dict[str, Any]:
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("manifest is not a mapping")
    errors: list[str] = []
    if manifest.get("schema") != "sipi.pb-01-legacy-leaf-replay-bound.v1" or manifest.get("status") != "accepted_scoped_23_key_leaf":
        errors.append("manifest schema/status drift")
    if manifest.get("relationship") != {
        "predecessor_evidence": "docs/baselines/pb-01-legacy-leaf.v1.yaml",
        "supersedes": "pending_immutable_replay_status_only",
        "preserves_branch_default_error_artifact_inventory": True,
    }:
        errors.append("predecessor relationship drift")
    if manifest.get("artifact", {}).get("tolerance") != {"absolute": 1.0e-7, "relative_scale": 1.0e-6, "formula": "absolute_tolerance + relative_scale * scale"} or manifest.get("reproducibility") != {"source_mode": "content_addressed_working_tree_files", "binary_bit_reproducible": False}:
        errors.append("manifest tolerance/reproducibility policy drift")
    for section in ("tools", "audit"):
        items = manifest.get(section, {})
        values = items.values() if section == "tools" and isinstance(items, dict) else [items]
        for binding in values:
            if not isinstance(binding, dict):
                errors.append(f"{section} binding malformed")
                continue
            try:
                path = _path(root, binding.get("path"))
            except ValueError as error:
                errors.append(str(error))
                continue
            if not path.is_file() or _sha(path) != binding.get("sha256"):
                errors.append(f"{section} hash drift: {binding.get('path')}")
    reports: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for binding in manifest.get("replays", []):
        try:
            path = _path(root, binding.get("path"))
            if _sha(path) != binding.get("sha256"):
                errors.append("replay complete hash drift")
            report = _load_json(path)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            errors.append(str(error))
            continue
        reports.append((binding, report))
        if ABSOLUTE_PATH.search(path.read_text(encoding="utf-8")):
            errors.append("replay leaks an absolute path")
        if report.get("schema") != "sipi.pb-01-legacy-leaf-replay.v1" or report.get("status") != "passed" or report.get("source_mode") != "git_archive_at_immutable_commit":
            errors.append("replay schema/status/source drift")
        if report.get("run_id") != binding.get("run_id") or report.get("fresh_run_nonce") != binding.get("fresh_run_nonce"):
            errors.append("replay id/nonce binding drift")
        if not _toolchain(report.get("toolchain")):
            errors.append("replay toolchain identity malformed")
        harness = report.get("harness")
        if not isinstance(harness, dict) or set(harness) != {"source_mode", "runner", "custody_runner_helper"} or harness.get("source_mode") != "content_addressed_working_tree_files":
            errors.append("content-addressed harness malformed")
        else:
            expected_harness_paths = {
                "runner": "tools/run_pb_01_legacy_leaf_replay.py",
                "custody_runner_helper": "tools/run_pb_02_direct_replay.py",
            }
            for name, expected_path in expected_harness_paths.items():
                value = harness.get(name)
                if not isinstance(value, dict) or value.get("path") != expected_path or set(value) != {"path", "sha256"}:
                    errors.append(f"{name} harness binding malformed")
                elif _sha(_path(root, expected_path)) != value.get("sha256"):
                    errors.append(f"{name} harness content hash drift")
        if report.get("reproducibility") != {"binary_bit_reproducible": False}:
            errors.append("binary bit reproducibility must remain false")
        candidate, upstream = report.get("candidate", {}), report.get("upstream", {})
        for field in ("commit", "tree", "archive_sha256"):
            if candidate.get(field) != manifest.get("candidate", {}).get(field) or upstream.get(field) != manifest.get("upstream", {}).get(field):
                errors.append(f"source {field} drift")
        if candidate.get("inventory", {}).get("sha256") != manifest.get("candidate", {}).get("inventory_sha256") or upstream.get("inventory", {}).get("sha256") != manifest.get("upstream", {}).get("inventory_sha256"):
            errors.append("source inventory drift")
        if report.get("fixture") != {"path": manifest["scope"]["fixture"], "bytes": manifest["fixture"]["bytes"], "sha256": manifest["fixture"]["sha256"]}:
            errors.append("fixture binding drift")
        schema = report.get("replay", {}).get("candidate_artifact_schema")
        if schema != {"kind": "python_pickle_dict", "schema": "sipi.pybert_data.v1", "item_names": list(CANONICAL_ITEM_NAMES), "array_keys": sorted(CANONICAL_ITEM_NAMES)}:
            errors.append("candidate 23-key artifact schema drift")
        comparison = report.get("replay", {}).get("comparison", {})
        rows = comparison.get("arrays", [])
        if comparison.get("policy") != COMPARISON_POLICY:
            errors.append("comparison policy drift")
        if comparison.get("status") != "passed" or comparison.get("blockers") != [] or [row.get("name") for row in rows] != list(ARRAY_NAMES) or not all(row.get("passed") is True for row in rows):
            errors.append("selected numeric comparison drift")
        for row in rows:
            numeric = [row.get("max_abs"), row.get("scale"), row.get("tolerance")]
            if type(row.get("length")) is not int or row["length"] <= 0 or any(not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) for value in numeric):
                errors.append("comparison row numeric facts malformed")
                continue
            expected_tolerance = COMPARISON_POLICY["absolute_tolerance"] + COMPARISON_POLICY["relative_scale"] * row["scale"]
            if row["scale"] < 1.0 or row["max_abs"] < 0.0 or not math.isclose(row["tolerance"], expected_tolerance, rel_tol=0.0, abs_tol=1.0e-15) or row["max_abs"] > row["tolerance"]:
                errors.append("comparison row tolerance contract failed")
        replay = report.get("replay", {})
        build = replay.get("build", {})
        if build.get("exit_code") != 0 or type(build.get("binary_bytes")) is not int or build["binary_bytes"] <= 0 or not isinstance(build.get("binary_sha256"), str) or HEX64.fullmatch(build["binary_sha256"]) is None:
            errors.append("candidate build facts are not successful")
        for role, expected_path in (("candidate", "candidate-result.pybert_data"), ("oracle", "oracle-result.pybert_data")):
            process = replay.get(role, {})
            artifact = process.get("artifact", {}) if isinstance(process, dict) else {}
            if process.get("exit_code") != 0 or artifact.get("present") is not True or artifact.get("path") != expected_path or type(artifact.get("bytes")) is not int or artifact["bytes"] <= 0 or not isinstance(artifact.get("sha256"), str) or HEX64.fullmatch(artifact["sha256"]) is None:
                errors.append(f"{role} process/artifact facts are not successful")
        required_open = ("Imported S2P", ".pybert_cfg", "AMI/IBIS", "periodic/random noise", "adaptive DFE/Viterbi", "jitter/eye/bathtub")
        joined = "\n".join(report.get("non_claims", []))
        if any(text not in joined for text in required_open) or "not a PyBertData class-compatible pickle" not in joined:
            errors.append("replay non-claims drift")
    if len(reports) != 2:
        errors.append("exactly two replay bindings are required")
    else:
        first_binding, first = reports[0]
        second_binding, second = reports[1]
        if first_binding.get("path") == second_binding.get("path") or first_binding.get("sha256") == second_binding.get("sha256") or first.get("run_id") == second.get("run_id") or first.get("fresh_run_nonce") == second.get("fresh_run_nonce"):
            errors.append("independent replay distinctness drift")
        if first.get("candidate") != second.get("candidate") or first.get("upstream") != second.get("upstream") or first.get("fixture") != second.get("fixture") or first.get("toolchain") != second.get("toolchain"):
            errors.append("replay identity drift")
    aggregate_binding = manifest.get("aggregate", {})
    try:
        aggregate_path = _path(root, aggregate_binding.get("path"))
        aggregate = _load_json(aggregate_path)
        if _sha(aggregate_path) != aggregate_binding.get("sha256"):
            errors.append("aggregate complete hash drift")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        errors.append(str(error))
        aggregate = {}
    if aggregate.get("schema") != aggregate_binding.get("schema") or aggregate.get("status") != "passed" or aggregate.get("blockers") != []:
        errors.append("aggregate schema/status drift")
    if reports and aggregate.get("reports") != [{"path": b["path"], "sha256": b["sha256"], "run_id": r["run_id"], "fresh_run_nonce": r["fresh_run_nonce"]} for b, r in reports]:
        errors.append("aggregate report binding drift")
    if reports:
        first = reports[0][1]
        for name, source in (
            ("harness", first.get("harness")),
            ("reproducibility", first.get("reproducibility")),
            ("comparison", first.get("replay", {}).get("comparison")),
            ("artifact_contract", first.get("artifact_contract")),
        ):
            if aggregate.get(name) != source:
                errors.append(f"aggregate {name} binding drift")
    expected_open = {"imported_S2P", "pybert_cfg_pickle_input", "AMI_and_IBIS_models", "periodic_and_random_noise", "adaptive_DFE_and_Viterbi", "jitter_eye_and_bathtub_analysis", "exact_PyBertData_class_pickle"}
    if set(manifest.get("open_branches", [])) != expected_open or manifest.get("claims") != {"scoped_23_key_dictionary_leaf": True, "exact_PyBertData_class_pickle": False, "branch_complete": False, "product_capability_admission": False, "license_decision": False, "release_approval": False}:
        errors.append("claim/open-branch boundary drift")
    return {"valid": not errors, "errors": errors, "candidate_commit": manifest.get("candidate", {}).get("commit"), "aggregate_sha256": aggregate_binding.get("sha256")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    try:
        result = verify(args.manifest.resolve())
    except (OSError, ValueError, yaml.YAMLError) as error:
        result = {"valid": False, "errors": [str(error)]}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
