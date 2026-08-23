"""Fail-closed verifier for PB-01..PB-05 immutable current-bound evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_COMMIT = "64b783f66d7e986d0975be5ac3946b453b15c4ed"
CANDIDATE_TREE = "0e11721f2bb5b564002820cc7a5aaab45e30ba3b"
UPSTREAM_COMMIT = "5bf6d7ea0ace261891aaeb611ffc1c267e160afe"
UPSTREAM_TREE = "5faef6bdb341d444ad65d82a11c0018b15805e24"
HEX64 = re.compile(r"[0-9a-f]{32,64}\Z")
PATH_LEAK = re.compile(r"(?:[A-Za-z]:[\\/]|(?:^|[^A-Za-z0-9])/(?:Users|home|tmp|var/tmp)/|\\(?:Users|Temp)\\)")
ROWS = {
    "PB-01": {"report_schema": "sipi.pb-01-legacy-leaf-replay.v1", "fixture": "crates/sipi-pybert-direct/fixtures/pb-01-legacy-nrz.yaml"},
    "PB-02": {"report_schema": "sipi.pb-02-direct-replay.v1", "fixture": "crates/sipi-pybert-direct/fixtures/pb-02-nrz.json"},
    "PB-03": {"report_schema": "sipi.pb-03-direct-replay.v1", "fixture": "crates/sipi-pybert-direct/fixtures/pb-03-legacy-nrz.yaml"},
    "PB-04": {"report_schema": "sipi.pb-04-direct-replay.v1", "fixture": "crates/sipi-pybert-direct/fixtures/pb-03-legacy-nrz.yaml"},
    "PB-05": {"report_schema": "sipi.pb-05-direct-replay.v1", "fixture": "crates/sipi-pybert-direct/fixtures/pb-03-legacy-nrz.yaml"},
}


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def file_sha256(path: Path) -> str | None:
    try:
        return sha256(path.read_bytes())
    except OSError:
        return None


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def check(blockers: list[str], condition: bool, message: str) -> None:
    if not condition:
        blockers.append(message)


def has_overlay_claim(value: Any) -> bool:
    """Reject every worktree-overlay field or textual claim in evidence."""
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = str(key).lower()
            if "overlay" in normalized_key or "working_tree" in normalized_key:
                return True
            if has_overlay_claim(item):
                return True
        return False
    if isinstance(value, list):
        return any(has_overlay_claim(item) for item in value)
    if isinstance(value, str):
        normalized = value.lower()
        return "overlay" in normalized or "working_tree" in normalized
    return False


def load_json(root: Path, relative: Any, blockers: list[str], label: str) -> tuple[dict[str, Any] | None, str | None]:
    check(blockers, isinstance(relative, str) and ".." not in Path(relative).parts and not Path(relative).is_absolute(), f"{label} path invalid")
    if not isinstance(relative, str):
        return None, None
    path = root / relative
    try:
        payload = path.read_bytes()
        value = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        blockers.append(f"{label} cannot be loaded: {error}")
        return None, None
    check(blockers, isinstance(value, dict), f"{label} is not an object")
    return value if isinstance(value, dict) else None, sha256(payload)


def archive_lane_inventory(commit: str) -> str | None:
    try:
        paths = subprocess.run(["git", "-C", str(ROOT), "ls-tree", "-r", "--name-only", commit, "--", "crates/sipi-pybert-direct"], check=True, capture_output=True, text=True).stdout.splitlines()
        entries = []
        for path in paths:
            payload = subprocess.run(["git", "-C", str(ROOT), "show", f"{commit}:{path}"], check=True, capture_output=True).stdout
            entries.append({"path": path, "bytes": len(payload), "sha256": sha256(payload)})
        return sha256(canonical(entries))
    except (OSError, subprocess.CalledProcessError):
        return None


def verify_report(row: str, report: dict[str, Any], expected: dict[str, Any], blockers: list[str], label: str) -> None:
    spec = ROWS[row]
    check(blockers, not has_overlay_claim(report), f"{label} worktree overlay claim present")
    check(blockers, report.get("schema") == spec["report_schema"], f"{label} schema drift")
    check(blockers, report.get("source_mode") == "git_archive_at_immutable_commit", f"{label} source mode drift")
    check(blockers, isinstance(report.get("fresh_run_nonce"), str) and HEX64.fullmatch(report.get("fresh_run_nonce", "")) is not None, f"{label} nonce malformed")
    candidate = report.get("candidate")
    upstream = report.get("upstream")
    check(blockers, isinstance(candidate, dict), f"{label} candidate identity missing")
    check(blockers, isinstance(upstream, dict), f"{label} upstream identity missing")
    if isinstance(candidate, dict):
        check(blockers, candidate.get("commit") == CANDIDATE_COMMIT, f"{label} candidate commit drift")
        check(blockers, candidate.get("tree") == CANDIDATE_TREE, f"{label} candidate tree drift")
        check(blockers, candidate.get("archive_sha256") == expected["candidate_archive_sha256"], f"{label} candidate archive drift")
    if isinstance(upstream, dict):
        check(blockers, upstream.get("commit") == UPSTREAM_COMMIT, f"{label} upstream commit drift")
        check(blockers, upstream.get("tree") == UPSTREAM_TREE, f"{label} upstream tree drift")
        check(blockers, upstream.get("archive_sha256") == expected["upstream_archive_sha256"], f"{label} upstream archive drift")
    fixture = report.get("fixture")
    check(blockers, isinstance(fixture, dict), f"{label} fixture missing")
    if isinstance(fixture, dict):
        check(blockers, fixture.get("path") == expected["fixture_path"], f"{label} fixture path drift")
        check(blockers, fixture.get("sha256") == expected["fixture_sha256"], f"{label} fixture digest drift")
        check(blockers, fixture.get("archive_present") is True, f"{label} fixture is not present in candidate archive")
    check(blockers, isinstance(report.get("toolchain"), dict) and sha256(canonical(report["toolchain"])) == expected["toolchain_sha256"], f"{label} toolchain drift")
    replay = report.get("replay") or {}
    if row == "PB-01":
        comparison = replay.get("comparison") or {}
        check(blockers, comparison.get("status") == "blocked", f"{label} PB-01 actual replay status drift")
        check(blockers, any("tx_out_p" in str(item) for item in comparison.get("blockers", [])), f"{label} PB-01 mismatch evidence missing")
    elif row == "PB-02":
        parity = replay.get("parity") or {}
        check(blockers, parity.get("candidate_exit_zero") is True and parity.get("oracle_exit_zero") is True, f"{label} PB-02 process gate drift")
        check(blockers, parity.get("candidate_array_members_equal_oracle") is False, f"{label} PB-02 payload blocker drift")
    elif row == "PB-03":
        check(blockers, report.get("status") == "passed" and replay.get("semantic_gate") is True, f"{label} PB-03 pass gate drift")
        check(blockers, (replay.get("payload") or {}).get("equal") is True, f"{label} PB-03 payload drift")
    elif row == "PB-04":
        selection = (replay.get("selection") or {}).get("candidate") or {}
        check(blockers, replay.get("semantic_gate") is True, f"{label} PB-04 semantic gate drift")
        check(blockers, selection.get("selected") == "python" and selection.get("implementation") == "external_python_reference_required" and selection.get("rust_only") is False, f"{label} PB-04 Python fallback drift")
    elif row == "PB-05":
        comparison = (replay.get("comparison") or {}).get("candidate") or {}
        check(blockers, replay.get("semantic_gate") is True, f"{label} PB-05 semantic gate drift")
        check(blockers, comparison.get("reason") == "not_evaluated" and comparison.get("reference_required") == "external_python_reference_required" and comparison.get("status_only_comparison") is False, f"{label} PB-05 reference gate drift")
    check(blockers, PATH_LEAK.search(json.dumps(report, ensure_ascii=True, sort_keys=True)) is None, f"{label} path leak")


def verify(document: dict[str, Any], root: Path = ROOT) -> dict[str, Any]:
    blockers: list[str] = []
    row = document.get("row") if isinstance(document, dict) else None
    check(blockers, row in ROWS, "row missing or invalid")
    if row not in ROWS:
        return {"valid": False, "blockers": blockers}
    check(blockers, document.get("schema") == f"sipi.{row.lower()}-current-bound.v1", "manifest schema drift")
    source = document.get("source")
    check(blockers, isinstance(source, dict), "source binding missing")
    expected = source if isinstance(source, dict) else {}
    check(blockers, expected.get("candidate_commit") == CANDIDATE_COMMIT and expected.get("candidate_tree") == CANDIDATE_TREE, "candidate identity drift")
    check(blockers, expected.get("upstream_commit") == UPSTREAM_COMMIT and expected.get("upstream_tree") == UPSTREAM_TREE, "upstream identity drift")
    check(blockers, expected.get("candidate_archive_sha256") == "c89bc44b36849724b9544eb6222a6431ecd3855ce4c943e6a3845cafe19375b9", "candidate archive binding drift")
    check(blockers, expected.get("upstream_archive_sha256") == "e6ed484e87712e7120ea4314f21ae74386443ca90c6fe5f0bcfdbf1d99ebeb25", "upstream archive binding drift")
    check(blockers, expected.get("lane_inventory_sha256") == archive_lane_inventory(CANDIDATE_COMMIT), "lane inventory drift")
    fixture = document.get("fixture")
    check(blockers, isinstance(fixture, dict) and fixture.get("path") == ROWS[row]["fixture"], "manifest fixture binding drift")
    if isinstance(fixture, dict):
        check(blockers, file_sha256(root / fixture["path"]) == fixture.get("sha256"), "manifest fixture digest drift")
    expected["fixture_path"] = fixture.get("path") if isinstance(fixture, dict) else None
    expected["fixture_sha256"] = fixture.get("sha256") if isinstance(fixture, dict) else None
    expected["toolchain_sha256"] = document.get("toolchain_sha256")
    harness = document.get("harness")
    check(blockers, isinstance(harness, dict), "harness binding missing")
    if isinstance(harness, dict):
        for key in ("runner", "aggregate", "verifier"):
            item = harness.get(key)
            check(blockers, isinstance(item, dict) and file_sha256(root / item.get("path", "")) == item.get("sha256"), f"harness {key} drift")
        helper = harness.get("helper")
        check(blockers, isinstance(helper, dict) and file_sha256(root / helper.get("path", "")) == helper.get("sha256"), "harness helper drift")
    evidence = document.get("evidence")
    check(blockers, isinstance(evidence, dict), "evidence binding missing")
    reports = evidence.get("reports") if isinstance(evidence, dict) else None
    loaded: list[dict[str, Any]] = []
    if isinstance(reports, list) and len(reports) == 2:
        for index, binding in enumerate(reports):
            label = f"report-{index + 1}"
            check(blockers, isinstance(binding, dict), f"{label} binding missing")
            if not isinstance(binding, dict):
                continue
            report, actual = load_json(root, binding.get("path"), blockers, label)
            check(blockers, actual == binding.get("sha256"), f"{label} digest binding drift")
            if report is not None:
                verify_report(row, report, expected, blockers, label)
                check(blockers, report.get("run_id") == binding.get("run_id"), f"{label} run id drift")
                check(blockers, report.get("fresh_run_nonce") == binding.get("fresh_run_nonce"), f"{label} nonce binding drift")
                loaded.append(report)
    else:
        blockers.append("exactly two report bindings are required")
    if len(loaded) == 2:
        check(blockers, loaded[0].get("run_id") != loaded[1].get("run_id"), "report run ids are not independent")
        check(blockers, loaded[0].get("fresh_run_nonce") != loaded[1].get("fresh_run_nonce"), "report nonces are not independent")
        check(blockers, loaded[0].get("toolchain") == loaded[1].get("toolchain"), "report toolchains drift")
    aggregate = evidence.get("aggregate") if isinstance(evidence, dict) else None
    aggregate_value, aggregate_hash = load_json(root, aggregate.get("path") if isinstance(aggregate, dict) else None, blockers, "aggregate")
    if isinstance(aggregate, dict):
        check(blockers, aggregate_hash == aggregate.get("sha256"), "aggregate digest binding drift")
    if aggregate_value is not None:
        check(blockers, not has_overlay_claim(aggregate_value), "aggregate worktree overlay claim present")
        check(blockers, aggregate_value.get("schema") == "sipi.pb-current-bound-replay-aggregate.v1", "aggregate schema drift")
        check(blockers, aggregate_value.get("row") == row, "aggregate row drift")
        check(blockers, aggregate_value.get("candidate") == loaded[0].get("candidate") if loaded else False, "aggregate candidate drift")
        check(blockers, aggregate_value.get("upstream") == loaded[0].get("upstream") if loaded else False, "aggregate upstream drift")
        check(blockers, aggregate_value.get("fixture") == loaded[0].get("fixture") if loaded else False, "aggregate fixture drift")
        check(blockers, aggregate_value.get("toolchain") == loaded[0].get("toolchain") if loaded else False, "aggregate toolchain drift")
        check(blockers, isinstance(aggregate_value.get("blockers"), list), "aggregate blockers missing")
        check(blockers, PATH_LEAK.search(json.dumps(aggregate_value, ensure_ascii=True, sort_keys=True)) is None, "aggregate path leak")
    audit = document.get("audit")
    check(blockers, isinstance(audit, dict) and file_sha256(root / audit.get("path", "")) == audit.get("sha256"), "audit binding drift")
    return {"valid": not blockers, "row": row, "blockers": blockers}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        result = verify(yaml.safe_load(args.evidence.read_text(encoding="utf-8")), args.root.resolve())
    except (OSError, ValueError, yaml.YAMLError) as error:
        result = {"valid": False, "blockers": [str(error)]}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
