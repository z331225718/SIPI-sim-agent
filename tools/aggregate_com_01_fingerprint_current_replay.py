"""Aggregate two exact COM-01 fingerprint replay reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from .run_com_01_fingerprint_current_replay import ROOT, _atomic_json_create, _validate_directory_root  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - direct script import
    from run_com_01_fingerprint_current_replay import ROOT, _atomic_json_create, _validate_directory_root

try:
    from .verify_com_01_fingerprint_current_replay import (  # type: ignore[import-not-found]
        AGGREGATE_SCHEMA,
        AGGREGATE_STATUS,
        EXPECTED_ARTIFACT_POLICY,
        NON_CLAIMS,
        RAW_BINARY_POLICY,
        VerificationError,
        _without_build,
        read_json,
        validate_aggregate,
        validate_report,
    )
except ImportError:  # pragma: no cover - direct script import
    from verify_com_01_fingerprint_current_replay import (
        AGGREGATE_SCHEMA,
        AGGREGATE_STATUS,
        EXPECTED_ARTIFACT_POLICY,
        NON_CLAIMS,
        RAW_BINARY_POLICY,
        VerificationError,
        _without_build,
        read_json,
        validate_aggregate,
        validate_report,
    )


def _absolute(path: Path) -> Path:
    return path if path.is_absolute() else Path.cwd() / path


def _bundle_root(first_path: Path, second_path: Path, output: Path) -> Path:
    paths = [_absolute(path) for path in (first_path, second_path, output)]
    if len({path.parent for path in paths}) != 1:
        raise VerificationError("reports and aggregate must share one fixed output root")
    root = _validate_directory_root(paths[0].parent)
    if any(path.parent != root or not path.name for path in paths) or len({path.name for path in paths}) != 3:
        raise VerificationError("reports and aggregate must be distinct direct children of the fixed root")
    return root


def aggregate(first_path: Path, second_path: Path, output: Path, *, repo_root: Path = ROOT, upstream_root: Path | None = None) -> dict[str, Any]:
    root = _bundle_root(first_path, second_path, output)
    first, first_sha = read_json(first_path, input_root=root)
    second, second_sha = read_json(second_path, input_root=root)
    validate_report(first, repo_root=repo_root, upstream_root=upstream_root)
    validate_report(second, repo_root=repo_root, upstream_root=upstream_root)
    if first_sha == second_sha:
        raise VerificationError("fresh report hashes must be distinct")
    if first["run_id"] == second["run_id"] or first["fresh_run_nonce"] == second["fresh_run_nonce"]:
        raise VerificationError("fresh replay identities must be distinct")
    if _without_build(first["candidate"]) != _without_build(second["candidate"]):
        raise VerificationError("candidate static identity drift")
    for key in ("upstream", "harness", "toolchain", "fixture", "scenario", "expected", "exact"):
        if first[key] != second[key]:
            raise VerificationError(f"{key} drift between fresh replays")
    binary_first = first["candidate"]["build"]["binary_post"]["sha256"]
    binary_second = second["candidate"]["build"]["binary_post"]["sha256"]
    if first["exact"]["all"] is not True:
        raise VerificationError("exact fingerprint gate is not closed")
    document = {
        "schema": AGGREGATE_SCHEMA,
        "status": AGGREGATE_STATUS,
        "work_item": "COM-01",
        "leaf": "config-validate",
        "fresh_replays": 2,
        "reports": [
            {"path": _absolute(first_path).name, "sha256": first_sha, "run_id": first["run_id"], "fresh_run_nonce": first["fresh_run_nonce"], "candidate_binary_sha256": binary_first},
            {"path": _absolute(second_path).name, "sha256": second_sha, "run_id": second["run_id"], "fresh_run_nonce": second["fresh_run_nonce"], "candidate_binary_sha256": binary_second},
        ],
        "candidate": _without_build(first["candidate"]),
        "build_receipts": [first["candidate"]["build"], second["candidate"]["build"]],
        "upstream": first["upstream"],
        "harness": first["harness"],
        "toolchain": first["toolchain"],
        "fixture": first["fixture"],
        "scenario": first["scenario"],
        "expected": first["expected"],
        "exact": first["exact"],
        "binary_bit_reproducible": False,
        "binary_reproducibility": RAW_BINARY_POLICY,
        "raw_binary_sha_equal": binary_first == binary_second,
        "blockers": [],
        "acceptance": False,
        "artifact_policy": EXPECTED_ARTIFACT_POLICY,
        "non_claims": list(NON_CLAIMS),
    }
    validate_aggregate(document)
    _atomic_json_create(output, document, output_root=root)
    return document


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first", type=Path, required=True)
    parser.add_argument("--second", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--upstream-repo", type=Path)
    args = parser.parse_args()
    try:
        document = aggregate(args.first, args.second, args.output, repo_root=args.repo_root, upstream_root=args.upstream_repo)
    except (OSError, ValueError, VerificationError, json.JSONDecodeError, TypeError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, sort_keys=True))
        return 2
    print(json.dumps({"schema": document["schema"], "status": document["status"], "fresh_replays": 2}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
