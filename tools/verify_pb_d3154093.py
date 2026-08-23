"""Fail-closed verifier for the additive d3154093 PB-01/PB-02 evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_COMMIT = "d3154093fd58aeaa596444825dc17be6cb7e35c0"
CANDIDATE_TREE = "2d51e84554558bb4947c0152259af9bf7f927efe"
CANDIDATE_ARCHIVE = "693c95330b36f0a8068db3ce9a44bf4d45bfd1b73f47189d8149d67cfd909a24"
CANDIDATE_LANE = "ea550701da812ed7c9952f034202e7285f9d3ba38f933536d41bf9d2b5e9dce6"
UPSTREAM_COMMIT = "5bf6d7ea0ace261891aaeb611ffc1c267e160afe"
UPSTREAM_TREE = "5faef6bdb341d444ad65d82a11c0018b15805e24"
UPSTREAM_ARCHIVE = "e6ed484e87712e7120ea4314f21ae74386443ca90c6fe5f0bcfdbf1d99ebeb25"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
PATH_LEAK = re.compile(r"(?:[A-Za-z]:[\\/]|(?:^|[^A-Za-z0-9])/(?:Users|home|tmp|var/tmp)/|\\(?:Users|Temp)\\)")
ROWS = {
    "PB-01": {
        "schema": "sipi.pb-01-legacy-leaf-replay.v1",
        "manifest_schema": "sipi.pb-01-current-d3154093.v1",
        "fixture": "crates/sipi-pybert-direct/fixtures/pb-01-legacy-nrz.yaml",
        "report_prefix": "pb-01-legacy-leaf-current-d3154093",
        "arrays": [
            "chnl_h",
            "tx_out_h",
            "ctle_out_h",
            "dfe_out_h",
            "chnl_s",
            "tx_out_s",
            "ctle_out_s",
            "dfe_out_s",
            "chnl_p",
            "tx_out_p",
            "ctle_out_p",
            "dfe_out_p",
        ],
    },
    "PB-02": {
        "schema": "sipi.pb-02-direct-replay.v1",
        "manifest_schema": "sipi.pb-02-current-d3154093.v1",
        "fixture": "crates/sipi-pybert-direct/fixtures/pb-02-nrz.json",
        "report_prefix": "pb-02-direct-current-d3154093",
        "arrays": [
            "channel_impulse_v_per_v.npy",
            "channel_output_v.npy",
            "ctle_output_v.npy",
            "rx_ffe_impulse_v_per_v.npy",
            "rx_filter_impulse_v_per_v.npy",
            "rx_input_v.npy",
            "rx_output_v.npy",
            "symbols_v.npy",
            "time_s.npy",
            "tx_channel_impulse_v_per_v.npy",
            "tx_waveform_v.npy",
        ],
    },
}


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def file_sha256(path: Path) -> str | None:
    try:
        return sha256(path.read_bytes())
    except OSError:
        return None


def check(blockers: list[str], condition: bool, message: str) -> None:
    if not condition:
        blockers.append(message)


def has_forbidden_claim(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            "overlay" in str(key).lower()
            or "working_tree" in str(key).lower()
            or has_forbidden_claim(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(has_forbidden_claim(item) for item in value)
    return isinstance(value, str) and ("overlay" in value.lower() or "working_tree" in value.lower())


def safe_relative(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts and not PATH_LEAK.search(value)


def load_json(root: Path, binding: Any, blockers: list[str], label: str) -> tuple[dict[str, Any] | None, str | None]:
    check(blockers, isinstance(binding, dict), f"{label} binding missing")
    if not isinstance(binding, dict):
        return None, None
    relative = binding.get("path")
    check(blockers, safe_relative(relative), f"{label} path is not repository-relative")
    if not safe_relative(relative):
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


def verify_report(row: str, report: dict[str, Any], expected: dict[str, Any], blockers: list[str], label: str) -> None:
    spec = ROWS[row]
    check(blockers, not has_forbidden_claim(report), f"{label} contains an overlay claim")
    check(blockers, PATH_LEAK.search(json.dumps(report, ensure_ascii=True, sort_keys=True)) is None, f"{label} contains an absolute path")
    check(blockers, report.get("schema") == spec["schema"], f"{label} schema drift")
    check(blockers, report.get("source_mode") == "git_archive_at_immutable_commit", f"{label} source mode drift")
    check(blockers, report.get("status") == "passed", f"{label} replay status drift")
    nonce = report.get("fresh_run_nonce")
    check(blockers, isinstance(nonce, str) and HEX64.fullmatch(nonce) is not None, f"{label} nonce malformed")
    candidate = report.get("candidate")
    upstream = report.get("upstream")
    check(blockers, isinstance(candidate, dict), f"{label} candidate binding missing")
    check(blockers, isinstance(upstream, dict), f"{label} upstream binding missing")
    if isinstance(candidate, dict):
        check(blockers, candidate.get("commit") == CANDIDATE_COMMIT, f"{label} candidate commit drift")
        check(blockers, candidate.get("tree") == CANDIDATE_TREE, f"{label} candidate tree drift")
        check(blockers, candidate.get("archive_sha256") == CANDIDATE_ARCHIVE, f"{label} candidate archive drift")
        check(blockers, candidate.get("inventory", {}).get("sha256") == CANDIDATE_LANE, f"{label} candidate lane inventory drift")
    if isinstance(upstream, dict):
        check(blockers, upstream.get("commit") == UPSTREAM_COMMIT, f"{label} upstream commit drift")
        check(blockers, upstream.get("tree") == UPSTREAM_TREE, f"{label} upstream tree drift")
        check(blockers, upstream.get("archive_sha256") == UPSTREAM_ARCHIVE, f"{label} upstream archive drift")
    fixture = report.get("fixture")
    check(blockers, isinstance(fixture, dict), f"{label} fixture binding missing")
    if isinstance(fixture, dict):
        check(blockers, fixture.get("path") == spec["fixture"], f"{label} fixture path drift")
        check(blockers, fixture.get("archive_present") is True, f"{label} fixture archive presence drift")
        check(blockers, fixture.get("sha256") == expected.get("fixture_sha256"), f"{label} fixture digest drift")
    check(blockers, isinstance(report.get("toolchain"), dict), f"{label} toolchain missing")
    check(blockers, sha256(canonical(report.get("toolchain"))) == expected.get("toolchain_sha256"), f"{label} toolchain drift")
    replay = report.get("replay") if isinstance(report.get("replay"), dict) else {}
    if row == "PB-01":
        comparison = replay.get("comparison") if isinstance(replay.get("comparison"), dict) else {}
        arrays = comparison.get("arrays") if isinstance(comparison.get("arrays"), list) else []
        check(blockers, comparison.get("status") == "passed", f"{label} PB-01 comparison status drift")
        check(blockers, comparison.get("blockers") == [], f"{label} PB-01 comparison blockers drift")
        check(blockers, [item.get("name") for item in arrays] == spec["arrays"], f"{label} PB-01 12-array inventory drift")
        check(blockers, all(item.get("passed") is True for item in arrays), f"{label} PB-01 array parity drift")
    else:
        parity = replay.get("parity") if isinstance(replay.get("parity"), dict) else {}
        check(blockers, parity.get("candidate_exit_zero") is True, f"{label} PB-02 candidate exit drift")
        check(blockers, parity.get("oracle_exit_zero") is True, f"{label} PB-02 oracle exit drift")
        check(blockers, parity.get("candidate_array_members_equal_oracle") is True, f"{label} PB-02 payload parity drift")
        check(blockers, parity.get("array_member_names") == spec["arrays"], f"{label} PB-02 11-member inventory drift")


def verify(document: dict[str, Any], root: Path = ROOT) -> dict[str, Any]:
    blockers: list[str] = []
    check(blockers, isinstance(document, dict), "manifest is not an object")
    if not isinstance(document, dict):
        return {"valid": False, "blockers": blockers}
    row = document.get("row")
    check(blockers, row in ROWS, "row missing or unsupported")
    if row not in ROWS:
        return {"valid": False, "row": row, "blockers": blockers}
    spec = ROWS[row]
    check(blockers, document.get("schema") == spec["manifest_schema"], "manifest schema drift")
    check(blockers, document.get("status") == "passed_replay_open", "manifest status must remain replay-open")
    check(blockers, not has_forbidden_claim(document), "manifest contains an overlay claim")
    check(blockers, PATH_LEAK.search(json.dumps(document, ensure_ascii=True, sort_keys=True)) is None, "manifest contains an absolute path")

    source = document.get("source")
    check(blockers, isinstance(source, dict), "source binding missing")
    if isinstance(source, dict):
        check(blockers, source.get("candidate_commit") == CANDIDATE_COMMIT, "candidate commit drift")
        check(blockers, source.get("candidate_tree") == CANDIDATE_TREE, "candidate tree drift")
        check(blockers, source.get("candidate_archive_sha256") == CANDIDATE_ARCHIVE, "candidate archive drift")
        check(blockers, source.get("lane_inventory_sha256") == CANDIDATE_LANE, "lane inventory drift")
        check(blockers, source.get("upstream_commit") == UPSTREAM_COMMIT, "upstream commit drift")
        check(blockers, source.get("upstream_tree") == UPSTREAM_TREE, "upstream tree drift")
        check(blockers, source.get("upstream_archive_sha256") == UPSTREAM_ARCHIVE, "upstream archive drift")

    fixture = document.get("fixture")
    check(blockers, isinstance(fixture, dict), "manifest fixture binding missing")
    fixture_path = fixture.get("path") if isinstance(fixture, dict) else None
    fixture_sha = fixture.get("sha256") if isinstance(fixture, dict) else None
    check(blockers, safe_relative(fixture_path) and fixture_path == spec["fixture"], "manifest fixture path drift")
    if safe_relative(fixture_path):
        check(blockers, file_sha256(root / fixture_path) == fixture_sha, "manifest fixture digest drift")

    toolchain_sha = document.get("toolchain_sha256")
    check(blockers, isinstance(toolchain_sha, str) and HEX64.fullmatch(toolchain_sha) is not None, "toolchain binding malformed")
    harness = document.get("harness")
    check(blockers, isinstance(harness, dict), "harness binding missing")
    if isinstance(harness, dict):
        for key in ("runner", "helper", "aggregate", "verifier", "mutation_tests"):
            item = harness.get(key)
            check(blockers, isinstance(item, dict), f"harness {key} binding missing")
            if isinstance(item, dict) and safe_relative(item.get("path")):
                check(blockers, file_sha256(root / item["path"]) == item.get("sha256"), f"harness {key} digest drift")

    evidence = document.get("evidence")
    check(blockers, isinstance(evidence, dict), "evidence binding missing")
    reports = evidence.get("reports") if isinstance(evidence, dict) else None
    loaded: list[dict[str, Any]] = []
    if isinstance(reports, list) and len(reports) == 2:
        for index, binding in enumerate(reports):
            report, actual = load_json(root, binding, blockers, f"report-{index + 1}")
            if isinstance(binding, dict):
                check(blockers, actual == binding.get("sha256"), f"report-{index + 1} digest drift")
            if report is not None:
                expected = {
                    "fixture_sha256": fixture_sha,
                    "toolchain_sha256": toolchain_sha,
                }
                verify_report(row, report, expected, blockers, f"report-{index + 1}")
                if isinstance(binding, dict):
                    check(blockers, report.get("run_id") == binding.get("run_id"), f"report-{index + 1} run id drift")
                    check(blockers, report.get("fresh_run_nonce") == binding.get("fresh_run_nonce"), f"report-{index + 1} nonce drift")
                loaded.append(report)
    else:
        blockers.append("exactly two report bindings are required")
    if len(loaded) == 2:
        check(blockers, loaded[0].get("run_id") != loaded[1].get("run_id"), "replay run ids are not independent")
        check(blockers, loaded[0].get("fresh_run_nonce") != loaded[1].get("fresh_run_nonce"), "replay nonces are not independent")
        check(blockers, loaded[0].get("candidate") == loaded[1].get("candidate"), "candidate identity drift across replays")
        check(blockers, loaded[0].get("upstream") == loaded[1].get("upstream"), "upstream identity drift across replays")
        check(blockers, loaded[0].get("fixture") == loaded[1].get("fixture"), "fixture identity drift across replays")
        check(blockers, loaded[0].get("toolchain") == loaded[1].get("toolchain"), "toolchain drift across replays")

    aggregate_binding = evidence.get("aggregate") if isinstance(evidence, dict) else None
    aggregate, aggregate_hash = load_json(root, aggregate_binding, blockers, "aggregate")
    if isinstance(aggregate_binding, dict):
        check(blockers, aggregate_hash == aggregate_binding.get("sha256"), "aggregate digest drift")
    if aggregate is not None:
        check(blockers, not has_forbidden_claim(aggregate), "aggregate contains an overlay claim")
        check(blockers, aggregate.get("schema") == "sipi.pb-current-d3154093-replay-aggregate.v1", "aggregate schema drift")
        check(blockers, aggregate.get("row") == row, "aggregate row drift")
        check(blockers, aggregate.get("status") == "passed_replay_open", "aggregate status drift")
        check(blockers, aggregate.get("candidate") == (loaded[0].get("candidate") if loaded else None), "aggregate candidate drift")
        check(blockers, aggregate.get("upstream") == (loaded[0].get("upstream") if loaded else None), "aggregate upstream drift")
        check(blockers, aggregate.get("fixture") == (loaded[0].get("fixture") if loaded else None), "aggregate fixture drift")
        check(blockers, aggregate.get("toolchain") == (loaded[0].get("toolchain") if loaded else None), "aggregate toolchain drift")
        check(blockers, aggregate.get("claims", {}).get("fixture_payload_parity") is True, "aggregate payload claim drift")
        check(blockers, aggregate.get("claims", {}).get("global_row_closed") is False, "aggregate global closure drift")
        check(blockers, aggregate.get("claims", {}).get("promotion") is False, "aggregate promotion drift")
        if loaded:
            expected_reports = []
            for binding in reports:
                expected_reports.append({key: binding[key] for key in ("path", "sha256", "run_id", "fresh_run_nonce")})
            check(blockers, aggregate.get("reports") == expected_reports, "aggregate report binding drift")
        payload = aggregate.get("payload") if isinstance(aggregate.get("payload"), dict) else {}
        key = "array_names" if row == "PB-01" else "array_member_names"
        check(blockers, payload.get(key) == spec["arrays"], "aggregate payload inventory drift")
    audit = document.get("audit")
    check(blockers, isinstance(audit, dict), "audit binding missing")
    if isinstance(audit, dict) and safe_relative(audit.get("path")):
        check(blockers, file_sha256(root / audit["path"]) == audit.get("sha256"), "audit digest drift")

    claims = document.get("claims") if isinstance(document.get("claims"), dict) else {}
    check(blockers, claims.get("fixture_payload_parity") is True, "manifest payload claim drift")
    check(blockers, claims.get("global_row_closed") is False, "manifest global closure drift")
    check(blockers, claims.get("promotion") is False, "manifest promotion drift")
    check(blockers, claims.get("independent_branch_oracle_complete") is False, "manifest branch closure drift")
    return {"valid": not blockers, "row": row, "blockers": blockers}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        document = yaml.safe_load(args.evidence.read_text(encoding="utf-8"))
        result = verify(document, args.root.resolve())
    except (OSError, UnicodeDecodeError, yaml.YAMLError, ValueError) as error:
        result = {"valid": False, "blockers": [str(error)]}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("valid") else 1


if __name__ == "__main__":
    raise SystemExit(main())
