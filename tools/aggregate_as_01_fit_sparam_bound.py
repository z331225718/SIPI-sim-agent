"""Aggregate two AS-01 immutable replay reports while preserving mismatch/open."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_SCHEMA = "sipi.agent-spice-as-01-bound-replay.v1"
SCHEMA = "sipi.agent-spice-as-01-bound-aggregate.v1"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
EXPECTED_CANDIDATE_COMMIT = "8bcfd1d1bc511461615f19338e453f0148e5dcb1"
EXPECTED_CANDIDATE_TREE = "ed221a36f2d3325b0aac3f3336a9c8a14d13e99a"
EXPECTED_UPSTREAM_COMMIT = "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5"
EXPECTED_UPSTREAM_TREE = "b6bde97128030d6cea0d68b2f0a35d807be8c402"


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read(path: Path) -> tuple[dict[str, Any], str]:
    payload = path.read_bytes()
    document = json.loads(payload.decode("utf-8"))
    if not isinstance(document, dict):
        raise ValueError("replay report must be an object")
    return document, _sha256(payload)


def _stable_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.name


def _valid_toolchain(value: Any) -> bool:
    if not isinstance(value, dict) or set(value) != {
        "cargo",
        "rustc",
        "python",
        "uv",
        "timeout_seconds",
    }:
        return False
    if type(value["timeout_seconds"]) is not int or value["timeout_seconds"] <= 0:
        return False
    for role in ("cargo", "rustc", "python", "uv"):
        identity = value.get(role)
        if not isinstance(identity, dict) or set(identity) != {
            "role",
            "executable",
            "path_redacted",
            "file_sha256",
            "version_exit_code",
            "version_output_sha256",
        }:
            return False
        executable = identity.get("executable")
        if (
            identity.get("role") != role
            or identity.get("path_redacted") is not True
            or identity.get("version_exit_code") != 0
            or not isinstance(executable, str)
            or not executable
            or any(separator in executable for separator in ("/", "\\", ":"))
        ):
            return False
        if any(not isinstance(identity.get(key), str) or HEX64.fullmatch(identity[key]) is None for key in ("file_sha256", "version_output_sha256")):
            return False
    return True


def _contains_absolute_path(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_contains_absolute_path(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_absolute_path(item) for item in value)
    if not isinstance(value, str):
        return False
    normalized = value.replace("\\", "/")
    return bool(re.match(r"^[A-Za-z]:/", normalized) or normalized.startswith(("/Users/", "/home/", "//")))


def _valid_oracle_environment(value: Any) -> bool:
    if not isinstance(value, dict) or set(value) != {"lock", "venv", "sync", "runtime_python", "installed", "isolation"}:
        return False
    lock = value.get("lock")
    if (
        not isinstance(lock, dict)
        or set(lock) != {"path", "bytes", "sha256", "require_hashes"}
        or not isinstance(lock.get("path"), str)
        or any(separator in lock["path"] for separator in ("/", "\\", ":"))
        or type(lock.get("bytes")) is not int
        or lock["bytes"] <= 0
        or not isinstance(lock.get("sha256"), str)
        or HEX64.fullmatch(lock["sha256"]) is None
        or lock.get("require_hashes") is not True
    ):
        return False
    if value.get("venv") != {"exit_code": 0} or value.get("sync") != {"exit_code": 0}:
        return False
    runtime = value.get("runtime_python")
    if (
        not isinstance(runtime, dict)
        or set(runtime) != {"role", "executable", "path_redacted", "file_sha256", "version_exit_code", "version_output_sha256"}
        or runtime.get("role") != "oracle_python"
        or runtime.get("path_redacted") is not True
        or runtime.get("version_exit_code") != 0
        or not isinstance(runtime.get("executable"), str)
        or any(separator in runtime["executable"] for separator in ("/", "\\", ":"))
        or any(not isinstance(runtime.get(key), str) or HEX64.fullmatch(runtime[key]) is None for key in ("file_sha256", "version_output_sha256"))
    ):
        return False
    installed = value.get("installed")
    if (
        not isinstance(installed, dict)
        or set(installed) != {"distributions", "distribution_sha256", "numeric_config_sha256"}
        or not isinstance(installed.get("distributions"), list)
        or any(not isinstance(installed.get(key), str) or HEX64.fullmatch(installed[key]) is None for key in ("distribution_sha256", "numeric_config_sha256"))
    ):
        return False
    return value.get("isolation") == {
        "isolated_flag": "-I",
        "python_no_user_site": True,
        "python_path_cleared": True,
        "python_home_cleared": True,
        "virtual_env_cleared": True,
        "numeric_threads": 1,
    }


def aggregate(first_path: Path, second_path: Path, output_path: Path) -> dict[str, Any]:
    first, first_hash = _read(first_path)
    second, second_hash = _read(second_path)
    blockers: list[str] = []
    if first_path.resolve() == second_path.resolve() or first_path.samefile(second_path):
        blockers.append("report paths must be distinct")
    if first_hash == second_hash:
        blockers.append("complete report SHA-256 values must be distinct")
    for label, report in (("first", first), ("second", second)):
        if report.get("schema") != REPORT_SCHEMA:
            blockers.append(f"{label} report schema drift")
        if report.get("status") != "completed_numeric_mismatch":
            blockers.append(f"{label} report does not preserve mismatch/open")
        if report.get("custody_valid") is not True or report.get("parity_claim") is not False or report.get("numeric_mismatch_open") is not True:
            blockers.append(f"{label} custody/parity flags drift")
        if report.get("source_mode") != "candidate_and_upstream_git_archive_at_immutable_commit":
            blockers.append(f"{label} report is not immutable-archive bound")
        if report.get("harness_source_mode") != "content_addressed_worktree_file_pending_owner_commit":
            blockers.append(f"{label} harness source mode drift")
        nonce = report.get("fresh_run_nonce")
        if not isinstance(nonce, str) or HEX64.fullmatch(nonce) is None:
            blockers.append(f"{label} fresh nonce is malformed")
        comparison = report.get("comparison")
        if not isinstance(comparison, dict):
            blockers.append(f"{label} comparison is missing")
        elif (
            comparison.get("numeric_parity") is not False
            or comparison.get("complete_contract_parity_claim") is not False
            or comparison.get("numeric_mismatch_open") is not True
            or comparison.get("acceptance_tolerance") is not None
        ):
            blockers.append(f"{label} comparison overclaims parity")
        if not _valid_toolchain(report.get("toolchain")):
            blockers.append(f"{label} toolchain identity is invalid")
        if not _valid_oracle_environment(report.get("oracle_environment")):
            blockers.append(f"{label} oracle environment identity is invalid")
        build = report.get("build")
        if not isinstance(build, dict) or build.get("exit_code") != 0 or build.get("binary_present") is not True:
            blockers.append(f"{label} candidate archive build failed")
        if _contains_absolute_path(report):
            blockers.append(f"{label} report contains an absolute path")
        candidate_identity = report.get("candidate") or {}
        upstream_identity = report.get("upstream") or {}
        if (candidate_identity.get("commit"), candidate_identity.get("tree")) != (EXPECTED_CANDIDATE_COMMIT, EXPECTED_CANDIDATE_TREE):
            blockers.append(f"{label} candidate source identity drift")
        if (upstream_identity.get("commit"), upstream_identity.get("tree")) != (EXPECTED_UPSTREAM_COMMIT, EXPECTED_UPSTREAM_TREE):
            blockers.append(f"{label} upstream source identity drift")
    if first.get("run_id") == second.get("run_id"):
        blockers.append("run IDs must be distinct")
    if first.get("fresh_run_nonce") == second.get("fresh_run_nonce"):
        blockers.append("fresh nonces must be distinct")
    for key in (
        "candidate",
        "upstream",
        "archived_preparation_runner",
        "scenario_set_sha256",
        "fixture_sha256",
        "toolchain",
        "oracle_environment",
        "bound_runner",
        "bound_oracle_lock",
        "comparison",
    ):
        if first.get(key) != second.get(key):
            blockers.append(f"{key} drift between independent replays")
    if first.get("build", {}).get("binary_sha256") != second.get("build", {}).get("binary_sha256"):
        blockers.append("candidate binary digest drift between replays")
    report_paths = [_stable_path(first_path), _stable_path(second_path)]
    if report_paths[0] == report_paths[1]:
        blockers.append("stable report IDs must be distinct")
    aggregate_document = {
        "schema": SCHEMA,
        "status": "completed_numeric_mismatch" if not blockers else "blocked",
        "custody_valid": not blockers,
        "parity_claim": False,
        "numeric_mismatch_open": True,
        "acceptance_tolerance": None,
        "reports": [
            {
                "path": report_paths[0],
                "sha256": first_hash,
                "run_id": first.get("run_id"),
                "fresh_run_nonce": first.get("fresh_run_nonce"),
            },
            {
                "path": report_paths[1],
                "sha256": second_hash,
                "run_id": second.get("run_id"),
                "fresh_run_nonce": second.get("fresh_run_nonce"),
            },
        ],
        "candidate": first.get("candidate"),
        "upstream": first.get("upstream"),
        "archived_preparation_runner": first.get("archived_preparation_runner"),
        "scenario_set_sha256": first.get("scenario_set_sha256"),
        "fixture_sha256": first.get("fixture_sha256"),
        "toolchain": first.get("toolchain"),
        "oracle_environment": first.get("oracle_environment"),
        "bound_runner": first.get("bound_runner"),
        "bound_oracle_lock": first.get("bound_oracle_lock"),
        "binary_sha256": first.get("build", {}).get("binary_sha256"),
        "comparison": first.get("comparison"),
        "blockers": blockers,
        "non_claims": [
            "The aggregate binds a reproducible mismatch; it does not prove fit-sparam parity.",
            "The scoped two-port leaf and sampled passivity do not imply complete upstream behavior.",
            "This aggregate is not acceptance, release approval, license admission, or product capability promotion.",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(aggregate_document, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return aggregate_document


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first", type=Path, required=True)
    parser.add_argument("--second", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        document = aggregate(args.first, args.second, args.output)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"valid": False, "error": str(error)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps({"status": document["status"], "output": args.output.name}, sort_keys=True))
    return 0 if document["status"] == "completed_numeric_mismatch" else 1


if __name__ == "__main__":
    raise SystemExit(main())
