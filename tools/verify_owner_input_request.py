"""Verify the consolidated owner-input request against the remaining-items ledger.

The request entry set must equal the ledger ids whose blocker class is
owner_decision or external_asset_oracle; every entry must carry a
non-empty decision point, a kind matching its ledger blocker class, and an
existing gate file. Any drift fails closed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs" / "baselines" / "owner-input-request.v1.yaml"
LEDGER = ROOT / "docs" / "baselines" / "plan-remaining-items-ledger.v1.yaml"
SCHEMA = "sipi.owner-input-request.v1"
INPUT_CLASSES = {"owner_decision", "external_asset_oracle"}


class OwnerInputError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise OwnerInputError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    request = load_yaml(DEFAULT)
    if request.get("schema") != SCHEMA or request.get("status") != "awaiting_owner_input":
        raise OwnerInputError("request_schema_or_status_invalid")
    entries = request.get("entries")
    if not isinstance(entries, list) or not entries:
        raise OwnerInputError("entries_invalid")
    ledger = load_yaml(LEDGER)
    ledger_input = {
        entry["id"]: entry
        for entry in ledger.get("items", [])
        if isinstance(entry, dict) and entry.get("blocker") in INPUT_CLASSES
    }
    requested = {entry["id"] for entry in entries}
    if requested != set(ledger_input):
        missing = sorted(set(ledger_input) - requested)
        extra = sorted(requested - set(ledger_input))
        raise OwnerInputError(f"entry_set_drift:missing={missing}:extra={extra}")
    for entry in entries:
        entry_id = entry.get("id")
        kind = entry.get("kind")
        decision = entry.get("decision_point")
        gate = entry.get("gate")
        if not entry_id or entry_id not in ledger_input:
            raise OwnerInputError(f"entry_unknown:{entry_id}")
        expected_kind = "owner_decision" if ledger_input[entry_id]["blocker"] == "owner_decision" else "external_asset"
        if kind != expected_kind:
            raise OwnerInputError(f"entry_kind_mismatch:{entry_id}")
        if not isinstance(decision, str) or not decision:
            raise OwnerInputError(f"entry_decision_missing:{entry_id}")
        if not isinstance(gate, str) or not (root / gate).is_file():
            raise OwnerInputError(f"entry_gate_missing:{entry_id}:{gate}")
    return {"valid": True, "entries": len(entries), "owner_decision": sum(1 for e in entries if e["kind"] == "owner_decision"), "external_asset": sum(1 for e in entries if e["kind"] == "external_asset")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    arguments = parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except OwnerInputError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
