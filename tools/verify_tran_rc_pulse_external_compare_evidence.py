"""Verify the hash-only external comparison evidence for the fixed TRAN profile.

The external report itself remains outside the worktree.  This verifier checks
the tracked, hash-only attestation and can additionally bind it to a supplied
external report without retaining any fixture or waveform data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

from verify_tran_rc_pulse_acceptance import _load


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.tran.rc-pulse.external-compare-evidence.v1"
REPORT_SCHEMA = "sipi.tran.rc-pulse.compare.v1"
PROFILE_ID = "tran-rc-pulse-v1"
CONTRACT = ROOT / "docs" / "baselines" / "tran-rc-pulse-acceptance.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "tran-rc-pulse-external-compare-evidence.v1.yaml"


class EvidenceError(RuntimeError):
    pass


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _canonical_json_sha256(value: object) -> str:
    return _sha256_bytes(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8"))


def _sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _sha1(value: object) -> bool:
    return isinstance(value, str) and len(value) == 40 and all(char in "0123456789abcdef" for char in value)


def _exact(value: object, keys: set[str]) -> bool:
    return isinstance(value, dict) and set(value) == keys


def _git_object(revision: str, path: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", f"{revision}:{path}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _current_object(path: str) -> str:
    return _git_object("HEAD", path)


def _load_report(path: Path) -> dict[str, Any]:
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EvidenceError("external_report_invalid") from error
    if not isinstance(report, dict):
        raise EvidenceError("external_report_invalid")
    return report


def _metric_summary(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    comparisons = report.get("comparisons")
    if not isinstance(comparisons, list) or len(comparisons) != 3:
        raise EvidenceError("external_report_comparisons_invalid")
    summary: dict[str, dict[str, Any]] = {}
    for item in comparisons:
        keys = {
            "observable", "passed", "absolute_tolerance", "relative_tolerance",
            "max_absolute_error", "max_relative_error", "allowed_error_at_worst_index", "worst_index",
        }
        if not _exact(item, keys) or item["observable"] in summary or item["passed"] is not True:
            raise EvidenceError("external_report_comparisons_invalid")
        numeric_keys = ("absolute_tolerance", "relative_tolerance", "max_absolute_error", "max_relative_error", "allowed_error_at_worst_index")
        if not all(isinstance(item[key], (int, float)) and not isinstance(item[key], bool) and math.isfinite(float(item[key])) for key in numeric_keys):
            raise EvidenceError("external_report_comparisons_invalid")
        if not isinstance(item["worst_index"], int) or item["worst_index"] < 0:
            raise EvidenceError("external_report_comparisons_invalid")
        summary[item["observable"]] = {
            key: item[key] for key in (
                "absolute_tolerance", "relative_tolerance", "max_absolute_error",
                "max_relative_error", "allowed_error_at_worst_index", "worst_index",
            )
        }
    if set(summary) != {"time_axis_seconds", "voltage_in_volts", "voltage_out_volts"}:
        raise EvidenceError("external_report_comparisons_invalid")
    return summary


def _validate_report_binding(evidence: dict[str, Any], report: dict[str, Any]) -> None:
    expected_keys = {
        "schema", "profile_id", "status", "accepted", "contract_sha256", "source",
        "environment", "oracle", "product", "comparisons", "non_claims",
    }
    if set(report) != expected_keys or report["schema"] != REPORT_SCHEMA or report["profile_id"] != PROFILE_ID:
        raise EvidenceError("external_report_schema_invalid")
    if report["status"] != "passed" or report["accepted"] is not True:
        raise EvidenceError("external_report_not_accepted")
    if report["contract_sha256"] != evidence["contract"]["sha256"] or report["source"] != evidence["source"]:
        raise EvidenceError("external_report_contract_binding_mismatch")
    oracle = report["oracle"]
    product = report["product"]
    if not isinstance(oracle, dict) or not isinstance(product, dict):
        raise EvidenceError("external_report_identity_invalid")
    if oracle.get("sha256") != evidence["oracle"]["executable_sha256"]:
        raise EvidenceError("external_report_oracle_identity_mismatch")
    if _canonical_json_sha256(oracle.get("build_info")) != evidence["oracle"]["build_info_sha256"]:
        raise EvidenceError("external_report_oracle_build_info_mismatch")
    if product.get("sha256") != evidence["product"]["executable_sha256"] or product.get("source_commit") != evidence["product"]["source_commit"]:
        raise EvidenceError("external_report_product_identity_mismatch")
    runs = oracle.get("runs")
    if not _exact(runs, {"first", "second"}) or runs["first"] != runs["second"] or runs["first"] != evidence["replays"]["oracle_samples"]:
        raise EvidenceError("external_report_oracle_replay_mismatch")
    if product.get("samples") != evidence["replays"]["product_samples"]:
        raise EvidenceError("external_report_product_samples_mismatch")
    if _metric_summary(report) != evidence["comparison"]:
        raise EvidenceError("external_report_metrics_mismatch")


def verify_document(document: object, report_path: Path | None = None) -> dict[str, Any]:
    required = {"schema", "status", "profile_id", "contract", "external_report", "source", "oracle", "product", "replays", "comparison", "non_claims"}
    if not _exact(document, required) or document["schema"] != SCHEMA:
        raise EvidenceError("evidence_schema_invalid")
    if document["status"] != "accepted" or document["profile_id"] != PROFILE_ID:
        raise EvidenceError("evidence_status_invalid")
    contract = document["contract"]
    external_report = document["external_report"]
    source = document["source"]
    oracle = document["oracle"]
    product = document["product"]
    replays = document["replays"]
    comparison = document["comparison"]
    if not _exact(contract, {"schema", "sha256"}) or contract["schema"] != "sipi.tran.rc-pulse.acceptance.v1" or not _sha256(contract["sha256"]):
        raise EvidenceError("evidence_contract_invalid")
    if _sha256_file(CONTRACT) != contract["sha256"]:
        raise EvidenceError("evidence_contract_hash_mismatch")
    if not _exact(external_report, {"schema", "sha256", "custody"}) or external_report["schema"] != REPORT_SCHEMA or not _sha256(external_report["sha256"]) or external_report["custody"] != "operator_external_only":
        raise EvidenceError("evidence_report_invalid")
    acceptance = _load(CONTRACT)
    source_keys = {"canonical_origin", "commit", "tree", "path", "git_blob", "content_sha256", "redistribution"}
    expected_source = {key: acceptance["source"][key] for key in source_keys}
    if source != expected_source:
        raise EvidenceError("evidence_source_mismatch")
    if not _exact(oracle, {"executable_sha256", "build_info_sha256"}) or not all(_sha256(oracle[key]) for key in oracle):
        raise EvidenceError("evidence_oracle_invalid")
    expected_product_keys = {"source_commit", "source_trees", "cargo_lock_blob", "executable_sha256"}
    expected_tree_paths = {"sipi-tran": "crates/sipi-tran", "sipi-types": "crates/sipi-types", "sipi-runtime": "crates/sipi-runtime"}
    if not _exact(product, expected_product_keys) or not _sha1(product["source_commit"]) or not _exact(product["source_trees"], set(expected_tree_paths)) or not _sha1(product["cargo_lock_blob"]) or not _sha256(product["executable_sha256"]):
        raise EvidenceError("evidence_product_invalid")
    try:
        for name, path in expected_tree_paths.items():
            if not _sha1(product["source_trees"][name]) or _git_object(product["source_commit"], path) != product["source_trees"][name] or _current_object(path) != product["source_trees"][name]:
                raise EvidenceError("evidence_product_source_drift")
        if _git_object(product["source_commit"], "Cargo.lock") != product["cargo_lock_blob"] or _current_object("Cargo.lock") != product["cargo_lock_blob"]:
            raise EvidenceError("evidence_product_source_drift")
    except subprocess.CalledProcessError as error:
        raise EvidenceError("evidence_product_source_drift") from error
    sample_keys = {"length", "time_sha256_f64le", "voltage_in_sha256_f64le", "voltage_out_sha256_f64le"}
    if not _exact(replays, {"oracle_runs", "oracle_samples", "product_samples"}) or replays["oracle_runs"] != 2:
        raise EvidenceError("evidence_replays_invalid")
    for samples in (replays["oracle_samples"], replays["product_samples"]):
        if not _exact(samples, sample_keys) or samples["length"] != 4 or not all(_sha256(samples[key]) for key in sample_keys - {"length"}):
            raise EvidenceError("evidence_samples_invalid")
    expected_observables = {"time_axis_seconds", "voltage_in_volts", "voltage_out_volts"}
    expected_tolerances = {
        "time_axis_seconds": (acceptance["acceptance"]["time_axis"]["absolute_tolerance_seconds"], acceptance["acceptance"]["time_axis"]["relative_tolerance"]),
        "voltage_in_volts": (acceptance["acceptance"]["voltage_in"]["absolute_tolerance_volts"], acceptance["acceptance"]["voltage_in"]["relative_tolerance"]),
        "voltage_out_volts": (acceptance["acceptance"]["voltage_out"]["absolute_tolerance_volts"], acceptance["acceptance"]["voltage_out"]["relative_tolerance"]),
    }
    if not isinstance(comparison, dict) or set(comparison) != expected_observables:
        raise EvidenceError("evidence_comparison_invalid")
    for observable, metrics in comparison.items():
        numeric_keys = ("absolute_tolerance", "relative_tolerance", "max_absolute_error", "max_relative_error", "allowed_error_at_worst_index")
        if not _exact(metrics, {"absolute_tolerance", "relative_tolerance", "max_absolute_error", "max_relative_error", "allowed_error_at_worst_index", "worst_index"}) or not all(isinstance(metrics[key], (int, float)) and not isinstance(metrics[key], bool) and math.isfinite(float(metrics[key])) for key in numeric_keys) or not isinstance(metrics["worst_index"], int) or metrics["worst_index"] < 0:
            raise EvidenceError("evidence_comparison_invalid")
        if (metrics["absolute_tolerance"], metrics["relative_tolerance"]) != expected_tolerances[observable] or metrics["max_absolute_error"] > metrics["allowed_error_at_worst_index"]:
            raise EvidenceError("evidence_comparison_contract_mismatch")
    if not isinstance(document["non_claims"], list) or not document["non_claims"] or any(not isinstance(item, str) or not item for item in document["non_claims"]):
        raise EvidenceError("evidence_non_claims_invalid")
    if report_path is not None:
        if _sha256_file(report_path) != external_report["sha256"]:
            raise EvidenceError("external_report_hash_mismatch")
        _validate_report_binding(document, _load_report(report_path))
    return {"schema": SCHEMA, "valid": True, "profile_id": PROFILE_ID, "report_bound": report_path is not None}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=EVIDENCE)
    parser.add_argument("--report", type=Path)
    arguments = parser.parse_args()
    try:
        result = verify_document(_load(arguments.evidence), arguments.report)
    except (EvidenceError, OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
