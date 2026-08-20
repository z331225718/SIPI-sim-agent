# -*- coding: utf-8 -*-
"""Fail closed on the P4A-02b Gen5 authorized behavior-spec observation.

The owner decision (C1) directs behavior-spec formation at the authorized
external ADS Gen5 profile. This gate binds the observer-only behavior-spec
observation (IBIS [Algorithmic Model] structure, DLL identity authorized,
black-box probe status from P4B-07) and keeps parser/AMI/composition
semantics out of scope.
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
OBSERVATION = ROOT / "docs" / "baselines" / "p4a-02b-gen5-behavior-spec-observation.v1.yaml"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p4a-02b.gen5-behavior-spec-observation.v1"
IBS_SHA256 = "9ff15bf9a5ad685d0ad700b26287b5f50e1c6e1ff9c6808e5a0f0ef86896d665"


class BehaviorSpecError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise BehaviorSpecError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    observation = load_yaml(OBSERVATION)
    if observation.get("schema") != SCHEMA or observation.get("status") != "authorized_behavior_spec_observed":
        raise BehaviorSpecError("observation_schema_or_status_invalid")
    profile = observation.get("profile", {})
    if profile.get("sha256") != IBS_SHA256:
        raise BehaviorSpecError("profile_hash_drift")
    models = profile.get("models", [])
    if len(models) != 2 or models[0].get("model") != "pcie_tx" or models[1].get("model") != "pcie_rx":
        raise BehaviorSpecError("model_list_drift")
    if models[0].get("type") != "Output" or models[1].get("type") != "Input":
        raise BehaviorSpecError("model_type_drift")
    behavior = observation.get("behavior_spec_observation", {})
    if behavior.get("dll_identity_status") != "authorized_matched_record":
        raise BehaviorSpecError("dll_identity_drift")
    tx = behavior.get("tx_model", {})
    if tx.get("probe_status") != "success_all":
        raise BehaviorSpecError("tx_probe_status_drift")
    rx = behavior.get("rx_model", {})
    if rx.get("probe_status") != "probe_crash_all":
        raise BehaviorSpecError("rx_probe_status_drift")
    boundary = observation.get("semantic_boundary", {})
    if boundary.get("product_runtime_incurs") is not False:
        raise BehaviorSpecError("runtime_admission_drift")
    claims = observation.get("non_claims", [])
    if "not_a_product_behavior_implementation" not in claims:
        raise BehaviorSpecError("non_claim_drift")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P4A-02b" not in plan_text:
        raise BehaviorSpecError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except BehaviorSpecError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())