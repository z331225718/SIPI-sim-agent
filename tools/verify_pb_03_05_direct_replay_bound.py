"""Fail-closed verifier for the PB-03..PB-05 immutable replay evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_COMMIT = "5bf6d7ea0ace261891aaeb611ffc1c267e160afe"
UPSTREAM_TREE = "5faef6bdb341d444ad65d82a11c0018b15805e24"
CANDIDATE_COMMIT = "eb2a13f53fb54f09956a0ec8196fad9bc3da220f"
CANDIDATE_TREE = "cba5db1a594115f1859c23b67d20f4da5f356f53"
NONCE = re.compile(r"[0-9a-f]{32,64}\Z")
PATH_LEAK = re.compile(r"(?:[A-Za-z]:[\\/]|(?:^|[^A-Za-z0-9])/(?:Users|home|tmp|var/tmp)/|\\(?:Users|Temp)\\)")

ROWS = {
    "PB-03": {
        "baseline": "docs/baselines/pb-03-direct-port.v1.yaml",
        "schema": "sipi.pb-03-direct-port.v1",
        "report_schema": "sipi.pb-03-direct-replay.v1",
        "fixture": "crates/sipi-pybert-direct/fixtures/pb-03-legacy-nrz.yaml",
        "command": "sim-rust",
    },
    "PB-04": {
        "baseline": "docs/baselines/pb-04-direct-port.v1.yaml",
        "schema": "sipi.pb-04-direct-port.v1",
        "report_schema": "sipi.pb-04-direct-replay.v1",
        "fixture": "crates/sipi-pybert-direct/fixtures/pb-03-legacy-nrz.yaml",
        "command": "sim-auto",
    },
    "PB-05": {
        "baseline": "docs/baselines/pb-05-direct-port.v1.yaml",
        "schema": "sipi.pb-05-direct-port.v1",
        "report_schema": "sipi.pb-05-direct-replay.v1",
        "fixture": "crates/sipi-pybert-direct/fixtures/pb-03-legacy-nrz.yaml",
        "command": "sim-compare",
    },
}


def digest(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def repo_relative(value: Any) -> bool:
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        return False
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts and "." not in path.parts


def check(blockers: list[str], condition: bool, message: str) -> None:
    if not condition:
        blockers.append(message)


def path_free(value: Any) -> bool:
    return PATH_LEAK.search(json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)) is None


def load_json(root: Path, relative: Any, blockers: list[str], label: str) -> tuple[dict[str, Any] | None, str | None]:
    check(blockers, repo_relative(relative), f"{label} path is not repository-relative")
    if not repo_relative(relative):
        return None, None
    path = root / relative
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        blockers.append(f"{label} cannot be loaded: {error}")
        return None, None
    check(blockers, isinstance(value, dict), f"{label} is not an object")
    return value if isinstance(value, dict) else None, digest(path)


def verify_report(row: str, value: dict[str, Any], blockers: list[str], label: str, root: Path = ROOT) -> None:
    spec = ROWS[row]
    check(blockers, value.get("schema") == spec["report_schema"], f"{label} schema drift")
    check(blockers, value.get("row") == row, f"{label} row drift")
    source_mode = value.get("source_mode")
    check(
        blockers,
        source_mode in {"git_archive_at_immutable_commit", "git_archive_plus_lane_working_tree_content_addressed"},
        f"{label} source mode drift",
    )
    check(blockers, isinstance(value.get("fresh_run_nonce"), str) and NONCE.fullmatch(value.get("fresh_run_nonce", "")) is not None, f"{label} nonce malformed")
    candidate = value.get("candidate")
    check(blockers, isinstance(candidate, dict), f"{label} candidate identity missing")
    if isinstance(candidate, dict):
        check(blockers, candidate.get("commit") == CANDIDATE_COMMIT, f"{label} candidate commit drift")
        check(blockers, candidate.get("tree") == CANDIDATE_TREE, f"{label} candidate tree drift")
        check(blockers, isinstance(candidate.get("archive_sha256"), str) and len(candidate["archive_sha256"]) == 64, f"{label} candidate archive identity missing")
        if source_mode == "git_archive_plus_lane_working_tree_content_addressed":
            overlay = candidate.get("working_tree_overlay")
            check(blockers, isinstance(overlay, dict) and bool(overlay), f"{label} content-addressed lane overlay missing")
            if isinstance(overlay, dict):
                for path, value_digest in overlay.items():
                    check(blockers, repo_relative(path), f"{label} lane overlay path is not repository-relative")
                    check(blockers, isinstance(value_digest, str) and re.fullmatch(r"[0-9a-f]{64}", value_digest) is not None, f"{label} lane overlay digest malformed")
    upstream = value.get("upstream")
    check(blockers, isinstance(upstream, dict), f"{label} upstream identity missing")
    if isinstance(upstream, dict):
        check(blockers, upstream.get("commit") == UPSTREAM_COMMIT, f"{label} upstream commit drift")
        check(blockers, upstream.get("tree") == UPSTREAM_TREE, f"{label} upstream tree drift")
        check(blockers, isinstance(upstream.get("archive_sha256"), str) and len(upstream["archive_sha256"]) == 64, f"{label} upstream archive identity missing")
    fixture = value.get("fixture")
    check(blockers, isinstance(fixture, dict) and fixture.get("path") == spec["fixture"], f"{label} fixture shape drift")
    if isinstance(fixture, dict):
        check(blockers, repo_relative(fixture.get("path")), f"{label} fixture path leak")
        check(blockers, isinstance(fixture.get("bytes"), int) and fixture.get("bytes") > 0, f"{label} fixture byte count missing")
        check(blockers, isinstance(fixture.get("sha256"), str) and len(fixture["sha256"]) == 64, f"{label} fixture digest missing")
        fixture_path = root / fixture["path"] if repo_relative(fixture.get("path")) else None
        if fixture_path is not None:
            check(blockers, fixture_path.is_file(), f"{label} fixed corpus is missing")
            if fixture_path.is_file():
                check(blockers, digest(fixture_path) == fixture.get("sha256"), f"{label} fixed corpus digest drift")
                check(blockers, fixture_path.stat().st_size == fixture.get("bytes"), f"{label} fixed corpus byte drift")
    replay = value.get("replay")
    check(blockers, isinstance(replay, dict), f"{label} replay missing")
    if isinstance(replay, dict):
        candidate_process = replay.get("candidate_process")
        oracle_process = replay.get("oracle_process")
        check(blockers, isinstance(candidate_process, dict), f"{label} candidate process missing")
        check(blockers, isinstance(oracle_process, dict), f"{label} oracle process missing")
        payload = replay.get("payload")
        check(blockers, isinstance(payload, dict), f"{label} payload gate missing")
        semantic_gate = replay.get("semantic_gate")
        check(blockers, semantic_gate in {True, False}, f"{label} semantic gate missing")
        if row == "PB-04":
            selection = replay.get("selection")
            candidate_selection = selection.get("candidate") if isinstance(selection, dict) else None
            oracle = selection.get("oracle") if isinstance(selection, dict) else None
            gate = oracle.get("parity_gate") if isinstance(oracle, dict) else None
            candidate_gate = candidate_selection.get("parity_gate") if isinstance(candidate_selection, dict) else None
            check(blockers, isinstance(candidate_selection, dict) and candidate_selection.get("requested") == "auto", f"{label} portable auto requested semantic missing")
            check(blockers, isinstance(candidate_selection, dict) and candidate_selection.get("selected") == "python", f"{label} auto selected semantic drift")
            check(blockers, isinstance(candidate_selection, dict) and candidate_selection.get("implementation") == "external_python_reference_required", f"{label} external reference requirement drift")
            check(blockers, isinstance(candidate_selection, dict) and candidate_selection.get("rust_only") is False, f"{label} rust-only substitution drift")
            check(blockers, isinstance(candidate_gate, dict) and candidate_gate.get("status") == "blocked", f"{label} portable parity gate drift")
            check(blockers, isinstance(oracle, dict) and oracle.get("requested") == "auto", f"{label} auto requested semantic missing")
            check(blockers, isinstance(oracle, dict) and oracle.get("selected") == "python", f"{label} auto selected semantic drift")
            check(blockers, isinstance(gate, dict) and gate.get("status") == "blocked", f"{label} auto parity gate drift")
        if row == "PB-05":
            comparison = replay.get("comparison")
            gate = comparison.get("payload_gate") if isinstance(comparison, dict) else None
            check(blockers, isinstance(gate, dict), f"{label} comparison payload gate missing")
            check(blockers, isinstance(gate, dict) and gate.get("status_only_comparison") is False, f"{label} status-only compare gate")
        status = value.get("status")
        report_blockers = value.get("blockers")
        check(blockers, status in {"passed", "blocked"}, f"{label} status invalid")
        check(blockers, isinstance(report_blockers, list), f"{label} blockers missing")
        if status == "passed":
            check(blockers, report_blockers == [], f"{label} passed with blockers")
            check(blockers, isinstance(candidate_process, dict) and candidate_process.get("exit_code") == 0, f"{label} candidate process gate drift")
            check(blockers, isinstance(oracle_process, dict) and oracle_process.get("exit_code") == 0, f"{label} oracle process gate drift")
            payload_gate = replay.get("payload")
            check(blockers, isinstance(payload_gate, dict) and payload_gate.get("equal") is True, f"{label} payload gate drift")
            fixture = value.get("fixture")
            check(
                blockers,
                isinstance(fixture, dict)
                and (fixture.get("archive_present") is True or fixture.get("working_tree_overlay_present") is True),
                f"{label} fixture source gate drift",
            )
        else:
            check(blockers, bool(report_blockers), f"{label} blocked without a reason")
            if semantic_gate is False:
                check(blockers, "workflow semantic gate failed" in report_blockers, f"{label} semantic blocker is not recorded")
    claims = value.get("claims")
    check(blockers, isinstance(claims, dict), f"{label} claims missing")
    if isinstance(claims, dict):
        check(blockers, claims.get("global_row_closed") is False, f"{label} global closure claim drift")
        check(blockers, claims.get("release_approval") is False, f"{label} release claim drift")
    check(blockers, path_free(value), f"{label} contains an absolute host path")


def verify(document: dict[str, Any], root: Path, row: str) -> dict[str, Any]:
    blockers: list[str] = []
    spec = ROWS[row]
    check(blockers, isinstance(document, dict), "baseline is not an object")
    if not isinstance(document, dict):
        return {"valid": False, "row": row, "blockers": blockers}
    check(blockers, document.get("schema") == spec["schema"], "baseline schema drift")
    check(blockers, document.get("row") == row, "baseline row drift")
    check(blockers, document.get("status") in {"open_blocked", "accepted_scoped_native_core_bound_open"}, "baseline must remain open")
    check(blockers, document.get("claims", {}).get("global_row_closed") is False, "baseline global closure claim drift")
    check(blockers, document.get("claims", {}).get("release_approval") is False, "baseline release claim drift")
    source = document.get("source")
    check(blockers, isinstance(source, dict), "baseline source missing")
    if isinstance(source, dict):
        check(blockers, source.get("upstream_commit") == UPSTREAM_COMMIT, "baseline upstream commit drift")
        check(blockers, source.get("upstream_tree") == UPSTREAM_TREE, "baseline upstream tree drift")
        check(blockers, source.get("candidate_commit") == CANDIDATE_COMMIT, "baseline candidate commit drift")
        check(blockers, source.get("candidate_tree") == CANDIDATE_TREE, "baseline candidate tree drift")
    evidence = document.get("evidence")
    check(blockers, isinstance(evidence, dict), "baseline evidence missing")
    if not isinstance(evidence, dict):
        return {"valid": not blockers, "row": row, "blockers": blockers}
    bindings = evidence.get("reports")
    check(blockers, isinstance(bindings, list) and len(bindings) == 2, "baseline requires two reports")
    loaded: list[dict[str, Any]] = []
    hashes: list[str | None] = []
    if isinstance(bindings, list):
        for index, binding in enumerate(bindings):
            label = f"report-{index + 1}"
            check(blockers, isinstance(binding, dict), f"{label} binding missing")
            if not isinstance(binding, dict):
                continue
            value, actual_hash = load_json(root, binding.get("path"), blockers, label)
            check(blockers, actual_hash == binding.get("sha256"), f"{label} digest drift")
            hashes.append(actual_hash)
            if value is not None:
                verify_report(row, value, blockers, label, root)
                check(blockers, value.get("run_id") == binding.get("run_id"), f"{label} run id drift")
                check(blockers, value.get("fresh_run_nonce") == binding.get("fresh_run_nonce"), f"{label} nonce binding drift")
                loaded.append(value)
    if len(loaded) == 2:
        first, second = loaded
        check(blockers, first.get("run_id") != second.get("run_id"), "run IDs are not independent")
        check(blockers, first.get("fresh_run_nonce") != second.get("fresh_run_nonce"), "fresh nonces are not independent")
        check(blockers, hashes[0] != hashes[1], "report digests are not independent")
        check(blockers, first.get("candidate") == second.get("candidate"), "candidate identity drift")
        check(blockers, first.get("upstream") == second.get("upstream"), "upstream identity drift")
        check(blockers, first.get("fixture") == second.get("fixture"), "fixture identity drift")
        check(blockers, first.get("toolchain") == second.get("toolchain"), "toolchain identity drift")
    aggregate = evidence.get("aggregate")
    aggregate_value, aggregate_hash = load_json(root, aggregate.get("path") if isinstance(aggregate, dict) else None, blockers, "aggregate")
    if isinstance(aggregate, dict):
        check(blockers, aggregate_hash == aggregate.get("sha256"), "aggregate digest drift")
    if aggregate_value is not None:
        check(blockers, aggregate_value.get("schema") == "sipi.pb-direct-replay-aggregate.v1", "aggregate schema drift")
        check(blockers, aggregate_value.get("row") == row, "aggregate row drift")
        check(blockers, aggregate_value.get("status") in {"blocked", "passed"}, "aggregate status invalid")
        check(blockers, isinstance(aggregate_value.get("blockers"), list), "aggregate blockers missing")
        if any(value.get("status") == "blocked" for value in loaded):
            check(blockers, aggregate_value.get("status") == "blocked", "blocked reports cannot produce passed aggregate")
            check(blockers, bool(aggregate_value.get("blockers")), "blocked aggregate has no reason")
        aggregate_reports = aggregate_value.get("reports")
        check(blockers, isinstance(aggregate_reports, list) and len(aggregate_reports) == 2, "aggregate report bindings missing")
        if isinstance(aggregate_reports, list) and isinstance(bindings, list) and len(bindings) == 2:
            for index, binding in enumerate(bindings):
                item = aggregate_reports[index] if index < len(aggregate_reports) else None
                check(blockers, isinstance(item, dict), f"aggregate report {index + 1} missing")
                if isinstance(item, dict) and isinstance(binding, dict):
                    check(blockers, item.get("path") == binding.get("path"), f"aggregate report {index + 1} path drift")
                    check(blockers, item.get("sha256") == binding.get("sha256"), f"aggregate report {index + 1} digest drift")
                    check(blockers, item.get("run_id") == binding.get("run_id"), f"aggregate report {index + 1} run id drift")
                    check(blockers, item.get("fresh_run_nonce") == binding.get("fresh_run_nonce"), f"aggregate report {index + 1} nonce drift")
        if loaded:
            check(blockers, aggregate_value.get("candidate") == loaded[0].get("candidate"), "aggregate candidate identity drift")
            check(blockers, aggregate_value.get("upstream") == loaded[0].get("upstream"), "aggregate upstream identity drift")
            check(blockers, aggregate_value.get("fixture") == loaded[0].get("fixture"), "aggregate fixture identity drift")
            check(blockers, aggregate_value.get("toolchain") == loaded[0].get("toolchain"), "aggregate toolchain identity drift")
        distinct = aggregate_value.get("distinct_gate")
        check(blockers, isinstance(distinct, dict), "aggregate distinct gate missing")
        if isinstance(distinct, dict):
            for key in ("unique_report_paths", "unique_report_sha256", "unique_run_ids", "unique_fresh_run_nonces", "exact_toolchain_identity"):
                check(blockers, distinct.get(key) is True, f"aggregate {key} drift")
        claims = aggregate_value.get("claims")
        check(blockers, isinstance(claims, dict) and claims.get("global_row_closed") is False and claims.get("release_approval") is False, "aggregate claims drift")
        check(blockers, path_free(aggregate_value), "aggregate contains an absolute host path")
    audit = evidence.get("audit")
    check(blockers, repo_relative(audit), "audit path is not repository-relative")
    if repo_relative(audit):
        audit_path = root / audit
        check(blockers, audit_path.is_file(), "audit file is missing")
        expected_audit_sha256 = evidence.get("audit_sha256")
        if expected_audit_sha256 is not None:
            check(blockers, isinstance(expected_audit_sha256, str) and digest(audit_path) == expected_audit_sha256, "audit digest drift")
    check(blockers, path_free(document), "baseline contains an absolute host path")
    return {"valid": not blockers, "row": row, "blockers": blockers}


def main(default_row: str | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--row", choices=sorted(ROWS), default=default_row)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    if args.row is None:
        parser.error("--row is required")
    spec = ROWS[args.row]
    evidence_path = args.evidence or (args.root / spec["baseline"])
    try:
        document = yaml.safe_load(evidence_path.read_text(encoding="utf-8"))
        result = verify(document, args.root.resolve(), args.row)
    except (OSError, ValueError, yaml.YAMLError) as error:
        result = {"valid": False, "row": args.row, "blockers": [str(error)]}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
