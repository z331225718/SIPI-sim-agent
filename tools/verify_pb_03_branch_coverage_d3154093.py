"""Verify the additive PB-03 portable branch probe for candidate d3154093."""

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
MATRIX = ROOT / "docs/baselines/pb-03-legacy-branch-coverage-d3154093.v1.yaml"
CANDIDATE_COMMIT = "d3154093fd58aeaa596444825dc17be6cb7e35c0"
CANDIDATE_TREE = "2d51e84554558bb4947c0152259af9bf7f927efe"
UPSTREAM_COMMIT = "5bf6d7ea0ace261891aaeb611ffc1c267e160afe"
UPSTREAM_TREE = "5faef6bdb341d444ad65d82a11c0018b15805e24"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
PATH_LEAK = re.compile(r"(?:[A-Za-z]:[\\/]|(?:^|[^A-Za-z0-9])/(?:Users|home|tmp|var/tmp)/|\\(?:Users|Temp)\\)")
ALLOWED_STATUSES = {"exercised", "external_blocked", "implemented_blocked"}


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def check(errors: list[str], condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


def forbidden_claim(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            "overlay" in str(key).lower()
            or "working_tree" in str(key).lower()
            or forbidden_claim(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(forbidden_claim(item) for item in value)
    return isinstance(value, str) and ("overlay" in value.lower() or "working_tree" in value.lower())


def git_sha(root: Path, path: str) -> str | None:
    try:
        payload = subprocess.run(
            ["git", "-C", str(root), "show", f"{CANDIDATE_COMMIT}:{path}"],
            check=True,
            capture_output=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    return sha256(payload)


def verify(document: dict[str, Any], root: Path = ROOT) -> dict[str, Any]:
    errors: list[str] = []
    check(errors, isinstance(document, dict), "matrix is not an object")
    if not isinstance(document, dict):
        return {"valid": False, "errors": errors}
    check(errors, document.get("schema") == "sipi.pb-03-legacy-branch-coverage-d3154093.v1", "schema mismatch")
    check(errors, document.get("row") == "PB-03", "row mismatch")
    check(errors, document.get("status") == "branch_probe_open", "status must remain branch_probe_open")
    check(errors, not forbidden_claim(document), "forbidden source claim present")
    check(errors, PATH_LEAK.search(json.dumps(document, ensure_ascii=True, sort_keys=True)) is None, "absolute path present")
    source = document.get("source")
    check(errors, isinstance(source, dict), "source binding missing")
    if isinstance(source, dict):
        check(errors, source.get("candidate_commit") == CANDIDATE_COMMIT, "candidate commit mismatch")
        check(errors, source.get("candidate_tree") == CANDIDATE_TREE, "candidate tree mismatch")
        check(errors, source.get("upstream_commit") == UPSTREAM_COMMIT, "upstream commit mismatch")
        check(errors, source.get("upstream_tree") == UPSTREAM_TREE, "upstream tree mismatch")
        check(errors, source.get("candidate_basis") == "immutable_candidate_commit", "candidate basis is not immutable")
        source_files = source.get("source_files")
        check(errors, isinstance(source_files, dict) and bool(source_files), "source files missing")
        if isinstance(source_files, dict):
            for relative, expected in source_files.items():
                path = root / relative
                check(errors, not Path(relative).is_absolute() and ".." not in Path(relative).parts, f"unsafe source path: {relative}")
                check(errors, isinstance(expected, str) and HEX64.fullmatch(expected) is not None, f"source hash malformed: {relative}")
                if path.is_file():
                    check(errors, sha256(path.read_bytes()) == expected, f"working source hash mismatch: {relative}")
                else:
                    errors.append(f"source file missing: {relative}")
                check(errors, git_sha(root, relative) == expected, f"candidate source hash mismatch: {relative}")

    check(errors, document.get("portable_missing") == [], "portable_missing must remain empty for this covered probe")
    branches = document.get("branches")
    check(errors, isinstance(branches, list) and bool(branches), "branch matrix missing")
    seen: set[str] = set()
    if isinstance(branches, list):
        for branch in branches:
            check(errors, isinstance(branch, dict), "branch entry is not an object")
            if not isinstance(branch, dict):
                continue
            branch_id = branch.get("id")
            check(errors, isinstance(branch_id, str) and bool(branch_id), "branch id missing")
            if isinstance(branch_id, str):
                check(errors, branch_id not in seen, f"duplicate branch: {branch_id}")
                seen.add(branch_id)
            status = branch.get("status")
            check(errors, status in ALLOWED_STATUSES, f"invalid branch status: {branch_id}")
            check(errors, isinstance(branch.get("test"), str) and bool(branch["test"]), f"branch test missing: {branch_id}")
            if status in {"external_blocked", "implemented_blocked"}:
                check(errors, isinstance(branch.get("blocker"), str) and bool(branch["blocker"]), f"branch blocker missing: {branch_id}")

    blockers = document.get("external_blockers")
    check(errors, isinstance(blockers, list) and bool(blockers), "external blockers must remain explicit")
    claims = document.get("claims")
    check(errors, isinstance(claims, dict), "claims missing")
    if isinstance(claims, dict):
        check(errors, claims.get("portable_projection_branch_probe") is True, "portable probe claim missing")
        check(errors, claims.get("oracle_payload_parity") is False, "oracle parity must remain unclaimed")
        check(errors, claims.get("global_row_closed") is False, "global closure must remain open")
        check(errors, claims.get("release_approval") is False, "release approval must remain false")
    verification = document.get("verification")
    check(errors, isinstance(verification, dict), "verification record missing")
    if isinstance(verification, dict):
        check(errors, verification.get("candidate_materialization") == "immutable_candidate_commit_source_bound", "candidate materialization drift")
        check(errors, verification.get("oracle") == "not_run", "PB-03 oracle status drift")
        check(errors, isinstance(verification.get("command"), str) and "cargo test" in verification["command"], "test command missing")
    harness = document.get("harness")
    check(errors, isinstance(harness, dict), "harness binding missing")
    if isinstance(harness, dict):
        for key in ("verifier", "mutation_tests"):
            item = harness.get(key)
            check(errors, isinstance(item, dict), f"harness {key} binding missing")
            if isinstance(item, dict):
                relative = item.get("path")
                check(errors, isinstance(relative, str) and not Path(relative).is_absolute() and ".." not in Path(relative).parts, f"harness {key} path invalid")
                if isinstance(relative, str) and (root / relative).is_file():
                    check(errors, sha256((root / relative).read_bytes()) == item.get("sha256"), f"harness {key} digest mismatch")
    audit = document.get("audit")
    check(errors, isinstance(audit, dict), "audit binding missing")
    if isinstance(audit, dict):
        relative = audit.get("path")
        check(errors, isinstance(relative, str) and not Path(relative).is_absolute() and ".." not in Path(relative).parts, "audit path invalid")
        if isinstance(relative, str) and (root / relative).is_file():
            check(errors, sha256((root / relative).read_bytes()) == audit.get("sha256"), "audit digest mismatch")
    return {"valid": not errors, "errors": errors, "branch_count": len(branches) if isinstance(branches, list) else 0}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        document = yaml.safe_load(args.evidence.read_text(encoding="utf-8"))
        result = verify(document, args.root.resolve())
    except (OSError, UnicodeDecodeError, yaml.YAMLError, ValueError) as error:
        result = {"valid": False, "errors": [str(error)]}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("valid") else 1


if __name__ == "__main__":
    raise SystemExit(main())
