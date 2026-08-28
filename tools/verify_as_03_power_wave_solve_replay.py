"""Verify two AS-03 power-wave reports and their aggregate."""

from __future__ import annotations

import argparse
import io
import json
import sys
import tarfile
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aggregate_as_03_power_wave_solve_replay as aggregate_module
import run_as_03_power_wave_solve_replay as replay


def verify_values(first: Any, second: Any, aggregate: Any, first_payload: bytes, second_payload: bytes, first_name: str, second_name: str) -> dict[str, Any]:
    reports = [replay.validate_report(first), replay.validate_report(second)]
    bound = aggregate_module.validate_aggregate(aggregate)
    if reports[0]["run_id"] == reports[1]["run_id"] or reports[0]["nonce"] == reports[1]["nonce"]:
        raise ValueError("report freshness drift")
    if replay._sha256(first_payload) == replay._sha256(second_payload) or first_name.casefold() == second_name.casefold():
        raise ValueError("report physical distinctness drift")
    for index, (report, payload, name) in enumerate(zip(reports, (first_payload, second_payload), (first_name, second_name), strict=True)):
        receipt = bound["reports"][index]
        if receipt != {"basename": name, "path_redacted": True, "bytes": len(payload), "sha256": replay._sha256(payload), "nlink": 1, "run_id": report["run_id"], "nonce": report["nonce"]}:
            raise ValueError("aggregate report receipt drift")
    shared = bound["shared"]
    first = reports[0]
    expected_shared = {
        "prep_commit": first["prep"]["commit"],
        "prep_tree": first["prep"]["tree"],
        "prep_parent": first["prep"]["parent"],
        "candidate_commit": first["candidate"]["commit"],
        "candidate_tree": first["candidate"]["tree"],
        "baseline_path": first["baseline"]["path"],
        "baseline_candidate_commit": first["baseline"]["candidate_commit"],
        "baseline_candidate_tree": first["baseline"]["candidate_tree"],
        "upstream_commit": first["upstream"]["commit"],
        "upstream_tree": first["upstream"]["tree"],
        "scikit_rf_commit": first["scikit_rf"]["commit"],
        "scikit_rf_tree": first["scikit_rf"]["tree"],
        "toolchain": first["toolchain"],
        "fixture_sha256": first["fixture"]["sha256"],
        "baseline_sha256": first["baseline"]["sha256"],
    }
    if shared != expected_shared:
        raise ValueError("aggregate shared projection drift")
    for label in ("prep", "baseline", "upstream", "scikit_rf", "toolchain", "fixture", "numeric_change", "blockers", "claims", "non_claims"):
        if reports[0][label] != reports[1][label]:
            raise ValueError(f"report {label} drift")
    if aggregate_module._candidate_crossrun(reports[0]["candidate"]) != aggregate_module._candidate_crossrun(reports[1]["candidate"]):
        raise ValueError("report candidate immutable-input drift")
    return {"schema": aggregate_module.SCHEMA, "status": "valid", "blocked_numeric_semantics": True, "numeric_parity": False}


def _load(path: Path, root: Path, maximum: int) -> tuple[Any, bytes]:
    resolved = path.resolve(strict=True)
    if resolved.parent != root or replay._is_reparse(path):
        raise ValueError("evidence path must be a direct regular child of evidence root")
    payload = replay._read_regular(resolved, maximum)
    return json.loads(payload.decode("utf-8")), payload


def _archive_receipt(git: Path, repository: Path, commit: str) -> dict[str, Any]:
    payload = replay._git(git, repository, "archive", "--format=tar", commit, raw=True)
    assert isinstance(payload, bytes)
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as archive:
        names: set[str] = set()
        for member in archive.getmembers():
            pure = PurePosixPath(member.name)
            folded = member.name.casefold()
            if not member.name or "\\" in member.name or pure.is_absolute() or ".." in pure.parts or ":" in pure.parts[0] or folded in names or not (member.isdir() or member.isfile()) or member.issym() or member.islnk():
                raise ValueError("unsafe archive member during verification")
            names.add(folded)
    return {"bytes": len(payload), "sha256": replay._sha256(payload), "links_rejected": True, "overlay": False}


def verify_files(repository: Path, upstream_repository: Path, skrf_repository: Path, prep_commit: str, evidence_root: Path, first_path: Path, second_path: Path, aggregate_path: Path, git_value: str, temp_root: Path) -> dict[str, Any]:
    root = replay._safe_directory(evidence_root)
    paths = [path.resolve(strict=True) for path in (first_path, second_path, aggregate_path)]
    if len(set(paths)) != 3:
        raise ValueError("evidence paths must be distinct")
    first, first_payload = _load(paths[0], root, replay.MAX_REPORT_BYTES)
    second, second_payload = _load(paths[1], root, replay.MAX_REPORT_BYTES)
    aggregate, _ = _load(paths[2], root, replay.MAX_REPORT_BYTES)
    result = verify_values(first, second, aggregate, first_payload, second_payload, paths[0].name, paths[1].name)
    recomputed = aggregate_module.aggregate(paths[0], paths[1], root)
    if recomputed != aggregate:
        raise ValueError("aggregate does not equal mechanical report projection")
    repo = replay._safe_directory(repository)
    upstream_repo = replay._safe_directory(upstream_repository)
    skrf_repo = replay._safe_directory(skrf_repository)
    verifier_temp = replay._safe_directory(temp_root)
    replay._require_disjoint_roots({"repository": repo, "agent_spice": upstream_repo, "scikit_rf": skrf_repo, "evidence": root, "temp": verifier_temp})
    work = replay._fresh_child(verifier_temp, "as03-verify")
    source_git = replay._resolve_tool(git_value, "git")
    git = replay._stage_tool(source_git, "git", work)
    git_pre = replay._tool_snapshot(source_git, git, "git", ("--version",))
    prep = replay._prep_gate(git, repo, prep_commit)
    if first["prep"]["commit"] != prep["commit"] or first["prep"]["tree"] != prep["tree"]:
        raise ValueError("prep commit binding drift")
    binding = replay._source_binding(git, repo, prep["commit"], replay.PREP_PATHS, repo)
    if binding["git"] != first["prep"]["sources"] or binding["live"] != first["prep"]["live_pre"]:
        raise ValueError("prep raw Git/live binding drift")
    candidate = replay._repo_identity(git, repo, replay.PRODUCTION_COMMIT, replay.PRODUCTION_TREE)
    candidate_sources = replay._source_binding(git, repo, candidate["commit"], replay.PRODUCTION_PATHS, repo)
    if candidate_sources["git"] != first["candidate"]["sources"] or candidate_sources["live"] != first["candidate"]["live_pre"] or _archive_receipt(git, repo, candidate["commit"]) != first["candidate"]["archive"]:
        raise ValueError("candidate Git/archive/live binding drift")
    asserted = replay._candidate_real_assertions(replay._git_blob(git, repo, candidate["commit"], replay.SOURCE_PATH))
    if asserted != first["numeric_change"]["current"]["committed_asserted_real_bits"]:
        raise ValueError("candidate committed runtime assertion binding drift")
    baseline = replay._git_receipt(git, repo, candidate["commit"], replay.BASELINE_PATH)
    if any(first["baseline"][key] != baseline[key] for key in ("path", "git_blob", "bytes", "sha256")):
        raise ValueError("baseline raw Git binding drift")
    for label, source_repo, commit, tree, source_paths in (
        ("upstream", upstream_repo, replay.UPSTREAM_COMMIT, replay.UPSTREAM_TREE, replay.UPSTREAM_PATHS),
        ("scikit_rf", skrf_repo, replay.SKRF_COMMIT, replay.SKRF_TREE, replay.SKRF_PATHS),
    ):
        identity = replay._repo_identity(git, source_repo, commit, tree)
        sources = replay._source_binding(git, source_repo, identity["commit"], source_paths)["git"]
        if sources != first[label]["sources"] or _archive_receipt(git, source_repo, identity["commit"]) != first[label]["archive"]:
            raise ValueError(f"{label} Git/archive binding drift")
    if replay._tool_snapshot(source_git, git, "git", ("--version",)) != git_pre:
        raise ValueError("verifier Git source/copy drift")
    replay._remove_fresh_tree(work, verifier_temp)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default=str(replay.ROOT))
    parser.add_argument("--upstream-repository", default=str(replay.ROOT.parent / "agent-spice"))
    parser.add_argument("--scikit-rf-repository", required=True)
    parser.add_argument("--prep-commit", required=True)
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--first", required=True)
    parser.add_argument("--second", required=True)
    parser.add_argument("--aggregate", required=True)
    parser.add_argument("--temp-root", required=True)
    parser.add_argument("--git", default="git")
    args = parser.parse_args()
    try:
        result = verify_files(Path(args.repository), Path(args.upstream_repository), Path(args.scikit_rf_repository), args.prep_commit, Path(args.evidence_root), Path(args.first), Path(args.second), Path(args.aggregate), args.git, Path(args.temp_root))
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"AS-03 verifier blocked: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
