"""Strict, fail-closed aggregator for COM preparation reports."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath

try:
    from .verify_com_workbook_accm_replay_v1 import stable_candidate, verify_report
except ImportError:
    from verify_com_workbook_accm_replay_v1 import stable_candidate, verify_report

SCHEMA = "sipi.com.workbook-accm-replay-aggregate-prep.v4"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_report_name(path: Path) -> str:
    name = PurePosixPath(path.name)
    if name.name != path.name or name.is_absolute() or any(part in ("", ".", "..") for part in name.parts):
        raise ValueError("report path is not a safe basename")
    return name.as_posix()


def aggregate(run1: Path, run2: Path, output: Path, cargo_home: Path | None = None) -> dict[str, object]:
    first = verify_report(run1, cargo_home)
    second = verify_report(run2, cargo_home)
    if any(report["toolchain"]["pre"]["linker"]["basename"].lower() != "rust-lld.exe" for report in (first, second)):
        raise ValueError("aggregate linker identity must be rust-lld.exe")
    if first["candidate"]["binary"]["canonical_sha256"] != second["candidate"]["binary"]["canonical_sha256"] or first["candidate"]["binary"]["normalization_map"] != second["candidate"]["binary"]["normalization_map"]:
        raise ValueError("aggregate typed PE canonical identity drift")
    if first["run_id"] == second["run_id"] or first["nonce"] == second["nonce"]:
        raise ValueError("fresh run identities must be distinct")
    build_identity = lambda report: {key: report["build"][key] for key in ("command", "exit", "timeout_s", "env_policy", "env_receipt", "deterministic_flags")}
    if stable_candidate(first["candidate"]) != stable_candidate(second["candidate"]) or first["fixtures"] != second["fixtures"] or first["upstream"] != second["upstream"] or first["toolchain"] != second["toolchain"] or build_identity(first) != build_identity(second) or first["execution"] != second["execution"]:
        raise ValueError("candidate, fixture, source, toolchain, or build identity drift")
    aggregate_status = "numeric_observation" if first["parity"]["status"] == second["parity"]["status"] == "numeric_observation" else "blocked"
    result = {
        "schema": SCHEMA,
        "report_slots": [{"slot": "run1", "run_id": first["run_id"], "path": safe_report_name(run1), "sha256": digest(run1)}, {"slot": "run2", "run_id": second["run_id"], "path": safe_report_name(run2), "sha256": digest(run2)}],
        "candidate": first["candidate"],
        "fixtures": first["fixtures"],
        "upstream": first["upstream"],
        "toolchain": first["toolchain"],
        "controls": first["controls"],
        "parity": {"status": aggregate_status, "matched": False, "acceptance": False},
        "fresh_runs": 2,
        "non_claims": ["no upstream numeric parity", "no global/product/release claim", "aggregate is preparation-only", "PDB is opaque environment-local debug custody and nonpublish"],
    }
    if output.exists():
        raise FileExistsError("aggregate path already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run1", type=Path, required=True)
    parser.add_argument("--run2", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cargo-home", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(aggregate(args.run1, args.run2, args.output, args.cargo_home), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
