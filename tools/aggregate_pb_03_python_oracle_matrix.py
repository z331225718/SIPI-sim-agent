"""Aggregate two archive-only PB-03 Python-oracle matrix replays."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

from pb_03_replay_common import compare_windows_pe_custody, windows_pe_custody_shape, windows_pe_repro_policy


ROOT = Path(__file__).resolve().parents[1]
HEX32 = re.compile(r"[0-9a-f]{32}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
MANIFEST = ROOT / "docs/baselines/pb-03-python-oracle-18-branch-d3154093.v1.yaml"
AUDIT = ROOT / "docs/baselines/audits/2026-08-24-pb-03-python-oracle-18-branch-d3154093.md"


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def stable(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.name


def load(path: Path) -> tuple[dict[str, Any], str]:
    payload = path.read_bytes()
    value = json.loads(payload.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("matrix report must be an object")
    return value, sha256(payload)


def manifest_binding(path: Path) -> str:
    """Hash manifest identity/coverage without the cyclic evidence bindings."""
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("PB-03 manifest must be an object")
    corpus = document.get("corpus")
    if not isinstance(corpus, dict):
        raise ValueError("PB-03 manifest corpus is missing")
    core = {
        "schema": document.get("schema"),
        "version": document.get("version"),
        "successor_of": document.get("successor_of"),
        "row": document.get("row"),
        "status": document.get("status"),
        "purpose": document.get("purpose"),
        "source": document.get("source"),
        "corpus": {key: corpus.get(key) for key in ("path", "sha256", "cases")},
        "branch_inventory": document.get("branch_inventory"),
        "portable_branch_probe_missing": document.get("portable_branch_probe_missing"),
        "python_payload_oracle_missing": document.get("python_payload_oracle_missing"),
        "external_blockers": document.get("external_blockers"),
        "claims": document.get("claims"),
    }
    return sha256(canonical(core))


def aggregate(first_path: Path, second_path: Path, output: Path) -> dict[str, Any]:
    first, first_sha = load(first_path)
    second, second_sha = load(second_path)
    blockers: list[str] = []
    if first_path.resolve() == second_path.resolve():
        blockers.append("report paths must be distinct")
    if first_sha == second_sha:
        blockers.append("report digests must be distinct")
    if first.get("run_id") == second.get("run_id"):
        blockers.append("run IDs must be distinct")
    if first.get("fresh_run_nonce") == second.get("fresh_run_nonce"):
        blockers.append("fresh run nonces must be distinct")
    first_binary = first.get("build", {}).get("binary_sha256") if isinstance(first.get("build"), dict) else None
    second_binary = second.get("build", {}).get("binary_sha256") if isinstance(second.get("build"), dict) else None
    first_custody = first.get("build", {}).get("binary_custody") if isinstance(first.get("build"), dict) else None
    second_custody = second.get("build", {}).get("binary_custody") if isinstance(second.get("build"), dict) else None
    if not isinstance(first_custody, dict) or first_binary != first_custody.get("raw_sha256"):
        blockers.append("first raw binary digest is not bound to PE custody")
    if not isinstance(second_custody, dict) or second_binary != second_custody.get("raw_sha256"):
        blockers.append("second raw binary digest is not bound to PE custody")
    blockers.extend(compare_windows_pe_custody(first_custody, second_custody))
    for label, report in (("first", first), ("second", second)):
        if report.get("schema") != "sipi.pb-03-python-oracle-matrix-replay.v1":
            blockers.append(f"{label} schema mismatch")
        if report.get("row") != "PB-03":
            blockers.append(f"{label} row mismatch")
        if report.get("source_mode") != "git_archive_at_candidate_prep_commit_plus_content_addressed_input_corpus_and_harness_snapshot":
            blockers.append(f"{label} source is not archive-only")
        if report.get("claims", {}).get("independent_python_payload_oracle") is not True:
            blockers.append(f"{label} independent Python oracle claim missing")
        if report.get("claims", {}).get("global_branch_parity") is not False:
            blockers.append(f"{label} global parity was incorrectly closed")
        nonce = report.get("fresh_run_nonce")
        if not isinstance(nonce, str) or HEX32.fullmatch(nonce) is None:
            blockers.append(f"{label} nonce malformed")
        if report.get("status") != "blocked":
            blockers.append(f"{label} report unexpectedly closed")
    for identity in ("candidate", "upstream", "fixture", "corpus", "harness", "toolchain"):
        if first.get(identity) != second.get(identity):
            blockers.append(f"{identity} identity drift")
    first_cases = {case.get("id"): case for case in first.get("cases", []) if isinstance(case, dict)}
    second_cases = {case.get("id"): case for case in second.get("cases", []) if isinstance(case, dict)}
    if set(first_cases) != set(second_cases):
        blockers.append("case matrix drift")
    case_summary: list[dict[str, Any]] = []
    for case_id in sorted(first_cases):
        left = first_cases[case_id]
        right = second_cases.get(case_id, {})
        if left.get("expected_fields") != right.get("expected_fields"):
            blockers.append(f"{case_id} expected-field drift")
        if left.get("status") != right.get("status"):
            blockers.append(f"{case_id} status drift")
        case_summary.append(
            {
                "id": case_id,
                "status": left.get("status"),
                "expected_fields": left.get("expected_fields"),
                "first_blockers": left.get("blockers", []),
                "second_blockers": right.get("blockers", []),
                "first_payload": left.get("payload"),
                "second_payload": right.get("payload"),
            }
        )
    result = {
        "schema": "sipi.pb-03-python-oracle-matrix-aggregate.v1",
        "version": 1,
        "row": "PB-03",
        "status": "blocked",
        "source_mode": "git_archive_at_immutable_commit_plus_content_addressed_input_corpus",
        "reports": [
            {"path": stable(first_path), "sha256": first_sha, "run_id": first.get("run_id"), "fresh_run_nonce": first.get("fresh_run_nonce")},
            {"path": stable(second_path), "sha256": second_sha, "run_id": second.get("run_id"), "fresh_run_nonce": second.get("fresh_run_nonce")},
        ],
        "candidate": first.get("candidate"),
        "upstream": first.get("upstream"),
        "fixture": first.get("fixture"),
        "corpus": first.get("corpus"),
        "harness": first.get("harness"),
        "toolchain": first.get("toolchain"),
        "builds": [
            {"report": stable(first_path), "binary_sha256": first_binary, "binary_custody": first_custody},
            {"report": stable(second_path), "binary_sha256": second_binary, "binary_custody": second_custody},
        ],
        "manifest": {
            "path": stable(MANIFEST),
            "binding_sha256": manifest_binding(MANIFEST),
        },
        "audit": {
            "path": stable(AUDIT),
            "sha256": sha256(AUDIT.read_bytes()),
        },
        "cases": case_summary,
        "distinct_gate": {
            "unique_report_paths": first_path.resolve() != second_path.resolve(),
            "unique_report_sha256": first_sha != second_sha,
            "unique_run_ids": first.get("run_id") != second.get("run_id"),
            "unique_fresh_run_nonces": first.get("fresh_run_nonce") != second.get("fresh_run_nonce"),
            "exact_candidate_identity": first.get("candidate") == second.get("candidate"),
            "exact_upstream_identity": first.get("upstream") == second.get("upstream"),
            "exact_toolchain_identity": first.get("toolchain") == second.get("toolchain"),
            "exact_binary_sha256": first_binary == second_binary,
            "exact_binary_canonical_sha256": isinstance(first_custody, dict)
            and isinstance(second_custody, dict)
            and first_custody.get("canonical_sha256") == second_custody.get("canonical_sha256"),
        },
        "binary_custody_gate": {
            "raw_sha256_equal": first_binary == second_binary,
            "canonical_sha256_equal": isinstance(first_custody, dict)
            and isinstance(second_custody, dict)
            and first_custody.get("canonical_sha256") == second_custody.get("canonical_sha256"),
            "normalization_shape_equal": windows_pe_custody_shape(first_custody) == windows_pe_custody_shape(second_custody),
            "repro_policy": windows_pe_repro_policy(first_custody, second_custody),
            "blockers": compare_windows_pe_custody(first_custody, second_custody),
        },
        "blockers": blockers + ["portable branch payload mismatches and pinned upstream FEC runtime error remain open"],
        "claims": {
            "independent_python_payload_oracle": True,
            "portable_case_matrix_executed": True,
            "global_branch_parity": False,
            "promotion": False,
        },
        "non_claims": [
            "A Python oracle execution is independent from the Rust candidate but does not close mismatched payload branches.",
            "AMI/IBIS/DLL/GetWave and exact PyBertData class restoration remain outside this portable matrix.",
            "Raw PE digests may differ when only approved timestamp/RSDS-GUID fields differ; canonical digest, profile/normalization shape, or REPRO payload drift blocks aggregation and never promotes a row.",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--first", type=Path, required=True)
    parser.add_argument("--second", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = aggregate(args.first, args.second, args.output)
    print(json.dumps({"status": result["status"], "output": stable(args.output)}, sort_keys=True))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
