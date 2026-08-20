"""Fail closed on the P5-06c normalized-input surface.

The surface cross-references the canonical R480 parameter keys against
the authorized 120g C2M TP1a config sheet values and records the
port-order fact, hash-bound. The verifier binds counts, config hash,
port order, and the PLAN P5-06c row.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
SURFACE = ROOT / "docs" / "baselines" / "p5-06-normalized-input-surface.v1.yaml"
REGISTRY = ROOT / "docs" / "baselines" / "authorized-material-registry.v1.yaml"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p5-06.normalized-input-surface.v1"
CONFIG_ID = "com-r480-config-120g-c2m"
CANONICAL_KEYS = 214
KEYS_IN_CONFIG = 82
PORT_ORDER = "[ 1 3 2 4 ]"


class InputSurfaceError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise InputSurfaceError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    surface = load_yaml(SURFACE)
    if surface.get("schema") != SCHEMA or surface.get("status") != "normalized_input_surface_observed_hash_bound":
        raise InputSurfaceError("surface_schema_or_status_invalid")
    if surface.get("canonical_keys") != CANONICAL_KEYS or surface.get("keys_in_config") != KEYS_IN_CONFIG:
        raise InputSurfaceError("count_drift")
    if surface.get("port_order_observed") != PORT_ORDER:
        raise InputSurfaceError("port_order_drift")
    registry = load_yaml(REGISTRY)
    material = next((m for m in registry.get("materials", []) if m.get("id") == CONFIG_ID), None)
    if material is None or surface.get("config_sha256") != material.get("sha256", "").lower():
        raise InputSurfaceError("config_hash_drift")
    keys = surface.get("keys")
    if not isinstance(keys, dict) or len(keys) != CANONICAL_KEYS:
        raise InputSurfaceError("keys_drift")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P5-06c" not in plan_text:
        raise InputSurfaceError("plan_row_missing")
    return {"valid": True, "in_config": KEYS_IN_CONFIG}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    arguments = parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except InputSurfaceError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
