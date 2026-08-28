"""Verify the formal COM-01 Stage2 bundle and its Git cross-bindings."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

try:
    from .run_com_01_fingerprint_current_replay import (  # type: ignore[import-not-found]
        CANDIDATE_COMMIT,
        CANDIDATE_TREE,
        CRATE_RELATIVE,
        GIT_EXECUTABLE,
        HARNESS_FILES,
        MAX_HARNESS_FILE_BYTES,
        MAX_REPORT_BYTES,
        PREP_PARENT_COMMIT,
        _git,
        _finite_json,
        _read_bounded_regular,
        _validate_directory_root,
    )
    from .verify_com_01_fingerprint_current_replay import (  # type: ignore[import-not-found]
        HEX40,
        HEX64,
        VerificationError,
        read_json,
        require,
        verify_bundle,
    )
except ImportError:  # pragma: no cover - direct script import
    from run_com_01_fingerprint_current_replay import (
        CANDIDATE_COMMIT,
        CANDIDATE_TREE,
        CRATE_RELATIVE,
        GIT_EXECUTABLE,
        HARNESS_FILES,
        MAX_HARNESS_FILE_BYTES,
        MAX_REPORT_BYTES,
        PREP_PARENT_COMMIT,
        _git,
        _finite_json,
        _read_bounded_regular,
        _validate_directory_root,
    )
    from verify_com_01_fingerprint_current_replay import HEX40, HEX64, VerificationError, read_json, require, verify_bundle


FORMAL_SCHEMA = "sipi.com-01.fingerprint-current-replay.stage2-formal-bundle.v1"
FORMAL_STATUS = "scoped_exact_materialized_fingerprint_stage2_formal_record"
PREP_COMMIT = "d44581ac8b10adbc8f803bb0292107ae3303e015"
PREP_TREE = "2577bdea09e4263937f6253197746b17dd4af78c"
FORMAL_GATE_PARENT = "e3b1d2dc482be64bff8a3f69f1fdf03eb0792d26"
FORMAL_GATE_PATHS = (
    "tools/verify_com_01_fingerprint_current_replay_formal.py",
    "tools/test_verify_com_01_fingerprint_current_replay_formal.py",
)
AUDIT_PATH = "docs/baselines/audits/2026-08-28-com-01-fingerprint-current-replay-stage2.md"
AUDIT_SCHEMA = "sipi.com-01.fingerprint-current-replay.stage2-audit.v1"
AUDIT_NORMALIZED = {
    "schema": AUDIT_SCHEMA,
    "status": FORMAL_STATUS,
    "scope": {"work_item": "COM-01", "leaf": "config-validate", "acceptance": False, "binary_claim": "raw_sha256_per_replay_only", "parity_claim": "scoped_exact_fingerprint_only"},
    "exact": True,
    "claims": ["raw_sha256_per_replay_only", "scoped_exact_fingerprint_only"],
    "non_claims": ["no_complete_com_parity", "no_global_migration_row_close", "no_product_capability_promotion", "no_release_readiness", "no_configuration_value_payloads_committed", "no_S_parameter_fit", "channel_impulse_only_policy_unchanged", "no_canonical_pe_or_bit_reproducibility"],
}
REPORT_NAMES = (
    "com-01-fingerprint-current-replay-stage2-run-01.json",
    "com-01-fingerprint-current-replay-stage2-run-02.json",
)
AGGREGATE_NAME = "com-01-fingerprint-current-replay-stage2-aggregate.json"
FORMAL_RECORD_PATHS = (
    *REPORT_NAMES,
    AGGREGATE_NAME,
    "com-01-fingerprint-current-replay-stage2.manifest.json",
    AUDIT_PATH,
)


def _sha(path: Path, maximum: int) -> str:
    return hashlib.sha256(_read_bounded_regular(path, maximum)).hexdigest()


def _git_text(root: Path, *args: str) -> str:
    try:
        value = _git(root, *args)
    except (OSError, subprocess.SubprocessError) as error:
        raise VerificationError("Git identity query failed") from error
    require(isinstance(value, str) and value and "\n" not in value and "\r" not in value, "Git identity output drift")
    return value


def _direct_file(root: Path, name: str) -> Path:
    require(type(name) is str and bool(name) and Path(name).name == name and "/" not in name and "\\" not in name, "formal path is not a direct child")
    path = root / name
    require(path.parent == root, "formal path escaped fixed root")
    return path


def _project_file(root: Path, name: str) -> Path:
    require(type(name) is str and bool(name) and not Path(name).is_absolute(), "formal project path is not relative")
    relative = Path(name)
    require(".." not in relative.parts, "formal project path escaped root")
    path = root / relative
    require(path.parent.exists() and path.is_relative_to(root), "formal project path escaped root")
    return path


def _read_manifest(path: Path) -> tuple[dict[str, Any], str]:
    root = _validate_directory_root(path.parent)
    value, digest = read_json(path, input_root=root)
    require(type(value) is dict, "formal manifest is not an object")
    return value, digest


def _git_exists(root: Path, expression: str) -> bool:
    try:
        _git(root, "cat-file", "-e", expression)
    except (OSError, subprocess.SubprocessError):
        return False
    return True


def _audit_normalized(value: Any) -> dict[str, Any]:
    require(type(value) is dict and value == AUDIT_NORMALIZED, "audit normalized shape drift")
    return value


def _canonical(value: Any) -> bytes:
    _finite_json(value)
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _parse_audit(path: Path, normalized: dict[str, Any], canonical_sha256: str) -> None:
    try:
        raw = _read_bounded_regular(path, MAX_HARNESS_FILE_BYTES)
        parsed = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"invalid JSON constant: {value}")))
    except UnicodeDecodeError as error:
        raise VerificationError("audit is not UTF-8") from error
    _finite_json(parsed)
    require(type(parsed) is dict and parsed == AUDIT_NORMALIZED and parsed == normalized, "audit structured projection drift")
    require(hashlib.sha256(_canonical(parsed)).hexdigest() == canonical_sha256, "audit canonical digest drift")


def validate_audit_receipt(value: Any) -> None:
    require(type(value) is dict and set(value) == {"path", "sha256", "canonical_sha256", "normalized"} and value["path"] == AUDIT_PATH and HEX64.fullmatch(value["sha256"]) and HEX64.fullmatch(value["canonical_sha256"]), "audit receipt shape drift")
    _audit_normalized(value["normalized"])


def validate_formal_gate(value: Any, repo_root: Path | None = None) -> None:
    require(type(value) is dict and set(value) == {"commit", "parent", "tree", "changed_paths", "first_introduction", "formal_artifacts_absent", "files"}, "formal gate shape drift")
    require(HEX40.fullmatch(value["commit"]) and value["parent"] == FORMAL_GATE_PARENT and HEX40.fullmatch(value["parent"]) and HEX40.fullmatch(value["tree"]), "formal gate commit binding drift")
    require(type(value["changed_paths"]) is list and value["changed_paths"] == list(FORMAL_GATE_PATHS) and value["first_introduction"] is True and value["formal_artifacts_absent"] is True, "formal gate policy drift")
    files = value["files"]
    require(type(files) is list and len(files) == len(FORMAL_GATE_PATHS) and [item.get("path") if type(item) is dict else None for item in files] == list(FORMAL_GATE_PATHS), "formal gate file order drift")
    for item in files:
        require(type(item) is dict and set(item) == {"path", "git_blob_sha1", "bytes", "content_sha256"} and HEX40.fullmatch(item["git_blob_sha1"]) and type(item["bytes"]) is int and item["bytes"] > 0 and HEX64.fullmatch(item["content_sha256"]), "formal gate file identity drift")
    if repo_root is None:
        return
    repo_root = _validate_directory_root(repo_root)
    commit = value["commit"]
    require(_git_text(repo_root, "rev-parse", f"{commit}^{{commit}}") == commit and _git_text(repo_root, "rev-parse", f"{commit}^{{tree}}") == value["tree"], "formal gate Git identity drift")
    require(_git_text(repo_root, "rev-list", "--parents", "-n", "1", commit).split() == [commit, value["parent"]], "formal gate must have one pinned parent")
    require(_git(repo_root, "merge-base", "--is-ancestor", PREP_COMMIT, commit) == "", "prep commit is not an ancestor of formal gate")
    require(_git(repo_root, "diff", "--name-only", f"{PREP_COMMIT}..{commit}", "--", CRATE_RELATIVE.as_posix(), *HARNESS_FILES) == "", "COM production or Stage1 harness path changed after prep")
    changes = _git(repo_root, "diff-tree", "--no-commit-id", "--no-renames", "--name-status", "-r", f"{commit}^", commit)
    require(sorted(changes.splitlines()) == sorted(f"A\t{path}" for path in FORMAL_GATE_PATHS), "formal gate changed paths drift")
    require(all(not _git_exists(repo_root, f"{commit}^:{path}") for path in FORMAL_GATE_PATHS), "formal gate files were not first introduced")
    paths = _git(repo_root, "ls-tree", "-r", "--name-only", commit).splitlines()
    require(not any(path.startswith("docs/baselines/com-01-fingerprint-current-replay-stage2") or path == AUDIT_PATH for path in paths), "formal artifacts existed at formal gate")
    for item in files:
        raw = _git(repo_root, "show", f"{commit}:{item['path']}", raw=True)
        require(isinstance(raw, bytes) and len(raw) == item["bytes"] and hashlib.sha256(raw).hexdigest() == item["content_sha256"] and _git_text(repo_root, "rev-parse", f"{commit}:{item['path']}") == item["git_blob_sha1"], f"formal gate blob drift: {item['path']}")
        require(_read_bounded_regular(repo_root / item["path"], MAX_HARNESS_FILE_BYTES) == raw, f"formal gate live source drift: {item['path']}")


def validate_formal_record(repo_root: Path, *, gate_commit: str) -> None:
    repo_root = _validate_directory_root(repo_root)
    require(HEX40.fullmatch(gate_commit), "formal gate commit shape drift")
    commit = _git_text(repo_root, "rev-parse", "HEAD")
    require(commit != gate_commit, "runtime HEAD is still the formal gate")
    require(_git_text(repo_root, "rev-parse", f"{commit}^{{tree}}"), "formal record tree is missing")
    require(_git_text(repo_root, "rev-list", "--parents", "-n", "1", commit).split() == [commit, gate_commit], "formal record must be a direct child of gate")
    changes = _git(repo_root, "diff-tree", "--no-commit-id", "--no-renames", "--name-status", "-r", f"{commit}^", commit)
    require(sorted(changes.splitlines()) == sorted(f"A\t{path}" for path in FORMAL_RECORD_PATHS), "formal record changed paths drift")
    require(all(not _git_exists(repo_root, f"{commit}^:{path}") for path in FORMAL_RECORD_PATHS), "formal record paths were not first introduced")
    require(_git(repo_root, "status", "--porcelain=v1", "--untracked-files=all") == "", "formal record worktree is not clean")
    for path in FORMAL_RECORD_PATHS:
        raw = _git(repo_root, "show", f"{commit}:{path}", raw=True)
        blob_raw = _git(repo_root, "cat-file", "-p", f"{commit}:{path}", raw=True)
        require(isinstance(raw, bytes) and raw and isinstance(blob_raw, bytes) and blob_raw == raw and _git_text(repo_root, "rev-parse", f"{commit}:{path}") and _read_bounded_regular(repo_root / path, MAX_REPORT_BYTES) == raw, f"formal record raw/live drift: {path}")


def validate_manifest(value: Any, root: Path) -> None:
    root = _validate_directory_root(root)
    require(type(value) is dict and set(value) == {"schema", "status", "scope", "formal_gate", "prep", "reports", "aggregate", "audit", "artifact_policy", "non_claims"}, "formal manifest shape drift")
    require(value["schema"] == FORMAL_SCHEMA and value["status"] == FORMAL_STATUS, "formal manifest identity drift")
    require(value["scope"] == {"work_item": "COM-01", "leaf": "config-validate", "acceptance": False, "binary_claim": "raw_sha256_per_replay_only", "parity_claim": "scoped_exact_fingerprint_only"}, "formal scope drift")
    validate_formal_gate(value["formal_gate"])
    prep = value["prep"]
    require(type(prep) is dict and set(prep) == {"commit", "tree", "parent", "candidate_commit", "candidate_tree", "production_path_unchanged"}, "formal prep shape drift")
    require(prep["commit"] == PREP_COMMIT and prep["tree"] == PREP_TREE and prep["parent"] == PREP_PARENT_COMMIT and prep["candidate_commit"] == CANDIDATE_COMMIT and prep["candidate_tree"] == CANDIDATE_TREE and prep["production_path_unchanged"] is True, "formal prep Git binding drift")
    reports = value["reports"]
    require(type(reports) is list and len(reports) == 2, "formal report list drift")
    expected_report_paths = list(REPORT_NAMES)
    for item, expected_name in zip(reports, expected_report_paths):
        require(type(item) is dict and set(item) == {"path", "sha256", "run_id", "fresh_run_nonce", "candidate_binary_sha256"} and item["path"] == expected_name and HEX64.fullmatch(item["sha256"]) and HEX64.fullmatch(item["run_id"]) and HEX64.fullmatch(item["fresh_run_nonce"]) and HEX64.fullmatch(item["candidate_binary_sha256"]), "formal report identity drift")
        report_path = _direct_file(root, expected_name)
        require(_sha(report_path, MAX_REPORT_BYTES) == item["sha256"], f"formal report hash drift: {expected_name}")
        report, report_sha = read_json(report_path, input_root=root)
        require(report_sha == item["sha256"] and report["run_id"] == item["run_id"] and report["fresh_run_nonce"] == item["fresh_run_nonce"] and report["candidate"]["build"]["binary_post"]["sha256"] == item["candidate_binary_sha256"], f"formal report crossbind drift: {expected_name}")
    aggregate = value["aggregate"]
    require(type(aggregate) is dict and set(aggregate) == {"path", "sha256"} and aggregate["path"] == AGGREGATE_NAME and HEX64.fullmatch(aggregate["sha256"]), "formal aggregate identity drift")
    aggregate_path = _direct_file(root, AGGREGATE_NAME)
    require(_sha(aggregate_path, MAX_REPORT_BYTES) == aggregate["sha256"], "formal aggregate hash drift")
    for field in ("audit",):
        item = value[field]
        validate_audit_receipt(item)
    require(value["artifact_policy"] == "hash_counts_and_exactness_only_no_configuration_payloads" and type(value["non_claims"]) is list and value["non_claims"] == ["no_complete_com_parity", "no_global_migration_row_close", "no_product_capability_promotion", "no_release_readiness", "no_configuration_value_payloads_committed", "no_S_parameter_fit", "channel_impulse_only_policy_unchanged", "no_canonical_pe_or_bit_reproducibility"], "formal policy drift")


def validate_formal_bundle(manifest_path: Path, *, repo_root: Path, upstream_root: Path) -> dict[str, Any]:
    manifest_path = manifest_path if manifest_path.is_absolute() else Path.cwd() / manifest_path
    root = _validate_directory_root(manifest_path.parent)
    value, manifest_sha = _read_manifest(manifest_path)
    validate_manifest(value, root)
    project_root = _validate_directory_root(repo_root)
    validate_formal_gate(value["formal_gate"], project_root)
    validate_formal_record(project_root, gate_commit=value["formal_gate"]["commit"])
    for field in ("audit",):
        item = value[field]
        audit_path = _project_file(project_root, item["path"])
        require(_sha(audit_path, MAX_HARNESS_FILE_BYTES) == item["sha256"], f"formal {field} hash drift")
        _parse_audit(audit_path, item["normalized"], item["canonical_sha256"])
    prep = value["prep"]
    require(_git_text(repo_root, "rev-parse", f"{prep['commit']}^{{commit}}") == prep["commit"], "prep commit is not present")
    require(_git_text(repo_root, "rev-parse", f"{prep['commit']}^{{tree}}") == prep["tree"], "prep tree is not present")
    require(_git_text(repo_root, "rev-list", "--parents", "-n", "1", prep["commit"]).split() == [prep["commit"], prep["parent"]], "prep parent drift")
    require(_git_text(repo_root, "rev-parse", f"{prep['candidate_commit']}^{{commit}}") == prep["candidate_commit"] and _git_text(repo_root, "rev-parse", f"{prep['candidate_commit']}^{{tree}}") == prep["candidate_tree"], "candidate Git binding drift")
    require(_git(repo_root, "merge-base", "--is-ancestor", prep["candidate_commit"], prep["commit"]) == "", "candidate is not an ancestor of prep")
    require(_git(repo_root, "diff", "--name-only", f"{prep['candidate_commit']}..{prep['commit']}", "--", CRATE_RELATIVE.as_posix()) == "", "candidate production path changed after candidate")
    first = _direct_file(root, REPORT_NAMES[0])
    second = _direct_file(root, REPORT_NAMES[1])
    aggregate = _direct_file(root, AGGREGATE_NAME)
    result = verify_bundle(first, second, aggregate, repo_root=repo_root, upstream_root=upstream_root)
    return {"schema": value["schema"], "status": value["status"], "manifest_sha256": manifest_sha, "fresh_replays": result["fresh_replays"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--upstream-repo", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = validate_formal_bundle(args.manifest, repo_root=args.repo_root, upstream_root=args.upstream_repo)
    except (OSError, ValueError, VerificationError, json.JSONDecodeError, subprocess.SubprocessError, TypeError):
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
