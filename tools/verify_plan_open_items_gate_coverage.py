"""Verify that every open PLAN item has a tracked gate inventory.

This verifier checks coverage only. It deliberately does not claim that the
listed gates were executed; execution belongs to the session-health/gate
sweep. The ledger is the sole gate mapping authority and must match the open
checklist identifiers parsed from PLAN.md.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.plan-open-items.gate-coverage.v2"
PLAN_PATH = "PLAN.md"
LEDGER_PATH = "docs/baselines/plan-remaining-items-ledger.v1.yaml"
OPEN_ITEM_RE = re.compile(r"^\s*- \[ \] \*\*(P[0-9A-Z-]+)\*\*", re.MULTILINE)
EXPECTED_BLOCKER_COUNTS = {
    "external_asset_oracle": 10,
    "semantics_not_implemented": 0,
    "release_gate": 9,
}


class CoverageError(RuntimeError):
    pass


def _read_ledger(root: Path) -> dict[str, Any]:
    try:
        document = json.loads((root / LEDGER_PATH).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CoverageError("ledger_invalid") from error
    if document.get("schema") != "sipi.plan-remaining-items.ledger.v1":
        raise CoverageError("ledger_schema_invalid")
    return document


def _ledger_gate_map(document: dict[str, Any]) -> dict[str, list[str]]:
    items = document.get("items")
    if not isinstance(items, list) or not items:
        raise CoverageError("ledger_items_invalid")
    result: dict[str, list[str]] = {}
    counts = {key: 0 for key in EXPECTED_BLOCKER_COUNTS}
    for entry in items:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            raise CoverageError("ledger_item_invalid")
        item_id = entry["id"]
        blocker = entry.get("blocker")
        if blocker not in counts:
            raise CoverageError(f"ledger_blocker_invalid:{item_id}")
        counts[blocker] += 1
        gates = entry.get("gate")
        if item_id in result:
            raise CoverageError(f"ledger_item_duplicate:{item_id}")
        if not isinstance(gates, list) or not gates or not all(isinstance(gate, str) for gate in gates):
            raise CoverageError(f"item_gates_empty:{item_id}")
        result[item_id] = gates
    if document.get("total_open") != len(result):
        raise CoverageError("ledger_total_open_mismatch")
    if counts != EXPECTED_BLOCKER_COUNTS:
        raise CoverageError(f"ledger_blocker_counts_invalid:{counts}")
    return result


def _plan_open_items(root: Path) -> list[str]:
    try:
        plan = (root / PLAN_PATH).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise CoverageError("plan_invalid") from error
    for line_number, line in enumerate(plan.splitlines(), start=1):
        if len(line) > 10_000:
            raise CoverageError(f"plan_line_too_long:{line_number}:{len(line)}")
        if line.count("- [ ]") + line.count("- [x]") > 1:
            raise CoverageError(f"plan_checklists_concatenated:{line_number}")
    items = OPEN_ITEM_RE.findall(plan)
    if not items:
        raise CoverageError("plan_open_items_missing")
    if len(items) != len(set(items)):
        raise CoverageError("plan_open_item_duplicate")
    return items


def _tracked_paths(root: Path) -> set[str]:
    completed = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        capture_output=True,
        timeout=60,
    )
    if completed.returncode != 0:
        raise CoverageError("git_inventory_unavailable")
    return {
        item.decode("utf-8", errors="strict")
        for item in completed.stdout.split(b"\0")
        if item
    }


def validate(root: Path = ROOT) -> dict[str, Any]:
    gate_map = _ledger_gate_map(_read_ledger(root))
    plan_items = _plan_open_items(root)
    if set(plan_items) != set(gate_map):
        missing = sorted(set(plan_items) - set(gate_map))
        extra = sorted(set(gate_map) - set(plan_items))
        raise CoverageError(f"plan_ledger_item_mismatch:missing={missing}:extra={extra}")

    tracked = _tracked_paths(root)
    gate_count = 0
    for item_id, gates in sorted(gate_map.items()):
        if len(gates) != len(set(gates)):
            raise CoverageError(f"item_gate_duplicate:{item_id}")
        for gate in gates:
            if not gate.startswith("tools/verify_") or not gate.endswith(".py") or ".." in gate:
                raise CoverageError(f"gate_path_invalid:{item_id}:{gate}")
            if gate not in tracked:
                raise CoverageError(f"gate_untracked:{item_id}:{gate}")
            if not (root / gate).is_file():
                raise CoverageError(f"gate_missing:{item_id}:{gate}")
            gate_count += 1

    return {
        "valid": True,
        "items": len(gate_map),
        "gates": gate_count,
        "blocker_counts": {
            blocker: sum(entry.get("blocker") == blocker for entry in _read_ledger(root).get("items", []))
            for blocker in EXPECTED_BLOCKER_COUNTS
        },
        "coverage_scope": "tracked_gate_inventory_only",
        "executed_gates": 0,
        "execution_claim": "not_evaluated_by_this_verifier",
    }


# Compatibility for sweep_coverage_gates.py. Importing this mapping does not
# imply that any gate was executed.
OPEN_ITEM_GATES = _ledger_gate_map(_read_ledger(ROOT))


def main() -> int:
    argparse.ArgumentParser().parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, **result}, sort_keys=True))
        return 0
    except CoverageError as error:
        print(
            json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
