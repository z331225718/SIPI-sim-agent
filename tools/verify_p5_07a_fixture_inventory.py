"""Fail closed on the P5-07a synthetic fixture inventory.

The inventory lists the registered synthetic fixture set with hashes,
manifest facts (generator, port orders, grid), and any manifest-vs-
current hash differences, bound to the MATLAB oracle first run. The
verifier binds counts, manifest facts, and the PLAN P5-07a row.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs" / "baselines" / "p5-07-synthetic-fixture-inventory.v1.yaml"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p5-07.synthetic-fixture-inventory.v1"
FIXTURE_COUNT = 14


class InventoryError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise InventoryError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    inventory = load_yaml(INVENTORY)
    if inventory.get("schema") != SCHEMA or inventory.get("status") != "synthetic_fixture_set_inventoried_hash_bound":
        raise InventoryError("inventory_schema_or_status_invalid")
    if inventory.get("fixture_count") != FIXTURE_COUNT:
        raise InventoryError("fixture_count_drift")
    fixtures = inventory.get("fixtures")
    if not isinstance(fixtures, list) or len(fixtures) != FIXTURE_COUNT:
        raise InventoryError("fixtures_drift")
    for fixture in fixtures:
        if not fixture.get("logical_name") or not fixture.get("sha256"):
            raise InventoryError("fixture_entry_invalid")
    facts = inventory.get("manifest_facts")
    if not isinstance(facts, dict) or facts.get("file_port_order") != ["TX+", "RX+", "TX-", "RX-"]:
        raise InventoryError("manifest_facts_drift")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P5-07a" not in plan_text:
        raise InventoryError("plan_row_missing")
    return {"valid": True, "fixtures": FIXTURE_COUNT}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    arguments = parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except InventoryError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
