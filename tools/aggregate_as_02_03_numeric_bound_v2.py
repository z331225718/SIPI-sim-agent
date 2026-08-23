"""Aggregate two fresh bound numeric observations for AS-02 or AS-03."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _has_absolute_path(value: object) -> bool:
    if isinstance(value, dict):
        return any(_has_absolute_path(key) or _has_absolute_path(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_has_absolute_path(item) for item in value)
    return isinstance(value, str) and bool(re.search(r"(?:^[A-Za-z]:[\\/]|^//|^/(?!sipi-(?:candidate|target)(?:/|$)))", value))


def aggregate(first_path: Path, second_path: Path, output: Path) -> dict[str, object]:
    first = json.loads(first_path.read_text(encoding="utf-8"))
    second = json.loads(second_path.read_text(encoding="utf-8"))
    blockers: list[str] = []
    if _has_absolute_path(first) or _has_absolute_path(second):
        blockers.append("absolute path disclosure")
    first_sha, second_sha = sha(first_path), sha(second_path)
    if first_sha == second_sha or first.get("run_id") == second.get("run_id") or first.get("fresh_run_nonce") == second.get("fresh_run_nonce"):
        blockers.append("fresh identity")
    for key in ("workflow", "candidate", "upstream", "toolchain", "fixture_sha256", "metrics"):
        if first.get(key) != second.get(key):
            blockers.append(f"cross-run drift:{key}")
    if first.get("build", {}).get("binary_sha256") != second.get("build", {}).get("binary_sha256"):
        blockers.append("binary drift")
    for report in (first, second):
        if report.get("status") != "completed_numeric_mismatch_open" or report.get("parity_claim") is not False or report.get("numeric_parity") is not False:
            blockers.append("parity overclaim")
    relative = lambda path: path.resolve().relative_to(ROOT.resolve()).as_posix()
    document = {
        "schema": "sipi.agent-spice-as-numeric-bound-aggregate.v2",
        "workflow": first.get("workflow"),
        "status": "completed_numeric_mismatch_open" if not blockers else "blocked",
        "custody_valid": not blockers,
        "parity_claim": False,
        "numeric_parity": False,
        "reports": [{"path": relative(first_path), "sha256": first_sha, "run_id": first.get("run_id"), "fresh_run_nonce": first.get("fresh_run_nonce")}, {"path": relative(second_path), "sha256": second_sha, "run_id": second.get("run_id"), "fresh_run_nonce": second.get("fresh_run_nonce")}],
        "candidate": first.get("candidate"),
        "upstream": first.get("upstream"),
        "toolchain": first.get("toolchain"),
        "metrics": first.get("metrics"),
        "blockers": blockers,
        "non_claims": ["Numeric mismatch remains open.", "No acceptance tolerance or product parity is claimed."],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return document


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--first", type=Path, required=True)
    parser.add_argument("--second", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    document = aggregate(args.first, args.second, args.output)
    print(json.dumps({"status": document["status"], "output": args.output.name}, sort_keys=True))
    return 0 if document["status"] == "completed_numeric_mismatch_open" else 1


if __name__ == "__main__":
    raise SystemExit(main())
