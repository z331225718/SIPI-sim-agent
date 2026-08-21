"""Verify the PLAN remaining-items ledger matches the actual unchecked items.

The ledger classifies every unchecked PLAN item by its blocker type and
binds each to a state-keeping gate. This verifier fails closed if the
ledger item set drifts from the PLAN file, if any item is missing its
blocker class or gate, or if the gate file disappears.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.plan-remaining-items.ledger.v1"
LEDGER = ROOT / "docs" / "baselines" / "plan-remaining-items-ledger.v1.yaml"
PLAN = ROOT / "PLAN.md"

BLOCKER_CLASSES = frozenset({
    "owner_decision",
    "external_asset_oracle",
    "semantics_not_implemented",
    "release_gate",
})
EXPECTED_BLOCKER_COUNTS = {
    "external_asset_oracle": 10,
    "semantics_not_implemented": 0,
    "release_gate": 9,
}


class LedgerError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    if yaml is None:
        raise LedgerError("pyyaml_unavailable")
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise LedgerError("ledger_not_object")
    return value


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise LedgerError("plan_read_failed") from error


def plan_open_items(root: Path) -> set[str]:
    text = read_text(root / "PLAN.md")
    items: set[str] = set()
    for line in text.splitlines():
        match = re.match(r"- \[ \] \*\*(P\d+[A-Za-z0-9-]*)\*\*", line.strip())
        if match:
            items.add(match.group(1))
    return items


def validate(root: Path = ROOT) -> dict[str, Any]:
    for path in (LEDGER, PLAN):
        if not path.is_file():
            raise LedgerError(f"file_missing:{path.name}")
    ledger = load_yaml(LEDGER)
    if ledger.get("schema") != SCHEMA:
        raise LedgerError("ledger_schema_invalid")
    actual = plan_open_items(root)
    ledger_items = {entry["id"]: entry for entry in ledger.get("items", []) if isinstance(entry, dict)}
    if set(ledger_items) != actual:
        missing = sorted(actual - set(ledger_items))
        extra = sorted(set(ledger_items) - actual)
        raise LedgerError(f"ledger_drift:missing={missing}:extra={extra}")
    counts = {blocker: sum(entry.get("blocker") == blocker for entry in ledger_items.values()) for blocker in BLOCKER_CLASSES}
    if counts != {**{key: 0 for key in BLOCKER_CLASSES}, **EXPECTED_BLOCKER_COUNTS}:
        raise LedgerError(f"blocker_counts_invalid:{counts}")
    for item_id, entry in ledger_items.items():
        if entry.get("blocker") not in BLOCKER_CLASSES:
            raise LedgerError(f"item_blocker_invalid:{item_id}")
        gates = entry.get("gate")
        if not isinstance(gates, list) or not gates:
            raise LedgerError(f"item_gates_empty:{item_id}")
        for gate in gates:
            if not (root / gate).is_file():
                raise LedgerError(f"item_gate_missing:{item_id}:{gate}")
    return {"valid": True, "items": len(ledger_items), "blocker_counts": counts}


def main() -> int:
    parser = argparse.ArgumentParser()
    arguments = parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except LedgerError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
