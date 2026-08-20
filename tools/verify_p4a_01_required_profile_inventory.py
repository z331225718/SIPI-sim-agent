"""Fail closed on the P4A-01 required-profile IBIS inventory.

The owner selected the required IBIS profile (5.0, fixtures/ibis/
as4c512m16md4v-053bin.ibs). This gate binds the observer-only structural
inventory (version / component / keyword / model-block / table-family) to
the hash of the physical file, and binds the owner profile decision.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs" / "baselines" / "p4a-01-required-profile-inventory.v1.yaml"
IBS_FILE = ROOT / "fixtures" / "ibis" / "as4c512m16md4v-053bin.ibs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p4a-01.required-profile-inventory.v1"
EXPECTED_SHA256 = "d72cf62b56d67d30f4004f56ea3b79b4cb1241615692b147682f47540e615a0b"
EXPECTED_IBIS_VERSION = "5.0"
EXPECTED_COMPONENT = "AS4C512M16MD4V-053BIN"
EXPECTED_MODEL_BLOCK_COUNT = 67


class ProfileInventoryError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ProfileInventoryError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    if not IBS_FILE.is_file():
        raise ProfileInventoryError("ibis_file_missing")
    data = IBS_FILE.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    if sha != EXPECTED_SHA256:
        raise ProfileInventoryError("ibis_file_hash_drift")
    inventory = load_yaml(INVENTORY)
    if inventory.get("schema") != SCHEMA or inventory.get("status") != "observed_hash_bound":
        raise ProfileInventoryError("inventory_schema_or_status_invalid")
    facts = inventory.get("facts", {})
    if facts.get("ibis_version") != EXPECTED_IBIS_VERSION:
        raise ProfileInventoryError("ibis_version_drift")
    if facts.get("component") != EXPECTED_COMPONENT:
        raise ProfileInventoryError("component_drift")
    if facts.get("model_block_count") != EXPECTED_MODEL_BLOCK_COUNT:
        raise ProfileInventoryError("model_block_count_drift")
    if facts.get("unique_keyword_count") != 26:
        raise ProfileInventoryError("keyword_count_drift")
    if "Model Selector" not in facts.get("unique_keywords", []):
        raise ProfileInventoryError("model_selector_keyword_missing")
    file_meta = inventory.get("file", {})
    if file_meta.get("sha256") != EXPECTED_SHA256:
        raise ProfileInventoryError("inventory_hash_drift")
    non_claims = inventory.get("non_claims", [])
    if "not_a_product_ibis_parser" not in non_claims:
        raise ProfileInventoryError("non_claim_drift")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P4A-01" not in plan_text:
        raise ProfileInventoryError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except ProfileInventoryError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
