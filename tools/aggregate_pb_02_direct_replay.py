"""Aggregate two immutable PB-02 replay reports without storing payloads."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


SCHEMA = "sipi.pb-02-direct-replay.v1"
AGGREGATE_SCHEMA = "sipi.pb-02-direct-replay-aggregate.v1"
ROOT = Path(__file__).resolve().parents[1]
HEX64 = re.compile(r"[0-9a-f]{64}\Z")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _read(path: Path) -> tuple[dict[str, Any], str]:
    payload = path.read_bytes()
    document = json.loads(payload.decode("utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"replay report must be an object: {path}")
    return document, _sha256(payload)


def _get(document: dict[str, Any], *keys: str) -> Any:
    value: Any = document
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _stable_report_id(path: Path) -> str:
    """Return a repository-relative report id, never a caller absolute path."""

    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.name


def _toolchain_identity(document: dict[str, Any], label: str, blockers: list[str]) -> dict[str, Any] | None:
    value = document.get("toolchain")
    if not isinstance(value, dict):
        blockers.append(f"{label} toolchain identity is missing")
        return None
    allowed_toolchain_keys = {"cargo", "rustc", "uv", "timeout_seconds"}
    if set(value) != allowed_toolchain_keys:
        blockers.append(f"{label} toolchain keys are not exact")
    for role in ("cargo", "rustc", "uv"):
        identity = value.get(role)
        if not isinstance(identity, dict):
            blockers.append(f"{label} {role} identity is missing")
            continue
        allowed_identity_keys = {
            "role",
            "executable",
            "path_redacted",
            "file_sha256",
            "version_exit_code",
            "version_output_sha256",
        }
        if set(identity) != allowed_identity_keys:
            blockers.append(f"{label} {role} identity keys are not exact")
        if identity.get("role") != role:
            blockers.append(f"{label} {role} identity role drift")
        executable = identity.get("executable")
        if (
            not isinstance(executable, str)
            or not executable
            or any(separator in executable for separator in ("/", "\\"))
            or ":" in executable
        ):
            blockers.append(f"{label} {role} identity contains a path")
        if identity.get("path_redacted") is not True:
            blockers.append(f"{label} {role} path redaction is missing")
        for digest_name in ("file_sha256", "version_output_sha256"):
            digest = identity.get(digest_name)
            if not isinstance(digest, str) or HEX64.fullmatch(digest) is None:
                blockers.append(f"{label} {role} {digest_name} is missing or malformed")
        if identity.get("version_exit_code") != 0:
            blockers.append(f"{label} {role} version command did not pass")
    if type(value.get("timeout_seconds")) is not int or value["timeout_seconds"] <= 0:
        blockers.append(f"{label} toolchain timeout is invalid")
    return value


def aggregate(first_path: Path, second_path: Path, output: Path) -> dict[str, Any]:
    first, first_hash = _read(first_path)
    second, second_hash = _read(second_path)
    blockers: list[str] = []
    if first_path.resolve() == second_path.resolve():
        blockers.append("report paths must be distinct")
    if first_hash == second_hash:
        blockers.append("complete report digests must be distinct")
    for label, document in (("first", first), ("second", second)):
        if document.get("schema") != SCHEMA:
            blockers.append(f"{label} schema drift")
        if document.get("status") != "passed":
            blockers.append(f"{label} replay is not passed")
        if document.get("source_mode") != "git_archive_at_immutable_commit":
            blockers.append(f"{label} is not archive-bound")
    first_toolchain = _toolchain_identity(first, "first", blockers)
    second_toolchain = _toolchain_identity(second, "second", blockers)
    if first_toolchain is not None and second_toolchain is not None and first_toolchain != second_toolchain:
        blockers.append("toolchain identity drift between replays")
    if first.get("run_id") == second.get("run_id"):
        blockers.append("run IDs must be distinct")
    first_nonce = first.get("fresh_run_nonce")
    second_nonce = second.get("fresh_run_nonce")
    if not isinstance(first_nonce, str) or HEX64.fullmatch(first_nonce) is None:
        blockers.append("first fresh run nonce is missing or malformed")
    if not isinstance(second_nonce, str) or HEX64.fullmatch(second_nonce) is None:
        blockers.append("second fresh run nonce is missing or malformed")
    if isinstance(first_nonce, str) and isinstance(second_nonce, str) and first_nonce == second_nonce:
        blockers.append("fresh run nonces must be distinct")
    for name in ("candidate", "upstream", "fixture"):
        if first.get(name) != second.get(name):
            blockers.append(f"{name} identity drift between replays")
    first_parity = first.get("replay", {}).get("parity", {})
    second_parity = second.get("replay", {}).get("parity", {})
    if first_parity.get("candidate_array_members_equal_oracle") is not True:
        blockers.append("first replay does not prove candidate/oracle array equality")
    if second_parity.get("candidate_array_members_equal_oracle") is not True:
        blockers.append("second replay does not prove candidate/oracle array equality")
    first_candidate_arrays = _get(first, "replay", "candidate", "artifacts", "arrays", "logical_members")
    second_candidate_arrays = _get(second, "replay", "candidate", "artifacts", "arrays", "logical_members")
    first_oracle_arrays = _get(first, "replay", "oracle", "artifacts", "arrays", "logical_members")
    second_oracle_arrays = _get(second, "replay", "oracle", "artifacts", "arrays", "logical_members")
    if first_candidate_arrays != second_candidate_arrays:
        blockers.append("candidate array member hashes drift between replays")
    if first_oracle_arrays != second_oracle_arrays:
        blockers.append("oracle array member hashes drift between replays")
    first_report_id = _stable_report_id(first_path)
    second_report_id = _stable_report_id(second_path)
    if first_report_id == second_report_id:
        blockers.append("stable report ids must be distinct")
    aggregate_document = {
        "schema": AGGREGATE_SCHEMA,
        "status": "passed" if not blockers else "blocked",
        "reports": [
            {
                "path": first_report_id,
                "sha256": first_hash,
                "run_id": first.get("run_id"),
                "fresh_run_nonce": first_nonce,
                "logical_array_sha256": _get(first, "replay", "candidate", "artifacts", "arrays", "logical_sha256"),
            },
            {
                "path": second_report_id,
                "sha256": second_hash,
                "run_id": second.get("run_id"),
                "fresh_run_nonce": second_nonce,
                "logical_array_sha256": _get(second, "replay", "candidate", "artifacts", "arrays", "logical_sha256"),
            },
        ],
        "candidate": first.get("candidate"),
        "upstream": first.get("upstream"),
        "fixture": first.get("fixture"),
        "toolchain": first_toolchain,
        "logical_array_member_sha256": first_candidate_arrays,
        "blockers": blockers,
        "non_claims": [
            "This aggregate proves only the one explicit PB-02 fixture and does not close uncovered SimulationInputV1 branches.",
            "SIPI wrapper admission and artifact policies remain outside upstream numerical parity.",
            "This aggregate is not a license decision, release approval, or product capability admission.",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(aggregate_document, ensure_ascii=False, indent=2, sort_keys=True))
        stream.write("\n")
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
        print(json.dumps({"valid": False, "error": str(error)}), file=sys.stderr)
        return 2
    print(json.dumps({"status": document["status"], "output": str(args.output)}, sort_keys=True))
    return 0 if document["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
