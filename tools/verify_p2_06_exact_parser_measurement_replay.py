"""Verify P2-06 same-deck parser and engine-measurement replay evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "docs/baselines/p2-06-exact-parser-measurement-replay.v2.yaml"
PREDECESSOR = ROOT / "docs/baselines/p2-06-exact-rc-measurement-current-external-compare.v1.yaml"
SCHEMA = "sipi.p2-06.exact-parser-measurement-replay.v2"
COMMIT = "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5"
TREE = "b6bde97128030d6cea0d68b2f0a35d807be8c402"
PREDECESSOR_SHA256 = "a3089d5eb13173e1fc8c54aa8fb2c17d9b2d29263e786fd80e7308317b901682"
REPORT_SHA256 = "4678a4febb13d105e6ed739701f1e860916d369ab54e20ae6f50ed4251836d96"
SOURCE_OBJECTS = {
    "LICENSE": "55aac2e4f8c36a978d315efb02815972579b8293",
    "LICENSE-MANIFEST.md": "2b549451fdf28b4fbaf524010efbe33c6d49b385",
    "native/agent-spice-sim/Cargo.toml": "b56d29811d0293c878b22485523f03ea06dc2d91",
    "native/agent-spice-sim/src/netlist.rs": "83ffa04c90fb7c523875fb93c64b1f245793bcd1",
    "native/agent-spice-sim/src/simulator.rs": "ed5712567420013d70c39a14257e1f77004a64b4",
    "native/agent-spice-sim/src/result.rs": "f13c37b9fd367c5cb66a148deecedcea7d12b794",
    "native/agent-spice-sim/src/main.rs": "a333857287fc093f2f1fa515b135fe31a2bc9eb1",
}


class ReplayEvidenceError(ValueError):
    pass


def load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReplayEvidenceError("record_invalid") from error
    if not isinstance(value, dict):
        raise ReplayEvidenceError("record_invalid")
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_document(document: dict[str, Any]) -> dict[str, Any]:
    if document.get("schema") != SCHEMA or document.get("status") != "exact_profile_scoped_close_supported":
        raise ReplayEvidenceError("identity_invalid")
    if document.get("predecessor") != {"path": "docs/baselines/p2-06-exact-rc-measurement-current-external-compare.v1.yaml", "sha256": PREDECESSOR_SHA256, "limitation_superseded": "waveform_observed_measurement_authority_not_bound", "unchanged": True}:
        raise ReplayEvidenceError("predecessor_invalid")
    exact_input = document.get("input")
    if exact_input != {"profile": "strict_seven_line_single_pulse_rc_tran_max_vout", "bytes": 143, "sha256": "e205a2e1ba71c77d1063f92bd877b449bcf10bfdedc3e9dd2ebdf505038d4f84", "same_bytes_supplied_to_oracle_and_product": True, "origin": "first_party_exact_profile"}:
        raise ReplayEvidenceError("input_binding_invalid")
    source = document.get("external_source")
    if not isinstance(source, dict) or source.get("commit") != COMMIT or source.get("tree") != TREE or source.get("license") != "MIT" or source.get("redistribution") != "external_only_hash_bound":
        raise ReplayEvidenceError("external_source_invalid")
    if source.get("objects") != SOURCE_OBJECTS:
        raise ReplayEvidenceError("external_objects_invalid")
    replay = document.get("replay")
    if not isinstance(replay, dict) or replay.get("oracle_fresh_processes") != 2 or replay.get("product_fresh_processes") != 2 or replay.get("oracle_git_dirty") is not False or replay.get("oracle_measurement_source") != "SimulationResult.measurements[0]" or replay.get("accepted") is not True:
        raise ReplayEvidenceError("replay_invalid")
    if replay.get("measurement_max_absolute_error_volts") != 9.963737488231927e-7 or replay.get("absolute_tolerance_volts") != 2.0e-6 or replay.get("relative_tolerance") != 5.0e-4:
        raise ReplayEvidenceError("comparison_invalid")
    closure = document.get("closure")
    if closure != {"exact_profile_scoped_close": True, "same_input_original_parser_executed": True, "external_measurement_result_observed": True, "measurement_reduced_by_original_engine": True, "sampled_max_reduced_by_comparator": False, "generic_spice_or_mna": False, "op_or_ac": False, "general_measurements": False}:
        raise ReplayEvidenceError("closure_invalid")
    report = document.get("external_report")
    if report != {"schema": "sipi.p2-06.exact-rc-measurement-compare.v1", "sha256": REPORT_SHA256, "custody": "operator_external_only"}:
        raise ReplayEvidenceError("external_report_invalid")
    product = document.get("product")
    if not isinstance(product, dict) or product.get("stdin_budget_bytes") != 4096:
        raise ReplayEvidenceError("product_invalid")
    non_claims = document.get("non_claims")
    if not isinstance(non_claims, list) or len(non_claims) != 3:
        raise ReplayEvidenceError("non_claims_invalid")
    return {"valid": True, "status": document["status"], "exact_profile_scoped_close": True}


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8", errors="strict", timeout=60)
    if completed.returncode != 0:
        raise ReplayEvidenceError("external_git_object_unavailable")
    return completed.stdout.strip()


def verify(root: Path = ROOT, report_path: Path | None = None, source_root: Path | None = None) -> dict[str, Any]:
    document = load(root / RECORD.relative_to(ROOT))
    result = validate_document(document)
    if sha256(root / PREDECESSOR.relative_to(ROOT)) != PREDECESSOR_SHA256:
        raise ReplayEvidenceError("predecessor_hash_drift")
    product = document["product"]
    for path_key, hash_key in (("parser_source", "parser_source_sha256"), ("harness_source", "harness_source_sha256"), ("comparator", "comparator_sha256")):
        if sha256(root / product[path_key]) != product[hash_key]:
            raise ReplayEvidenceError("product_source_hash_drift")
    if report_path is not None:
        if sha256(report_path) != document["external_report"]["sha256"]:
            raise ReplayEvidenceError("external_report_hash_mismatch")
        report = load(report_path)
        if report.get("accepted") is not True or report.get("input", {}).get("sha256") != document["input"]["sha256"] or report.get("oracle", {}).get("measurement", {}).get("source_path") != "SimulationResult.measurements[0]":
            raise ReplayEvidenceError("external_report_content_invalid")
        if report.get("source", {}).get("objects") != document["external_source"]["objects"]:
            raise ReplayEvidenceError("external_report_source_mismatch")
        report_sources = report.get("product", {}).get("source_sha256", {})
        if report_sources.get(product["parser_source"]) != product["parser_source_sha256"] or report_sources.get(product["harness_source"]) != product["harness_source_sha256"]:
            raise ReplayEvidenceError("external_report_product_source_mismatch")
    if source_root is not None:
        if git(source_root, "rev-parse", f"{COMMIT}^{{tree}}") != TREE:
            raise ReplayEvidenceError("external_tree_drift")
        for path, blob in document["external_source"]["objects"].items():
            if git(source_root, "rev-parse", f"{COMMIT}:{path}") != blob:
                raise ReplayEvidenceError("external_source_object_drift")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--external-report", type=Path)
    parser.add_argument("--source-root", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps({"schema": SCHEMA, **verify(args.root, args.external_report, args.source_root)}, sort_keys=True))
        return 0
    except (OSError, ReplayEvidenceError) as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
